# Requirements: incimin.io — AI SRE Agent

**Defined:** 2026-08-05
**Core Value:** When an incident fires, the agent autonomously traverses the live service graph, queries correlated telemetry, and retrieves the relevant runbook — delivering root cause and recommended remediation steps before any human has opened a dashboard.

## v1 Requirements

### Infrastructure

- [x] **INFRA-01**: Docker Compose stack runs all services (OTel Astronomy Shop minimal, SigNoz Foundry, Memgraph MAGE, Qdrant, Streamlit agent) with no manual steps beyond `docker compose up`
- [x] **INFRA-02**: Port assignments are collision-free (SigNoz UI on 3301, OTel frontend-proxy on 8090; no two services share a host port)
- [x] **INFRA-03**: OTel Astronomy Shop telemetry (traces, logs, metrics from all 14 services) flows to SigNoz/ClickHouse via a custom OTel Collector pipeline config
- [ ] **INFRA-04**: Memgraph data persists across container restarts via a named Docker volume
- [ ] **INFRA-05**: Host memory usage stays within 14GB Docker Desktop allocation (OTel demo in minimal mode)

### Topology Plane (Memgraph)

- [ ] **TOPO-01**: Seed script populates Memgraph with all 14 OTel Astronomy Shop service nodes and their dependency edges using `MERGE` (idempotent)
- [ ] **TOPO-02**: BFS traversal tool queries Memgraph using `[*BFS]` Cypher syntax and returns the dependency path from a given source service to the root cause service
- [ ] **TOPO-03**: Topology graph survives `docker compose restart memgraph` with all 14 nodes intact

### Telemetry Plane (SigNoz / ClickHouse)

- [ ] **TELE-01**: Log query tool generates parameterized SQL against `signoz_logs.distributed_logs` (or the verified v0.135.1 equivalent) using nanosecond timestamps
- [ ] **TELE-02**: Log query tool returns ERROR-level logs and trace IDs for a specified service within a specified time window
- [ ] **TELE-03**: ClickHouse table name and schema verified against the running SigNoz v0.135.1 instance (resolves `distributed_logs` vs `distributed_logs_v2` ambiguity)

### Knowledge Plane (Qdrant)

- [ ] **KNOW-01**: Qdrant `runbooks` collection hydrated with ≥3 embedded Markdown runbooks: paymentservice crash, checkoutservice high-latency, frontendservice 5xx errors
- [ ] **KNOW-02**: Runbooks embedded with fastembed `BAAI/bge-small-en-v1.5` (384-dim); collection dimension matches client embedding dimension
- [ ] **KNOW-03**: Runbook search tool returns the correct playbook for a given incident description via semantic similarity + payload metadata filtering

### Agent Orchestration (LangGraph)

- [ ] **AGENT-01**: LangGraph `SREAgentState` TypedDict with `add_messages` reducer and typed `IncidentContext` defined and tested
- [ ] **AGENT-02**: Three `@tool` decorated functions — `graph_bfs_tool`, `clickhouse_log_tool`, `qdrant_runbook_tool` — each touching exactly one data plane; no cross-plane access within a tool
- [ ] **AGENT-03**: StateGraph compiled with `recursion_limit=10` and a `RemainingSteps` guard that routes to a graceful "insufficient data" response when `remaining_steps <= 2`
- [ ] **AGENT-04**: Agent uses Anthropic Claude (claude-sonnet-5 or latest Sonnet) as the LLM backbone via `langchain-anthropic`
- [ ] **AGENT-05**: Agent never outputs or suggests remediation actions — response format is: root cause identification + recommended next steps (human executes)
- [ ] **AGENT-06**: Each tool has unit tests with mock clients verifying correct output format and error handling

### Demo Interface (Streamlit)

- [ ] **UI-01**: Streamlit chat UI renders agent responses in real time using synchronous `graph.stream(stream_mode="updates")` (not `.astream()`)
- [ ] **UI-02**: Each tool call rendered as a `st.status` expander showing tool name, input parameters, and raw output (glass-box visibility)
- [ ] **UI-03**: UI handles ≥3 consecutive queries without event loop errors or session state corruption
- [ ] **UI-04**: Chat history persists within a session (subsequent queries have access to prior context)

### Chaos Injection

