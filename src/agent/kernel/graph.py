"""The kernel loop.

    ground ─▶ seed ─┬─▶ probe ×N ─▶ update_beliefs ─┬─▶ (loop back to probe)
                    │                                └─▶ verify ─┬─▶ report
                    └─▶ verify                                   └─▶ graceful_exit

Three properties the v1 graph did not have:

  - **It can revise.** A single forward pass commits to whatever framing its first tool call
    produced. This one can refute a leading hypothesis and promote a rival.
  - **It reports what it ruled out.** Google SRE's own agent writeup makes "options considered
    and rejected" a hard requirement; a tournament produces it as a by-product.
  - **Stopping is arithmetic.** No node asks a model whether it has seen enough.

Fan-in is a plain `add_edge("probe", "update_beliefs")`, deliberately not `defer=True`. Every
probe is the same node type exactly one hop deep, so they resolve in a single superstep and
ordinary fan-in is correct — and `defer` is reported to interact badly with `Command` and
conditional edges (langgraph#5182, #6005). Revisit only if probes ever gain unequal depth.
"""
import logging
import os
from typing import Literal, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from langgraph.types import Send, interrupt

from src.agent.kernel import beliefs as belief_math
from src.agent.kernel.budget import DEFAULT_TAU, size_budget, stop_reason
from src.agent.kernel.selection import select_probes
from src.agent.kernel.state import (
    Budget,
    Evidence,
    Hypothesis,
    IncidentState,
    ProbeRun,
    Synthesis,
)
from src.agent.kernel.verifier import verify
from src.agent.probes import core as _core_probes  # noqa: F401  (import registers core probes)
from src.agent.probes.base import ProbeRequest
from src.agent.probes.registry import registry_for_team
from src.agent.subagents.topology import run_topology_subagent

log = logging.getLogger("incimin.kernel")

DEFAULT_TEAM = os.getenv("INCIMIN_DEFAULT_TEAM", "default")
MIN_HYPOTHESES = 3


def deterministic_mode() -> bool:
    """Golden path and CI run with the model out of the loop entirely.

    Read at call time, not import time, so a test can flip it without reimporting the module.
    """
    return os.getenv("INCIMIN_DETERMINISTIC", "").strip().lower() in ("1", "true", "yes")


class ProbeNodeState(TypedDict):
    """Private input for one fanned-out probe.

    Narrow on purpose: a probe gets its request, never the incident's message history. Log and
    metric payloads are enormous, and this is the boundary that keeps them out of the parts of
    state a model will later read.
    """

    request: dict
    round_index: int


# --------------------------------------------------------------------------- ground


def ground_node(state: IncidentState) -> dict:
    """Establish candidates before any hypothesis exists.

    Google SRE's agent grounds in topology/dependency data to fix "domain and intent" *before*
    forming hypotheses; most agents jump straight from alert to speculation. This is a hard
    edge rather than a tool call so the model cannot skip it.
    """
    alert = state.get("alert") or {}
    source_service = alert.get("service") or ""
    result = run_topology_subagent(source_service)

    evidence: list[Evidence] = [dict(e) for e in result.evidence]
    candidates = result.candidate_services or ([source_service] if source_service else [])

    return {
        "candidate_services": candidates,
        "evidence": evidence,
        "team_id": state.get("team_id") or DEFAULT_TEAM,
        "round_index": 0,
        "messages": [AIMessage(content=f"Grounded: {result.summary}")],
    }


# --------------------------------------------------------------------------- seed


def seed_node(state: IncidentState) -> dict:
    """Three-tier hypothesis generation: playbook, then topology, then the model.

    The model only runs if the deterministic tiers underfill. When a team playbook matches,
    seeding never touches an LLM at all — which is precisely why the configurable layer makes
    the system *more* deterministic rather than less.
    """
    alert = state.get("alert") or {}
    candidates = list(state.get("candidate_services") or [])

    hypotheses = _seed_from_playbooks(state) or []
    if len(hypotheses) < MIN_HYPOTHESES:
        hypotheses += _seed_from_topology(candidates, exclude={h.subject_service for h in hypotheses})
    if len(hypotheses) < MIN_HYPOTHESES and not deterministic_mode():
        hypotheses += _seed_from_llm(alert, candidates, existing=hypotheses)

    if not hypotheses:
        return {
            "hypotheses": [],
            "budget": Budget(max_rounds=0, exit_reason="no_hypotheses"),
            "round_index": 0,
        }

    hypotheses = belief_math.seed_posteriors(hypotheses)
    budget = size_budget(hypotheses)
    log.info(
        "seeded %d hypotheses, budget=%d round(s), leader=%s",
        len(hypotheses),
        budget.max_rounds,
        hypotheses[0].id,
    )
    return {"hypotheses": hypotheses, "budget": budget, "round_index": 0}


