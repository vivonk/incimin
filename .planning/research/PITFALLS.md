# Pitfalls Research

**Domain:** Adding Postgres persistence, LangGraph HITL interrupts, SSE live updates, a React step-graph SPA, and gated remediation execution to an existing threading-based webhook + no-checkpointer LangGraph agent.
**Researched:** 2026-08-08
**Confidence:** HIGH (LangGraph interrupt semantics, Alertmanager delivery semantics, Postgres ON CONFLICT pattern, asyncio task GC — all confirmed against current docs/issues; MEDIUM on SSE/React Flow specifics, which are well-documented community patterns rather than versioned API guarantees)

**Grounded against this repo:** `src/webhook/app.py` (in-memory `_recent: dict` dedupe under a `threading.Lock`, `threading.Thread(target=run_alert, ...).start()` fire-and-forget per alert), `src/webhook/alert.py` (`dedupe_key = fingerprint or f"{alertname}|{service}"`, RFC3339-nanosecond `parse_time`, `0001-01-01` zero-value handling), `src/production/db.py` (`_insert_ch` builds a Python source string via f-string and runs it with `subprocess.run([sys.executable, "-c", code])` — arbitrary code execution, not just SQL injection, if any interpolated value contains a quote; `merge_deployment_event`'s Cypher also f-string-interpolates `now_str` and UUIDs directly into the query body instead of using the `$repo`/`$service` params it already has available), `src/production/mcp_server.py` (ClickHouse queries built with f-strings at lines ~50, ~70).

## Critical Pitfalls

### Pitfall 1: Node code before `interrupt()` re-runs verbatim on resume

**What goes wrong:**
`interrupt()` does not suspend mid-function and resume from that line — on resume, LangGraph replays the **entire node from its start**, using the checkpointed state for everything already produced by *earlier* nodes, but re-executing every line of the interrupted node itself, including any side effect that ran before the `interrupt()` call. If the approval node writes an `approvals` row, calls an external API, or increments a counter before pausing, that write happens again on resume — and again on a second resume if the human clicks stale UI twice.

**Why it happens:**
Durable execution in LangGraph is implemented by checkpointing graph *state*, not *program counters* — there's no continuation to resume into. Developers coming from generator/coroutine mental models (`await` suspends in place) assume the same for `interrupt()`, which does not hold. This is a documented, current gotcha in the LangGraph interrupts docs and issue tracker, not a version-specific bug.

**How to avoid:**
- Put `interrupt()` as the **first statement** in the node (or in its own single-purpose node) — no side effects before it, ever.
- Any side effect that must happen exactly once per approval (writing the audit row, calling the remediation executor) belongs strictly **after** the `interrupt()` call returns, in the same node, gated on the resume value — never before.
- Make the pre-interrupt read path itself idempotent (pure reads from state/DB, no writes) so replay is a no-op.
- Do not wrap `interrupt()` in try/except — LangGraph raises `GraphInterrupt` internally to unwind the node, and swallowing it breaks the pause.

**Warning signs:** duplicate rows in the audit table per single approval click; the remediation command executed twice; a Langfuse trace showing the same tool call twice around one interrupt.

**Phase to address:** Phase 11 (agent HITL gates) — enforce as a structural rule when writing the approval node: `interrupt()` first, side effects after.

---

### Pitfall 2: Compiling the graph without `.setup()` on `AsyncPostgresSaver`, or without a checkpointer at all

**What goes wrong:**
The graph currently compiles with `app = builder.compile()` and no checkpointer (per PROJECT.md decision log: "The graph previously compiled with no checkpointer, so a pause could not survive a restart"). Two distinct failure modes when adding durability: (1) forgetting to call `await checkpointer.setup()` once before first use — `AsyncPostgresSaver` needs its own tables (`checkpoints`, `checkpoint_writes`, etc.) created in the Postgres DB, and skipping this raises a runtime error the first time `interrupt()` tries to persist state, not at startup; (2) compiling with a checkpointer but the webhook's `threading.Thread(target=run_alert, ...)` fire-and-forget pattern means the response object/websocket handle from that request is gone by the time a human approves — resume must happen via a *separate* request path keyed by `thread_id`, not by holding the original call open.

**Why it happens:** `.setup()` is a manual migration step, easy to treat as one-time and then forget in a fresh environment (new dev machine, CI, redeployed container with an empty DB). The threading pattern predates checkpointing and was designed around "run and forget," which is structurally incompatible with "pause and wait for a second, unrelated HTTP request."

**How to avoid:**
- Run `checkpointer.setup()` idempotently on app startup (FastAPI lifespan), not as a separate manual script — `CREATE TABLE IF NOT EXISTS` semantics inside `setup()` make repeated calls safe.
- Replace the fire-and-forget `threading.Thread` invocation entirely for graphs with interrupts: the webhook handler starts the run and returns immediately with a `thread_id`; a *separate* `/approvals/{id}/decide` endpoint resumes the same `thread_id` via `Command(resume=...)`. The original thread's Python call stack is gone — resume must reconstruct via checkpointer state, not via any in-memory reference.
- Use one `thread_id` per alert (e.g., derived from the alert's Postgres primary key or fingerprint, not a random UUID per run) so a duplicate webhook delivery resumes/observes the same run instead of starting a second graph over the same incident.

**Warning signs:** `asyncpg.exceptions.UndefinedTableError` on first interrupt in a new environment; approvals that "disappear" because the resume call targets a `thread_id` nothing was ever checkpointed under.

**Phase to address:** Phase 10 (persistence + API) — `.setup()` belongs in the same migration/bootstrap step as the alerts and audit tables. Phase 11 (HITL gates) — the resume-via-separate-request architecture is the core design decision for that phase.

---

### Pitfall 3: In-memory dedupe dict cannot survive concurrency or restarts — replace with a Postgres partial unique index

**What goes wrong:**
`src/webhook/app.py`'s `_recent: dict[str, float]` under `threading.Lock` has three faults once alerts must be durable: (1) it's per-process — restart the FastAPI process (or run two replicas) and every in-flight suppression window resets, so a redelivered Alertmanager alert that arrives right after a restart is treated as new; (2) check-then-act is not atomic across the *webhook boundary* even though the Python lock makes the dict update atomic — two near-simultaneous deliveries of the same fingerprint (Alertmanager's own retry-on-non-2xx behavior, or two Alertmanager replicas both notifying) can both pass `_is_duplicate()` before either has inserted a durable row, if the durable insert happens after the check rather than being the check; (3) `WEBHOOK_DEDUPE_SECONDS` (default 300) is a *time window* heuristic standing in for what should be a hard identity constraint — Alertmanager's `repeat_interval` is often 4h+, so an alert that legitimately re-fires 6 minutes after the window closes is treated as new, doubling the agent run for a still-ongoing incident.

**Why it happens:** the in-memory dict was correct for the pre-persistence design (webhook only trigger agent runs, nothing durable to protect). Moving to Postgres-backed alerts without revisiting dedupe just adds a second, disagreeing source of truth.

**How to avoid:**
- Give the `alerts` table a unique (or partial unique) index on the Alertmanager `fingerprint` (already computed as `AlertContext.dedupe_key`), and make the insert path `INSERT ... ON CONFLICT (fingerprint) DO NOTHING RETURNING id` (or `DO UPDATE ... RETURNING id` if a resend should refresh `last_seen_at`/status). The `RETURNING` clause is the atomic duplicate signal — no rows returned means "already existed," decided entirely inside Postgres, immune to the two-replica/two-thread race that a check-then-insert (or a Python dict) cannot close.
- Treat the fingerprint-less fallback (`f"{alertname}|{service}"` in `AlertContext.dedupe_key`) as a second unique constraint column combination, since not every alert source guarantees a fingerprint.
- Keep a short in-memory guard only as a *pre-filter* to avoid hitting Postgres for an obvious immediate double-POST (e.g., a proxy retry within milliseconds) — never as the source of truth for whether the agent already ran.
- Decide new-run-vs-same-run explicitly: a resend of a `firing` alert under the same fingerprint while a run is `in_progress`/`awaiting_approval` should attach to the existing row and thread_id, not spawn a second agent run.

**Warning signs:** two duplicate rows for the same fingerprint appearing only under load (never in solo manual testing — this is a race that needs concurrent delivery to manifest); an incident's Langfuse session (currently keyed off `dedupe_key`) showing two unrelated agent runs.

**Phase to address:** Phase 10 (persistence + API) — this is the schema/insert-path design; get the constraint and `ON CONFLICT` clause right before anything depends on `alerts.id` being unique per incident.

---

### Pitfall 4: SQL/Cypher built via f-string interpolation — an established bad habit in this repo that must not migrate into the new Postgres layer

**What goes wrong:**
`src/production/db.py::_insert_ch` builds a *Python source string* via f-string (`code = f"""...client.command('''{query}''')..."""`) and executes it with `subprocess.run([sys.executable, "-c", code])` — this is worse than SQL injection: any interpolated value containing `'''` or backslash-quote sequences breaks out of the ClickHouse query string *and* the embedding Python string, achieving arbitrary code execution in a subprocess, not just an unintended query. `merge_deployment_event` in the same file f-string-interpolates `now_str`, `repo_ext_id`, `svc_ext_id`, `rel_ext_id` directly into Cypher text even though the function *already* passes `repo`/`service` as bound Neo4j params two lines later — it inconsistently parameterizes some values and inlines others. `src/production/mcp_server.py` builds ClickHouse queries the same f-string way. This pattern predates v1.7, and the new Postgres alert/audit/checkpoint tables are the highest-value place it must not reappear, since they'll carry the raw webhook JSONB payload and free-text alert messages/annotations (attacker- or upstream-service-controlled strings) directly into SQL.

**Why it happens:** f-string query building looks identical to parameterized calls at a glance, and Python's ORMs/drivers all accept raw strings, so nothing forces the safer path. It's fastest to write and works fine until a value contains a quote, apostrophe, or (in `_insert_ch`'s case) a triple-quote sequence.

**How to avoid:**
- Every new Postgres write/read (alerts, agent step log, audit table) uses `asyncpg`/`psycopg` **parameterized queries** (`$1, $2, ...` or `%s` placeholders passed as a separate args tuple) — never f-string or `.format()` into SQL text. This applies especially to alert `message`/`annotations` fields, which come from `alert.py`'s `to_prompt()` — arbitrary upstream-controlled text.
- The webhook's raw payload (`ctx.raw`) is stored as JSONB via a bound parameter (`INSERT INTO alerts (payload) VALUES ($1)` with the dict passed as the param, letting the driver serialize it) — never JSON-dumped into an f-string.
- Code review checklist item for phase 10/11: grep the diff for `f"""` / `f"` immediately followed by `SELECT`/`INSERT`/`UPDATE`/`MERGE` and reject on sight, given the repo's demonstrated pattern of doing exactly this in `db.py` and `mcp_server.py`.
- Do not fix the old `db.py`/`mcp_server.py` files as part of this milestone (out of scope) — but do not copy their pattern into the new files, and flag them in the PR description as known pre-existing debt so a reviewer doesn't assume "this is how the repo does it" is sanctioned.

**Warning signs:** any new file with `f"""` immediately preceding a SQL/Cypher keyword; any `subprocess.run` wrapping a string-built script.

**Phase to address:** Phase 10 (persistence + API) — set the parameterized-query convention in the very first migration/DAO code, since every later phase (11, 12) writes through this same layer.

---

### Pitfall 5: Executing remediation post-approval without closing the TOCTOU gap or re-validating the allowlist at execution time

**What goes wrong:**
Between "human clicks Approve" and "executor actually runs the command," several things can go stale: the approval record can be replayed (double-submit on a slow UI, or two browser tabs both showing the pending approval), the *proposed* command can differ from what gets executed if the executor re-derives the command from mutable state instead of the exact string that was shown to and approved by the human (classic time-of-check/time-of-use), and an allowlist check performed only at proposal time (when the LLM drafts the remediation) gives no guarantee the same check runs again immediately before `subprocess` invocation.

**Why it happens:** it's natural to treat "the LLM proposed an allowlisted action" and "the human approved" as sufficient gating, forgetting that the object executed must be re-validated at the moment of execution, and that "approved" is a state that can be read by two racing requests.

**How to avoid:**
- **Never let the LLM construct a shell string.** The allowlist is a set of *parameterized action templates* (e.g., `restart_service(service_name: str)` → `["kubectl", "rollout", "restart", f"deployment/{service_name}"]` built with `subprocess.run([...], shell=False)` and a list, never a single interpolated string passed to `shell=True`). Validate `service_name` against the known topology service set (Memgraph node names) before building the argv list — this closes command injection at the same layer that closes the SQL-injection habit above.
- **Re-check the allowlist and the approval row's status at execution time, inside the same transaction that flips status to `executing`.** `UPDATE approvals SET status='executing' WHERE id=$1 AND status='pending' RETURNING *` — zero rows returned means someone already claimed/executed/expired this approval; abort. This is the same atomic-conditional-update pattern as the webhook dedupe (Pitfall 3), applied to approval consumption instead of alert insertion, and is what actually prevents double-execution — a `SELECT` followed by an `UPDATE` is exactly the check-then-act race Pitfall 3 warns about.
- **Bind the executed command to the approval row, not to live state.** Store the fully-resolved argv (or template + params) in the `approvals` row at proposal time; execution reads *that stored value*, not a fresh re-derivation from current alert/topology state — otherwise the service topology could have changed between proposal and click, and the human approved a description of an action that doesn't match what runs.
- **Write the audit trail before and after execution, not only after.** Row states: `proposed → approved → executing → succeeded|failed`, each transition its own timestamped row/update, so a crash mid-execution leaves visible evidence of "we started this" rather than silence.
- **Blast-radius controls:** enforce a hard low ceiling (e.g., exactly one action per approval, one target service, no wildcard/glob targets) and require the allowlist to be a Python enum/mapping checked into source, never data loaded from the DB or from LLM output — an LLM should never be able to add a new allowlisted verb by generating one that merely looks like an existing name.

**Warning signs:** two `executing` rows for one approval id; the audit log missing the intermediate `executing` state; any code path where the argv list is built from a variable that also flows into a ClickHouse/Cypher query elsewhere unescaped (same-shaped bug as Pitfall 4, different sink).

**Phase to address:** Phase 11 (agent HITL gates) — the allowlist template design and the conditional `UPDATE ... WHERE status='pending'` claim pattern are core to this phase, since they sit directly on the interrupt/resume boundary. Phase 10 provides the audit table schema this depends on.

---

### Pitfall 6: `0001-01-01` / Go zero-value timestamps and RFC3339-nanosecond parsing regressing when moved into Postgres columns

**What goes wrong:** `alert.py::parse_time` already handles two Go-specific timestamp quirks correctly for the in-memory `AlertContext` (nanosecond fractional seconds truncated to 6 digits for `datetime.fromisoformat`, and Alertmanager's `0001-01-01...` zero value for "unset" treated as `None` rather than a real ancient date). The risk when this data lands in Postgres is regression at the boundary: (1) inserting `resolved_at` as `NULL` (correct) vs. accidentally letting a raw unparsed `"0001-01-01T00:00:00Z"` string reach the column if any new code path bypasses `parse_time` (e.g., a direct dict access on `ctx.raw` for a "raw payload preserved" JSONB field is fine — the bug is if a *typed* column reads from `raw` instead of from the already-parsed `AlertContext` field); (2) storing `TIMESTAMP` instead of `TIMESTAMPTZ` — `parse_time` returns tz-aware UTC datetimes, and a naive/local column silently drops or reinterprets the offset on write.
**Why it happens:** the payload JSONB column and the typed timestamp columns are two representations of the same event; it's easy for a later query/report to read the convenient one (JSONB) and skip the already-solved parsing logic.
**How to avoid:** typed alert columns (`fired_at`, `resolved_at`) are populated exclusively from `AlertContext.fired_at`/`resolved_at` (already-parsed, UTC-aware `datetime` objects), never re-parsed from `raw`; declare them `TIMESTAMPTZ`; `resolved_at` is nullable and stays `NULL` for the zero-value case, never a sentinel date. Add one test asserting that an alert payload with `endsAt: "0001-01-01T00:00:00Z"` round-trips through the DB as `NULL`.
**Warning signs:** a report/query that joins on `raw->>'startsAt'` instead of the typed column; any alert row showing `resolved_at` in year 1 or 0001.
**Phase to address:** Phase 10 (persistence + API) — schema design and insert-path field mapping.

---

### Pitfall 7: SSE clients each holding an open Postgres LISTEN connection — pool exhaustion under normal multi-tab usage

**What goes wrong:** the natural implementation opens a dedicated `asyncpg`/`psycopg` connection per SSE client and issues `LISTEN alerts_channel` on it, since `LISTEN` is connection-scoped and can't share a pooled connection that gets returned between queries. With a typical connection pool sized for request/response traffic (e.g., 10-20), a handful of dashboard tabs left open (normal SRE behavior — a dashboard tab per monitor) exhausts the pool, and every *other* request (webhook ingestion, the React SPA's own REST polling, approval submission) starts blocking or erroring.
**Why it happens:** `LISTEN/NOTIFY` requires a long-lived, dedicated connection per listener, which is structurally different from every other DB access pattern in the app (borrow-query-return).
**How to avoid:** run exactly **one** dedicated `LISTEN` connection for the whole process (in the FastAPI lifespan), fan its `NOTIFY` payloads out to per-client `asyncio.Queue`s held in memory, and have each SSE handler `await` its own queue rather than opening its own DB connection. This decouples "number of SSE clients" from "number of DB connections" entirely — the pool sizing only has to account for normal request traffic.
**Warning signs:** connection pool exhaustion errors correlating with SSE client count, not request rate; `too many clients already` from Postgres under light dashboard usage.
**Phase to address:** Phase 12 (SPA + replay) — this is the SSE fan-out architecture decision, made once when the `/events` endpoint is built.

---

### Pitfall 8: The initial-snapshot race — events emitted between "page loads its REST snapshot" and "EventSource subscribes" are silently lost

**What goes wrong:** `NOTIFY` delivers only to connections that are already `LISTEN`ing at the moment it fires — it is not a queue and has no replay/backlog. If the SPA first fetches a REST snapshot (`GET /alerts`) and *then* opens the `EventSource` connection, any status change or step-graph event that happens in that gap is never delivered, and the UI is stuck showing stale data until the next event arrives (which may be minutes away, or never, if that was the last event of the run).
**Why it happens:** snapshot-then-subscribe is the obvious naive ordering (get current state, then listen for changes), but it has a window; the correct ordering is subscribe-then-snapshot, or a sequence-numbered reconciliation.
**How to avoid:** either (a) open the SSE connection first, and only once the server confirms it is actively `LISTEN`ing does the server itself push an initial full-state event as the *first* SSE message (so "connect" and "get current state" are the same request, ordered correctly on the server side, not two racing client-side calls), or (b) tag every alert/step-log row with a monotonically increasing sequence number, have the client remember the last sequence number it rendered, and on (re)connect send `Last-Event-ID` (native `EventSource` reconnect header) so the server can backfill anything missed from Postgres before switching to live `NOTIFY` forwarding.
**Warning signs:** a step graph that "misses" the very first tool call of a run right after page load, but is correct for everything after; discrepancies that only appear on hard refresh timed against an in-flight incident.
**Phase to address:** Phase 12 (SPA + replay) — design the `/events` endpoint to push the snapshot as the first SSE frame server-side, and use `Last-Event-ID` for reconnects, rather than a client-side fetch-then-subscribe sequence.

---

### Pitfall 9: Reverse proxy buffering SSE, and missing heartbeats leaving dead connections undetected

**What goes wrong:** any intermediary buffering the response (a reverse proxy, or FastAPI/Starlette serving it without disabling buffering) can hold SSE chunks until a buffer threshold is hit, turning "live" updates into "arrives in bursts every N KB." Separately, without periodic heartbeat comments (`: ping\n\n`), a half-closed connection (client's laptop slept, network dropped without a clean FIN) looks identical to an idle-but-healthy one from the server's perspective, so a dead SSE generator can sit consuming a queue/task slot indefinitely.
**How to avoid:** set `X-Accel-Buffering: no` (if fronted by nginx-style proxy) and `Cache-Control: no-cache` on the SSE response; send a comment-only heartbeat frame every ~15-30s; on the client, rely on native `EventSource` auto-reconnect (it reconnects on its own after a drop) but pair it with the `Last-Event-ID` backfill from Pitfall 8 so a reconnect doesn't just resume blind.
**Warning signs:** step graph updates that appear in visible batches rather than one-by-one in a dev environment behind any proxy; server task/connection count that only grows, never shrinks, as tabs are closed without a clean disconnect.
**Phase to address:** Phase 12 (SPA + replay).

---

### Pitfall 10: Bare `asyncio.create_task()` for the agent run — task silently garbage-collected or its exception swallowed

**What goes wrong:** replacing the current `threading.Thread(target=run_alert, ...).start()` with `asyncio.create_task(run_alert_async(ctx))` (natural when the webhook handler becomes async to talk to Postgres) without holding a reference means the event loop keeps only a weak reference to the task — it can be garbage-collected mid-run, and any exception it raises is never retrieved, so it's logged only as an opaque "Task exception was never retrieved" with no application context, not routed through this repo's existing `log.exception("[%s] %s failed", ...)` pattern in `run_alert`.
**Why it happens:** `create_task` looks like fire-and-forget by design, and nothing raises immediately when the reference is dropped — the failure is silent and probabilistic (GC timing), making it hard to catch in quick manual testing.
**How to avoid:** keep a module-level `set()` of in-flight tasks, add each new task to it, and register a `task.add_done_callback(tasks.discard)` so the set self-cleans on completion while holding a strong reference for the task's full lifetime; the done-callback (or an explicit `try/except` inside the coroutine, matching the existing `run_alert`'s "must never raise" contract) is what surfaces exceptions into structured logs instead of asyncio's fallback logger. On FastAPI shutdown (lifespan), await/cancel all tasks in the set with a timeout so a reload/redeploy doesn't kill in-flight agent runs invisibly — or, better, rely on the checkpointer (Phase 11) so an interrupted/killed run resumes on next process start rather than needing graceful in-process shutdown at all.
**Warning signs:** agent runs that "just stop" with no log line at all (vs. the current code's guaranteed `log.exception` on any failure); run count metrics that don't match completed+failed counts.
**Phase to address:** Phase 10/11 boundary — whichever phase converts the webhook handler to async and replaces `threading.Thread` must adopt the strong-reference task-set pattern as part of that conversion, not as an afterthought.

---

### Pitfall 11: Blocking sync calls (Anthropic SDK, `subprocess` for remediation) inside an async event loop stall every concurrent SSE stream and webhook

**What goes wrong:** once the webhook and SSE endpoints share one FastAPI process/event loop, any blocking call made directly in an `async def` handler — a synchronous Anthropic SDK call inside the LangGraph node, or `subprocess.run(...)` for remediation execution — blocks the *entire* event loop for its duration, freezing every open SSE connection's ability to receive `NOTIFY` fan-out and every other concurrent webhook delivery, not just the one request that made the blocking call. The current code avoids this by construction (agent runs on a real OS thread via `threading.Thread`), so this is a regression risk specifically introduced by moving toward an async-first design for phases 10-12, not a pre-existing problem.
**Why it happens:** LangChain/Anthropic SDK calls and `subprocess.run` are synchronous APIs; calling them from inside `async def` code without `await asyncio.to_thread(...)` runs them on the loop thread by default.
**How to avoid:** any synchronous SDK call or `subprocess` invocation inside the agent graph or remediation executor is wrapped in `await asyncio.to_thread(fn, *args)` (the same pattern `db.py` already uses correctly for `_insert_ch`) — or, simpler and consistent with the current design, keep the agent's LangGraph `.stream()` execution running on a dedicated worker thread/executor (not the request-handling event loop) and communicate progress back to the SSE fan-out via the same Postgres LISTEN/NOTIFY channel used for everything else, so the async event loop never directly calls into agent/LLM code at all.
**Warning signs:** SSE updates for *other* incidents pausing during any single agent's LLM call; webhook `/health` latency spiking exactly when an agent run is mid-tool-call.
**Phase to address:** Phase 10 (webhook async conversion) sets the pattern; Phase 11 (agent graph) must not violate it when wiring interrupts/tool calls; Phase 12 is unaffected but benefits from the isolation (SSE stays responsive regardless of agent load).

---

### Pitfall 12: React Flow re-layout thrash and unstable node identity on every step-graph event

**What goes wrong:** two related but distinct failures when the step graph grows from live SSE events: (1) running an auto-layout algorithm (dagre/elk) on *every* incoming event recomputes positions for the whole graph each time, causing existing nodes to visibly jump/reflow instead of the new node simply appending — jarring during a live incident and expensive as node count grows; (2) deriving node `id`s from array index or from a value that isn't stable across re-renders (e.g., regenerating a random id each time the event list is mapped to nodes) causes React Flow (keyed by `id`) to unmount/remount existing nodes on every update instead of just adding the new one, losing any node-local UI state (expanded/collapsed) and causing flicker.
**Why it happens:** it's simplest to recompute the whole `nodes`/`edges` array from the full event log on every SSE message and re-run layout — correct-looking in a demo with 5 events, visibly bad by 30+.
**How to avoid:** derive each node's `id` deterministically from a stable identity already present in the agent event (e.g., `f"{node_name}:{step_index}"` from the LangGraph `stream_mode="updates"` sequence, or a DB-assigned step-log row id) so the same logical step always maps to the same React Flow id across re-renders; only run auto-layout for genuinely *new* nodes (position new nodes relative to their parent/predecessor, e.g., dagre incremental layout or a simple "append below last node of this branch" heuristic) rather than re-laying-out the whole graph on each event; memoize existing node/edge objects (React Flow supports partial updates) so unaffected nodes don't get new object identities each render.
**Warning signs:** the whole graph visibly reflowing/jumping on each new step during a live demo; browser dev tools showing full component remounts (not just re-renders) of already-rendered step nodes.
**Phase to address:** Phase 12 (SPA + replay) — decide the node-id derivation and incremental-layout strategy before wiring live SSE updates into the graph, since retrofitting stable ids after the fact means touching every event-to-node mapping call site.

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|-----------------|------------------|
| Keep `threading.Thread` fire-and-forget for the webhook instead of converting to async + task-set | No event-loop/blocking-call rework needed | Can't share the process event loop with SSE cleanly; agent run isn't visible to `/events` without a second signalling path (e.g., have the thread itself issue `NOTIFY` via a short-lived sync connection) | Only as an explicit interim step within phase 10, not as the final phase-12 architecture |
| In-memory pre-filter dedupe kept alongside the Postgres unique index | Avoids a DB round-trip for obvious millisecond-scale double-POSTs | Two sources of truth that can disagree post-restart | Acceptable as a *pure latency optimization* layered on top of the DB constraint, never as a replacement for it |
| Single global allowlist table stored in Postgres (editable via SQL) instead of a Python-source enum | Ops can add a new allowed action without a deploy | An LLM-influenced write path (or a compromised admin session) could add a dangerous action without code review | Never for this project — PROJECT.md's stated reason for allowing execution at all is the audit/allowlist guarantee; a DB-editable allowlist breaks that guarantee |
| Recomputing full graph layout each SSE event (Pitfall 12) rather than incremental positioning | Simpler to implement in a demo timeframe | Visible thrash, degrades with incident length | Acceptable only for the very first Phase 12 spike/prototype, must be replaced before the replay-script demo is considered done |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|-----------------|-------------------|
| Alertmanager (SigNoz) | Treating `repeat_interval` resends as new incidents | Unique-index on `fingerprint` with `ON CONFLICT DO NOTHING/UPDATE RETURNING` (Pitfall 3) |
| `AsyncPostgresSaver` | Assuming tables exist because the driver "just works" | Explicit idempotent `.setup()` call in app startup lifespan (Pitfall 2) |
| Postgres `LISTEN/NOTIFY` | One DB connection per SSE client | One process-wide LISTEN connection fanning out to per-client in-memory queues (Pitfall 7) |
| `EventSource` (browser) | Assuming no events are missed across reconnects | `Last-Event-ID` + server-side sequence-numbered backfill from Postgres (Pitfall 8) |
| React Flow | Feeding it a freshly-derived `nodes` array with unstable ids each render | Deterministic id per logical step, incremental layout only for new nodes (Pitfall 12) |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|-----------------|
| Per-SSE-client Postgres connection | Pool exhaustion errors correlate with open dashboard tabs, not request volume | Single shared LISTEN connection + in-memory fan-out (Pitfall 7) | Breaks with as few as (pool_size - normal_traffic_headroom) concurrent tabs — can be single digits |
| Full-graph re-layout per event | UI jank increasing with incident duration/step count | Incremental layout, stable node ids (Pitfall 12) | Noticeable well before 50 steps; a long-running incident with many tool calls will hit this |
| Blocking sync call on the shared event loop | All SSE streams pause in lockstep with agent LLM calls | `asyncio.to_thread` or keep agent execution on a dedicated worker thread (Pitfall 11) | Breaks the moment webhook async conversion + SSE share one process, i.e., immediately in phase 10/12, not at scale |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| f-string/`.format()`-built SQL or Cypher in the new Postgres DAO layer (repo's established bad habit — Pitfall 4) | SQL injection via alert `message`/`annotations` (upstream-controlled text) or arbitrary code execution (as in `db.py`'s `subprocess.run([sys.executable, "-c", code])` pattern) | Parameterized queries only; JSONB payload via bound param, never string-built |
| LLM-authored remediation command strings passed to `shell=True` | Command injection through crafted service names or alert metadata reaching the shell | Fixed argv-list allowlist templates with validated params, `shell=False` (Pitfall 5) |
| Approval consumed via `SELECT` then `UPDATE` instead of one conditional `UPDATE ... RETURNING` | TOCTOU double-execution of a remediation action | Atomic conditional update as the sole gate for claiming an approval (Pitfall 5) |
| Allowlist stored as mutable DB data | Bypasses the audit/allowlist guarantee the exclusion in PROJECT.md exists to satisfy | Allowlist as versioned Python source, reviewed like code |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-------------------|
| Dashboard shows stale status until the next unrelated event arrives (Pitfall 8) | Operator thinks an incident is unresolved/unhandled when it's actually already progressed | Server pushes full snapshot as first SSE frame on connect, sequence-numbered backfill on reconnect |
| Step graph visibly reflows on every new tool call during a live incident (Pitfall 12) | Distracting during exactly the moment the operator most needs to read the graph calmly | Append-only incremental layout |
| Double-clicking Approve (slow network) silently no-ops the second click with no feedback | Operator unsure whether the action ran once, twice, or not at all | Conditional `UPDATE ... RETURNING` (Pitfall 5) + disable the button optimistically on first click, reconcile via SSE state |

## "Looks Done But Isn't" Checklist

- [ ] **Webhook dedupe:** Looks done once manual curl testing shows one accepted request → verify concurrent duplicate POSTs (two near-simultaneous requests, same fingerprint) both resolve to one row via `ON CONFLICT`, not via timing luck.
- [ ] **Interrupt/resume:** Looks done once one approve-click completes a run → verify a second (replayed) resume on the same `thread_id`/approval id is rejected, and that nothing before the `interrupt()` call in that node re-executes visibly (check for duplicate audit rows).
- [ ] **SSE live updates:** Looks done in a single-tab dev session → verify with the browser network tab that the very first status after page load didn't require a page refresh to appear (Pitfall 8), and that a second browser tab doesn't cause pool errors (Pitfall 7).
- [ ] **Remediation execution:** Looks done once one allowlisted command runs successfully post-approval → verify a crafted service-name/label value containing shell metacharacters (`;`, `$()`, backticks) is rejected before argv construction, not merely "doesn't happen to break" in the happy path.
- [ ] **Checkpointer setup:** Looks done in the dev environment where `.setup()` was run manually once → verify a fresh `docker compose up` from an empty Postgres volume succeeds without a manual step.
- [ ] **Timestamps:** Looks done for normal alerts → verify a payload with `endsAt: "0001-01-01T00:00:00Z"` (Alertmanager's zero value) round-trips as `NULL`, not a year-1 date, in the persisted row.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|----------------|-----------------|
| Duplicate remediation execution already happened | HIGH | Manual incident review; add the conditional `UPDATE ... WHERE status='pending'` retroactively; backfill audit table with a "duplicate-detected" flag for the affected row |
| In-memory dedupe race caused two agent runs for one incident | LOW | Add the unique index + `ON CONFLICT`; merge/close the duplicate row referencing the same fingerprint |
| SQL/Cypher injection found in a new DAO function | MEDIUM | Rewrite the call to parameterized form; audit git history for whether the vulnerable version ever ran against untrusted input in a shared environment |
| React Flow layout thrash shipped to demo | LOW | Swap in stable ids + incremental layout; no data-layer changes needed, purely a frontend fix |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|----------------|
| Side effects before `interrupt()` re-run on resume | Phase 11 | Trigger one resume; assert no duplicate audit/DB rows for that step |
| `AsyncPostgresSaver` missing `.setup()` / thread_id design | Phase 10 (setup), Phase 11 (thread_id + resume architecture) | Fresh empty-DB startup succeeds; resume via separate HTTP request works after simulated process restart |
| In-memory dedupe dict → Postgres unique index | Phase 10 | Concurrent duplicate-fingerprint POST test produces exactly one row |
| f-string SQL/Cypher construction | Phase 10 | Diff review / grep gate for `f"""`+SQL keyword in new files |
| TOCTOU / replay on remediation approval | Phase 11 | Double-submit the same approval id concurrently; assert exactly one execution |
| `0001-01-01` zero-value timestamp handling in Postgres columns | Phase 10 | Test payload with Go zero-value `endsAt` round-trips as `NULL` |
| Per-client Postgres LISTEN connection pool exhaustion | Phase 12 | Open N dashboard tabs; assert pool usage stays flat, not O(N) |
| Initial-snapshot race on page load | Phase 12 | Load page, then immediately trigger an event server-side; assert it appears without refresh |
| Proxy buffering / missing heartbeats | Phase 12 | Verify `X-Accel-Buffering: no` header present; verify heartbeat frames every ~15-30s in captured stream |
| Bare `create_task` GC / swallowed exceptions | Phase 10/11 boundary (async webhook conversion) | Force an exception in the agent run; assert it appears in structured logs, not asyncio's fallback logger |
| Blocking sync calls stalling the shared event loop | Phase 10 (pattern), Phase 11 (must not violate) | Load-test: one long agent run in progress; assert SSE latency for other incidents is unaffected |
| React Flow unstable ids / full re-layout thrash | Phase 12 | Inspect React dev tools during a multi-step replay; assert existing nodes re-render, not remount |

## Sources

- [LangGraph interrupts docs](https://docs.langchain.com/oss/python/langgraph/interrupts) — HIGH confidence (official docs, current)
- [The Hidden Replay Risk in LangGraph: How "Durable Execution" Can Burn You](https://medium.com/@mehul_parmar/the-hidden-replay-risk-in-langgraph-how-durable-execution-can-burn-you-1d966141e71a) — MEDIUM confidence (community write-up, consistent with official docs)
- [langgraph#7361 — resume from checkpoint_id becomes replay](https://github.com/langchain-ai/langgraph/issues/7361), [langgraph#4796 — subgraph interrupt restarts instead of resuming](https://github.com/langchain-ai/langgraph/issues/4796) — HIGH confidence (maintainer-tracked issues, confirm the replay-from-node-start behavior)
- [prometheus/alertmanager#3846 — repeat_interval not respected on duplicate alert](https://github.com/prometheus/alertmanager/issues/3846), [#4108 — gossip cluster duplicate notifications on retries](https://github.com/prometheus/alertmanager/issues/4108) — HIGH confidence (maintainer-tracked issues)
- [Idempotent Event Delivery for Webhooks](https://meshes.io/blog/idempotent-event-delivery), [Svix — Idempotency and Deduplication](https://www.svix.com/resources/webhook-university/reliability/idempotency-and-deduplication/) — MEDIUM confidence (vendor best-practice docs, consistent pattern across sources)
- [Real-time updates from postgres using notify listen and SSE](https://tom.catshoek.dev/posts/postgres-sse/) — MEDIUM confidence (independent implementation write-up, matches Postgres docs on LISTEN/NOTIFY being connection-scoped and non-persistent)
- [FastAPI — Server-Sent Events tutorial](https://fastapi.tiangolo.com/tutorial/server-sent-events/) — HIGH confidence (official docs)
- [Understanding Pitfalls of Async Task Management in FastAPI Requests](https://leapcell.io/blog/understanding-pitfalls-of-async-task-management-in-fastapi-requests) — MEDIUM confidence, corroborated by [Python asyncio-task docs](https://docs.python.org/3/library/asyncio-task.html) (HIGH confidence, official) on weak-reference task GC behavior
- Direct repo inspection — `src/webhook/app.py`, `src/webhook/alert.py`, `src/production/db.py`, `src/production/mcp_server.py` — HIGH confidence (primary source, current code)

---
*Pitfalls research for: incimin.io v1.7 Incident Dashboard milestone*
*Researched: 2026-08-08*
