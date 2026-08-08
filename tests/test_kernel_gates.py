"""Human-in-the-loop gates in the kernel graph.

Driven with an in-memory checkpointer so the interrupt/resume round trip is
exercised without Postgres. The property under test is not "does it pause" but
"what runs, and how many times, on either side of the pause" — `interrupt()`
replays its node from the top, so a side effect placed above the call fires again
on every resume.
"""
from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.types import Command

from src.agent.kernel import graph as kernel
from src.agent.kernel.state import Hypothesis, IncidentState


@pytest.fixture
def running(monkeypatch):
    from src.agent import remediation

    monkeypatch.setattr(remediation, "running_containers", lambda: {"payment", "cart"})


@pytest.fixture
def no_exec(monkeypatch):
    """Never actually spawn docker from a test."""
    from src.agent import remediation

    calls: list[dict] = []

    def fake_execute(proposal):
        calls.append(proposal)
        return remediation.ActionResult(True, "restarted payment", ["docker", "restart", "payment"])

    monkeypatch.setattr(remediation, "execute", fake_execute)
    return calls


def _hypothesis(service="payment", posterior=0.9):
    return Hypothesis(
        id="h-1",
        kind="dependency_failure",
        statement=f"{service} is failing",
        subject_service=service,
        origin="topology",
        prior=0.9,
        posterior=posterior,
    )


def _gate_graph():
    """Just the gate half of the kernel: report -> propose -> await -> execute.

    Isolated deliberately — the full graph would need Memgraph and ClickHouse, and
    what is under test here is the gate wiring, not evidence gathering.
    """
    wf = StateGraph(IncidentState)
    wf.add_node("propose_remediation", kernel.propose_remediation_node)
    wf.add_node("await_approval", kernel.await_approval_node)
    wf.add_node("execute_remediation", kernel.execute_remediation_node)
    wf.set_entry_point("propose_remediation")
    wf.add_conditional_edges(
        "propose_remediation",
        kernel.route_after_proposal,
        {"await_approval": "await_approval", "__end__": END},
    )
    wf.add_conditional_edges(
        "await_approval",
        kernel.route_after_approval,
        {"execute_remediation": "execute_remediation", "__end__": END},
    )
    wf.add_edge("execute_remediation", END)
    return wf.compile(checkpointer=MemorySaver())


def _config(thread="t1"):
    return {"configurable": {"thread_id": thread}}


def test_run_pauses_before_remediation_with_a_readable_proposal(running, no_exec):
    """HITL-01: nothing executes until a human has seen what is proposed and why."""
    graph = _gate_graph()

    result = graph.invoke({"hypotheses": [_hypothesis()]}, _config())

    assert no_exec == [], "execution must not happen before approval"
    interrupts = result["__interrupt__"]
    payload = interrupts[0].value
    assert payload["gate"] == "remediation"
    proposal = payload["proposal"]
    assert proposal["container"] == "payment"
    assert proposal["argv"] == ["docker", "restart", "payment"]
    # Rationale is phrased for the approver, not the internal score: no bare
    # probability, but the leading explanation stated in words.
    assert "payment" in proposal["rationale"]
    assert "dependency failure" in proposal["rationale"]
    assert "0.9" not in proposal["rationale"]


def test_approval_executes_exactly_once(running, no_exec):
    """HITL-02/03: an approved gate runs the allowlisted action, once."""
    graph = _gate_graph()
    cfg = _config("t-approve")
    graph.invoke({"hypotheses": [_hypothesis()]}, cfg)

    final = graph.invoke(Command(resume={"decision": "approved"}), cfg)

    assert len(no_exec) == 1
    assert final["execution_result"]["ok"] is True


def test_rejection_executes_nothing(running, no_exec):
    graph = _gate_graph()
    cfg = _config("t-reject")
    graph.invoke({"hypotheses": [_hypothesis()]}, cfg)

    final = graph.invoke(Command(resume={"decision": "rejected", "note": "not now"}), cfg)

    assert no_exec == []
    assert final["approval_decision"]["decision"] == "rejected"
    assert "execution_result" not in final or final.get("execution_result") is None


def test_proposal_node_does_not_re_execute_side_effects_on_resume(running, no_exec):
    """The replay hazard, stated as a test.

    `interrupt()` re-runs its node from the top on resume. If `await_approval` did
    any work before interrupting, that work would happen twice. Proposal building
    lives in its own upstream node precisely so the interrupting node has nothing
    above the call.
    """
    graph = _gate_graph()
    cfg = _config("t-replay")
    graph.invoke({"hypotheses": [_hypothesis()]}, cfg)

    graph.invoke(Command(resume={"decision": "approved"}), cfg)

    assert len(no_exec) == 1, "a resume must not execute the action twice"


def test_unexecutable_proposal_does_not_wake_a_human(running, no_exec):
    """A service with no running container cannot be restarted, so there is nothing
    to ask about — the run ends rather than parking on a gate nobody can action."""
    graph = _gate_graph()

    result = graph.invoke({"hypotheses": [_hypothesis(service="ghost")]}, _config("t-ghost"))

    assert "__interrupt__" not in result
    assert result["remediation_proposal"]["executable"] is False
    assert no_exec == []


def test_no_hypothesis_yields_no_proposal(running, no_exec):
    graph = _gate_graph()

    result = graph.invoke({"hypotheses": []}, _config("t-empty"))

    assert result.get("remediation_proposal") is None
    assert no_exec == []


def test_escalation_gate_carries_the_best_unconfirmed_guess():
    """HITL-05: the agent does not decide on its own that it is beaten."""
    wf = StateGraph(IncidentState)
    wf.add_node("await_escalation", kernel.await_escalation_node)
    wf.set_entry_point("await_escalation")
    wf.add_edge("await_escalation", END)
    graph = wf.compile(checkpointer=MemorySaver())

    result = graph.invoke(
        {
            "hypotheses": [_hypothesis(posterior=0.42)],
            "verification_result": {
                "passed": False,
                "failed_checks": ["evidence_grounding"],
                "detail": "no supporting evidence",
            },
        },
        _config("t-esc"),
    )

    payload = result["__interrupt__"][0].value
    assert payload["gate"] == "escalation"
    assert payload["best_guess"]["service"] == "payment"
    assert payload["failed_checks"] == ["evidence_grounding"]


def test_gates_can_be_compiled_out():
    """A graph compiled without a checkpointer must not contain interrupt nodes —
    `interrupt()` needs somewhere to persist the pause, so it would fail at the
    first gate rather than at build time."""
    ungated = kernel.build_graph(gates=False).compile()
    nodes = set(ungated.get_graph().nodes)

    assert "await_approval" not in nodes
    assert "await_escalation" not in nodes
    assert "report" in nodes
