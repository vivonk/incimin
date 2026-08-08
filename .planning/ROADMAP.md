# Roadmap: incimin.io — AI SRE Agent

## Milestones

- ✅ **v1.5 Milestone** — Phases 1-5 (shipped 2026-08-06)
- ✅ **v1.6 Plugin-based Service Topology** — Phases 07-09 (shipped 2026-08-07)
- 🚧 **v1.7 Incident Dashboard** — Phases 10-12 (in progress)

## Phases

<details>
<summary>✅ v1.5 Milestone (Phases 1-5) — SHIPPED 2026-08-06</summary>

- [x] Phase 1: Infrastructure Foundation (4/4 plans) — completed 2026-08-05
- [x] Phase 2: Data Plane Initialization (4/4 plans) — completed 2026-08-06
- [x] Phase 3: Agent Core (1/1 plans) — completed 2026-08-06
- [x] Phase 4: UI Integration & Demo Choreography (1/1 plans) — completed 2026-08-06
- [x] Phase 5: Golden Path Validation (1/1 plans) — completed 2026-08-06

</details>

<details>
<summary>✅ v1.6 Plugin-based Service Topology (Phases 07-09) — SHIPPED 2026-08-07</summary>

- [x] Phase 07: Core Models and DB Integration (1/1 plans) — completed 2026-08-06
- [x] Phase 08: Core Abstraction Layer and Plugin Registry (1/1 plans) — completed 2026-08-06
- [x] Phase 09: SigNoz Plugin MVP Implementation (1/1 plans) — completed 2026-08-07

</details>

### 🚧 v1.7 Incident Dashboard (In Progress)

**Milestone Goal:** Give every SigNoz alert a durable, observable lifecycle — persisted, tracked live in a web dashboard, and pausable for human approval.

- [ ] **Phase 10: Incident Persistence & API** - Postgres schema, psycopg3, and a new FastAPI app absorb the webhook and record every agent step, with a first React alert list rendering real rows
- [ ] **Phase 11: Agent HITL Gates** - The agent gains a durable checkpointer and pauses for human approval before remediation and escalation
- [ ] **Phase 12: Dashboard SPA & Replay Script** - A React SPA renders live incidents and a dynamic step graph over SSE; a replay script drives the whole path offline

## Phase Details

### Phase 10: Incident Persistence & API
**Goal**: Every SigNoz alert becomes a durable, deduplicated incident row in Postgres, served by a new async FastAPI app that absorbs the retired Starlette webhook — with every agent node entry and tool call recorded as an ordered, attributed step, and a first React alert list rendering those rows so the foundation is visible, not just testable.
**Depends on**: Phase 09 (existing agent core, topology, and telemetry planes)
**Requirements**: INC-01, INC-02, INC-03, INC-04, INC-05, INC-06, UI-01, UI-03, RET-01, RET-03
**Success Criteria** (what must be TRUE):
  1. Posting a SigNoz alert payload to the new API's webhook endpoint creates exactly one incident row containing the verbatim payload plus parsed alertname, service, severity, message, and fired-at time.
  2. Firing the same alert fingerprint twice concurrently, and again after the API process restarts, still results in exactly one incident row each time — because the database enforces it, not process memory.
  3. A resolved alert, or one with no resolvable service label, is recorded as skipped and never triggers an agent run.
  4. An in-progress incident's status and current-step field update as the agent runs, and every node entry and tool call the agent makes appears as its own ordered step row, attributed to the node that issued it.
  5. The webhook is reachable only on the new API's port-ledger-registered port; the old Starlette receiver is gone; and posting legacy-shaped payloads (Go RFC3339-nanosecond timestamps, the zero-time sentinel, existing label resolution order) still parses exactly as before.
  6. Opening the dashboard in a browser shows every incident in a list with its status, severity, service, alert name, and fired-at time, filterable by status and by severity — real rows from Postgres, refreshed on demand. Posting an alert and refreshing shows it appear.
