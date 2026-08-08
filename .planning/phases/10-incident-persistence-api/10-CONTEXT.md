# Phase 10 Context: Incident Persistence & API

**Source:** PRD Express Path — `/Users/sanjay/.claude/plans/read-my-requirements-and-fizzy-phoenix.md` (design approved by user 2026-08-08), plus decisions captured during milestone planning.
**Date:** 2026-08-08

## Domain

Every SigNoz alert currently lives and dies as a log line. `src/webhook/app.py` parses it, spawns a `threading.Thread`, streams the LangGraph meta-agent, and prints each node to stdout. Nothing is persisted; nothing is visible. This phase makes the alert a durable, queryable, observable object — and puts a first React list in front of it.

## Locked Decisions

These are decided. Do not re-open, re-derive, or offer alternatives.

### Storage

- **Postgres, not ClickHouse.** Alert status mutates many times per incident; ClickHouse `ALTER TABLE UPDATE` is an async, non-transactional mutation with no real upsert. Postgres gives row updates, a unique index for idempotent delivery, JSONB for the raw payload, LISTEN/NOTIFY for later SSE, and `AsyncPostgresSaver` so Phase 11's agent checkpoints share one database. ClickHouse remains the read-only telemetry source the agent queries.
- **New Postgres service on host port 5433.** SigNoz's own Postgres is unpublished so there is no conflict; 5433 avoids colliding with a developer's local 5432. Register it in `docs/PORTS.md`.
- **psycopg3 (`psycopg[binary,pool]`) is the single driver** for both the application and Phase 11's checkpointer. Do NOT add asyncpg — `langgraph-checkpoint-postgres` requires psycopg3, and two drivers means two pools against one database.
- **Schema applied idempotently at app startup from `src/api/schema.sql`.** The repo has no Alembic, and the existing `system_changes` ClickHouse table has no committed DDL at all. Four tables do not justify adopting a migration tool; they do justify committing the DDL.

### Tables

