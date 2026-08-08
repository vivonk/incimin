# Project Research Summary

**Project:** incimin.io — AI SRE Agent
**Milestone:** v1.7 "Incident Dashboard"
**Domain:** Durable human-in-the-loop agent orchestration + real-time incident dashboard (FastAPI/Postgres backend, React SPA frontend)
**Researched:** 2026-08-08
**Confidence:** HIGH

## Executive Summary

v1.7 converts the existing stateless, fire-and-forget LangGraph agent into a durable, observable, human-gated system. Three structural changes drive everything else: (1) the graph gains a Postgres-backed checkpointer (`AsyncPostgresSaver`) and a new `await_approval` node that calls `interrupt()`, making pauses survive process restarts; (2) the Starlette webhook's `threading.Thread` fire-and-forget model is retired in favor of an async FastAPI app with tracked `asyncio.Task`s, a Postgres-backed `incident_events` audit log, and Postgres `LISTEN/NOTIFY` fanned out in-process to Server-Sent Events; (3) a new Vite/React SPA renders alert lists, an approval gate, and a **dynamic** step graph driven by real agent events (loop iterations, retries, dead ends, exit paths — not a static diagram with a status overlay, per explicit user scope decision).

The recommended approach is conservative and reuses proven mechanisms already present in the codebase: `interrupt()`/`Command(resume=...)` is the correct, currently-supported LangGraph 1.2.10 HITL primitive (confirmed against installed package internals, not just docs); the existing `trace_config()` merge-into-`callbacks` pattern is the extension point for a new `DBStepLogger` callback handler that runs alongside the current Langfuse handler; and Postgres `ON CONFLICT ... RETURNING` atomic upserts replace both the in-memory alert-dedupe dict and any check-then-act approval consumption. All new dependencies (`psycopg[binary,pool]`, `langgraph-checkpoint-postgres`, `sse-starlette`, the Vite/React/`@xyflow/react` frontend stack) are verified compatible with existing pins (numpy<2.0, langgraph 1.2.10, starlette<1.4.0) — no forced version bumps.

The dominant risks are not "will the library work" but "will the concurrency and replay semantics be respected": LangGraph re-runs the entire interrupted node on resume (side effects before `interrupt()` fire twice), Postgres `LISTEN` is connection-scoped so per-SSE-client connections will exhaust the pool, `NOTIFY` has no backlog so a naive snapshot-then-subscribe ordering silently drops events, and a bare `asyncio.create_task()` can be garbage-collected mid-run. Each of these has a well-documented, cheap-to-adopt prevention pattern (documented per-phase below) — the risk is skipping them under sprint time pressure, not that they're hard to fix once known. A second-order risk, orthogonal to the above, is the repo's own established habit of building SQL/Cypher via f-string interpolation (`src/production/db.py`) — this must not propagate into the new Postgres DAO layer, which will carry upstream-controlled alert text directly into queries.

## Key Findings

### Recommended Stack

Backend additions are minimal and driver-consistent: `psycopg[binary,pool]` (psycopg3, async-native) is required by `langgraph-checkpoint-postgres` and doubles as the app's own Postgres driver — deliberately avoiding a second driver/pool (e.g. asyncpg) against the same database. `AsyncPostgresSaver.setup()` must be called explicitly (idempotently, at FastAPI lifespan startup) to create checkpoint tables — it is not automatic. `sse-starlette` provides SSE framing/keepalive/disconnect-detection that a bare `StreamingResponse` would require hand-rolling. Frontend is a clean addition: Vite 8 + React 19 + TypeScript pinned to `^5.9.3` (NOT `latest`, which resolves to the incompatible Go-native TS 7.0.2 rejected by `typescript-eslint`'s peer range), plus `@xyflow/react` for the step graph with `@dagrejs/dagre` (not the unmaintained plain `dagre`) for layout.

**Core technologies:**
- `psycopg[binary,pool]` (3.2+): async Postgres driver + pool — shared by app code and `langgraph-checkpoint-postgres`, avoiding a second connection pool
- `langgraph-checkpoint-postgres` (3.1.x): activates the already-declared-but-unused `langgraph-checkpoint>=4.1.0,<5` pin; provides `AsyncPostgresSaver`
- `sse-starlette` (3.x): SSE response helper — framing, keepalive, disconnect detection, zero new transitive dependency surface
- `@xyflow/react` + `@dagrejs/dagre`: dynamic step-graph rendering with auto-layout for new nodes
- Vite + React 19 + TypeScript `^5.9.3`: SPA toolchain

