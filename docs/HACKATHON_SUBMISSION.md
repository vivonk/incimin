# incimin.io — an AI SRE that investigates incidents like a scientist, not a chatbot

## Problem Statement

When a production alert fires at 3 AM, the first 15–30 minutes are spent doing the same
mechanical work every time: who's on call opens a dashboard, traces the alert to a service,
checks whether that service was just deployed, greps its error logs, checks its immediate
dependencies, and tries to figure out — before doing anything else — *what actually broke*.
This is "L1 triage": necessary, time-critical, and almost entirely pattern-matching over three
disconnected systems that never talk to each other:

- **Topology** — which services call which, and how a failure in one propagates to the one
  the alert fired on. Usually lives in nobody's head but the team that built it.
- **Telemetry** — logs, traces, and metrics in an observability backend (SigNoz/ClickHouse in
  our stack) that answer "what does the failure look like" but not "why."
- **Operational history** — deploys, config changes, PR merges — the single strongest signal
  for *why now*, and usually the last thing anyone checks because it lives in yet another tool.

Existing "AI SRE" tools tend to fail in one of two directions. Either they're a chatbot wrapper
around a single LLM call that free-associates over whatever context you paste in — fast, but
it hallucinates root causes, can't tell you what it ruled out, and gives a different answer if
you ask twice. Or they're deterministic runbooks — reliable, but brittle, and blind to any
failure mode nobody scripted for. Neither produces something a human can actually **trust**
enough to hand production remediation to.

The problem we set out to solve: **can an agent investigate an incident the way a good SRE
does** — form multiple competing explanations, go looking for evidence that would rule them
out (not just confirm the first guess), stop when the evidence actually says "enough," and
show its work well enough that a human can audit *why* it concluded what it concluded —
**while remaining fast and deterministic enough to demo and to trust in production**?

## What We Built

**incimin.io** is an autonomous SRE agent that ingests a live infrastructure alert, traverses
the real service dependency graph, runs a structured tournament between competing root-cause
hypotheses using evidence pulled live from telemetry and deploy history, and produces a root
cause with a calibrated confidence level, a full account of what it ruled out and why, and an
optional allowlisted remediation action — gated behind mandatory human approval before
anything executes.

It is not a single LLM call with tools bolted on. It is a **LangGraph state machine in which
the LLM never decides the things that matter most for correctness** — service topology, the
stop/continue decision, the winning hypothesis, and what commands are allowed to run are all
arithmetic or table lookups in plain code. The LLM's job is narrower and better-suited to what
LLMs are actually good at: proposing candidate explanations, judging how one piece of evidence
bears on one hypothesis (an ordinal five-way call, not a probability it would happily
overstate), and writing the human-readable narrative at the end.

The system runs end-to-end against a real 14-service microservice application (the
OpenTelemetry Astronomy Shop demo), a real SigNoz/ClickHouse telemetry backend, a real
Memgraph service graph, and a Postgres-backed incident dashboard with a live React UI — all
orchestrated through Docker Compose, with zero cloud dependencies for the demo.

---

## System Architecture

Three data planes, unified by one incident lifecycle:

