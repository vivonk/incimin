# Roadmap: incimin.io — AI SRE Agent

## Overview

Five phases gate-on-gate from infrastructure readiness to a live demo. Phase 1 locks the Docker Compose stack before any code is written. Phase 2 seeds all three data planes in parallel tracks. Phase 3 assembles the LangGraph agent against live data. Phase 4 connects the Streamlit UI and chaos injection scripts. Phase 5 runs the full golden path and closes every known pitfall before demo day.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Infrastructure Foundation** - Full Docker Compose stack verified, telemetry flowing, no port conflicts
- [ ] **Phase 2: Data Plane Initialization** - All three data planes seeded and smoke-tested (3 parallel tracks)
- [x] **Phase 3: Agent Core** - LangGraph state machine assembled, guarded, and unit-tested (completed 2026-08-06)
- [ ] **Phase 4: UI Integration & Demo Choreography** - Streamlit chat UI and chaos injection scripts validated
- [ ] **Phase 5: Golden Path Validation** - Full demo scenario runs end-to-end under 60 seconds

## Phase Details

### Phase 1: Infrastructure Foundation

**Goal**: Full Docker Compose stack is running and verified before any feature work begins — port conflicts resolved, telemetry flowing to SigNoz, Memgraph persisting data, memory within budget
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05, TELE-03
**Success Criteria** (what must be TRUE):

  1. `docker compose up` starts all services with zero port conflicts (`docker ps` port audit clean — SigNoz UI on 3301, OTel frontend-proxy on 8090)
  2. SigNoz Services page shows all 14 OTel Astronomy Shop services actively emitting telemetry (traces, logs, metrics)
  3. Memgraph container is reachable and data persists across `docker compose restart memgraph` (named volume confirmed)
  4. `docker stats` baseline shows no OOM kills and host memory stays within 14GB Docker Desktop allocation
  5. ClickHouse table name for SigNoz v0.135.1 logs is confirmed (`distributed_logs` vs `distributed_logs_v2` ambiguity resolved via `SHOW TABLES`)

**Note on criterion 2**: OTel demo runs in *minimal* mode (D-07, required by the 14GB budget), which drops Kafka and its dependent services. The true service count is below 14. Plan 01-03 records the actual minimal-mode service list in `docs/OTEL_DEMO_SERVICES.md`; that file supersedes the "all 14" wording here. The three golden-path services (payment, checkout, frontend) must all be present.

**Plans**: 4 plans in 4 waves

Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Repo scaffold, canonical port ledger, Memgraph MAGE + Lab + Qdrant online with proven restart persistence

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — SigNoz + ClickHouse deployed via foundryctl, ClickHouse schema ambiguity resolved, OTLP ingress smoke-tested

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — OTel Astronomy Shop minimal mode on 8090, telemetry routed to SigNoz via pipeline-complete collector overlay, project-wide port audit

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-04-PLAN.md — Single-command verification gate across all three planes, measured memory baseline, cold-start reproducibility

### Phase 2: Data Plane Initialization

**Goal**: All three data planes independently seeded, verified, and query-ready for agent integration
**Mode:** mvp
**Depends on**: Phase 1
**Parallel tracks** (run simultaneously across 2-3 engineers):

  - Track A — Topology (Memgraph): TOPO-01, TOPO-02, TOPO-03
  - Track B — Telemetry (ClickHouse): TELE-01, TELE-02
  - Track C — Knowledge (Qdrant): KNOW-01, KNOW-02, KNOW-03

**Requirements**: TOPO-01, TOPO-02, TOPO-03, TELE-01, TELE-02, KNOW-01, KNOW-02, KNOW-03
**Success Criteria** (what must be TRUE):

  1. Memgraph contains all 14 OTel Astronomy Shop service nodes and dependency edges; a BFS traversal using `[*BFS]` Cypher syntax returns the correct dependency path from checkoutservice to paymentservice
  2. Topology survives `docker compose restart memgraph` with all 14 nodes and edges intact (MERGE idempotency confirmed)
  3. ClickHouse log query tool returns ERROR-level logs and trace IDs for paymentservice within a specified time window using nanosecond timestamps
  4. Qdrant `runbooks` collection returns the correct playbook for a given incident description via semantic similarity search (fastembed BAAI/bge-small-en-v1.5, 384-dim verified)

**Plans**: 3/4 plans executed

Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Memgraph Topology Seed & Verify
- [x] 02-02-PLAN.md — ClickHouse Telemetry Query & Verify
- [x] 02-03-PLAN.md — Qdrant Knowledge Seed & Verify

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-04-PLAN.md — Data Plane Verification Gate

### Phase 3: Agent Core

**Goal**: LangGraph state machine with three isolated, tested tools is assembled and guarded against recursion failures
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: AGENT-01, AGENT-02, AGENT-03, AGENT-04, AGENT-05, AGENT-06
**Success Criteria** (what must be TRUE):

  1. `SREAgentState` TypedDict with `add_messages` reducer compiles and the StateGraph runs end-to-end against live data without hitting recursion limit
  2. Each of the three `@tool` functions executes in isolation and touches exactly one data plane — no cross-plane access
  3. `RemainingSteps` guard routes to a "insufficient data" graceful response (not a Python traceback) when `remaining_steps <= 2`
  4. All three tools pass unit tests with mock clients for both happy path output format and error handling

**Plans**: TBD

### Phase 4: UI Integration & Demo Choreography [Completed]

**Goal**: Streamlit chat UI delivers real-time glass-box agent output and chaos injection scripts are deterministic and rehearsed
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: UI-01, UI-02, UI-03, UI-04, CHAOS-01, CHAOS-02, CHAOS-03, CHAOS-04
**Success Criteria** (what must be TRUE):

  1. Streamlit chat UI renders `st.status` expanders for each tool call in real time with no async event loop errors across 3+ consecutive queries
  2. Chat history persists within a session so a follow-up query has access to prior conversation context
  3. `chaos_inject.py --mode stop` triggers paymentservice ERROR logs visible in SigNoz within 30 seconds; `--recover` restores normal state; both modes are idempotent
  4. Memgraph Lab BFS query is scripted, rehearsed, and executable by the demo operator during the agent's graph traversal step

**Plans**: 1/1 plans executed

- [x] 04-PLAN.md

**UI hint**: yes

### Phase 5: Golden Path Validation

**Goal**: The full demo scenario runs end-to-end, deterministically, within the 60-second SLA, with all known pitfalls verified closed
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: GOLDEN-01, GOLDEN-02, GOLDEN-03
**Success Criteria** (what must be TRUE):

  1. The prompt "Checkout latency is spiking. Investigate and give me a recommendation." produces: root cause identifying paymentservice, a retrieved runbook, and a recommendation — all within 60 seconds wall clock
  2. All PITFALLS.md checklist items are verified closed (port collisions, Memgraph persistence, nanosecond timestamps, recursion guard, async event loop, BFS syntax, RAM baseline)
  3. Split-screen demo is rehearsed: Streamlit chat (right) + Memgraph Lab showing topology with the BFS query ready to execute (left)

**Plans**: 1/1 plans executed

- [x] 05-PLAN.md

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Infrastructure Foundation | 4/4 | Complete | 2026-08-05 |
| 2. Data Plane Initialization | 3/4 | In Progress|  |
| 3. Agent Core | 1/1 | Complete    | 2026-08-06 |
| 4. UI Integration & Demo Choreography | 1/1 | Complete    | 2026-08-06 |
| 5. Golden Path Validation | 1/1 | In Progress|  |