### Expected Features

**Must have (table stakes):** alert list with status/severity/service/timestamps, filterable/sortable; per-alert detail view (Findings/Next Steps/Step Graph/Raw tabs); an explicit "agent is running" in-progress state; chronological audit/event timeline per alert; approval gate showing proposed action + rationale before a human can act; post-decision audit record (who/when/outcome); step-by-step agent visualization with per-node status.

**Should have (differentiators):** a first-class "Awaiting Approval" status in the alert lifecycle (no PagerDuty/incident.io analog — this project's core novelty, an agent that pauses itself); a **live, SSE-driven, dynamic** step graph tied to the actual running agent — **decided scope**: this renders real agent events including loop iterations, which tools ran, retries, dead ends, and the actual exit path taken, not a static diagram with a status overlay (this overrides FEATURES.md's original "read-only overlay on a static diagram" recommendation, per explicit user decision); inline agent-authored root-cause narrative surfaced at the exact approval decision point; deterministic replay of a full historical run against a committed SigNoz fixture.

**Defer (v2+):** alert grouping/deduplication (one alert = one agent run at this scale); on-call scheduling/paging; multi-approver quorum; full postmortem-authoring tooling; checkpoint-fork/time-travel debugging UI; configurable status lifecycle. **Explicitly out of scope entirely, not just deferred:** any graph-authoring/editing UI — the step graph is dynamic in *what it shows* but remains strictly read-only in *interaction*; visual editing of the LangGraph topology would reintroduce the non-determinism PROJECT.md forbids.

### Architecture Approach

The system splits into an unchanged agent core (Memgraph/SigNoz/Qdrant/Langfuse tool calls) and three new layers wrapped around it: a Postgres persistence layer (checkpoints + `incident_events` audit table, both durable across restarts), an async FastAPI app (replacing the Starlette webhook) that drives the graph via `.ainvoke()`, tracks background tasks, and exposes SSE, and a React SPA consuming that SSE stream plus a resume/approve endpoint. The key insight from reading the actual code: `workflow.compile()` currently takes no `checkpointer` argument, and `src/webhook/app.py` drives the graph synchronously inside a daemon thread with no persistence — both of these are the concrete things that must change, not abstractions to design from scratch.

**Major components:**
1. FastAPI app — webhook intake, SSE fan-out, resume/approve endpoint, static SPA serving (replaces `src/webhook/app.py`)
2. Agent run task (tracked `asyncio.Task`) — drives `graph.ainvoke()` per incident to completion or `interrupt()` pause
3. `AsyncPostgresSaver` checkpointer — persists graph state across the pause, keyed by `thread_id` = alert dedupe key
4. `DBStepLogger` (`BaseCallbackHandler`) — writes one row per node/tool start/end into `incident_events`, appended into `config["callbacks"]` alongside the existing Langfuse handler via `trace_config()`'s merge behavior (no changes needed there)
5. Single NOTIFY listener task + in-process pub/sub — decouples SSE client count from Postgres connection count (O(1) DB connections regardless of open dashboard tabs)
6. Vite/React SPA — alert list, detail tabs, dynamic step graph (`@xyflow/react`), approval controls

### Critical Pitfalls