- [ ] **CHAOS-01**: `chaos_inject.py --mode stop` stops the `paymentservice` container, triggering ERROR logs visible in SigNoz within 30 seconds
- [ ] **CHAOS-02**: `chaos_inject.py --mode latency` injects network latency on the paymentservice port via toxiproxy, producing latency spike visible in SigNoz traces
- [ ] **CHAOS-03**: `chaos_inject.py --recover` restores normal service state for both chaos modes
- [ ] **CHAOS-04**: Chaos injection is idempotent — running `--mode stop` twice does not error

### Golden Path

- [ ] **GOLDEN-01**: End-to-end: "Checkout latency is spiking. Investigate and give me a recommendation." → root cause identifies paymentservice → runbook retrieved → recommendation output, in <60 seconds wall clock
- [ ] **GOLDEN-02**: Memgraph Lab displays the service topology graph; a pre-written BFS Cypher query is scripted and rehearsed for the demo operator to execute during the agent's graph traversal step
- [ ] **GOLDEN-03**: All PITFALLS.md "looks done but isn't" checklist items verified before demo day

## v2 Requirements

### Observability Extensions

- **OBS-01**: Blast radius estimation — BFS traversal extended to compute downstream impact count from a failed service
- **OBS-02**: Incident timeline reconstruction — agent produces a timestamped sequence of events from the first anomaly to the RCA conclusion
- **OBS-03**: Alert deduplication — agent groups related alerts from the same incident into a single RCA query

### Integrations

- **INT-01**: Slack push — agent posts RCA summary to a configured Slack channel on incident trigger
- **INT-02**: PagerDuty integration — agent pulls active incident context from PagerDuty and pushes RCA as an incident note
- **INT-03**: Incident similarity retrieval — given a new incident, agent surfaces the 3 most similar historical incidents from Qdrant

### Security & Multi-tenancy

- **SEC-01**: RBAC — per-team access control for runbook collections and Memgraph subgraph views
- **SEC-02**: Audit log — every agent invocation logged with timestamp, user, input query, tools called, and output

## Out of Scope

| Feature | Reason |
|---------|--------|
| Automated remediation execution | Violates ITIL/CAB change management; destroys enterprise trust on first false positive; explicitly excluded from v1 by design |
| LLM-inferred service topology | Hallucinated dependencies produce wrong RCA paths; topology is always algorithmic (Cypher BFS) |
| Cloud infrastructure management (IaC, autoscaling) | Agent operates at app-observability layer only; infra management is a different product |
| Multi-tenant SaaS platform | Strategic decision post-PMF; single-org deployment for v1 |
| Custom observability dashboard | $500K+ existing investments won't be abandoned; agent sits on top of SigNoz, not replaces it |
| Alert suppression without explicit reasoning | Creates blind spots and audit failures in enterprise environments |
| Predictive anomaly flagging | Defer until reactive RCA is trusted by pilot customers |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Complete |
| INFRA-02 | Phase 1 | Complete |
| INFRA-03 | Phase 1 | Complete |
| INFRA-04 | Phase 1 | Pending |
| INFRA-05 | Phase 1 | Pending |
| TOPO-01 | Phase 2 | Pending |
| TOPO-02 | Phase 2 | Pending |
| TOPO-03 | Phase 2 | Pending |
| TELE-01 | Phase 2 | Pending |
| TELE-02 | Phase 2 | Pending |
| TELE-03 | Phase 1 | Pending |
| KNOW-01 | Phase 2 | Pending |
| KNOW-02 | Phase 2 | Pending |
| KNOW-03 | Phase 2 | Pending |
| AGENT-01 | Phase 3 | Pending |
| AGENT-02 | Phase 3 | Pending |
| AGENT-03 | Phase 3 | Pending |
| AGENT-04 | Phase 3 | Pending |
| AGENT-05 | Phase 3 | Pending |
| AGENT-06 | Phase 3 | Pending |
| UI-01 | Phase 4 | Pending |
| UI-02 | Phase 4 | Pending |
| UI-03 | Phase 4 | Pending |
| UI-04 | Phase 4 | Pending |
| CHAOS-01 | Phase 4 | Pending |
| CHAOS-02 | Phase 4 | Pending |
| CHAOS-03 | Phase 4 | Pending |
| CHAOS-04 | Phase 4 | Pending |
| GOLDEN-01 | Phase 5 | Pending |
| GOLDEN-02 | Phase 5 | Pending |
| GOLDEN-03 | Phase 5 | Pending |

**Coverage:**

- v1 requirements: 31 total
- Mapped to phases: 31
- Unmapped: 0 ✓

---
*Requirements defined: 2026-08-05*
*Last updated: 2026-08-05 after initial definition*