```
                     SigNoz Alertmanager webhook
                                │
                                ▼
                   ┌─────────────────────────┐
                   │   FastAPI Incident API    │  src/api/main.py
                   │   POST /webhook/signoz     │  • parses Alertmanager payload
                   │                            │  • dedupes on alert fingerprint
                   └──────────┬─────────────────┘  • persists incident row (Postgres)
                              │ spawns background task
                              ▼
                   ┌─────────────────────────┐
                   │   Kernel (LangGraph)      │  ◄── the agent, see below
                   │   src/agent/kernel/       │
                   └───┬──────────┬───────────┘
                       │          │
        ┌──────────────┘          └───────────────┐
        ▼                                          ▼
┌───────────────┐  ┌───────────────┐   ┌──────────────────┐
│   Memgraph     │  │  ClickHouse    │   │  incimin-sre MCP  │
│   (topology)   │  │  (SigNoz logs, │   │  server (2nd,     │
│   BFS traversal│  │   system_      │   │  protocol-mediated│
│   over Service │  │   changes)     │   │  view of topology  │
│   nodes/edges  │  │                │   │  + deploy events)  │
└───────────────┘  └───────────────┘   └──────────────────┘
        deterministic Cypher              LLM-directed tool calls
        (never LLM-inferred)              (Meta-Agent decides IF/how)

                              │
                              ▼
                   ┌─────────────────────────┐
                   │   Postgres                │  agent_steps, approvals,
                   │   (incidents +            │  execution results — the
                   │   LangGraph checkpointer) │  full audit trail + durable
                   │                            │  pause/resume for HITL gates
                   └──────────┬─────────────────┘
                              │
                              ▼
                   ┌─────────────────────────┐
                   │   React dashboard          │  frontend/ (Vite + React)
                   │   incident list, findings,  │  Findings / Next Steps /
                   │   step graph, approve/reject│  Step Graph / Raw tabs
                   └─────────────────────────┘
```

**Ingestion.** SigNoz/Alertmanager posts an alert to `POST /webhook/signoz`. The handler
always returns 2xx immediately (alert senders retry aggressively on slow or non-2xx
responses) and hands the alert to a background task — the agent run itself takes tens of
seconds. Repeat suppression is a Postgres uniqueness constraint on the alert fingerprint, not
an in-process dict, so it survives a restart and can't race between two concurrent deliveries
of the same incident.

**Persistence & audit trail.** Every node the kernel visits, every probe it runs, every tool
call, and every human decision is written to Postgres as an ordered, parent-linked step —
`agent_steps` is a graph, not a flat log, which is what lets the dashboard render an actual
step graph instead of a scrollback. LangGraph's own checkpointer lives in the same Postgres
instance, keyed on the incident's own id, so a paused run (waiting on human approval) survives
a process restart and resumes on exactly the thread it paused on.

**Observability of the agent itself.** Every run — the kernel's tool-calling, the synthesis
step, and every LLM call a sub-agent makes — exports as one Langfuse trace when credentials
are present, grouped by the alert's dedupe key so repeat fires of one incident read as one
session. Tracing fails open: a missing key or unreachable host degrades to an untraced run
with a log line, never a failed triage.

**Dashboard.** A Vite + React SPA polls the incident API for the incident list (filterable by
status/severity), and for a selected incident renders Findings, Next Steps, a dynamic Step
Graph built from the real `agent_steps` rows, and the raw alert payload — plus Approve/Reject
controls when a run is parked at a human gate.

---

## The Agent, In Depth: A Hypothesis Tournament, Not a ReAct Loop

This is the core of the system, and the part we think is genuinely different from a typical
"agent with tools." Most agent designs are a single forward pass: the model gets a query, calls
some tools, and commits to whatever explanation its first line of reasoning produced. Ours is a
**belief-tracking tournament between multiple named hypotheses**, with a structural verifier
gate before any answer is allowed to leave the graph, and every decision that determines
*correctness* — as opposed to *explanation* — pinned to arithmetic in code rather than an LLM
call.

### The graph

```
              ┌─▶ seed (Hypothesis Generation) ──┐
  ground ─────┤                                  ├─▶ update_beliefs ─┬─▶ (loop: more probes)
 (Meta-Agent) └─▶ probe ×N (Probe Agent, rd 0) ───┘                   └─▶ verify ─┬─▶ report ─▶ synthesize
                                                                                    │                │
                                                                          graceful_exit          propose_remediation
                                                                                │                    │
                                                                        await_escalation        route: executable?
                                                                          (human gate)                │
                                                                                                await_approval (human gate)
                                                                                                        │
                                                                                                execute_remediation
```

**1. `ground` — Meta-Agent.**
A deterministic Memgraph BFS traversal from the alerting service establishes the candidate
service list *before any hypothesis exists* — mirroring Google SRE's own published finding
that an agent must fix "domain and intent" from real topology before it starts speculating,
rather than jumping straight from alert text to a guess. That traversal is a hard edge in the
graph, not a tool the model can skip or reshape — topology is never LLM-inferred anywhere in
this system.