1. **Side effects before `interrupt()` re-run verbatim on resume** — LangGraph replays the entire interrupted node from the start; put `interrupt()` as the first statement in its own node, all side effects strictly after it, gated on the resume value.
2. **`AsyncPostgresSaver.setup()` never called, or manual/forgotten** — call it idempotently in FastAPI lifespan startup, not as a one-off script; a fresh empty-DB `docker compose up` must succeed without a manual step.
3. **In-memory dedupe dict can't survive concurrency or restarts** — replace with a Postgres unique/partial-unique index on `fingerprint` and `INSERT ... ON CONFLICT ... RETURNING`, the atomic signal for "already existed."
4. **f-string-built SQL/Cypher (an established repo habit in `db.py`/`mcp_server.py`) must not migrate into the new Postgres layer** — all new alert/audit/checkpoint writes use parameterized queries exclusively; this is a code-review gate from the first migration onward.
5. **TOCTOU on remediation approval consumption and execution** — claim an approval via one atomic `UPDATE ... WHERE status='pending' RETURNING *`, never `SELECT` then `UPDATE`; bind the executed argv to the approval row at proposal time, never re-derive from live state; never let the LLM construct a shell string (`shell=False`, fixed argv templates only).
6. **Per-SSE-client Postgres `LISTEN` connections exhaust the pool** — exactly one process-wide `LISTEN` connection, fanned out in-process to per-client `asyncio.Queue`s.
7. **Initial-snapshot race** — `NOTIFY` has no backlog; server must push a full snapshot as the first SSE frame on connect (or use sequence numbers + `Last-Event-ID` backfill), never snapshot-then-subscribe on the client.

## Implications for Roadmap

The planned phase split (10 = persistence + API, 11 = agent HITL gates, 12 = SPA + replay) is well-supported by the dependency structure found in ARCHITECTURE.md and confirms the pitfall ownership below. One build-order dependency is load-bearing: **the checkpointer/interrupt round-trip must be proven against `graph.py` directly, before any FastAPI/HTTP work depends on it being real** — this is explicitly the architecture research's step 1 ("highest-risk unknown"), and it should be validated as a narrow spike inside Phase 10 or as a Phase 10→11 gate, not assumed to work once wired into the full stack.

### Phase 10: Persistence + API
**Rationale:** Everything downstream (HITL resume, audit timeline, SSE) depends on a Postgres schema and an async driver being correct first; this phase also converts the webhook from sync/threaded to async, which is a prerequisite for sharing an event loop with SSE in Phase 12.
**Delivers:** Postgres schema (alerts, `incident_events`, checkpoint tables), `AsyncPostgresSaver.setup()` wired into FastAPI lifespan, `ON CONFLICT`-based alert dedupe replacing the in-memory dict, async FastAPI app replacing `src/webhook/app.py`'s threading model with a tracked-`asyncio.Task` pattern.
**Addresses (FEATURES.md):** alert list with status/severity/timestamps; chronological audit timeline (schema origin).
**Owns these pitfalls:** #2 (`.setup()`), #3 (dedupe -> unique index + `ON CONFLICT ... RETURNING`), #4 (parameterized queries — set the convention here since every later phase writes through this layer), #6 (`0001-01-01`/timestamp handling), the async-webhook-conversion half of #10 (bare `create_task` GC) and #11 (blocking sync calls in the shared event loop — the pattern must be set correctly here even though the agent graph itself isn't touched yet).

### Phase 11: Agent HITL Gates
**Rationale:** Requires Phase 10's checkpointer and async driving loop to exist first; this is where `interrupt()` is actually inserted into `graph.py` and where the resume-via-separate-HTTP-request architecture (not the original call stack) is designed.
**Delivers:** `workflow.compile(checkpointer=...)`; new `await_approval` node between `verifier` and `finalize` calling `interrupt(...)` as its first statement; `Command(resume=...)` resume endpoint keyed by `thread_id`; allowlisted remediation execution behind an atomic `UPDATE ... WHERE status='pending' RETURNING *` claim.
**Addresses (FEATURES.md):** the "Awaiting Approval" differentiator status; approval gate UI backing (proposed action + rationale); audit record of approve/reject outcome.
**Owns these pitfalls:** #1 (side effects before `interrupt()`), the resume-architecture half of #2, #5 (TOCTOU on approval claim + execution, fixed argv templates), the "must not violate" half of #11 (blocking sync Anthropic SDK / `subprocess` calls inside the now-shared event loop).

