# Multi-Agent Architecture Research: Meta-Agent + Sub-Agents

**Domain:** AI SRE Incident Response Agent — evolving the v1.5 single-agent design toward a meta-agent (Coordinator) + specialist sub-agent topology
**Researched:** 2026-08-06 (revised same day — see Revision note below)
**Confidence:** HIGH for LangGraph mechanics (verified against current LangGraph docs via Context7 + `langgraph-supervisor-py` source), MEDIUM for RCA-specific role mapping (drawn from recent AIOps research papers, not yet validated against this project's live data)
**Status:** Research/design document only. **No code in `src/` has changed as a result of this doc.** This is intended to seed a future v2 milestone, not to be executed directly.

> **Revision note:** the first draft of this doc restricted LLM reasoning to the meta-agent only, with all four sub-agents (including the Verifier) as pure deterministic code. Per follow-up user direction, that restriction has been lifted: **every sub-agent, including the Verifier, may use LLM reasoning internally.** This is a deliberate loosening of v1.5's "zero LLM in the tool-execution path" philosophy, not an oversight — §0, §3.1, and §6 below now document what's gained, what's put at risk (specifically the golden-path determinism constraint and the Verifier's independence from the claim it's checking), and the mitigations recommended to keep those risks bounded rather than open-ended.

---

## 0. Relationship to v1.5 — read this first

v1.5 shipped a **single-agent** LangGraph ReAct loop (`src/agent/graph.py`): one LLM node (`agent`) bound via `llm.bind_tools()` to three flat, deterministic tools — `graph_bfs_tool` (Memgraph), `clickhouse_log_tool` (ClickHouse/SigNoz), `qdrant_runbook_tool` (Qdrant) — looping through a single `ToolNode` until the LLM stops calling tools or a `remaining_steps` budget forces a `graceful_exit`.

`.planning/RETROSPECTIVE.md` names this as the project's central success factor:

> "Keeping LLM out of critical topology traversal (relying on Memgraph BFS) is vital for deterministic demos."
> "Determinism over dynamic LLM inference for infrastructure workflows." (top lesson across milestones)

**This document partially walks that back, deliberately.** Per revised user direction (see the Revision note above), every sub-agent — Topology, Telemetry, Knowledge, and Verifier — is now permitted to use LLM reasoning internally, not just the meta-agent. That is a real change to the retrospective's "keep the LLM out of the critical path" lesson, and this doc does not paper over that: §3.1 recommends *how much* LLM reasoning each sub-agent actually needs (often none, or a narrowly-bounded disambiguation step), and §8 calls out the specific golden-path-latency and demo-determinism risk this reopens. The one piece of the original thesis that still holds without qualification: a new deterministic-*by-default* **Verifier** stage is added that today's v1.5 design does not have at all — today the LLM's final synthesis is trusted with zero cross-check. Whether the Verifier itself should use an LLM is the most consequential instance of this tradeoff and gets dedicated treatment in §6.

No prior `.planning/` doc discusses a meta-agent/sub-agent split — this is a net-new direction, not a course correction on a previously-agreed plan.

---

## 1. Why consider this now

Two forces motivate the redesign, both already latent in the current codebase:

1. **Extensibility, as CLAUDE.md requires it.** CLAUDE.md's binding constraint: *"Agent tool interface must be designed so adding new tools (e.g., alertmanager integration, k8s pod inspector) doesn't require rewriting the state machine."* Today this is satisfied only shallowly — a new tool means one more `@tool` function appended to a flat list bound to one LLM call. That works fine at 3 tools; it does not obviously scale to 6-8 tools with multi-step internal logic (e.g., a k8s pod inspector that needs to list pods, then describe the crashing one, then fetch its last N log lines — three API calls that today would have to be flattened into one tool function or awkwardly split across three tools the LLM has to sequence itself).
2. **No verification of the LLM's final answer.** `verify_golden_path.py` only checks that the final message *contains certain substrings* (`"paymentservice"`, one of `"recommend"/"step"/"restart"`) — it does not check that the claimed root cause is actually supported by the evidence the tools returned. There is currently no mechanism that would catch the LLM confidently naming the wrong service if evidence were ambiguous or partial.

---

## 2. Research summary

Findings gathered from current (2026) sources, condensed:

**Production multi-agent pattern shape.** The supervisor / orchestrator-worker pattern is the dominant production LangGraph shape for domains that decompose into independent, parallelizable subtasks with a synthesis step at the end — which is exactly the shape of "gather topology evidence, gather telemetry evidence, gather knowledge evidence, then explain." ([Architecting Multi-Agent Systems with LangGraph](https://medium.com/@timarkanta.sharma/architecting-multi-agent-systems-with-langgraph-patterns-trade-offs-and-real-world-design-ba8c535c6b35), [Multi-Agent Design Patterns: The Four That Work in Production](https://mudassirkhan.me/blog/multi-agent-design-patterns)) The four production patterns identified (Sequential, Orchestrator-Worker, Hierarchical, Dynamic Handoff) — our use case fits **Orchestrator-Worker**: "goals decomposable into non-interdependent subtasks... reduces wall-clock time to slowest subtask rather than sum total." Dynamic Handoff is explicitly warned against for cases needing testability/auditability, which rules it out for this project's demo-determinism requirement.

**`langgraph-supervisor` mechanics (not the package itself, but its primitives).** `create_supervisor()` wires worker agents to a central supervisor via **handoff tools** and the `Command` primitive:
```python
return Command(
    goto=agent_name,
    graph=Command.PARENT,
    update={"messages": messages + [tool_message]},
)
```
This is the standard mechanism for a supervisor to route control flow to a named node/subgraph and merge state back. The package assumes every worker is itself an LLM `create_react_agent` — under the revised decision that sub-agents *may* be LLM-based, that assumption now actually holds for this project, which means **`langgraph-supervisor` is a legitimate direct implementation option**, not just a source of reusable mechanics (see §5, Strategy B). It's still not mandated (§9 Non-goals) — a sub-agent with no need for internal LLM reasoning (e.g. Topology, if a fixed BFS query suffices) is simpler and cheaper as a plain deterministic subgraph, and mixing LLM-backed and plain-code sub-agents under one supervisor is fine; `create_supervisor()` doesn't require every worker to be homogeneous. ([langgraph-supervisor-py](https://github.com/langchain-ai/langgraph-supervisor-py))

**LangGraph subgraphs.** A compiled `StateGraph` can be used as a node inside a parent graph two ways: (a) added directly as a node when state schemas share keys, or (b) invoked inside a wrapper node function with explicit state transformation when schemas differ — the latter is what we need, since each sub-agent's internal working state (e.g., candidate ranking scratch state) shouldn't leak into the meta-agent's state. Verified pattern (Context7 / `docs.langchain.com/oss/python/langgraph/use-subgraphs`):
```python
def call_subgraph(state: ParentState):
    subgraph_output = subgraph.invoke({"bar": state["foo"]})   # transform in
    return {"foo": subgraph_output["bar"]}                      # transform out
```
`Command(update=, goto=, graph=Command.PARENT)` is the primitive for a subgraph to explicitly hand control back to a specific node in its parent when using the node-as-hub topology (Strategy B below) rather than the call-inside-a-node topology (Strategy A below).

**Academic precedent maps almost 1:1 onto this project's three data planes.** Recent AIOps research on graph-augmented multi-agent root cause analysis defines four collaborating roles: a **Navigator** that "guides the search space via calculated fault gradients" over a topology graph, a **Diagnoser** that "performs deep semantic analysis" on local node evidence, a **Verifier** that "enforces robust decision-making through multi-perspective consensus," and a **Coordinator** that "manages the global shared context and backtracking logic." Mapped onto this stack: Navigator → Memgraph/Topology, Diagnoser → ClickHouse/Telemetry, Coordinator → the meta-agent, and Verifier → a new deterministic gate this project doesn't have yet.

**The closest direct analog: auditable graph-guided RCA for Kubernetes** ([arXiv 2606.08590](https://arxiv.org/html/2606.08590)). This paper's system is, structurally, almost exactly what this project is trying to become: a LangGraph state machine over a typed incident graph, phases Graph Construction → Triage → Bounded BFS Traversal → Investigation → **Validation** → Chain Construction. Its central design principle, quoted directly because it is the thesis of this whole document:

> "Graph construction, queue management, tool execution, and validation checks are deterministic, while the LLM interprets node evidence and proposes hypotheses."

Its Validation stage runs three concrete, code-only checks before a hypothesis is allowed to finalize:
1. **Temporal ordering** — cause evidence must predate the first alert.
2. **Evidence grounding** — every claim must trace to a specific tool-returned fact, not be invented.
3. **Cross-modal consistency** — signals from different sources (in their case: K8s events, metrics, traces) must agree on the implicated resource.

Additional relevant details from that paper: a **read-only tool allow-list** (mutating operations, e.g. secrets access, explicitly blocked), and **checkpointing** so any run can be replayed/inspected — both directly applicable to this project's existing `MemorySaver` checkpointer and already-read-only tool set.

**Why multi-agent systems fail in production (MAST taxonomy, 1,600+ execution traces).** Failure breakdown: 41.8% specification problems (vague role/task contracts — "agents cannot read between lines, infer context, or ask clarifying questions during execution"), 36.9% coordination failures, 21.3% verification gaps. The taxonomy's own fix list: treat inter-agent contracts as schemas (JSON Schema/Pydantic), not prose; use independent validation isolated from the producing agent's own context, rather than letting an agent grade its own homework. This is the concrete justification for making the Verifier a separate, structurally-isolated stage — **structurally isolated is the load-bearing requirement, not necessarily code-only.** Under the revised decision to allow an LLM-based Verifier (§6), this taxonomy finding is the specific risk to design against: a second LLM call reviewing the first LLM's output is not automatically independent just because it's a separate node — if it shares conversation history/context with the meta-agent's reasoning, it inherits the same anchoring bias and still counts as "the same failure category the taxonomy warns about." §6 details the isolation and adversarial-framing mitigations needed to make an LLM-based Verifier actually independent rather than independent-in-name-only.

---

## 3. Recommended architecture

### 3.1 Roles

**Meta-agent (Coordinator)** — the only node with an LLM in the entire system, structurally identical in spirit to today's single `agent` node.
- Receives the incident query.
- Decides which sub-agent(s) to invoke and in what order. For the golden-path demo this should remain a **fixed default sequence** (Topology → Telemetry → Knowledge → Verifier) so the deterministic-demo constraint from CLAUDE.md is untouched; free-form LLM routing order is a v3+ concern, not this one.
- Emits a **structured synthesis** — a Pydantic object, not free text — so the Verifier can mechanically check it:
  ```python
  class Synthesis(BaseModel):
      root_cause_service: str
      evidence_refs: list[str]        # Evidence.id values the claim is grounded in
      remediation_runbook_id: str | None
      confidence: Literal["high", "low"]
  ```
- Retains today's `remaining_steps` step-budget guard and `graceful_exit` fallback, extended to also fire on Verifier failure (see §6).

Every sub-agent below **may** internally use LLM reasoning (a small bounded ReAct loop over a plane-scoped tool set) rather than a single fixed query — that's the revised decision. The recommendation for each is stated separately from what's *permitted*, because "permitted everywhere" and "needed everywhere" are different questions, and defaulting to LLM reasoning where a fixed query already works is pure added latency/non-determinism for no benefit.

**Topology sub-agent (Navigator)** — Memgraph. Output contract: a **ranked candidate list**, not a raw path string. *Recommendation: deterministic by default* — a fixed BFS/MAGE-centrality query already answers "what's near the alerting service" without ambiguity to resolve; LLM reasoning has nothing useful to disambiguate here on the golden path. Where it *could* earn its keep: choosing which edge types to traverse (`DEPENDS_ON` vs `CALLS` vs both) based on the incident description's language — a genuinely ambiguous, context-dependent choice.

**Telemetry sub-agent (Diagnoser)** — ClickHouse/SigNoz. Output contract: structured `Evidence` records. *Best candidate for bounded LLM reasoning*: picking which query template(s) to run (error logs vs. latency percentiles vs. both) based on symptoms in the incident description, and interpreting ambiguous log patterns that a fixed keyword filter (today's `severity_text = 'ERROR'`) would miss or over-match. Internally this looks like a small `create_react_agent` bound only to this plane's query-template tools, scoped to the Topology sub-agent's `candidate_services` so it can't wander the whole fleet.

**Knowledge sub-agent (Retriever)** — Qdrant. Output contract: top-K runbook matches with similarity scores. *Reasonable candidate for bounded LLM reasoning*: re-ranking/filtering the vector search's top-K by relevance to the specific evidence gathered (not just the raw query embedding), or reformulating the search query when the first pass returns low-similarity results.

**Verifier sub-agent** — no data plane of its own; operates on the `evidence` accumulated by the other three sub-agents plus the meta-agent's `Synthesis`. *May be LLM-based (revised decision)*, but — because a Verifier's entire value proposition is catching what the meta-agent got wrong — its design has the tightest constraints of any sub-agent in this system. See §6, which is written specifically for this case and should be read before implementing this one.

### 3.2 Extensibility story

A new evidence source (AlertManager, a k8s pod inspector) becomes a new self-contained sub-agent subgraph registered with the meta-agent's routing set. The Verifier and the other three sub-agents are untouched. This is a *stronger* fulfillment of CLAUDE.md's "adding new tools doesn't require rewriting the state machine" than today's flat-tool-list design, because a new source can have several internal deterministic steps (list → describe → fetch-logs) without bloating the single LLM's tool-calling surface with three new tool definitions it has to learn to sequence correctly itself. See §7 for a worked example.

---

## 4. State schema design

```python
from typing import Annotated, Literal, TypedDict
from langgraph.graph.message import add_messages
import operator

class Evidence(TypedDict):
    id: str                                          # e.g. "topology-0", "telemetry-3"
    source: Literal["topology", "telemetry", "knowledge"]
    service: str
    summary: str                                      # short human-readable fact
    raw: dict                                          # full tool payload, for audit/replay
    timestamp: str | None                              # ISO8601; None for topology facts

class VerificationResult(TypedDict):
    passed: bool
    failed_checks: list[str]                           # e.g. ["evidence_grounding", "temporal_ordering"]
    detail: str

class SREAgentState(TypedDict):
    messages: Annotated[list, add_messages]             # unchanged from today
    remaining_steps: int                                 # unchanged from today
    evidence: Annotated[list[Evidence], operator.add]    # accumulates across sub-agent calls
    candidate_services: list[str]                        # produced by Topology, consumed by Telemetry/Knowledge
    verification_result: VerificationResult | None
```

Notes:
- `evidence` uses `operator.add` as its reducer so each sub-agent can append its findings without clobbering prior sub-agents' output — this is the direct multi-agent analog of today's `add_messages` reducer on `messages`.
- `candidate_services` is the explicit hand-off contract between Topology and the two downstream evidence sub-agents — replacing the implicit "the LLM reads the BFS path string and decides what to check next" behavior of today's design with an explicit, inspectable field. This directly addresses the MAST taxonomy's "specification problems" failure mode (schema contract, not prose).
- Today's `SREAgentState` is a plain `TypedDict`; this design keeps that convention rather than introducing Pydantic for the *graph* state (Pydantic is used only for the meta-agent's `Synthesis` output, where structured-output enforcement matters).
- **LLM-backed sub-agents get their own private state, not a shared one.** Per the LangGraph subgraph docs (§2), a subgraph with a different schema than its parent is invoked inside a wrapper node with explicit state transformation — this is the exact mechanism for giving, say, the Telemetry sub-agent its own internal `messages` history (its ReAct loop's scratchpad) without that scratchpad leaking into the meta-agent's `messages` or the Verifier's view of the world. Only the sub-agent's final structured output crosses back into `SREAgentState.evidence`:
  ```python
  class SubAgentState(TypedDict):
      messages: Annotated[list, add_messages]   # private scratchpad, if this sub-agent uses an LLM
      plane_input: dict                          # scoped input from parent, e.g. candidate_services
      evidence_out: list[Evidence]                # only this crosses back to SREAgentState.evidence
  ```
  This isolation is not optional polish — it's the mechanism that makes the Verifier's independence (§6) possible at all. If sub-agent scratchpads leaked into shared state, an LLM-based Verifier reading `state["messages"]` would see the meta-agent's (and every other sub-agent's) reasoning trace and inherit its framing/anchoring, defeating the point of having a Verifier.

---

## 5. Graph topology — two implementation strategies

Both are valid LangGraph shapes for this design; they trade off migration risk against how "textbook multi-agent" the result looks. **Strategy A is recommended** as the actual next-milestone target; Strategy B is documented as the reference architecture to grow into later if/when true agent-level parallelism is needed.

### Strategy A (recommended) — tools that wrap subgraphs

Keep today's `agent ⇄ tools ⇄ agent` loop shape almost byte-for-byte unchanged. Each of today's three `@tool` functions is replaced by a `@tool` function that internally does `.invoke()` on a compiled per-plane subgraph instead of one raw DB call — that subgraph may be a plain deterministic pipeline (Topology, per §3.1's recommendation) or itself an internal `create_react_agent`-style ReAct loop over a small plane-scoped tool set (Telemetry/Knowledge, where bounded LLM reasoning earns its keep). The Verifier becomes a fourth tool the meta-agent calls once evidence-gathering tools have run, or — better — a plain conditional edge that always runs right before `END` regardless of what the LLM decides, so it can't be skipped even if it's LLM-backed internally.

```
                    ┌─────────────────────────────────────────┐
                    │              agent (LLM)                  │  ← only LLM node,
                    │   bind_tools([topology, telemetry,         │    unchanged shape
                    │               knowledge])                  │    from today
                    └───────────────┬─────────────┬─────────────┘
                                     │ tool_calls  │ no tool_calls
                         ┌───────────▼─────┐       │
                         │   ToolNode        │       │
                         │  ┌─────────────┐  │       │
                         │  │ topology_    │  │       │
                         │  │ tool → BFS   │  │       │
                         │  │ subgraph     │  │       │
                         │  ├─────────────┤  │       │
                         │  │ telemetry_   │  │       │
                         │  │ tool → CH    │  │       │
                         │  │ subgraph     │  │       │
                         │  ├─────────────┤  │       │
                         │  │ knowledge_   │  │       │
                         │  │ tool → Qdrant│  │       │
                         │  │ subgraph     │  │       │
                         │  └─────────────┘  │       │
                         └─────────┬─────────┘       │
                                   │ loop back        ▼
                                   └──────────►  verifier_node (always runs,
                                                  not LLM-callable)
                                                        │
                                              pass ──────┼────── fail
                                                │                  │
                                                ▼                  ▼
                                              END          graceful_exit → END
```

Migration risk: **low**. `graph.py`'s node/edge wiring barely changes; `route_condition` gains one more terminal case (route to `verifier_node` instead of straight to `END`); `verify_golden_path.py`'s assumptions (final message content, <60s latency) still hold with minor extension.

### Strategy B — explicit hub-and-spoke via `Command`

Each sub-agent is a top-level graph node (backed by its own compiled subgraph), and the meta-agent routes to it explicitly:

```
                              ┌───────────────────┐
                     ┌───────►│   meta_agent (LLM)  │◄───────┐
                     │        │  Coordinator         │        │
                     │        └─────────┬───────────┘        │
        Command(goto=X, update=...)     │                     │ Command(graph=PARENT,
                     │                  │ Command(goto=       │  goto="meta_agent")
                     │                  │  "topology"|...)     │
         ┌───────────┴──┐   ┌──────────▼──────┐   ┌──────────┴────┐
         │  topology_sg  │   │  telemetry_sg    │   │  knowledge_sg  │
         │  (Navigator)  │   │  (Diagnoser)     │   │  (Retriever)   │
         └───────────────┘   └──────────────────┘   └────────────────┘
                                       │
                              (meta_agent decides evidence is sufficient)
                                       │
                                       ▼
                              ┌─────────────────┐
                              │  verifier_sg      │
                              └────────┬──────────┘
                                pass   │   fail
                                       ▼
                                 END / graceful_exit
```

This is the more idiomatic multi-agent shape (clean per-agent tracing/visualization in LangSmith, natural extension point for running Topology+Telemetry concurrently via `Send`), and — now that sub-agents may be LLM-backed — it's also where `langgraph-supervisor`'s `create_supervisor()` becomes a direct fit rather than just a source of borrowed mechanics: each worker passed to `create_supervisor([topology_agent, telemetry_agent, knowledge_agent, verifier_agent], model=..., prompt=...)` can be a real `create_react_agent`. It's still a bigger structural rewrite of `graph.py` than Strategy A and changes what `verify_golden_path.py` can assert about the call sequence. Reach for this once there's an actual need for sub-agent-level parallelism, independently-checkpointed sub-agent state, or once enough sub-agents are LLM-backed that the hand-rolled `Command` routing in Strategy A starts duplicating what the package already gives you for free.

---

## 6. Verifier design detail

The three checks below are the substance of verification regardless of whether the Verifier is deterministic code or LLM-backed. **Recommendation: implement all three as deterministic code gates that run unconditionally, and layer an optional LLM judgment pass on top for the harder semantic question those three checks can't cover** — not as a replacement for them. This is a hybrid, and it's a deliberate response to the revised decision to permit an LLM-based Verifier: it gets you the flexibility the user asked for (an LLM can catch things regex/schema checks can't — "this evidence is topically related but doesn't actually support this specific causal claim") without giving up the one property that makes a Verifier worth having, i.e. that at least *some* of its checks can't be talked out of a wrong answer by confident LLM prose.

**Layer 1 — deterministic gates (always run, cannot be bypassed by an LLM verifier's judgment):**

1. **Temporal ordering.** ClickHouse/SigNoz timestamps are nanosecond epoch ints (per `PITFALLS.md` P3 — a well-known gotcha in this codebase already). Check: every `Evidence` with `source == "telemetry"` and non-null `timestamp` must have occurred at or before the incident query's reference time (the chaos-injection time in the demo, or "now" in production). Pure integer comparison.
2. **Evidence grounding (existence).** Every id in the meta-agent's `Synthesis.evidence_refs` must exist in `state["evidence"]` and belong to the same `service` as `Synthesis.root_cause_service`. Set-membership + field-equality check — enforceable because §4's schema makes `evidence_refs` a list of concrete IDs, not unconstrained prose. This is the check that catches an LLM citing an evidence ID that doesn't exist or belongs to the wrong service; it cannot catch an LLM citing a *real* ID that doesn't actually support the claim it's attached to — that's Layer 2's job.
3. **Cross-modal consistency.** The service in `candidate_services` (from Topology) and the service most represented in telemetry `evidence` must agree with `Synthesis.root_cause_service`, or at minimum the claimed service must be *reachable in* `candidate_services`.

**Layer 2 — optional LLM judgment (only runs if Layer 1 passes; may be skipped entirely for the deterministic golden-path demo):**

Judges the question Layer 1 structurally cannot: *does the cited evidence semantically support the specific causal claim, not just share a service tag with it?* If used, it must be built to actually be independent, not independent-in-name:

- **Isolated context.** Per §4's `SubAgentState` design, the Verifier's LLM call sees only the raw `Evidence` records and the `Synthesis` object — never the meta-agent's own reasoning/tool-call trace. Seeing *how* the meta-agent arrived at its answer is exactly what would let the Verifier inherit its anchoring bias.
- **Adversarial framing, not confirmatory framing.** Prompt it to try to refute the claim ("find the strongest reason this conclusion is wrong given only this evidence"), not to confirm it. A verifier asked "is this right?" defaults to yes; a verifier asked "what's wrong with this?" has to do the work.
- **Structured output only.** Same discipline as the meta-agent's `Synthesis` — the Verifier LLM must return a `VerificationResult`-shaped object (`passed`, `failed_checks`, `detail`), not free text, so its own output stays machine-checkable and auditable.
- **Consider N-of-M voting for the golden path if this layer is enabled there at all**: run the adversarial check multiple times (or with a couple of prompt variants) and require majority agreement before overriding Layer 1's pass — a single LLM judgment call is still a single point of failure the MAST taxonomy's "verification gaps" category warns about.

On any Layer 1 check failing, or Layer 2 (if enabled) failing: `verification_result.passed = False`, and the graph routes to `graceful_exit` (today's existing "insufficient data to determine root cause" fallback) rather than presenting an unverified claim — **fail closed**, matching the existing anti-hallucination philosophy. For the demo/golden-path specifically: **recommend Layer 1 only**, both for latency (an extra LLM round-trip inside the <60s budget) and for repeatability — Layer 2 is the piece of this design most worth prototyping separately, on non-demo traffic, before trusting it live.

---

## 7. Extensibility walkthrough — adding a hypothetical AlertManager sub-agent

1. Write `alertmanager_subgraph` (new file, e.g. `src/agent/subagents/alertmanager.py`) with its own internal deterministic steps (list active alerts → filter by service → format as `Evidence` records). No LLM inside, same as every other sub-agent.
2. Wrap it as a tool (Strategy A) — `alertmanager_tool(service: str) -> list[Evidence]` — and add it to the meta-agent's `bind_tools([...])` list.
3. No change needed to: `topology`/`telemetry`/`knowledge` sub-agents, the Verifier (its checks already operate generically over `state["evidence"]` regardless of `source` value — just add `"alertmanager"` to the `Evidence.source` Literal), or `graph.py`'s node/edge wiring.
4. Update `.env.example` / docs for the new connection, same pattern as the three existing planes.

This is the concrete demonstration of CLAUDE.md's extensibility requirement holding under this design.

---

## 8. Open questions / risks for whoever picks this up next

- **Golden-path determinism vs. LLM-everywhere.** This is now the central open risk of the whole document, introduced by the revised decision. CLAUDE.md's constraint is explicit: *"Any non-determinism (LLM topology reasoning, dynamic port assignment, etc.) is a blocker"* for the demo. If every sub-agent defaults to an internal ReAct loop, the golden path stops being deterministic in exactly the way the retrospective says made v1.5 work. **Recommendation, not yet a locked decision:** each LLM-capable sub-agent should have a deterministic fast-path (a fixed query/template) that runs by default, with the internal LLM loop reserved for an explicit "ambiguous/low-confidence" branch — so the demo path stays deterministic while the *capability* exists for messier real-world incidents. This needs to be validated, not assumed; flagging it rather than deciding it here.
- **Latency budget.** Today's golden path must finish in <60s (`verify_golden_path.py`). Each sub-agent pipeline adds steps, and any sub-agent running its own internal LLM ReAct loop adds a full extra LLM round-trip (or several) on top of the meta-agent's. Needs a latency budget breakdown per sub-agent before implementation, not just an aggregate check at the end — this is more pressing now than in the original deterministic-only draft.
- **`remaining_steps` allocation.** Today's flat budget (`remaining_steps: int`, decremented once per meta-agent turn) doesn't generalize to "how many internal LLM turns can the Telemetry subgraph's own ReAct loop take before it must return." Needs a per-sub-agent sub-budget, most urgently for any sub-agent with an internal LLM loop (a runaway inner loop is now possible in a way it wasn't in the all-deterministic draft).
- **Query surface growth.** Telemetry moving from 1 fixed query to "N candidate services × M query templates, LLM-selected" needs a cap on the template set even when LLM-selected — a fixed, enumerable set of templates the LLM picks from, not LLM-generated SQL, per the existing "no LLM-inferred topology" anti-feature in `FEATURES.md`. The "LLM chooses" freedom should apply to *which* deterministic template runs, not to generating new queries.
- **Verifier Layer 2 independence in practice.** §6's isolation/adversarial-framing mitigations are design intent, not yet validated — an LLM verifier that's supposed to be independent but still shares an underlying model/training with the meta-agent's LLM may have correlated blind spots no amount of prompt framing fixes. Worth a dedicated eval (deliberately-wrong synthesis inputs, does Layer 2 actually catch them) before trusting it on real incidents.
- **Golden-path verification script.** `verify_golden_path.py` currently only checks final-message substrings; this design's Verifier stage should have its own explicit test fixture (a known-good evidence set that should pass, and at least one known-bad set — e.g., contradictory topology/telemetry — that should trigger `graceful_exit`) before it's trusted in the demo path. This matters more now: with LLM-backed sub-agents, "did the right deterministic tool get called" is no longer guaranteed by construction, so this needs to become an explicit assertion.
- **`langgraph-supervisor` package.** Revised assessment (see §2, §5 Strategy B): now a legitimate direct implementation option since sub-agents may be real `create_react_agent`s. Still not mandatory — a sub-agent with no internal LLM loop is simpler as a plain deterministic subgraph, and mixing both under one supervisor is fine.

---

## 9. Non-goals

This document does **not** propose or endorse:
- **Mandating** that every sub-agent use an LLM. Permitted everywhere (revised decision) is not the same as recommended everywhere — §3.1 gives a per-sub-agent recommendation, and Topology in particular has no clear need for one on the golden path.
- Skipping Layer 1's deterministic gates in the Verifier (§6) in favor of LLM judgment alone, even though an LLM-based Verifier is now permitted — Layer 1 stays unconditional regardless of whether Layer 2 is enabled.
- **Mandating** adoption of the `langgraph-supervisor` PyPI package as a dependency — it's now a more direct fit than the original draft assessed (§2, §5), but plain hand-rolled subgraphs remain valid for sub-agents that don't need an internal LLM loop.
- Free-form (non-fixed-order) LLM routing *between* sub-agents for the golden-path demo — that's a separate axis from "does an individual sub-agent reason internally," still out of scope here, still a v3+ concern once determinism at the current scope is proven.
- Any change to `src/`, `tests/`, or the golden-path demo script as part of this document. Implementation is future work for a dedicated milestone (via the project's GSD phase workflow), informed by this doc.

---

## Sources

- [Architecting Multi-Agent Systems with LangGraph](https://medium.com/@timarkanta.sharma/architecting-multi-agent-systems-with-langgraph-patterns-trade-offs-and-real-world-design-ba8c535c6b35) — supervisor pattern as production default
- [Multi-Agent Design Patterns: The Four That Work in Production](https://mudassirkhan.me/blog/multi-agent-design-patterns) — Sequential / Orchestrator-Worker / Hierarchical / Dynamic Handoff taxonomy
- [langgraph-supervisor-py](https://github.com/langchain-ai/langgraph-supervisor-py) — `create_supervisor`, handoff tools, `Command(goto=, graph=Command.PARENT)` mechanics
- LangGraph subgraph docs (`docs.langchain.com/oss/python/langgraph/use-subgraphs`, via Context7 `/websites/langchain_oss_python_langgraph`) — subgraph-as-node vs. subgraph-invoked-in-node-function patterns, state transformation
- LangGraph `Command` primitive docs (via Context7) — `update`/`goto`/`graph`/`resume` parameters
- Graph-Augmented Multi-Agent Robust Root Cause Analysis in AIOps ([ScienceDirect](https://www.sciencedirect.com/org/science/article/pii/S1546221826005011)) — Diagnoser/Navigator/Verifier/Coordinator role framework
- Auditable Graph-Guided Root Cause Analysis for Kubernetes Incidents ([arXiv 2606.08590](https://arxiv.org/html/2606.08590)) — closest direct analog; deterministic-vs-LLM separation principle, three-check Validation stage, read-only tool allow-list, checkpointing for auditability
- Why Multi-Agent LLM Systems Fail (MAST taxonomy) ([Augment Code guide](https://www.augmentcode.com/guides/why-multi-agent-llm-systems-fail-and-how-to-fix-them)) — specification/coordination/verification failure breakdown, schema-contract and independent-validation fixes
- This repo: `.planning/RETROSPECTIVE.md`, `.planning/PROJECT.md`, `.planning/research/ARCHITECTURE.md`, `CLAUDE.md`, `src/agent/graph.py`, `src/agent/tools.py`, `src/agent/state.py`, `scripts/verify_golden_path.py` — current-state grounding