What *is* left to the model here: whether and how to reach for a second, protocol-mediated
evidence source. The Meta-Agent is bound (via `bind_tools`) to two tools served over MCP by a
separate `incimin-sre` server — `get_service_topology` (a second view of the dependency graph,
useful to corroborate or extend the BFS pass) and `get_system_events` (recent deploys/PR
merges/config changes — often the single strongest causal signal). The model can call zero,
one, or both, for however many candidate services it judges worthwhile, in a single bounded
turn — no back-and-forth react loop, because each MCP round-trip already costs 15–30s cold.
Every result becomes typed `Evidence` regardless of which tool produced it. If the LLM or the
MCP server is unavailable, this pass degrades silently back to whatever the unconditional BFS
already found — the deterministic path never depends on the model succeeding.

**2. `seed` and round-0 `probe` — run concurrently.**
Hypothesis generation and the first breadth round of evidence-gathering fan out from `ground`
at the same time and join back into `update_beliefs`, because round-0 probe selection never
looks at hypothesis *content* — at round 0 every hypothesis is still a guess, so there is
nothing to gain by making evidence-gathering wait for hypothesis text to exist.

Hypotheses are seeded in **tiers**, each one only firing if the previous underfilled the
minimum of three:
1. *Playbook match* (hook point for future team-specific playbooks).
2. *Topology* — every BFS candidate becomes a `dependency_failure` hypothesis, prior weighted
   by BFS depth (closer to the alerting service = more likely implicated).
3. *Evidence-driven* — any real deploy/change evidence the Meta-Agent's MCP pass already found
   becomes a `deploy_regression` hypothesis in its own right, not just later corroboration.