def _seed_from_playbooks(state: IncidentState) -> list[Hypothesis]:
    """Tier 1. Wired in Phase 15 — see `src/agent/config/`. Empty until then."""
    try:
        from src.agent.config.playbooks import seed_from_playbooks
    except ImportError:
        return []
    return seed_from_playbooks(state)


def _seed_from_topology(candidates: list[str], *, exclude: set[str]) -> list[Hypothesis]:
    """Tier 2. Each BFS candidate becomes a dependency-failure hypothesis, weighted by depth.

    BFS order is a fault-gradient proxy: the nearer a service is to the alerting one, the more
    likely it is implicated. Weights decay so the ordering survives normalization.
    """
    out: list[Hypothesis] = []
    for rank, service in enumerate(candidates):
        if service in exclude:
            continue
        out.append(
            Hypothesis(
                id=f"h-topo-{rank}",
                kind="dependency_failure",
                statement=f"{service} is failing and propagating to the alerting service",
                subject_service=service,
                origin="topology",
                prior=1.0 / (rank + 1),
            )
        )
    return out


def _seed_from_llm(alert: dict, candidates: list[str], *, existing: list[Hypothesis]) -> list[Hypothesis]:
    """Tier 3. Only fires when the deterministic tiers came up short."""
    from pydantic import BaseModel, Field

    from src.agent.kernel.state import BASE_HYPOTHESIS_KINDS
    from src.agent.llm import build_llm

    class SeedCandidate(BaseModel):
        kind: str = Field(description=f"one of {list(BASE_HYPOTHESIS_KINDS)}")
        statement: str
        subject_service: str
        prior: float = Field(ge=0.0, le=1.0)

    class SeedBatch(BaseModel):
        hypotheses: list[SeedCandidate] = Field(default_factory=list)

    prompt = (
        f"Alert: {alert.get('alertname')} on service {alert.get('service')} "
        f"(severity {alert.get('severity')}).\n"
        f"Message: {alert.get('message') or 'n/a'}\n"
        f"Services reachable in the dependency graph: {candidates or 'unknown'}\n"
        f"Already-considered explanations: {[h.statement for h in existing] or 'none'}\n\n"
        f"Propose up to {MIN_HYPOTHESES} additional, mutually distinct root-cause hypotheses. "
        f"Each must name a concrete subject_service drawn from the list above. "
        f"Use only these kinds: {list(BASE_HYPOTHESIS_KINDS)}."
    )
    try:
        batch = build_llm().with_structured_output(SeedBatch).invoke(prompt)
    except Exception as e:  # noqa: BLE001
        log.warning("LLM hypothesis seeding unavailable (%s); continuing with what we have", e)
        return []

    known = set(candidates)
    out: list[Hypothesis] = []
    for i, c in enumerate(batch.hypotheses):
        # A hypothesis about a service outside the dependency graph cannot be corroborated by
        # any probe scoped to the candidate set, so it would sit at its prior forever.
        if known and c.subject_service not in known:
            continue
        out.append(
            Hypothesis(
                id=f"h-llm-{i}",
                kind=c.kind if c.kind in BASE_HYPOTHESIS_KINDS else "dependency_failure",
                statement=c.statement,
                subject_service=c.subject_service,
                origin="llm",
                prior=c.prior,
            )
        )
    return out


# --------------------------------------------------------------------------- probe fan-out