- `incidents` — one row per firing alert. Carries `id uuid` (doubles as Phase 11's LangGraph `thread_id`), dedupe/fingerprint keys, parsed alertname/service/severity/message, `status`, `current_step`, `fired_at`/`resolved_at`/`created_at`/`updated_at` as **TIMESTAMPTZ**, `labels`/`annotations`/`raw` as JSONB, and result fields (`root_cause_service`, `confidence`, `evidence_refs`, `final_answer`).
- `agent_steps` — the event log the step graph is later built from. `incident_id`, `seq`, `parent_seq`, `kind` (`node`|`tool_call`|`tool_result`|`gate`), `name`, `status`, `input`/`output` JSONB, `started_at`/`ended_at`. `parent_seq` is what makes it a graph: tool calls hang off the node that issued them.
- `approvals` — created in this phase, populated in Phase 11. `incident_id`, `step_seq`, `kind`, `proposal` JSONB, `decision`, `decided_by`, `decided_at`, `note`, `execution_result` JSONB.

### Status lifecycle

```
open → agent_running → awaiting_approval → executing_remediation → done
                    ↘                   ↘ (rejected)            ↘
                      failed              needs_human             failed
```

`status` is the coarse column the list renders. `current_step` carries the live detail (`telemetry_tool`, `verifier`) so the list shows progress without joining `agent_steps`.

### Server layout

- **A new `src/api/` FastAPI app absorbs `POST /webhook/signoz`.** The Starlette app in `src/webhook/app.py` is deleted. This also resolves a standing violation: its docstring says port 8080, which `docs/PORTS.md` marks reserved-unbound.
- **`src/webhook/alert.py` is reused UNTOUCHED.** `AlertContext`, `parse_alerts()`, `SERVICE_LABEL_KEYS` resolution order, and `parse_time()`'s handling of Go RFC3339 nanoseconds and the `0001-01-01` zero-value sentinel are hard-won and already covered by tests. Do not rewrite, refactor, or "improve" this file.
- `message_text()` (currently `src/webhook/app.py:80`) moves to a shared module so the step recorder can use it.
- Webhook contract is preserved: always fast, always 2xx, filters resolved / no-service / duplicate alerts.
- Concurrency moves from `threading.Thread` + `BoundedSemaphore` to `asyncio.create_task` + `asyncio.Semaphore`. Keep the lazy `src.agent.graph` import — it builds an LLM at import time and raises without an API key, which must not kill the receiver at startup.

### Frontend (pulled forward from Phase 12 by user decision)

- **Scope is bounded:** Vite + React + TypeScript scaffold, the incident table (status pill, severity, service, alert name, fired-at), status and severity filters, and a typed API client over `GET /api/incidents`, fed by a **plain refresh**.
- **All live-update plumbing stays in Phase 12** — LISTEN/NOTIFY triggers, the shared listener, in-process fan-out, `EventSource`, the initial-snapshot frame. Do not build SSE in this phase.
- Dev server on **5173**. Port 3000 is taken by Memgraph Lab — do not use the CRA/Next default.
- Pins (verified live against npm): Vite 8.2.1, React 19.2.8, `typescript@^5.9.3`. **NOT `typescript@latest`** — that resolves to 7.0.2, which `typescript-eslint` rejects.

## Claude's Discretion

- Exact module split inside `src/api/` (the design sketches `main.py`, `db.py`, `repository.py`, `schema.sql`, `runner.py`, `steps.py`, `routes/`, `settings.py` — treat as a strong suggestion, not a contract).
- Whether the API port is 8088 or another free, ledger-registered port.
- Pydantic response model shapes and the REST payload contract.
- React component decomposition, styling approach, and state management.
- How `schema.sql` is applied (single file vs. per-table statements) as long as it is idempotent.

## Specifics

- **Every query parameterized.** This is non-negotiable and is the convention later phases inherit. The repo has a demonstrated habit to break with: `src/production/db.py::_insert_ch` f-string-builds a **Python source string** and runs it via `subprocess.run([sys.executable, "-c", code])` — arbitrary code execution, not merely SQL injection — and `src/production/mcp_server.py` interpolates service names straight into ClickHouse WHERE clauses. The webhook payload is upstream-controlled text. No f-string or `.format()`-built SQL anywhere in `src/api/`.
- **Dedupe is a database constraint, not process memory.** Partial unique index on the dedupe key where status is not terminal, with `INSERT ... ON CONFLICT ... RETURNING` as the atomic "already existed" signal. This replaces the `_recent` dict + `threading.Lock` at `src/webhook/app.py:58`, which cannot survive a restart and races between two concurrent deliveries of the same fingerprint.
- **Timestamps are TIMESTAMPTZ, fed only from already-parsed `AlertContext` fields** — never re-parsed from raw JSONB. `parse_time()` already handles the nanosecond truncation and zero-value sentinel correctly; reading raw JSONB would regress that.
- **`AsyncPostgresSaver.setup()` must be called explicitly** at lifespan startup, idempotently. It does not run automatically. If a connection is built manually rather than via the pool, it needs `autocommit=True, row_factory=dict_row` or the DDL silently fails to commit. A fresh empty-DB `docker compose up` must succeed with zero manual steps. (Creating the checkpointer tables here means Phase 11 has them ready.)
- **Background tasks must be strongly referenced** — a bare `asyncio.create_task` can be garbage-collected mid-run. Exceptions must be logged, not silently swallowed.
- `tests/test_webhook.py` (18 tests) is repointed at the FastAPI app. Starlette's `TestClient` is FastAPI's, so most test bodies stand. The `dispatched` fixture that clears the module-level `_recent` dict is replaced by per-test DB truncation.

## Deferred

- SSE, LISTEN/NOTIFY, live updates → Phase 12 (UI-02, UI-09)
- Detail panel, tabs, step graph → Phase 12
- `interrupt()`, checkpointer *usage*, approval gates, remediation executor → Phase 11 (this phase only creates the `approvals` table and calls `.setup()`)
- Orphaned-run detection on startup → Phase 11 (INC-07)
- Streamlit removal → Phase 12 (RET-02)
- Replay script → Phase 12 (OPS-01..03)

## Scope Fence

**In scope:** Postgres service + schema, psycopg3 pool, `src/api/` FastAPI app, webhook absorption, step recording, REST read endpoints, the React scaffold with list + filters, retiring `src/webhook/app.py`, port-ledger and `.env.example` updates.

**Out of scope — do not touch:**
- `src/webhook/alert.py` — reused verbatim
- `src/agent/graph.py` — Phase 11 modifies it; this phase must not
- `src/production/` — its unsafe SQL is real but is not this milestone's code
- `src/ui/app.py` — Streamlit dies in Phase 12, not here
- `tests/test_signoz_plugin.py` — known pre-existing failure from a stale fixture; leave it

## Success Criteria

1. Posting a SigNoz alert to the new API creates exactly one incident row with the verbatim payload plus parsed fields.
2. The same fingerprint fired twice concurrently, and again after a process restart, still yields exactly one incident — enforced by the database.
3. Resolved alerts and alerts with no resolvable service label are recorded as skipped and never start an agent run.
4. Status and current-step update as the agent runs; every node entry and tool call appears as an ordered step row attributed to its issuing node.
5. The webhook is served only on the new ledger-registered port, the Starlette receiver is gone, and legacy-shaped payloads parse exactly as before.
6. Opening the dashboard shows real incidents with status, severity, service, alert name, and fired-at, filterable by status and severity; posting an alert and refreshing shows it appear.

## Risk Summary

- Rewriting `alert.py` while deleting the app next to it would regress subtle timestamp handling — hence the explicit fence.
- Adopting asyncpg for the app would strand Phase 11's checkpointer on a second pool.
- A non-idempotent `schema.sql` breaks the zero-manual-steps startup requirement.
- Pulling the frontend forward risks scope creep into SSE; the boundary is stated above.