4. *LLM* — only if the deterministic tiers still came up short, the model proposes additional
   hypotheses constrained to the actual candidate-service list (a hypothesis about a service
   outside the graph can never be corroborated by any probe, so it's rejected outright) and a
   fixed taxonomy of hypothesis kinds.

Priors are then normalized into posteriors, and the round budget is **sized from the
hypothesis set's own ambiguity** — `B = min(B_max, B_min + entropy)` — a single dominant
hypothesis converges in one round; three near-equal ones earn up to five. This replaces a
flat, incident-blind step count with something that actually reflects how uncertain the
opening position is.

**3. `probe` — Probe Agent, fanned out via `Send`.**
Probes are a pluggable evidence-source contract (`src/agent/probes/`), each declaring up
front — without running — its cost tier (cheap/normal/expensive), which hypothesis *kinds* it
can discriminate between, and its evidence cap. Selection (`selection.py`) is a **table join,
not a model call**: round 0 runs every cheap probe as breadth; every later round runs *only*
probes that separate the current top-two hypotheses, scored by `discrimination / cost`. This
implements the one rule the diagnosis literature is unanimous on and that LLM agents
routinely get backwards: pick the test that most cleanly **separates** the leading
explanations, not the one most likely to confirm whichever came first — confirmatory probing
is exactly how an agent talks itself into its opening guess. Two probes ship today:
`signoz.error_logs` (ERROR-severity logs from ClickHouse, discriminates resource-exhaustion /
dependency-failure / data-issue) and `changes.deploys` (deploy/config-change events,
discriminates deploy-regression / config-change) — deliberately asymmetric in what they can
rule out, which is what makes the pair worth running together. A probe is contractually
forbidden from raising: a dead or rate-limited data source degrades one evidence stream, never
the whole investigation.

**4. `update_beliefs` — deterministic Bayesian-style update.**
Fresh evidence each round is judged by an LLM, but **the LLM never emits a number.** It
returns one of five ordinal verdicts per (hypothesis, evidence) pair —
`strongly_supports / supports / neutral / weakens / refutes` — because a model asked directly
for a probability will happily emit 0.85 for two unrelated facts in the same batch, while the
comparative judgement it's actually being asked for (does this evidence discriminate?) is
something it's much better calibrated on. Those five labels map to **fixed likelihood
ratios** (4.0 / 2.0 / 1.0 / 0.5 / 0.1), and the posterior update itself — multiply, prune
anything below a floor, renormalize across survivors — happens in plain code. `refutes` is
terminal: a refuted hypothesis stays refuted even if a later verdict would otherwise support
it, which is the minimal form of contradiction-consistency the design calls for. Under
`INCIMIN_DETERMINISTIC=1` (the golden path / CI mode), this step runs on a rule-based
stand-in instead — same shape, zero network calls, fully replayable.

The entire belief trajectory is therefore **exactly recomputable from the verdict log**: an
incident review can ask "why did it converge on this?" and get an arithmetic answer, not a
"the model said so."

**5. Stopping is arithmetic, not a judgement call.** A dedicated finding from the "Don't Let
Me Ask For It" literature (arXiv 2608.03388) motivates this directly: LLMs systematically
*under-ask* in multi-turn diagnostic settings — they stop gathering evidence too early and
commit. So the continue/stop decision is never handed to a model. Four independent, ordered
terminal conditions decide it: the leading hypothesis's posterior crosses τ=0.90
(`converged`), every hypothesis gets refuted (`all_refuted`), the round budget is exhausted
(`budget_exhausted`), or no remaining probe can discriminate the current field
(`no_discriminating_probe`). Only a τ-crossing earns high confidence in the final report — a
run that merely ran out of rounds may still have a plausible leader, but it never had the
chance to be refuted, and the report says so rather than dressing up exhaustion as confidence.

**6. `verify` — a deterministic, unbypassable gate.** Before any winning hypothesis is allowed
to become a report, five pure checks run against it in code:
- **Evidence grounding** — every citation the winner claims must actually exist and belong to
  its own subject service.
- **Cross-source consistency** — the claim must rest on at least two *distinct* evidence
  sources, not one probe's word alone.
- **Temporal ordering** — cited cause-evidence must predate the alert (with a small grace
  window for symptom evidence that keeps arriving after the fact) — a hypothesis "confirmed"
  by evidence from *after* the failure started is not a cause.
- **Refutation integrity** — a winner still carrying its own contradicting evidence fails,
  full stop.
- **Budget honesty** — records (without failing the run) whenever the stop reason wasn't a
  genuine convergence, so confidence-capping downstream is traceable to a real cause.

A run that fails verification routes to `graceful_exit` and a human escalation gate instead of
`report` — the agent is structurally prevented from confidently naming a service it cannot
actually ground.

**7. `report` → `synthesize` — decide, then explain, never the reverse.** `report_node` picks
the winner **by posterior, in code**, and writes the deterministic account: root cause,
confidence, cited evidence, and — deliberately, because most agents never surface this — the
full list of *what was ruled out and why*, per Google SRE's own writeup naming "options
considered and rejected" a hard requirement for a trustworthy triage agent. Only after that
decision is fixed does `synthesize_node` ask an LLM to write the human-facing narrative
explaining *why* the evidence points there and what to check next — it is given the winner as
settled fact and is explicitly instructed not to second-guess or rename it. If that call fails,
nothing is lost: the deterministic report is still the last message on the thread, and none of
the recorded outcome (root cause, confidence, evidence refs) depended on the narrative
succeeding.

### Human-in-the-loop remediation

A confident, verified report earns a remediation *proposal* — never an action. The winning
hypothesis is mapped to one of a fixed allowlist of actions (`src/agent/remediation.py`;
today: `restart_service`) by lookup, never composed by a model, and the target container name
is resolved and validated **before** anyone approves it, so what a human reads is exactly what
later runs. A regex protects the observability stack and the agent's own Postgres/checkpoint
store from ever being a valid target — the agent cannot blind itself or drop its own
checkpoint mid-investigation.

The graph then calls `interrupt()` and pauses — durably, via the Postgres checkpointer, across
process restarts — until a human hits Approve or Reject on the dashboard. Two people clicking
Approve on the same gate race on a `WHERE decision = 'pending'` database predicate; exactly one
wins. Only on approval does `execute_remediation` run — and it re-validates the target against
the allowlist a second time rather than trusting the stored proposal, because the cost of
checking again is a dictionary lookup. `subprocess.run` is always called with a list argv,
never `shell=True`. If verification instead fails or the field never converges, the graph
routes to a parallel `await_escalation` gate — the agent does not get to decide on its own that
it's beaten; a human is asked to take the incident with the best unconfirmed guess and the
list of failed checks in hand.

### Extensibility

A new evidence source is a new `Probe` implementation — `manifest` (cost tier, what hypothesis
kinds it discriminates) plus an async `run()` that returns typed `Evidence` and never raises —
registered once and immediately eligible for selection with zero changes to the kernel graph,
selection logic, or belief math. This directly satisfies the project's founding constraint that
adding a new tool (an Alertmanager integration, a k8s pod inspector) must never require
rewriting the state machine.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Agent state machine | LangGraph 1.2.10 (`StateGraph`, `Send` fan-out, `interrupt()`/`Command(resume=...)` for durable HITL) |
| LLM | Anthropic Claude (Sonnet), via `langchain-anthropic` — structured output for verdicts, hypothesis seeding, synthesis |
| Topology | Memgraph + memgraph-mage, Cypher BFS (`bolt://`, `neo4j` driver) |
| Telemetry | SigNoz (OTel Collector + ClickHouse), `clickhouse-connect` |
| Second evidence channel | Custom `incimin-sre` MCP server (topology + deploy events over SSE), consumed by the Meta-Agent via `bind_tools` |
| Incident API | FastAPI, Postgres (`psycopg3`), LangGraph `AsyncPostgresSaver` |
| Dashboard | Vite + React (TypeScript) |
| Tracing | Langfuse (fails open) |
| Victim application | OpenTelemetry Astronomy Shop (14-service demo app), for real, production-shaped telemetry with zero custom instrumentation |
| Runtime | Docker Compose v2, fully local, zero cloud dependency for the demo |

---

## Work Done In This Hackathon

`checkpoint-before-hackathon.md`, committed at the start of the build window, describes the
pre-hackathon state: a single-pass LangGraph coordinator with Topology/Telemetry/Knowledge/
Verifier sub-agents, a Streamlit chat UI, Qdrant-backed runbook retrieval, and a webhook
receiver good enough to demo but with no persistence, no audit trail, and no way for a human to
intervene. Everything below — 33 commits, ~10,700 lines added across 104 files — was built
during the hackathon on top of that baseline, and it changes the system on every axis: the
agent's reasoning core, its evidence sources, its data plane, its UI, and its safety story.

### 1. Rebuilt the agent core: single-pass coordinator → hypothesis-tournament kernel

The pre-hackathon agent (`src/agent/graph.py`, `subagents/`) was a ReAct loop: one LLM node
bound to a flat tool list, looping until it stopped calling tools or hit a step budget, with a
single `Synthesis` object as its only output. It could not revise an early guess, could not
report what it ruled out, and its stop/continue decision was implicitly whatever the model
felt like doing next.

`src/agent/kernel/` (new package, ~1,700 lines: `graph.py`, `state.py`, `beliefs.py`,
`budget.py`, `selection.py`, `verifier.py`, `mcp_tools.py`) replaces it with the tournament
architecture described above in full: multiple named `Hypothesis` objects carrying their own
posteriors, deterministic Bayesian-style belief updates from LLM-issued ordinal verdicts,
entropy-sized round budgets, discrimination-scored probe selection, and a five-check
verification gate before any answer can leave the graph. `src/agent/probes/` (new package) is
the pluggable evidence-source contract the old flat tool list didn't have — `base.py`,
`registry.py`, and two concrete probes (`core/logs.py`, `core/changes.py`) that ship today.
The old single-pass `graph.py`/`subagents/` code is still present for reference but the kernel
is the live path.

### 2. Gave the Meta-Agent a second, protocol-mediated evidence channel (MCP)

Ground node now binds the model to two tools served by a standalone `incimin-sre` MCP server
(`.mcp.json`, `src/agent/kernel/mcp_tools.py`) — `get_service_topology` and
`get_system_events` — and lets the model decide whether and how to call them in a single
bounded turn, on top of (never instead of) the unconditional Memgraph BFS pass. Every MCP
result is normalized into typed `Evidence`, and real deploy events found this way flow straight
into hypothesis generation (`hypotheses_from_evidence`) rather than sitting inert. This is new
end-to-end: the pre-hackathon agent's MCP awareness was limited to an unwired, parallel
`diagnosis.py` path that never shared code with the LangGraph coordinator.

### 3. Human-in-the-loop approval gates and gated remediation execution

None of this existed before the hackathon — the pre-hackathon agent only ever produced
recommendations. `src/agent/remediation.py` (new, 200 lines) is the allowlist + target
resolution + `subprocess.run` executor described above; the kernel graph gained four new nodes
(`propose_remediation`, `await_approval`, `execute_remediation`, `await_escalation`) built on
LangGraph's `interrupt()` / `Command(resume=...)`, durable across process restarts via a new
Postgres-backed checkpointer (`src/api/db.py`). The dashboard exposes `POST
/api/incidents/{id}/approve` and renders the pending proposal for a human to accept or reject.
Test coverage: `tests/test_kernel_gates.py`, `tests/test_remediation.py` (~375 lines, new).

### 4. Built the incident dashboard: Streamlit chat → FastAPI + Postgres + React SPA

The pre-hackathon UI was a single-session Streamlit chat window with no persistence — an
incident existed only for the duration of one browser tab. This hackathon replaced it with a
real incident lifecycle:

- **`src/api/`** (new package, ~1,270 lines: `main.py`, `db.py`, `repository.py`, `runner.py`,
  `schema.sql`, `settings.py`) — a FastAPI service that persists every alert as an incident row,
  runs the agent as a tracked background task, records every node/probe/tool-call as an ordered,
  parent-linked step (`agent_steps`), and serves the incident list, detail, step log, and
  approval endpoints the frontend consumes.
- **`frontend/`** (new, ~2,000 lines of TypeScript/CSS) — a Vite + React SPA (`App.tsx`,
  `Shell.tsx`, `DetailPanel.tsx`, `StepGraph.tsx`) with a Langfuse-style shell (banner, sidebar,
  stat cards), an incident list filterable by status/severity, and per-incident Findings / Next
  Steps / Step Graph / Raw tabs — the step graph is rendered live from real `agent_steps` rows,
  not a hardcoded diagram.
- The old Starlette webhook receiver (`src/webhook/app.py`, 238 lines) was retired once the
  FastAPI incident API absorbed `/webhook/signoz`; alert parsing was hardened and extracted into
  its own module (`src/webhook/alert.py`, new) with defensive multi-key label matching
  (`service` / `service.name` / `k8s_deployment_name` / …) so a differently-configured SigNoz
  alert query doesn't silently drop the service name.
- **Postgres replaces Qdrant** in `docker/compose.core.yaml` as the project's application
  datastore — it now backs incidents, the step log, approvals, and the LangGraph checkpointer.
  The knowledge/runbook plane (Qdrant, fastembed, the retriever sub-agent) was removed in the
  same window as a deliberate scope cut, documented in `hackathon_starting_checkpoint.md`.
- `scripts/init_clickhouse.py` (new) codifies the DDL for `system_changes` — the deploy/change
  events table three different components (the old webhook ingester, the MCP server, and the
  new `changes.deploys` probe) all depended on but that, before this, existed only as a table
  someone had created by hand on one machine.

### 5. SigNoz + OTel Demo integration: from scripted webhooks to real triggered failures

Chaos injection moved from "simulate a webhook and hope the story lines up" to actually
flipping the same Flagd feature flags (`docker/otel-demo/src/flagd/demo.flagd.json`) the demo
app's services read at runtime, so SigNoz captures **real** errors, not synthetic ones.
`scripts/simulate_scenarios.py` grew a `set_feature_flag()` helper wired into every existing
scenario (`payment_timeout`, `redis_leak`, `quote_logic`, `kafka_backup`, `noisy_neighbor`),
added a new **`delayed_cache_crash`** scenario that seeds a deploy, waits 60 seconds of healthy
traffic, then flips `recommendationCacheFailure` — deliberately built to test whether the
kernel's temporal-ordering verifier gate correctly treats a deploy that predates the failure by
a full minute as still causally relevant — and added a `reset` scenario to zero every chaos flag
back out. `tests/fixtures/signoz_alert.json` was corrected to reference a service name that
actually exists in the seeded Memgraph graph, closing a gap where the committed golden-path
fixture couldn't resolve to a real topology candidate.

Separately, `src/remediation_mcp.py` and `src/agent/action_executor.py` (new, standalone) are
an exploratory second MCP surface built during the hackathon — a stdio MCP server exposing
`toggle_feature_flag`, `post_incident_update`, and `revert_deployment` as remediation actions
directly against the OTel demo's Flagd config — kept in the repo as a prototype of a
richer remediation surface, distinct from (and not yet wired into) the allowlisted
`restart_service` path that actually ships in the kernel graph today.

### 6. Cut the LLM provider surface to one, deliberately

`src/agent/llm.py` dropped the `LLM_PROVIDER` switch between Anthropic/Gemini/OpenRouter that
existed pre-hackathon. The golden path cannot be deterministic if its behavior depends on which
of three providers happens to be configured on a given machine; the agent is now Anthropic-only,
with a legacy `LLM_PROVIDER` env var ignored with a warning rather than an error.

### 7. End-to-end agent tracing (Langfuse)

New: `src/agent/tracing.py` (206 lines) wires every agent entry point — the kernel's tool-calling
loop, the synthesis step, and every LLM call a sub-agent makes — into a single Langfuse trace per
incident, grouped by the alert's dedupe key so repeat Alertmanager resends of one incident read
as one session instead of scattering across unrelated traces. Deliberately fails open: a missing
key, unreachable host, or uninstalled package degrades to an untraced run with one log line,
never a failed triage. `scripts/verify_langfuse.py` (new) checks the whole path — credentials →
handler → auth → real trace delivery — end to end. Covered by `tests/test_tracing.py` (253
lines, new).

### 8. MCP surface for development itself

`.mcp.json` gained a `codebase-memory` server registration, and the `opentelemetry-demo` repo
(the victim application) was indexed into a tree-sitter code graph so the team could query its
service topology and call chains structurally while building probes and scenarios against it,
instead of grepping a 14-service repo file by file.

### 9. Test suite: +2,400 lines, 9 new files

New coverage added this hackathon: `test_kernel_graph.py`, `test_kernel_selection.py`,
`test_kernel_budget.py`, `test_kernel_verifier.py`, `test_kernel_gates.py`, `test_beliefs.py`,
`test_mcp_tools.py`, `test_remediation.py`, `test_api.py`, `test_alert.py`, `test_tracing.py` —
exercising the belief math in isolation, every verifier gate, probe selection/discrimination
scoring, the human-gate state machine, the incident API's concurrency-safe approval race, and
tracing's fail-open behavior. `test_webhook.py` (275 lines, testing the retired Starlette
receiver) and the knowledge-plane tests were removed as their subjects left the codebase.

---

## Why This Design

Three principles run through every part of the system, and they're the actual argument for why
this is trustworthy enough to eventually hand real remediation authority to:

1. **The model proposes; arithmetic decides.** Topology, the stop condition, the winning
   hypothesis, the allowlisted action, and the belief update itself are all deterministic. The
   LLM's surface area is narrowed to exactly the things language models are good at:
   generating plausible candidate explanations and making comparative (not absolute) judgement
   calls — never the final say on correctness.
2. **It reports what it ruled out, not just what it picked.** A tournament between named,
   scored hypotheses produces "options considered and rejected" as a structural by-product,
   not an afterthought bolted onto a single-shot answer.
3. **Nothing acts without a human, and what a human approves is exactly what runs.** The
   allowlist, the pre-resolved target, the durable pause, and the re-validation at execution
   time together mean the gap between "proposed" and "executed" is a database row, not trust in
   a model's judgment.