def pending_requests(state: IncidentState) -> list[ProbeRequest]:
    """Probes still worth running, given what has already been asked.

    Shared by `dispatch` and `verify_node` so the loop's exit reason is derived from the same
    facts that ended it. Deriving them separately is how a run that simply ran out of useful
    probes gets mislabelled as one that ran out of budget.
    """
    hypotheses = list(state.get("hypotheses") or [])
    if not hypotheses:
        return []
    return select_probes(
        hypotheses=hypotheses,
        registry=registry_for_team(state.get("team_id") or DEFAULT_TEAM),
        seen_keys=list(state.get("seen_probe_keys") or []),
        round_index=state.get("round_index", 0),
        services=list(state.get("candidate_services") or []),
    )


def exit_reason_for(state: IncidentState) -> str:
    hypotheses = list(state.get("hypotheses") or [])
    if not hypotheses:
        return "no_hypotheses"
    return stop_reason(
        hypotheses,
        state.get("budget") or Budget(),
        has_discriminating_probe=bool(pending_requests(state)),
    )


def dispatch(state: IncidentState) -> list[Send] | Literal["verify"]:
    """Routing function shared by `seed` and `update_beliefs`.

    Returns either a fan-out of probe Sends or the string "verify". Mixed return types are
    legal for a conditional edge as long as every string target appears in the path map.
    """
    hypotheses = list(state.get("hypotheses") or [])
    if not hypotheses:
        return "verify"

    reason = stop_reason(hypotheses, state.get("budget") or Budget())
    if reason:
        log.info("stopping: %s", reason)
        return "verify"

    requests = pending_requests(state)
    if not requests:
        log.info("stopping: no_discriminating_probe")
        return "verify"

    log.info("round %d: dispatching %s", state.get("round_index", 0), [r.probe_id for r in requests])
    return [
        Send("probe", {"request": r.model_dump(mode="json"), "round_index": r.round_index})
        for r in requests
    ]


async def probe_node(state: ProbeNodeState) -> dict:
    """Run one probe. Never raises — a dead evidence source degrades a run, it does not end one."""
    req = ProbeRequest.model_validate(state["request"])
    registry = registry_for_team(DEFAULT_TEAM)
    probe = registry.get(req.probe_id)

    if probe is None:
        result_status, summary, evidence = "skipped", f"probe {req.probe_id} not in roster", []
    else:
        try:
            result = await probe.run(req)
            result_status, summary, evidence = result.status, result.summary, result.evidence
        except Exception as e:  # noqa: BLE001 — defence in depth; probes are told not to raise
            log.exception("probe %s raised", req.probe_id)
            result_status, summary, evidence = "error", f"{type(e).__name__}: {e}", []

    run: ProbeRun = {
        "probe_id": req.probe_id,
        "dedup_key": req.dedup_key,
        "status": result_status,
        "summary": summary,
        "evidence_count": len(evidence),
        "round_index": req.round_index,
    }
    return {
        "evidence": list(evidence),
        "probe_log": [run],
        "seen_probe_keys": [req.dedup_key],
    }


# --------------------------------------------------------------------------- belief update


def update_beliefs_node(state: IncidentState) -> dict:
    """Judge this round's evidence, then do the arithmetic in code."""
    hypotheses = list(state.get("hypotheses") or [])
    evidence = list(state.get("evidence") or [])
    round_index = state.get("round_index", 0)

    judged_ids = {r for h in hypotheses for r in (h.supporting_refs + h.refuting_refs)}
    fresh = [e for e in evidence if e["id"] not in judged_ids]

    verdicts = (
        _rule_based_verdicts(hypotheses, fresh)
        if deterministic_mode()
        else _llm_verdicts(hypotheses, fresh)
    )
    update = belief_math.apply_verdicts(hypotheses, verdicts)
    for rejected in update.rejected_verdicts:
        log.debug("rejected verdict: %s", rejected)

    budget = (state.get("budget") or Budget()).model_copy()
    budget.rounds_used = round_index + 1

    top = belief_math.leader(update.hypotheses)
    log.info(
        "round %d complete: leader=%s posterior=%.3f",
        round_index,
        top.id if top else "none",
        top.posterior if top else 0.0,
    )
    return {"hypotheses": update.hypotheses, "budget": budget, "round_index": round_index + 1}