**Notes** (verified, not speculative — carry forward into planning):
  - `psycopg3` is the single DB driver for both the app and the checkpointer Phase 11 will add — do not introduce `asyncpg`. Set this convention here; every later phase writes through this layer.
  - `AsyncPostgresSaver.setup()` must be called explicitly (idempotently, at FastAPI lifespan startup) — it does not run automatically. If connections to run it are built manually rather than via the pool, they need `autocommit=True, row_factory=dict_row` or the DDL silently fails to commit. A fresh empty-DB `docker compose up` must succeed with zero manual steps.
  - Alert dedupe is a Postgres unique/partial-unique index on `fingerprint` with `INSERT ... ON CONFLICT ... RETURNING` — the atomic "already existed" signal. No f-string/`.format()`-built SQL anywhere in this layer; the raw webhook payload is upstream-controlled text and must go through parameterized queries and JSONB bound params only. This is the convention every later phase inherits.
  - **UI-01/UI-03 were pulled forward from Phase 12 by user decision** so the foundation is visible two phases earlier. Scope is deliberately bounded: the Vite + React + TypeScript scaffold, the incident table, status/severity filters, and a typed API client over `GET /api/incidents` — fed by a plain refresh, NOT by SSE. All live-update plumbing (LISTEN/NOTIFY, the shared listener, in-process fan-out, `EventSource`, the initial-snapshot frame) stays in Phase 12 under UI-02/UI-09. Only the fetch mechanism is later replaced; the table, pills, types, and client all survive.
  - Frontend pins (verified live): Vite 8.2.1, React 19.2.8, TypeScript **`^5.9.3` — NOT `latest`**, which resolves to 7.0.2 and is rejected by `typescript-eslint`'s peer range. Proving this toolchain here de-risks Phase 12 rather than discovering it at the end.
**Plans**: TBD

### Phase 11: Agent HITL Gates
**Goal**: The agent pauses for human approval before remediation and before escalation — durably, so the pause survives an API process restart and resumes the same run rather than starting over, and an orphaned run is recoverable from the UI.
**Depends on**: Phase 10 (Postgres schema and checkpointer tables must exist first)
**Requirements**: HITL-01, HITL-02, HITL-03, HITL-04, HITL-05, HITL-06, HITL-07, INC-07
**Success Criteria** (what must be TRUE):
  1. Before executing any remediation, the agent halts and records exactly what it proposes to do and why — nothing executes until a human decides.
  2. A human's Approve or Reject decision is reflected in the incident's state; an approved remediation executes only a fixed, pre-approved action assembled without an LLM-composed command — and submitting or replaying the same decision twice, even concurrently, still results in exactly one execution.
  3. Before escalating an incident it cannot resolve, the agent pauses for human sign-off the same way, rather than escalating on its own.
  4. Every approval — remediation or escalation — leaves a durable record of who decided, when, the outcome, and the execution result.
  5. A pause survives an API process restart: approving after a restart resumes the same run rather than starting over, and a run interrupted mid-execution by a crash is marked orphaned on startup and can be resumed by a human from the dashboard.
**Notes** (verified, not speculative — carry forward into planning):
  - `astream_events(version="v3")` is UNUSABLE at the pinned langgraph 1.2.10 — `_astream_events_v3_unsupported` exists on the compiled graph class. Use `v2`, or the `.ainvoke()` + `result["__interrupt__"]` / `Command(resume=...)` pattern.
  - `interrupt()` replays the ENTIRE node from its start on resume, not from where it paused. Side effects (audit writes, the executor call) must come strictly after the `interrupt()` call, gated on the resume value — never before it, or they fire twice on every resume.
  - Remediation execution needs an atomic claim: `UPDATE approvals SET status='executing' WHERE id=$1 AND status='pending' RETURNING *`. Zero rows returned means someone already claimed it — abort. A `SELECT` then `UPDATE` is exactly the TOCTOU/replay gap this closes. Bind the executed argv to the approval row at proposal time; never re-derive it from live state at execution time.
  - Spike gate before building on top of this: prove the checkpointer/`interrupt()`/`Command(resume=...)` round-trip against `graph.py` directly, with no FastAPI in the loop, before the resume-via-HTTP-endpoint architecture is built on the assumption that it works. Research flags this as the milestone's single highest-risk unknown.
**Plans**: TBD

