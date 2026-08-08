# Requirements: incimin.io — v1.7 Incident Dashboard

**Defined:** 2026-08-08
**Core Value:** When an incident fires, the agent autonomously traverses the live service graph and queries correlated telemetry — delivering root cause and recommended remediation steps before any human has opened a dashboard.

**Milestone goal:** Give every SigNoz alert a durable, observable lifecycle — persisted, tracked live in a web dashboard, and pausable for human approval.

## v1.7 Requirements

### Incident Persistence (INC)

- [ ] **INC-01**: An incoming SigNoz alert is stored as an incident row carrying its verbatim payload plus extracted alertname, service, severity, message, and fired-at time
- [ ] **INC-02**: A repeat delivery of an already-open alert is suppressed by the database, not by process memory, so suppression survives a restart
- [ ] **INC-03**: Two concurrent deliveries of the same alert fingerprint result in exactly one incident
- [ ] **INC-04**: A resolved alert, or one with no resolvable service label, is recorded as skipped rather than starting an agent run
- [ ] **INC-05**: Every incident carries a status reflecting its lifecycle stage, and a current-step field naming what the agent is doing right now
- [ ] **INC-06**: Each agent node entry and tool call is recorded as an ordered step row, with tool calls attributed to the node that issued them
- [ ] **INC-07**: An incident left mid-run by a process crash is marked as orphaned on startup and can be resumed by a human from the UI

### Agent Approval Gates (HITL)

- [ ] **HITL-01**: The agent pauses before any remediation and records what it proposes to do and why
- [ ] **HITL-02**: A human can approve or reject a proposed remediation, and the incident reflects that decision
- [ ] **HITL-03**: An approved remediation executes only an action drawn from a fixed allowlist, never a command composed by the LLM
- [ ] **HITL-04**: A remediation cannot be executed twice, even if approval is submitted concurrently or replayed
- [ ] **HITL-05**: The agent pauses for human sign-off before escalating an incident it cannot resolve
- [ ] **HITL-06**: Every approval records who decided, when, the outcome, and the execution result
- [ ] **HITL-07**: A pause survives an API process restart — approving after a restart resumes the same run rather than starting over

### Dashboard (UI)

- [ ] **UI-01**: A user sees all incidents in a list showing status, severity, service, alert name, and when it fired
- [ ] **UI-02**: The list updates live as incidents are created and as their status changes, without a manual refresh
- [ ] **UI-03**: A user can filter the list by status and by severity
- [ ] **UI-04**: Clicking an incident opens a detail panel below it
- [ ] **UI-05**: A Findings tab shows the agent's root cause, confidence, supporting evidence, and verifier outcome
- [ ] **UI-06**: A Next Steps tab shows a pending proposal with Approve and Reject controls, and afterwards the recorded decision and execution result
- [ ] **UI-07**: A Step Graph tab renders the agent's steps as a graph that grows live, showing which tools actually ran, repeated loop iterations, and which exit path was taken
- [ ] **UI-08**: A Raw tab shows the verbatim SigNoz payload as received
- [ ] **UI-09**: A user opening the dashboard mid-incident sees current state immediately, with no events lost between page load and the live connection opening

### Replay & Verification (OPS)

- [ ] **OPS-01**: A single command replays a committed SigNoz alert fixture through the full path and prints each step as it happens
- [ ] **OPS-02**: The replay script can drive an approval gate to either outcome without manual UI interaction
- [ ] **OPS-03**: The replay runs deterministically offline, requiring no live SigNoz

### Retirements (RET)

- [ ] **RET-01**: The alert webhook is served by the new API on a port registered in the port ledger, and the retired Starlette receiver is gone
- [ ] **RET-02**: Streamlit is removed from the codebase and its dependency dropped
- [ ] **RET-03**: Existing webhook parsing behavior is preserved — label resolution order, Go RFC3339-nanosecond timestamps, and the zero-time sentinel all still work

## Future Requirements

Deferred — tracked, not in this roadmap.

### Dashboard

- **UI-F01**: Incident timeline tab — a human-readable chronological event log per incident. Research classes this a table stake; the underlying data is already persisted by INC-06 and HITL-06, so this is a rendering task whenever it is wanted.
- **UI-F02**: Free-text search across service and alert name
- **UI-F03**: Manual status override — force an incident to done or needs-human regardless of agent state

### Integration

- **INT-F01**: Provision the SigNoz alert rule and webhook notification channel as committed config, closing the SigNoz→webhook loop
- **INT-F02**: Capture a genuine live SigNoz payload as the replay fixture — blocked on the API token, which authenticates but resolves to user `00000000-…` and 403s every data endpoint

## Out of Scope

| Feature | Reason |
|---------|--------|
| Unattended remediation | The agent never acts without a human clicking Approve. Execution is permitted only from a fixed allowlist behind that gate. |
| Remediation actions beyond the allowlist | Blast radius. The allowlist is the security boundary; widening it is a separate, deliberate decision. |
| Multi-approver quorum | Single-org, demo-scale. Research confirms this is over-engineering here. |
| Alert grouping / correlation engine | One alert, one incident. Grouping solves a volume problem this system doesn't have. |
| On-call paging, escalation policies, notifications | This dashboard replaces L1 triage; it is not a paging platform. |
| Graph authoring / editing UI | The step graph is read-only. Topology is defined in code. |
| Checkpoint fork / time-travel debugging | LangGraph supports it; nothing in this milestone needs it. |
| Auth / multi-tenancy | Loopback-only local stack per project constraints. |
| WebSocket fallback for SSE | Docker Compose local runtime; no hostile proxies in the path. |
| Fixing the pre-existing unsafe SQL in `src/production/` | Real and serious (`db.py::_insert_ch` executes an f-string-built Python source string via subprocess), but it is not this milestone's code. The new Postgres layer must not repeat it. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INC-01 | Phase 10 | Pending |
| INC-02 | Phase 10 | Pending |
| INC-03 | Phase 10 | Pending |
| INC-04 | Phase 10 | Pending |
| INC-05 | Phase 10 | Pending |
| INC-06 | Phase 10 | Pending |
| INC-07 | Phase 11 | Pending |
| HITL-01 | Phase 11 | Pending |
| HITL-02 | Phase 11 | Pending |
| HITL-03 | Phase 11 | Pending |
| HITL-04 | Phase 11 | Pending |
| HITL-05 | Phase 11 | Pending |
| HITL-06 | Phase 11 | Pending |
| HITL-07 | Phase 11 | Pending |
| UI-01 | Phase 10 | Pending |
| UI-02 | Phase 12 | Pending |
| UI-03 | Phase 10 | Pending |
| UI-04 | Phase 12 | Pending |
| UI-05 | Phase 12 | Pending |
| UI-06 | Phase 12 | Pending |
| UI-07 | Phase 12 | Pending |
| UI-08 | Phase 12 | Pending |
| UI-09 | Phase 12 | Pending |
| OPS-01 | Phase 12 | Pending |
| OPS-02 | Phase 12 | Pending |
| OPS-03 | Phase 12 | Pending |
| RET-01 | Phase 10 | Pending |
| RET-02 | Phase 12 | Pending |
| RET-03 | Phase 10 | Pending |