def _rule_based_verdicts(
    hypotheses: list[Hypothesis], evidence: list[Evidence]
) -> list[belief_math.EvidenceVerdict]:
    """Deterministic stand-in for the judging model.

    Coarse but honest: evidence about a hypothesis's own service supports it, evidence about a
    different service says nothing. Enough to drive the golden path with no model in the loop.
    """
    out: list[belief_math.EvidenceVerdict] = []
    for h in hypotheses:
        if h.status == "refuted":
            continue
        for e in evidence:
            if e["service"] != h.subject_service:
                continue
            verdict = "strongly_supports" if e["source"] == "telemetry" else "supports"
            out.append(
                belief_math.EvidenceVerdict(
                    hypothesis_id=h.id,
                    evidence_id=e["id"],
                    verdict=verdict,
                    rationale=f"{e['source']} evidence for {e['service']}",
                )
            )
    return out


def _llm_verdicts(
    hypotheses: list[Hypothesis], evidence: list[Evidence]
) -> list[belief_math.EvidenceVerdict]:
    """One structured call per round. The model ranks; it never computes."""
    from src.agent.llm import build_llm

    open_ = [h for h in hypotheses if h.status != "refuted"]
    if not open_ or not evidence:
        return []

    hypothesis_block = "\n".join(
        f"- {h.id} [{h.kind}] {h.subject_service}: {h.statement}" for h in open_
    )
    evidence_block = "\n".join(
        f"- {e['id']} [{e['source']}] service={e['service']}: {e['summary'][:300]}" for e in evidence
    )
    prompt = (
        "You are assessing how each piece of evidence bears on each competing root-cause "
        "hypothesis for a production incident.\n\n"
        f"Hypotheses:\n{hypothesis_block}\n\nNew evidence:\n{evidence_block}\n\n"
        "For every (hypothesis, evidence) pair that is materially related, emit one verdict. "
        "Omit pairs that are simply unrelated rather than labelling them neutral. "
        "Use 'refutes' only when the evidence is genuinely incompatible with the hypothesis — "
        "it permanently eliminates that hypothesis from consideration."
    )
    try:
        batch = build_llm().with_structured_output(belief_math.VerdictBatch).invoke(prompt)
    except Exception as e:  # noqa: BLE001
        log.warning("verdict model unavailable (%s); falling back to rule-based judging", e)
        return _rule_based_verdicts(hypotheses, evidence)
    return batch.verdicts


# --------------------------------------------------------------------------- verify / report


def verify_node(state: IncidentState) -> dict:
    hypotheses = list(state.get("hypotheses") or [])
    budget = state.get("budget") or Budget()
    reason = exit_reason_for(state) or "budget_exhausted"

    alert = state.get("alert") or {}
    result = verify(
        hypotheses,
        list(state.get("evidence") or []),
        alert_fired_at_ns=alert.get("fired_at_ns"),
        stop_reason=reason,
    )
    budget = budget.model_copy(update={"exit_reason": reason})
    return {"verification_result": result, "budget": budget}


def route_after_verify(state: IncidentState) -> Literal["report", "graceful_exit"]:
    vr = state.get("verification_result")
    return "report" if vr and vr.get("passed") else "graceful_exit"


def report_node(state: IncidentState) -> dict:
    hypotheses = list(state.get("hypotheses") or [])
    winner = belief_math.leader(hypotheses)
    budget = state.get("budget") or Budget()
    by_id = {e["id"]: e for e in state.get("evidence") or []}

    # Only a τ-crossing earns high confidence. A run that merely ran out of rounds may still
    # have a plausible leader, but that leader never got the chance to be refuted.
    confidence = "high" if budget.exit_reason == "converged" else "low"

    lines = [
        f"Root cause: {winner.subject_service} (confidence: {confidence}, "
        f"posterior {winner.posterior:.2f}, {budget.rounds_used} round(s))",
        f"Hypothesis: {winner.statement}",
    ]

    cited = [by_id[r] for r in winner.supporting_refs if r in by_id]
    if cited:
        lines.append("\nSupporting evidence:")
        lines.extend(f"- {e['id']} [{e['source']}] {e['summary'][:200]}" for e in cited)

    ruled_out = sorted(
        (h for h in hypotheses if h.id != winner.id),
        key=lambda h: -h.posterior,
    )
    if ruled_out:
        lines.append("\nRuled out:")
        for h in ruled_out:
            why = f"refuted by {', '.join(h.refuting_refs)}" if h.refuting_refs else "insufficient support"
            lines.append(f"- {h.statement} ({h.posterior:.2f}) — {why}")

    probes = [r["probe_id"] for r in state.get("probe_log") or []]
    if probes:
        lines.append(f"\nProbes run: {', '.join(probes)}")
    lines.append("\nEscalate to a human SRE for remediation steps.")

    synthesis = Synthesis(
        root_cause_service=winner.subject_service,
        evidence_refs=list(winner.supporting_refs),
        confidence=confidence,
    )
    return {"messages": [AIMessage(content="\n".join(lines))], "synthesis": synthesis}