### Phase 12: SPA + Replay
**Rationale:** Has no backend dependents of its own and benefits most from a stable API surface — correctly sequenced last per ARCHITECTURE.md's build order, though the NOTIFY-listener/SSE plumbing underneath it can be built and tested against synthetic rows as soon as Phase 10's `incident_events` table shape exists, in parallel with Phase 11's agent work.
**Delivers:** NOTIFY listener + in-process pub/sub + SSE endpoints; Vite/React SPA (alert list, detail tabs, approval controls); the **dynamic** step graph (`@xyflow/react` + `@dagrejs/dagre`) driven by real agent events per the decided scope; replay script driving a committed SigNoz fixture through the same SSE/UI event schema as the live path.
**Addresses (FEATURES.md):** live step graph, replay differentiator, live status updates without polling.
**Owns these pitfalls:** #6 (single shared LISTEN connection, not per-client), #7 (initial-snapshot race — snapshot-as-first-SSE-frame or sequence+`Last-Event-ID`), reverse-proxy buffering/heartbeats, and #12 (React Flow stable node ids + incremental layout — decide the id-derivation scheme, e.g. `f"{node_name}:{step_index}"`, *before* wiring live SSE into the graph, since retrofitting stable ids later means touching every event-to-node mapping call site — this is now a materially bigger concern given the dynamic-graph scope decision: loop iterations and retries mean the same logical node can recur multiple times, so node identity must disambiguate by occurrence, not just by node name).

### Phase Ordering Rationale