### Phase 12: Dashboard SPA & Replay Script
**Goal**: An operator watches an incident's full lifecycle live in a React dashboard — list, filters, a click-through detail panel, and a step graph that grows in real time from actual agent events — and the entire path is exercisable offline through a single replay command.
**Depends on**: Phase 10 (the incident/step row shape must be fixed, and this phase extends Phase 10's React scaffold and typed API client rather than starting a new frontend); step-graph rendering additionally needs validation against Phase 11's real event shapes (loop iterations, retries, dead ends) before being considered done, though initial SSE plumbing can be built in parallel with Phase 11 against synthetic rows.
**Requirements**: UI-02, UI-04, UI-05, UI-06, UI-07, UI-08, UI-09, OPS-01, OPS-02, OPS-03, RET-02
**Success Criteria** (what must be TRUE):
  1. The incident list built in Phase 10 now updates live as incidents are created and change status, with no manual refresh — its refresh-driven fetch replaced by a live connection, with the table, filters, and typed client carried over unchanged rather than rebuilt.
  2. Clicking an incident opens a detail panel with a Findings tab (root cause, confidence, evidence, verifier outcome), a Next Steps tab (a pending proposal with Approve/Reject controls, then the recorded decision and execution result), and a Raw tab (the verbatim SigNoz payload as received).
  3. A Step Graph tab renders the agent's steps as a graph that grows live — showing which tools actually ran, repeated loop iterations, and which exit path was taken — driven by real agent events, not a static diagram.
  4. A user opening the dashboard mid-incident sees current state immediately, with no events lost between page load and the live connection opening.
  5. A single command replays a committed SigNoz alert fixture through the full path, requiring no live SigNoz, printing each step as it happens, and can drive an approval gate to either outcome without manual UI interaction.
  6. Streamlit is gone from the codebase — no Streamlit entry point, import, or dependency remains.
**Notes** (verified, not speculative — carry forward into planning):
  - The step graph is DYNAMIC, derived from real agent events (loop iterations, retries, dead ends, actual exit path) — this is a settled user decision. Do not propose a static diagram with a status overlay.
  - SSE fan-out needs exactly ONE process-wide, shared `LISTEN` connection fanning out in-process (e.g. per-client `asyncio.Queue`s) — a `LISTEN` connection per SSE client exhausts the pool under normal multi-tab usage. `NOTIFY` has no backlog: the server must push a full snapshot as the first SSE frame on connect (or use sequence numbers + `Last-Event-ID` backfill) — never snapshot-then-subscribe on the client, or events in that gap are silently dropped.
  - React Flow node ids must be derived deterministically from a stable identity in the agent event (not array index or a freshly generated id each render), since loop iterations and retries mean the same logical node can recur multiple times — decide the id-derivation scheme before wiring live SSE into the graph. Only run auto-layout for genuinely new nodes; re-laying-out the whole graph on every event causes visible reflow.
**UI hint**: yes
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 10 → 11 → 12

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Infrastructure Foundation | v1.5 | 4/4 | Complete | 2026-08-05 |
| 2. Data Plane Initialization | v1.5 | 4/4 | Complete | 2026-08-06 |
| 3. Agent Core | v1.5 | 1/1 | Complete | 2026-08-06 |
| 4. UI Integration & Demo Choreography | v1.5 | 1/1 | Complete | 2026-08-06 |
| 5. Golden Path Validation | v1.5 | 1/1 | Complete | 2026-08-06 |
| 6. Production Data Planes | v1.5 | 1/1 | Complete | 2026-08-06 |
| 07. Core Models and DB Integration | v1.6 | 1/1 | Complete | 2026-08-06 |
| 08. Core Abstraction Layer and Plugin Registry | v1.6 | 1/1 | Complete | 2026-08-06 |
| 09. SigNoz Plugin MVP Implementation | v1.6 | 1/1 | Complete | 2026-08-07 |
| 10. Incident Persistence & API | v1.7 | 0/TBD | Not started | - |
| 11. Agent HITL Gates | v1.7 | 0/TBD | Not started | - |
| 12. Dashboard SPA & Replay Script | v1.7 | 0/TBD | Not started | - |
