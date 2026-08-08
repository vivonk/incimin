# incimin.io — AI SRE Agent

## Shipped: v1.6 Plugin-based Service Topology (2026-08-07)

3 phases, 3 plans, 10 tasks — extensible plugin architecture with SigNoz integration. See `.planning/milestones/v1.6-ROADMAP.md`.

## Current Milestone: v1.7 Incident Dashboard

**Goal:** Give every SigNoz alert a durable, observable lifecycle — persisted, tracked live in a web dashboard, and pausable for human approval.

**Target features:**
- Alerts persist in Postgres with full SigNoz metadata and a live status column
- FastAPI service absorbing `/webhook/signoz`; SSE-driven React SPA with Findings / Next Steps / Step Graph / Raw tabs
- Human-in-the-loop approval gates in the meta-agent (remediation + escalation), durable across process restarts
- Dynamic step graph derived from real agent events
- Replay script driving a committed SigNoz fixture end to end

## What This Is

An autonomous AI SRE (Site Reliability Engineering) agent that performs real-time, deterministic root-cause analysis during infrastructure incidents. It unifies two operational planes — live service topology (Memgraph) and high-velocity telemetry (SigNoz/ClickHouse) — to replace the L1 first-responder triage role. Targeted at mid-size and large enterprises running distributed microservice architectures.

## Core Value

When an incident fires, the agent autonomously traverses the live service graph and queries correlated telemetry — delivering root cause and recommended remediation steps before any human has opened a dashboard.

## Requirements

### Validated

- ✓ LangGraph state machine with 3 deterministic tools: Cypher/BFS graph traversal, ClickHouse SQL log query, Qdrant semantic runbook search — v1.5
- ⊘ ~~Agent never executes remediation actions — outputs recommendations only~~ — v1.5, **superseded in v1.7**: the agent may execute allowlisted actions, but only behind a mandatory human approval gate with a full audit trail
- ✓ End-to-end golden path: "Checkout latency is spiking" prompt → root cause + remediation output in <60 seconds — v1.5
- ✓ Full Docker Compose local stack: OTel Astronomy Shop (14 services) + SigNoz + Memgraph + Qdrant + Streamlit + LangGraph agent — v1.5
- ✓ Memgraph service topology seeded with 14 microservice nodes, edges representing dependencies — v1.5
- ⊘ ~~Qdrant pre-hydrated with ≥3 embedded Markdown runbooks with metadata filtering~~ — v1.5, **invalidated**: knowledge data plane removed from the codebase in `6dbab2f`
- ✓ Chaos injection script: deterministic P1 failure (paymentservice crash → checkout latency spike) — v1.5
- ✓ Streamlit chat UI rendering real-time tool-call glass-box visibility via `st.status` expanders — v1.5
- ✓ Memgraph Lab live node-highlighting as agent traverses graph (split-screen visual) — v1.5
- ✓ Codebase structured for production evolution post-demo (not throwaway) — v1.5
- ✓ CORE-02: TopologyPlugin ABC for standard async fetch interface — v1.6
- ✓ CORE-03: TopologyManager plugin registry with sub-class validation — v1.6
- ✓ CORE-01: ServiceNode/ServiceEdge Pydantic models with EntityMetadataMixin — v1.6
- ✓ ADV-01: Dual identity provenance (external_id + deterministic UUID5 internal_id) — v1.6
- ✓ PLUG-01: SigNozServiceMap fetches topology from SigNoz API, normalized to standard model — v1.6

### Active

(Defined in `.planning/REQUIREMENTS.md` for milestone v1.7)

### Out of Scope

- **Unattended** remediation execution — the agent never acts without a human clicking Approve. v1.7 permits execution of a fixed allowlist of actions behind that gate, with every proposal, decision, and result written to an audit table; anything beyond the allowlist, and any execution without approval, remains excluded.
- Cloud infrastructure scope (IaC, autoscaling, cloud resource management) — agent operates at the app-observability layer only.
- Multi-tenant SaaS platform — single-org enterprise deployment model.
- LLM-based topology inference — graph traversal is algorithmically delegated to Memgraph BFS; LLM never "figures out" service dependencies.
- Real production deployment for the demo — Docker Compose local stack only for the 3-day build sprint.

## Context

**Build timeline:** 3-day sprint (48 hours of build time) targeting a live demo for a real product pitch to enterprise prospects.

**Team:** Small team of 2-3 engineers splitting work across the three data planes.

**Demo format:** Dual-screen split — Streamlit Chat UI (right) + Memgraph Lab live graph visualization (left). Incident scenario is scripted and deterministic to guarantee demo reliability.

