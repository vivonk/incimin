# incimin.io — AI SRE Agent

## What This Is

An autonomous AI SRE (Site Reliability Engineering) agent that performs real-time, deterministic root-cause analysis during infrastructure incidents. It unifies three operational planes — live service topology (Memgraph), high-velocity telemetry (SigNoz/ClickHouse), and human operational knowledge (Qdrant) — to replace the L1 first-responder triage role. Targeted at mid-size and large enterprises running distributed microservice architectures.

## Core Value

When an incident fires, the agent autonomously traverses the live service graph, queries correlated telemetry, and retrieves the relevant runbook — delivering root cause and recommended remediation steps before any human has opened a dashboard.

## Requirements

### Validated

- [x] LangGraph state machine with 3 deterministic tools: Cypher/BFS graph traversal, ClickHouse SQL log query, Qdrant semantic runbook search (Validated in Phase 03: agent-core)
- [x] Agent never executes remediation actions — outputs recommendations only (Validated in Phase 03: agent-core)

### Active

- [ ] Full Docker Compose local stack: OTel Astronomy Shop (14 services) + SigNoz + Memgraph + Qdrant + Streamlit + LangGraph agent
- [ ] Memgraph service topology seeded with 14 microservice nodes, edges representing dependencies
- [ ] Qdrant pre-hydrated with ≥3 embedded Markdown runbooks with metadata filtering
- [ ] Chaos injection script: deterministic P1 failure (paymentservice crash → checkout latency spike)
- [ ] Streamlit chat UI rendering real-time tool-call glass-box visibility via `st.status` expanders
- [ ] Memgraph Lab live node-highlighting as agent traverses graph (split-screen visual)
- [ ] End-to-end golden path: "Checkout latency is spiking" prompt → root cause + remediation output in <60 seconds
- [ ] Codebase structured for production evolution post-demo (not throwaway)

### Out of Scope

- Automated remediation execution — agent recommends only; humans own execution. Security and audit requirements for production systems make auto-remediation out of scope for v1.
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

## Constraints

- **Timeline:** 3-day / 48-hour build sprint — phases must be parallelizable across 2-3 engineers
- **Tech Stack (locked):** LangGraph (Python), Memgraph + memgraph-mage, SigNoz (OTel Collector + ClickHouse), Qdrant, Streamlit — no substitutions; demo context depends on these specific tools
- **Runtime:** Docker Compose local — no cloud dependencies during build/demo
- **Demo reliability:** Golden path must be fully deterministic. Any non-determinism (LLM topology reasoning, dynamic port assignment, etc.) is a blocker.
- **Extensibility:** Agent tool interface must be designed so adding new tools (e.g., alertmanager integration, k8s pod inspector) doesn't require rewriting the state machine

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| LangGraph over raw LLM tool-use loop | State machine gives deterministic control flow + transparent debugging; critical for demo reliability | — Pending |
| Memgraph BFS for topology (not LLM inference) | Eliminates hallucination risk in the critical RCA path | — Pending |
| SigNoz over raw Grafana/Prometheus | Provides unified logs+traces+metrics with a SQL interface (ClickHouse), enabling dynamic query generation by the agent | — Pending |
| OTel Astronomy Shop as victim app | Pre-instrumented, multi-service, realistic telemetry — eliminates instrumentation scope from the sprint | — Pending |
| Streamlit for UI | Zero-overhead chat UI with `st.status` expanders for glass-box tool visibility; not investing in custom frontend for demo | — Pending |
| Recommendations-only agent (no auto-remediation) | Reduces blast radius risk for enterprise adoption; keeps v1 scope achievable | — Pending |

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
*Last updated: 2026-08-06 after Phase 03 completion*