# --------------------------------------------------------------------------- human gates
#
# `interrupt()` replays its node from the top on resume — not from the line that
# paused. Every node below is therefore split so that nothing with a side effect
# runs before the interrupt call: `propose_remediation` computes and returns, the
# `await_*` nodes interrupt first and act on the answer afterwards, and execution
# lives in its own node reached only after a decision exists.


def propose_remediation_node(state: IncidentState) -> dict:
    """Turn the winning hypothesis into a concrete, allowlisted proposal.

    Pure: builds the proposal and returns it. No interrupt, no side effect, so
    replaying it is free. The action is chosen by lookup, never composed by a
    model — see `src/agent/remediation.py`.
    """
    from src.agent import remediation

    winner = belief_math.leader(list(state.get("hypotheses") or []))
    if winner is None:
        return {"remediation_proposal": None}

    proposal = remediation.propose("restart_service", winner.subject_service)
    proposal["hypothesis"] = winner.statement
    proposal["posterior"] = round(winner.posterior, 4)
    # Rationale is written for the person about to approve a restart, so it states
    # the leading explanation in words. The posterior stays on the proposal for the
    # audit record but is deliberately not phrased into the sentence — a bare
    # probability invites arguing with the number instead of the reasoning.
    proposal["rationale"] = (
        f"Leading explanation is {winner.kind.replace('_', ' ')} in "
        f"{winner.subject_service}. {winner.statement}"
    )
    log.info(
        "proposing %s for %s (executable=%s)",
        proposal.get("action_id"),
        winner.subject_service,
        proposal.get("executable"),
    )
    return {"remediation_proposal": proposal}


def route_after_proposal(state: IncidentState) -> Literal["await_approval", "__end__"]:
    """A proposal that cannot be executed is not worth waking a human for."""
    p = state.get("remediation_proposal")
    return "await_approval" if p and p.get("executable") else "__end__"


def await_approval_node(state: IncidentState) -> dict:
    """Block until a human approves or rejects the remediation.

    `interrupt()` is the FIRST statement that matters here. The value it returns is
    supplied by `Command(resume=...)`; on resume the node re-executes from the top,
    so anything above this line would run twice.
    """
    decision = interrupt(
        {
            "gate": "remediation",
            "proposal": state.get("remediation_proposal"),
        }
    )
    decision = decision or {}
    log.info("remediation gate resolved: %s", decision.get("decision"))
    return {"approval_decision": decision}


def route_after_approval(state: IncidentState) -> Literal["execute_remediation", "__end__"]:
    d = state.get("approval_decision") or {}
    return "execute_remediation" if d.get("decision") == "approved" else "__end__"


def execute_remediation_node(state: IncidentState) -> dict:
    """Run the approved action.

    Reached only with a decision already in state, so this node never replays a
    pending gate. The caller is still expected to have claimed the approval row
    atomically — this function does not own that guarantee, the database does.
    """
    from src.agent import remediation

    proposal = state.get("remediation_proposal") or {}
    result = remediation.execute(proposal)
    log.info("remediation executed: ok=%s %s", result.ok, result.detail)

    verb = "Executed" if result.ok else "Attempted"
    return {
        "execution_result": result.to_dict(),
        "messages": [
            AIMessage(
                content=f"{verb} remediation: {proposal.get('statement')}\nResult: {result.detail}"
            )
        ],
    }