**Victim application:** OpenTelemetry Astronomy Shop — pre-built 14-service distributed app with real OTel traces and logs, chosen because it eliminates instrumentation overhead and emits production-realistic telemetry.

**Architecture philosophy:** Zero LLM hallucinations in the critical path. Topology traversal is pure Cypher BFS. SQL queries for log retrieval are dynamically generated but structurally validated. Only the synthesis step (root cause explanation + recommendation narrative) uses LLM reasoning.

**Post-demo trajectory:** This codebase becomes the product foundation. Code quality, modularity, and extensibility matter from day one.

**v1.6 state:** Plugin-based topology architecture shipped. `src/production/topology/` contains the full stack: Pydantic models with entity metadata enforcement, TopologyPlugin ABC, TopologyManager registry, and SigNozServiceMap plugin. 855 LOC added across 18 files. 6/6 tests passing.

## Constraints

- **Timeline:** 3-day / 48-hour build sprint — phases must be parallelizable across 2-3 engineers
- **Tech Stack (locked):** LangGraph (Python), Memgraph + memgraph-mage, SigNoz (OTel Collector + ClickHouse) — no substitutions; demo context depends on these specific tools. *(Qdrant dropped with the knowledge plane in `6dbab2f`; Streamlit retired in v1.7 in favour of a FastAPI + React SPA, which the dashboard's live status, click-through detail, and dynamic step graph require.)*
- **Runtime:** Docker Compose local — no cloud dependencies during build/demo
- **Demo reliability:** Golden path must be fully deterministic. Any non-determinism (LLM topology reasoning, dynamic port assignment, etc.) is a blocker.
- **Extensibility:** Agent tool interface must be designed so adding new tools (e.g., alertmanager integration, k8s pod inspector) doesn't require rewriting the state machine

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| LangGraph over raw LLM tool-use loop | State machine gives deterministic control flow + transparent debugging; critical for demo reliability | ✓ Good |
| Memgraph BFS for topology (not LLM inference) | Eliminates hallucination risk in the critical RCA path | ✓ Good |
| SigNoz over raw Grafana/Prometheus | Provides unified logs+traces+metrics with a SQL interface (ClickHouse), enabling dynamic query generation by the agent | ✓ Good |
| OTel Astronomy Shop as victim app | Pre-instrumented, multi-service, realistic telemetry — eliminates instrumentation scope from the sprint | ✓ Good |
| Streamlit for UI | Zero-overhead chat UI with `st.status` expanders for glass-box tool visibility; not investing in custom frontend for demo | ✓ Good |
| Recommendations-only agent (no auto-remediation) | Reduces blast radius risk for enterprise adoption; keeps v1 scope achievable | ✓ Good |
| Production Codebase Separation | Leave existing demo codebase intact in its current structure; develop production version in a new directory to preserve demo's working state and tests | ✓ Good |
| Explicit dict registry over entry_points | Plugin discovery via PLUGINS dict is simpler, safer (no dynamic loading), and sufficient for single-org deployment | ✓ Good — v1.6 |
| UUID5 for internal_id | Deterministic hash of (source, external_id) enables idempotent Memgraph MERGEs without read-before-write | ✓ Good — v1.6 |
| httpx + tenacity for SigNoz plugin | Async HTTP client with exponential backoff retries; resilient to transient SigNoz API failures | ✓ Good — v1.6 |
| **Reverse "recommendations-only"** — allow allowlisted execution behind a human approval gate | The original exclusion's stated reason was security and audit. An allowlist (never an LLM-authored command), a mandatory human Approve click, and an `approvals` audit row per decision answer exactly that reason. Recommending a fix a human then runs by hand loses the audit trail the exclusion wanted. | v1.7 |
| Postgres for application state (not ClickHouse) | Alert status mutates many times per incident; ClickHouse `ALTER TABLE UPDATE` is an async non-transactional mutation with no real upsert. Postgres gives row updates, a unique index for idempotent webhook delivery, JSONB for the raw payload, LISTEN/NOTIFY for SSE, and `AsyncPostgresSaver` so agent checkpoints and alert state share one DB. ClickHouse stays the read-only telemetry source. | v1.7 |
| Retire Streamlit for a React SPA | Streamlit cannot do live per-row status without a polling hack, and the dynamic step graph needs a real graph renderer. Serving a static Vite build from the same FastAPI process avoids a second runtime. | v1.7 |
| Durable HITL via `AsyncPostgresSaver` + `interrupt()` | The graph previously compiled with no checkpointer, so a pause could not survive a restart. Checkpointing is what makes an approval gate real rather than an in-memory promise. | v1.7 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-08 at start of v1.7 milestone*