- **Backend-first dependency chain is real, not arbitrary:** Phase 11's `interrupt()` has nowhere to persist state without Phase 10's checkpointer; Phase 12's resume/approve UI has nothing to call without Phase 11's endpoint. This is a hard sequential dependency, not a preference.
- **The frontend is parallelizable against backend work, but only after the API contract for SSE events and the `incident_events` row shape is fixed.** Concretely: once Phase 10 lands the `incident_events` table schema, Phase 12's SSE/pub-sub layer and even early SPA component work (alert list, static mockups of the step graph) can proceed against synthetic/seeded rows while Phase 11's actual `interrupt()` wiring is still in progress — this is the parallelization opportunity a 2-3 engineer sprint should exploit. The dynamic step-graph rendering logic specifically, however, should be validated against Phase 11's *real* event shapes (including loop/retry sequences) before being considered done, since a schema built only against straight-line synthetic data risks missing exactly the loop-iteration/retry/dead-end cases the dynamic-graph scope decision requires.
- **The one piece that must NOT be parallelized:** the checkpointer/interrupt round-trip proof (`interrupt()` + `Command(resume=...)` working against `graph.py` directly, no FastAPI). This is explicitly the architecture research's highest-risk unknown and the single blocking dependency for both Phase 11 and, transitively, Phase 12's approval UI. Treat it as a go/no-go spike at the start of the Phase 10->11 boundary.
- **Pitfall ownership avoids diffusion of responsibility:** each pitfall above is mapped to exactly one primary owning phase (with a secondary "must not violate" phase where relevant, e.g. #11's blocking-call pattern is set in Phase 10 but must hold in Phase 11 too) — this prevents "everyone assumed someone else handled it" gaps, particularly for the SQL-injection convention (#4) and the atomic-claim pattern (#3/#5) which share a shape and should be reviewed together.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 11:** the exact `interrupt()`/`Command(resume=...)` call shape against the *actually installed* `langgraph==1.2.10` should be re-verified with a throwaway script before committing to the node design — the orchestrator's verified facts below close the biggest open question (`astream_events(v3)` is unusable), but the specific conditional-edge routing after `await_approval` and how the resume value flows into `route_after_verifier`-equivalent logic is worth a focused `--research-phase` pass or at minimum a spike script.
- **Phase 12:** React Flow incremental layout strategy for a graph that can now contain loop iterations and retries (not just a linear sequence) is more complex than the original FEATURES.md "static diagram + status overlay" recommendation assumed — the node-id-per-occurrence scheme and layout algorithm choice (dagre's tree-layout assumption vs. a graph with cycles/retries) deserves explicit design time, not just implementation.

Phases with standard patterns (skip research-phase):
- **Phase 10:** Postgres schema design, `ON CONFLICT` dedupe, `.setup()` lifecycle, and the async-task-tracking pattern are all well-documented, directly-confirmed-against-official-docs patterns with no open questions.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All new package versions verified via live PyPI/npm/Docker Hub APIs; compatibility against existing pins (numpy, langgraph, starlette) explicitly cross-checked via `requires_dist` inspection, not inferred |
| Features | MEDIUM | Cross-checked across many official vendor docs (PagerDuty, incident.io, AWS SSM, StackStorm, Temporal, Airflow, LangGraph) but no primary-source code verification of those competitor tools — appropriately caveated as MEDIUM in FEATURES.md itself. The dynamic-vs-static step graph scope was subsequently overridden by explicit user decision, recorded above as decided, not open |
| Architecture | HIGH | LangGraph HITL/streaming mechanics verified against live official docs (context7) AND against this repo's actual source (`graph.py`, `state.py`, `app.py`, `tracing.py` read directly, not assumed); SSE/NOTIFY fan-out pattern is MEDIUM (community consensus, not an official psycopg/FastAPI-blessed recipe, but consistent across independent sources) |
| Pitfalls | HIGH | LangGraph interrupt-replay semantics confirmed against maintainer-tracked GitHub issues (#7361, #4796), not just docs prose; Alertmanager duplicate-delivery behavior confirmed against upstream issues; SQL-injection and TOCTOU findings grounded in direct repo code inspection (`db.py`, `mcp_server.py`) rather than generic best-practice lists |

**Overall confidence:** HIGH

### Gaps to Address

- **`astream_events(version="v3")` unusability — CLOSED, not a gap.** The orchestrator verified at runtime that `CompiledStateGraph` at langgraph 1.2.10 carries a method literally named `_astream_events_v3_unsupported`; ARCHITECTURE.md flagged this as an open question, but it is now resolved: use `v2`, or the classic `.ainvoke()` + `result["__interrupt__"]` / `Command(resume=...)` pattern that the research already recommends as the primary mechanism. No further validation needed.
- **Orphaned/killed in-flight runs on process restart:** ARCHITECTURE.md notes there is no auto-resume mechanism for a run killed mid-execution without additional bookkeeping (e.g., a `status='running'` row with a heartbeat) — this is an explicit, deferrable scope decision, not something the base architecture solves for free. Flag for Phase 10/11 planning: decide explicitly whether this milestone needs manual-resume-only (cheaper) or heartbeat-based auto-resume (more robust), and document the choice rather than leaving it implicit.
- **Dynamic step-graph event schema depth:** the decided scope (loop iterations, retries, dead ends, actual exit path) is a bigger data-modeling task than the original FEATURES.md recommendation assumed. The exact event schema needed to reconstruct this client-side (e.g., does a "retry" need an explicit `retry_of: step_id` field, or is it inferable from repeated `node_name` occurrences with an intervening tool-error event?) is not fully specified in the research and should be nailed down during Phase 11/12 planning, informed by real event traces from the Phase 11 spike.

## Sources

### Primary (HIGH confidence)
- LangGraph official docs via context7 (`/websites/langchain_oss_python_langgraph`) — `interrupt()`, `Command(resume=...)`, checkpointers, streaming, `get_state`
- PyPI JSON API, npm registry API, Docker Hub API — live version/dependency verification for all new packages
- Direct repo inspection — `src/agent/graph.py`, `src/agent/state.py`, `src/webhook/app.py`, `src/webhook/alert.py`, `src/agent/tracing.py`, `src/production/db.py`, `src/production/mcp_server.py`
- Orchestrator runtime verification against actually-installed packages — `langgraph.types.interrupt`, `Command` dataclass fields, `_astream_events_v3_unsupported` method presence (see Gaps section — this closes ARCHITECTURE.md's open v3 question)
- `langchain-ai/langgraph` GitHub issues #7361, #4796 — confirm replay-from-node-start behavior
- `prometheus/alertmanager` GitHub issues #3846, #4108 — confirm duplicate-delivery semantics

### Secondary (MEDIUM confidence)
- PagerDuty, incident.io, Grafana OnCall, AWS SSM, StackStorm, Temporal, Airflow, n8n, Langfuse vendor docs — feature-landscape survey (FEATURES.md)
- `tom.catshoek.dev/posts/postgres-sse/` and corroborating community writeups — psycopg3 `LISTEN`/`NOTIFY` + SSE fan-out pattern
- InfoQ TypeScript 7.0 GA coverage — corroborated against npm dist-tags directly

---
*Research completed: 2026-08-08*
*Ready for roadmap: yes*