def await_escalation_node(state: IncidentState) -> dict:
    """Ask a human to sign off before the incident is handed on.

    Same shape as the approval gate, and the same reason: interrupt first, act
    after. The agent does not get to decide on its own that it is beaten.
    """
    top = belief_math.leader(list(state.get("hypotheses") or []))
    vr = state.get("verification_result") or {}
    decision = interrupt(
        {
            "gate": "escalation",
            "best_guess": None
            if top is None
            else {
                "service": top.subject_service,
                "statement": top.statement,
                "posterior": round(top.posterior, 4),
            },
            "failed_checks": vr.get("failed_checks") or [],
            "detail": vr.get("detail"),
        }
    )
    decision = decision or {}
    log.info("escalation gate resolved: %s", decision.get("decision"))
    return {"escalation_decision": decision}


def graceful_exit_node(state: IncidentState) -> dict:
    vr = state.get("verification_result") or {}
    budget = state.get("budget") or Budget()
    detail = vr.get("detail") or "no hypothesis survived"
    content = f"Insufficient evidence to determine root cause ({budget.exit_reason}): {detail}"

    top = belief_math.leader(list(state.get("hypotheses") or []))
    if top is not None:
        content += (
            f"\n\nBest unconfirmed explanation: {top.statement} "
            f"({top.subject_service}, posterior {top.posterior:.2f}). "
            f"Failed checks: {', '.join(vr.get('failed_checks') or []) or 'none'}."
        )
    return {"messages": [AIMessage(content=content)]}


# --------------------------------------------------------------------------- assembly


def build_graph(*, gates: bool = True) -> StateGraph:
    """Assemble the kernel.

    `gates=False` drops the human-in-the-loop nodes, giving the old
    report/graceful_exit -> END shape. Used by tests and by any caller compiling
    without a checkpointer: `interrupt()` requires one, so a gated graph compiled
    bare would fail at the first pause rather than at build time.
    """
    workflow = StateGraph(IncidentState)
    workflow.add_node("ground", ground_node)
    workflow.add_node("seed", seed_node)
    workflow.add_node(
        "probe",
        probe_node,
        input_schema=ProbeNodeState,
        # A rate-limited or briefly unreachable data plane must degrade one evidence stream,
        # not abort an incident investigation.
        timeout=30,
    )
    workflow.add_node("update_beliefs", update_beliefs_node)
    workflow.add_node("verify", verify_node)
    workflow.add_node("report", report_node)
    workflow.add_node("graceful_exit", graceful_exit_node)

    workflow.set_entry_point("ground")
    workflow.add_edge("ground", "seed")
    workflow.add_conditional_edges("seed", dispatch, ["probe", "verify"])
    workflow.add_edge("probe", "update_beliefs")
    workflow.add_conditional_edges("update_beliefs", dispatch, ["probe", "verify"])
    workflow.add_conditional_edges(
        "verify", route_after_verify, {"report": "report", "graceful_exit": "graceful_exit"}
    )

    if not gates:
        workflow.add_edge("report", END)
        workflow.add_edge("graceful_exit", END)
        return workflow

    workflow.add_node("propose_remediation", propose_remediation_node)
    workflow.add_node("await_approval", await_approval_node)
    workflow.add_node("execute_remediation", execute_remediation_node)
    workflow.add_node("await_escalation", await_escalation_node)

    # A confident report earns a remediation proposal; a run that could not
    # establish a cause earns a human sign-off before it is handed on.
    workflow.add_edge("report", "propose_remediation")
    workflow.add_conditional_edges(
        "propose_remediation", route_after_proposal, {"await_approval": "await_approval", "__end__": END}
    )
    workflow.add_conditional_edges(
        "await_approval",
        route_after_approval,
        {"execute_remediation": "execute_remediation", "__end__": END},
    )
    workflow.add_edge("execute_remediation", END)

    workflow.add_edge("graceful_exit", "await_escalation")
    workflow.add_edge("await_escalation", END)
    return workflow


# Module-level app keeps the ungated shape: it compiles without a checkpointer, and
# `interrupt()` needs one. The API compiles its own gated graph with AsyncPostgresSaver.
app = build_graph(gates=False).compile()
