# Architecture Research — v1.7 Incident Dashboard

<<<<<<< Updated upstream
**Domain:** Adding durable human-in-the-loop, progress streaming, and a browser dashboard to an existing LangGraph SRE agent
**Researched:** 2026-08-08
**Confidence:** HIGH (LangGraph HITL/streaming verified against live docs); MEDIUM (SSE fan-out, asyncio task lifecycle — corroborated by current community sources, not project-specific benchmarked)
=======
**Domain:** Plugin-based Service Topology Integration
**Researched:** 2026-08-06
**Confidence:** HIGH
>>>>>>> Stashed changes

## Standard Architecture

### System Overview

```
<<<<<<< Updated upstream
┌──────────────────────────────────────────────────────────────────────┐
│  Browser (Vite SPA)                                                  │
│  - dashboard: incident list, live timeline, approve/reject controls  │
│  - EventSource client, one SSE connection per open incident view     │
└───────────────────────┬────────────────────────────────────────────┬─┘
                         │ GET /api/incidents/{id}/events (SSE)      │ static assets (dev: Vite proxy; prod: StaticFiles)
┌────────────────────────▼────────────────────────────────────────────▼┐
│  FastAPI app (NEW — replaces src/webhook/app.py Starlette app)       │
│  ┌──────────────┐  ┌────────────────┐  ┌────────────────────────┐   │
│  │ POST /webhook│  │ SSE endpoints  │  │ StaticFiles mount       │   │
│  │  /signoz     │  │ (subscribe to  │  │ (built SPA, history      │   │
│  │              │  │  in-proc pubsub)│  │  fallback to index.html) │   │
│  └──────┬───────┘  └───────┬────────┘  └──────────────────────────┘   │
│         │ asyncio.create_task            ▲                            │
│  ┌──────▼─────────────────────────┐      │ in-process pub/sub          │
│  │ Agent run task                 │──────┘ (fan-out, no DB round-trip) │
│  │ graph.astream(..., config=     │                                   │
│  │   {thread_id, checkpointer})   │      ┌────────────────────────┐   │
│  └──────┬─────────────┬───────────┘      │ NOTIFY listener task    │   │
│         │ per-step     │ on interrupt    │ (1 AsyncConnection,      │   │
│         │ row INSERT   │ persists paused │  LISTEN incident_events, │   │
│         ▼              ▼ state           │  .notifies() generator)  │   │
│  ┌────────────────────────────────────────▼───────────────────────┐   │
│  │ Postgres (NEW dependency)                                       │   │
│  │  - langgraph checkpoints (AsyncPostgresSaver tables)             │   │
│  │  - incident_events table (append-only step log)                 │   │
│  │  - NOTIFY incident_events on each INSERT (trigger or app-level)  │   │
│  └───────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
                         │ (unchanged) tool calls
┌────────────────────────▼────────────────────────────────────────────┐
│  Memgraph · SigNoz/ClickHouse · Qdrant · Langfuse (unchanged)        │
└────────────────────────────────────────────────────────────────────┘
=======
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                        │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐    │
│  │                Topology Manager                     │    │
│  │             (Core Abstraction Layer)                │    │
│  └────┬───────────────────────────────────────────┬────┘    │
│       │                                           │         │
├───────┴───────────────────────────────────────────┴─────────┤
│                     Plugin Registry                         │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ SigNozPlugin │  │ DataDogPlugin│  │ PromPlugin   │       │
│  │ (Active)     │  │ (Future)     │  │ (Future)     │       │
│  └──────┬───────┘  └──────────────┘  └──────────────┘       │
│         │                                                   │
├─────────┴───────────────────────────────────────────────────┤
│                   External Integrations                     │
│  ┌────────────────────────┐                                 │
│  │ SigNoz API/ClickHouse  │                                 │
│  └────────────────────────┘                                 │
├─────────────────────────────────────────────────────────────┤
│                     Data Store Layer                        │
│  ┌────────────────────────┐                                 │
│  │ Memgraph (Topology)    │                                 │
│  └────────────────────────┘                                 │
└─────────────────────────────────────────────────────────────┘
>>>>>>> Stashed changes
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
<<<<<<< Updated upstream
|-----------|----------------|-------------------------|
| FastAPI app | Webhook intake, SSE fan-out, static SPA serving, HITL resume endpoint | Single ASGI app, replaces `src/webhook/app.py` |
| Agent run task | Drives `graph.astream()` per incident to completion or pause | `asyncio.create_task`, tracked in a module-level set |
| Checkpointer | Persists graph state across the pause at `interrupt()` | `AsyncPostgresSaver`, one `thread_id` per incident |
| Step logger | One DB row per node entry / tool call, source for the dashboard timeline | Custom `BaseCallbackHandler`, composed with the existing Langfuse handler |
| NOTIFY listener | Single long-lived `LISTEN` connection, decouples DB fan-out from HTTP connection count | One `psycopg.AsyncConnection` (autocommit), `.notifies()` async generator, republishes into an in-process pub/sub (asyncio `Queue`/`Condition` per subscriber) |
| SSE endpoint | One HTTP response per browser tab, subscribes to the in-process pub/sub, never touches Postgres directly | `StreamingResponse` / `sse-starlette`, detects disconnect via `request.is_disconnected()` |

## Existing Architecture — What It Is Today

Read directly from the codebase (do not re-derive from memory):

- **`src/agent/graph.py`** — custom `StateGraph`, not `create_react_agent`. Nodes: `agent` (LLM, tool-binding) ⇄ `tools` (`ToolNode`) loop → `synthesize` (structured output) → `verifier` (deterministic) → `finalize` / `graceful_exit` → `END`. `workflow.compile()` is called with **no `checkpointer` argument and no `interrupt_before`/`interrupt_after`**. This is the single most important fact for Question 1: today the graph is stateless between runs and cannot pause.
- **`src/agent/state.py`** — `SREAgentState(TypedDict)`: `messages` (add_messages reducer), `remaining_steps` (int, decremented per LLM turn — this is the step-budget guard, not a HITL mechanism), `evidence` (operator.add reducer — append-only), `candidate_services`, `synthesis: Synthesis | None`, `verification_result: VerificationResult | None`.
- **`src/webhook/app.py`** — Starlette app. `POST /webhook/signoz` parses Alertmanager-shaped alerts into `AlertContext`, dedupes on `dedupe_key` in a `dict` guarded by a `threading.Lock`, and spawns a **daemon `threading.Thread`** per accepted alert that calls `run_alert(ctx)`. That function synchronously drives `meta_agent.stream(inputs, stream_mode="updates", config=trace_config(ctx, "agent"))` — a **sync**, non-checkpointed stream — logging each `{node: state}` update and extracting the last `AIMessage` with text as the final answer. Concurrency is capped by a `threading.BoundedSemaphore`. This whole module is explicitly being retired.
- **`src/agent/tracing.py`** — `trace_config()` builds a `RunnableConfig`; it **merges** into any existing `callbacks` list (`config["callbacks"] = [*existing, langfuse_handler]`) rather than overwriting, specifically so a caller's own callbacks survive. This merge behavior is the seam the new step-logging callback handler must reuse — do not replace `config["callbacks"]`, append to it.

## Q1 — Durable Human-in-the-Loop in LangGraph 1.2.x (verified against live docs, `/websites/langchain_oss_python_langgraph`)

### The mechanics

- `interrupt(value)` is called **inside a node function**, at the point where you want to pause. It is not async-specific — it works the same in sync or async node functions.
- Calling it **raises an internal control-flow signal** (LangGraph's own exception type, not something you catch) that unwinds execution back to the runtime. The runtime persists the current checkpoint (full graph state, plus which node was mid-execution) and returns control to the caller. The graph is now **paused**, not finished.
- This means `interrupt()` never "returns" on the call that raises it — nothing after it runs on that pass.
- **Resuming**: call the graph again with the **same `thread_id`** and input `Command(resume=<value>)` instead of a normal input dict. Docs, verbatim: *"When resuming an interrupt, you must use the same thread ID that was used when the interrupt occurred. The value passed to `Command(resume=...)` becomes the return value of the `interrupt` call, and the node restarts from the beginning of where `interrupt` was called."*
- **The re-execution problem is real and by design**, not a bug to work around: *"When `interrupt` is called within a node, LangGraph suspends execution... Upon resumption, the entire node restarts from the beginning, meaning any code that ran before the `interrupt` will execute again."* Concretely: any DB write, external API call, or side effect placed **before** the `interrupt()` call in that node runs a second time on resume. LangGraph's own guidance: (a) put side effects **after** the `interrupt()` call whenever possible, so they only fire once approval is granted; (b) if a side effect must happen before the interrupt, make it **idempotent** (e.g., upsert keyed on incident id, not a bare INSERT).
- **`thread_id` is mandatory** and lives at `config["configurable"]["thread_id"]`. Without a `checkpointer` compiled into the graph, `interrupt()` cannot persist state and the pause has nowhere to resume from — **this is the concrete reason `workflow.compile()` must change** from today's no-argument call to `workflow.compile(checkpointer=<a persistent saver>)`.

### Detecting a pause from outside the run

Two supported ways, both confirmed in docs:

1. **Synchronous check on the result.** `graph.invoke(inputs, config)` (or draining a `.stream(...)`) returns/produces a dict that carries a `__interrupt__` key when the run paused: `result["__interrupt__"]` is a tuple of `Interrupt(value=..., id=...)` objects. Docs state this explicitly as the fallback when you don't need streamed output: *"The default `graph.invoke(...)` API also works and surfaces interrupts under `result["__interrupt__"]`."*
2. **Out-of-band polling.** `graph.get_state(config)` returns a `StateSnapshot` whose `.next` tuple names the node(s) about to run and whose `.tasks` carry pending `.interrupts` — this is how a separate process (e.g., the FastAPI request handler answering "is this incident waiting on a human?") can inspect a paused thread without re-driving the graph at all. This is the correct mechanism for the dashboard's "is there a pending approval" indicator: query state by `thread_id`, don't try to keep the stream open across an HTTP request/response cycle.

### A version caveat worth flagging to the roadmapper

Context7's current docs describe a newer `graph.stream_events(..., version="v3")` API returning a `StreamProtocol`-like object (`.output`, `.interrupted`, `.interrupts`, `.messages`) as the *recommended* way to drive interruptible runs. **This may be ahead of the pinned `langgraph==1.2.10`** — treat `stream_events`/`version="v3"` as unverified for this pin. What is safe and stable across the 1.x line (and directly confirmed for this project's use case) is the **classic pattern already compatible with how `src/webhook/app.py` drives the graph today**:

```python
config = {"configurable": {"thread_id": ctx.dedupe_key}}
result = await app.ainvoke(inputs, config=trace_config(ctx, "agent") | config)
if "__interrupt__" in result:
    pending = result["__interrupt__"]          # tuple[Interrupt, ...]
    # persist "paused, waiting on <pending[0].value>" and return — do not block the request
else:
    final_answer = ...                          # existing extraction logic

# later, when a human responds via the dashboard:
config = {"configurable": {"thread_id": ctx.dedupe_key}}
result = await app.ainvoke(Command(resume=user_decision), config=config)
```

Before adopting `stream_events`, re-verify against the exact installed `langgraph` version (`pip show langgraph`) rather than trusting the docs snippet dates — this is a "phase needs deeper research" flag for the roadmap.

### Sync node, async driver — confirmed compatible

`interrupt()` itself doesn't care whether the node function is `def` or `async def`, or whether the graph is driven with `.invoke`/`.stream` or `.ainvoke`/`.astream`. LangGraph runs sync node bodies in a thread-pool executor when the graph is driven asynchronously, so **the existing sync `agent_node`, `synthesize_node`, `verifier_node` functions in `graph.py` do not need to become `async def`** just to add an interrupt-bearing node — only the *driver* (the new FastAPI code that calls `.astream`/`.ainvoke`) needs to be async. A new HITL node (e.g., `await_approval_node`) can be a plain sync function that calls `interrupt(...)`.

### Where the interrupt goes in *this* graph

The natural insertion point is a **new node between `verifier` and `finalize`**: after the Verifier passes, add `await_approval` which calls `interrupt({"synthesis": ..., "verification_result": ...})` and, once resumed, routes to `finalize` (approved) or `graceful_exit` (rejected) based on the resume value. This is additive — it does not change `agent`, `tools`, `synthesize`, or `verifier`. `route_after_verifier`'s conditional-edge target `"finalize"` becomes `"await_approval"`; a new conditional edge `await_approval -> {"finalize", "graceful_exit"}` reads the resume value out of state.

## Q2 — Streaming Agent Progress to a Database

| Approach | Node-level start/end fidelity | Composes with Langfuse handler | Verdict |
|---|---|---|---|
| `stream_mode="updates"` (already used in `src/webhook/app.py`) | **End-only.** Each chunk is `{node_name: state_after_node}` — you learn a node *finished* and what it wrote, never when it *started*. Confirmed in docs: *"Streams only the state updates returned by nodes after each step."* | N/A — it's a driver loop, not a callback; Langfuse tracing is independent and already wired via `config["callbacks"]`. | Good enough for "log what happened," insufficient for "show a live start indicator." |
| `astream_events(version="v2")` | Full fidelity: `on_chain_start`/`on_chain_end` per node (and per LLM call, per tool call) as discrete events with `run_id`, `name`, `data`. This is the standard event-dict format that has been stable since LangChain's callback-events design and is what powers most "live agent trace" UIs. | Runs *through* the same callback-manager machinery as `BaseCallbackHandler` — the Langfuse handler already installed in `config["callbacks"]` fires normally underneath an `astream_events` call; no conflict, both consume the same event stream from different mechanisms. | **Recommended** for the dashboard: gives real start+end boundaries with minimal new code (filter the event dict for `event in {"on_chain_start", "on_chain_end"}` and `name` matching your node names). |
| Custom `BaseCallbackHandler` (`on_chain_start`, `on_chain_end`, `on_tool_start`, `on_tool_end`) | Same fidelity as `astream_events` — they are two views onto the same callback events — but pushed synchronously as a **side effect during the run** rather than pulled by iterating a stream. | Add it to the same `callbacks` list the Langfuse handler occupies; `trace_config()`'s merge behavior (`config["callbacks"] = [*existing, handler]`) already supports appending a second handler without disturbing the first — this is the intended extension point, not a workaround. | **Recommended** as the actual implementation mechanism: a `DBStepLogger(BaseCallbackHandler)` that does `INSERT INTO incident_events` (and `NOTIFY`) on `on_chain_start`/`on_chain_end`/`on_tool_start`/`on_tool_end`, added alongside the Langfuse handler via the existing merge pattern in `tracing.trace_config()`. This avoids owning a second parallel stream-consumption loop next to whatever drives the graph for the HITL/resume logic in Q1. |

**Practical recommendation:** don't choose `astream_events` *or* a callback handler — use a **callback handler fed into the same `config` that already carries the Langfuse handler**, and keep the `.ainvoke()`/`.astream(stream_mode="updates")` loop from Q1 as the *driver* (it decides when to stop for an interrupt). The callback handler is a passive observer bolted onto that same run via `config["callbacks"]`; it doesn't need its own loop.

## Q3 — Live Push to a Browser

- **One dedicated `LISTEN` connection, not one per subscriber.** A pool connection held open per SSE client for the lifetime of that tab would exhaust the pool under a handful of concurrent viewers, since pool connections are meant to be checked out briefly, not parked. The verified pattern (current community consensus, corroborated by multiple 2025-era writeups on this exact combination): open **one** `psycopg.AsyncConnection` in **autocommit mode** at app startup, `await conn.execute("LISTEN incident_events")`, and consume `async for notify in conn.notifies():` in a single background task for the app's lifetime.
- **Fan-out is in-process, not per-client-to-Postgres.** That one listener task republishes each `NOTIFY` payload into an in-process pub/sub structure — the simplest correct version is a `dict[incident_id, set[asyncio.Queue]]` (or `broadcaster`/`anyio` memory streams) that each SSE endpoint subscribes an `asyncio.Queue` into on connect and removes on disconnect. This means the *number of Postgres connections is O(1)*, independent of the number of open browser tabs, which is the entire point of the pattern.
- **Client disconnects** are detected inside the SSE generator loop via `await request.is_disconnected()` (Starlette/FastAPI) checked between yields, or by catching the `asyncio.CancelledError` FastAPI raises into the generator when the client closes the connection — either way, the generator's `finally:` block must remove its queue from the pub/sub dict, or dead subscribers accumulate as a slow memory leak.
- **NOTIFY payload should be small** (event id / incident id / row id), with the SSE handler fetching the actual row from Postgres (or, more simply, having the callback handler pass the full small JSON payload straight into `NOTIFY channel, payload` — Postgres NOTIFY payloads are capped at 8000 bytes, which is fine for one step-event row but not for large tool outputs; truncate or reference-by-id for anything bigger).

## Q4 — Background asyncio Tasks in FastAPI

- **Never fire-and-forget a bare `asyncio.create_task(...)`** — without a live reference the task object can be garbage-collected mid-run (this is explicitly called out in the asyncio docs: "the event loop only keeps weak references to tasks"). Keep a module-level `set[asyncio.Task]` (or a small task-registry object owned by the FastAPI app's lifespan state), add each new task to it, and register `task.add_done_callback(registry.discard)` to self-clean on completion.
- **Bound concurrency** the same way `src/webhook/app.py` already does today with its `threading.BoundedSemaphore` — port that exact idea to `asyncio.Semaphore(WEBHOOK_MAX_CONCURRENCY)` acquired inside the task body, so an alert storm queues agent runs instead of fanning out unbounded concurrent LLM calls.
- **Lifecycle**: start the NOTIFY-listener task and any startup work in FastAPI's `lifespan` context manager (not `@app.on_event("startup")`, which is deprecated), and explicitly `task.cancel()` + `await` it on shutdown so the listener connection closes cleanly.
- **Surviving a process restart** is the reason the checkpointer (Q1) and the `incident_events` table (Q2) must both be in Postgres, not in-memory: an in-flight agent run whose process is killed mid-run is simply gone (no asyncio task survives a restart) — but because the graph state was checkpointed before every pause, and because completed steps are already durably logged, a restart's worst case is "this specific in-flight run must be manually resumed or re-triggered," not "the incident history disappears." There is no mechanism to auto-resume orphaned runs without additional bookkeeping (e.g., a `status='running'` row with a heartbeat) — flag this as an explicit, deferrable scope decision rather than something the base architecture solves for free.

## Q5 — Serving a Vite SPA from FastAPI

- **Production**: `app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")` for the hashed build output, plus a catch-all route (`@app.get("/{full_path:path}")`) that returns `FileResponse("frontend/dist/index.html")` for any path FastAPI's API routes didn't already claim — this is the SPA history-fallback pattern (client-side router paths like `/incidents/123` must 200 with `index.html`, not 404). Register API routes (`/webhook/signoz`, `/api/...`, SSE endpoints) **before** the catch-all, since route matching is order-sensitive.
- **Dev mode**: run Vite's dev server (`npm run dev`, default port 5173) separately from `uvicorn` (port 8080), and let Vite's own `server.proxy` config forward `/api` and `/webhook` to the FastAPI port — this gives hot module reload for the frontend without FastAPI needing to know dev mode exists at all. Do not try to have FastAPI proxy *to* Vite; the standard direction is Vite proxying *to* the backend.

## Integration Points

| Existing component | Modified vs New | Nature of change |
|---|---|---|
| `src/agent/graph.py` | **Modified** | Add `checkpointer=` to `workflow.compile(...)`; add one new `await_approval` node calling `interrupt(...)` between `verifier` and `finalize`; add its conditional edge. `agent_node`/`tools`/`synthesize_node`/`verifier_node`/`finalize_node`/`graceful_exit_node` bodies are unchanged. |
| `src/agent/state.py` | **Unmodified**, or additive only | `interrupt()` needs no new state fields (the resume value is passed via `Command`, not stored in `SREAgentState`) unless the dashboard wants the pending-approval payload persisted for display, in which case add one optional field. |
| `src/webhook/app.py` | **Retired** | Its dedupe logic, `AlertContext` parsing (`src/webhook/alert.py`, untouched), semaphore-bounded concurrency, and the `run_meta_agent`/`run_diagnosis` target dispatch all get ported into the new FastAPI app — this is a lift-and-adapt of the existing logic to `async def` + `asyncio` primitives, not a redesign. |
| `src/agent/tracing.py` | **Unmodified** | `trace_config()`'s merge-not-overwrite `callbacks` behavior is exactly the seam the new `DBStepLogger` callback handler plugs into; no changes needed, just add the second handler at the call site. |
| New: `src/api/app.py` (or similar) | **New** | FastAPI app: webhook route, SSE routes, resume/approve route, StaticFiles mount, lifespan-managed NOTIFY listener task and task registry. |
| New: checkpointer wiring | **New** | `AsyncPostgresSaver` instance (async context manager or held open for app lifetime), `thread_id` = incident dedupe key (reuse `AlertContext.dedupe_key`, already the Langfuse session id — one more reason to keep it as the single incident identity key throughout). |
| New: `incident_events` table + `DBStepLogger` | **New** | Callback handler appended into `config["callbacks"]` alongside the Langfuse handler; writes one row per `on_chain_start`/`on_chain_end`/`on_tool_start`/`on_tool_end`; issues `NOTIFY` per insert (either via a Postgres trigger on the table or an explicit `NOTIFY` call in the same transaction — trigger is more robust since it fires regardless of insert path). |
| New: NOTIFY listener + pub/sub + SSE endpoints | **New** | One `psycopg.AsyncConnection` listener task; in-process `dict[str, set[asyncio.Queue]]`; SSE `StreamingResponse` per client. |
| New: frontend (Vite SPA) | **New** | Dashboard, timeline view, approve/reject controls calling the resume endpoint. |

## Data Flow Changes

1. **Today:** `POST /webhook/signoz` → `threading.Thread` → sync `.stream(stream_mode="updates")` drains to completion or `graceful_exit`, no persistence, no pause, log line is the only output artifact.
2. **v1.7:** `POST /webhook/signoz` → `asyncio.create_task` (tracked, semaphore-bounded) → `.ainvoke(inputs, config={thread_id, checkpointer, callbacks:[langfuse, db_step_logger]})`. Each node's callback events write a row + trigger `NOTIFY`. If the run reaches `await_approval`, the checkpointer persists state, `interrupt()` unwinds, `result["__interrupt__"]` is written as a "pending approval" row, and the task returns (not exits with an error — this is a normal, expected outcome, and the task registry marks it done). Browser dashboard, subscribed via SSE, sees each row live and renders a pending-approval affordance. A human clicks approve/reject in the SPA → new `asyncio.create_task` calls `.ainvoke(Command(resume=decision), config={thread_id})` on the **same** `thread_id`, which resumes `await_approval` (re-running any code before the `interrupt()` call in that node — keep that code empty or idempotent) and proceeds to `finalize`/`graceful_exit`, streaming further rows the same way.

## Suggested Build Order

1. **Postgres + checkpointer plumbing first.** Stand up Postgres, wire `AsyncPostgresSaver`, add `checkpointer=` to `workflow.compile()`, and prove `interrupt()`/`Command(resume=...)` round-trips against `graph.py` directly (no FastAPI yet) — this is the highest-risk unknown (Q1) and everything else depends on the graph being checkpointed. Verify against the *actually installed* `langgraph` version before trusting any `stream_events`/`v3` snippet.
2. **`incident_events` table + `DBStepLogger` callback handler**, tested against the existing `.ainvoke`/`.astream` calls from step 1 — confirms node-level rows land correctly and confirms the merge-into-`callbacks` pattern in `tracing.trace_config()` works unchanged.
3. **New FastAPI app**, porting `src/webhook/app.py`'s dedupe/semaphore/target-dispatch logic to async, wired to steps 1–2. Old Starlette app can be deleted once parity is confirmed.
4. **NOTIFY listener + in-process pub/sub + SSE endpoints**, layered on top of the now-populated `incident_events` table — this has no dependency on the agent internals, only on the table shape from step 2, so it can be built/tested with synthetic rows before step 3 is finished.
5. **Resume/approve HTTP endpoint**, calling `Command(resume=...)` against the checkpointer from step 1 — depends on steps 1 and 3 both existing.
6. **Vite SPA**, consuming the SSE endpoint from step 4 and the resume endpoint from step 5 — last, since it's the only piece with no backend dependents and benefits most from a stable API to build against.
7. **StaticFiles mount + prod build wiring**, once the SPA exists — trivial, do last.

## Anti-Patterns to Avoid

### Anti-Pattern: Treating `remaining_steps` as a HITL gate

**What people might do:** try to reuse the existing `remaining_steps` step-budget field as the mechanism for pausing for human approval.
**Why it's wrong:** `remaining_steps` is a runaway-loop guard (decremented per LLM turn, routes to `graceful_exit` at low values) — it has nothing to do with checkpointing or resumability, and repurposing it conflates two unrelated concerns.
**Do this instead:** a dedicated `await_approval` node calling `interrupt()`, per Q1.

### Anti-Pattern: One Postgres connection per SSE subscriber

**What people might do:** have each SSE endpoint open its own `LISTEN` connection (simplest code, mirrors the mental model of "each client listens").
**Why it's wrong:** connection count scales with open browser tabs, not with incidents; a handful of viewers can exhaust a small connection pool, and most pools aren't designed for connections held open indefinitely.
**Do this instead:** one listener connection, in-process fan-out, per Q3.

### Anti-Pattern: Driving the interrupt-checking loop with `stream_mode="updates"` alone

**What people might do:** keep the exact loop already in `src/webhook/app.py` (`for update in ...stream(stream_mode="updates")`) and look for `"await_approval"` as a node name in the update dict to detect a pause.
**Why it's wrong:** an interrupted run's `__interrupt__` marker is a property of the **result/output**, not a per-node update chunk — `stream_mode="updates"` does not reliably surface it the same way `.invoke()`'s return value or `get_state()` does, per the docs' own recommended detection paths in Q1.
**Do this instead:** use `.ainvoke()` and check `"__interrupt__" in result`, or poll `graph.get_state(config)`.

## Sources

- LangGraph official docs, `docs.langchain.com/oss/python/langgraph/interrupts` — `interrupt()` semantics, `Command(resume=...)`, `thread_id` requirement, node re-execution on resume, idempotency guidance, `__interrupt__` key. Retrieved via context7 (`/websites/langchain_oss_python_langgraph`). Confidence: HIGH (official current docs).
- LangGraph official docs, `docs.langchain.com/oss/python/langgraph/graph-api`, `streaming`, `use-time-travel`, `functional-api`, `checkpointers`, `add-memory` — `stream_mode="updates"` semantics, `AsyncPostgresSaver` setup, `get_state`/`get_state_history`, sync-node-in-async-graph behavior. Retrieved via context7. Confidence: HIGH, with the explicit caveat that the `stream_events(version="v3")` object API shown in some snippets may be ahead of the pinned `langgraph==1.2.10` and needs re-verification against the installed version before use.
- `tom.catshoek.dev/posts/postgres-sse/` and corroborating community writeups on psycopg3 `LISTEN`/`NOTIFY` + FastAPI SSE — single dedicated autocommit `AsyncConnection`, `.notifies()` generator, in-process fan-out pattern. Confidence: MEDIUM (community consensus, not official psycopg/FastAPI documentation, but consistent across multiple independent sources).
- Project source: `src/agent/graph.py`, `src/agent/state.py`, `src/webhook/app.py`, `src/agent/tracing.py` — read directly for this research. Confidence: HIGH (ground truth).

---
*Architecture research for: incimin.io v1.7 Incident Dashboard milestone*
*Researched: 2026-08-08*
=======
|-----------|----------------|------------------------|
| `TopologyManager` | Orchestrates fetching from plugins and persisting to DB. | Python class executing scheduled/triggered tasks. |
| `PluginInterface` | Defines the standard contract for fetching topology data. | Python `abc.ABC` with async methods. |
| `SigNozPlugin` | Connects to SigNoz, fetches traces/topology, translates to standard model. | Concrete implementation of `PluginInterface`. |
| Internal Models | Standardize service nodes and edges with provenance metadata. | Pydantic models with `source`, `external_id`, etc. |
| `db.py` (Memgraph API) | Persists standard models into the graph database. | Async Neo4j/Memgraph driver using Cypher `MERGE`. |

## Recommended Project Structure

```
src/production/
├── main.py                  # MODIFIED: Add endpoint/trigger for topology sync
├── db.py                    # MODIFIED: Add topology merge queries
├── topology/                # NEW
│   ├── __init__.py          # NEW
│   ├── manager.py           # NEW: TopologyManager orchestration
│   ├── models.py            # NEW: Pydantic Canonical Models
│   └── plugins/             # NEW
│       ├── __init__.py      # NEW
│       ├── base.py          # NEW: Plugin abstract base class
│       └── signoz.py        # NEW: SigNozServiceMap plugin
```

### Structure Rationale

- **`topology/`:** Encapsulates the core domain logic for topology abstraction, keeping `main.py` clean.
- **`topology/plugins/`:** Separates concrete implementations from core logic, enabling a plug-and-play architecture for future providers (DataDog, Prometheus).
- **`models.py`:** Ensures a single source of truth for the Canonical Data Model, making it easy to enforce the Entity Metadata Principle.

## Architectural Patterns

### Pattern 1: Strategy Pattern (Plugin Architecture)

**What:** Defines a standard `PluginInterface` for topology providers. The `TopologyManager` uses the interface without knowing provider-specific details.
**When to use:** When you need to integrate with multiple disparate external systems that provide logically similar data (e.g., service maps from different OTel backends).
**Trade-offs:** Adds some boilerplate (interfaces, dynamic loading or registry), but is strictly required for the "Extensible Architecture" goal.

**Example:**
```python
from abc import ABC, abstractmethod
from typing import List
from .models import ServiceEdge

class TopologyPlugin(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str:
        pass

    @abstractmethod
    async def fetch_topology(self) -> List[ServiceEdge]:
        """Fetch and parse topology into canonical internal format."""
        pass
```

### Pattern 2: Canonical Data Model with Provenance

**What:** Translate external payloads immediately into an internal standardized format containing required provenance (`source`, `external_id`, `fetched_at`, `schema_version`).
**When to use:** Always, as per the `AGENTS.md` Entity Metadata Principle. Never store a bare external payload as an internal entity.
**Trade-offs:** Requires writing explicit mapping layers in each plugin, but guarantees database integrity and traceable lineage.

**Example:**
```python
from pydantic import BaseModel
from datetime import datetime

class ServiceNode(BaseModel):
    name: str
    # Provenance fields (Entity Metadata Principle)
    source: str
    external_id: str
    fetched_at: datetime
    schema_version: str = "1.0"
```

## Data Flow

### Request Flow (Topology Sync)

```
[API Trigger or Cron]
    ↓
[TopologyManager.sync()]
    ↓
    ├──→ [SigNozPlugin.fetch_topology()] 
    │       ↓
    │    (Query SigNoz API / ClickHouse)
    │       ↓
    │    (Map to Canonical ServiceNode/Edge Models)
    │       ↓
    ←─── (Return List[ServiceEdge])
    ↓
[db.py (merge_topology)]
    ↓
    (Execute Cypher MERGE with Metadata)
    ↓
[Memgraph Database]
```

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 0-100 Services | Synchronous fetch and monolithic Cypher merge query. |
| 100-1,000 Services | Batch inserts in Cypher; paginate external plugin fetches. |
| 1,000+ Services | Async message queue (Kafka/Redis) to stream topology updates; delta-based graph updates instead of full sync. |

### Scaling Priorities

1. **First bottleneck:** Large Cypher transactions blocking the Memgraph event loop. Fix by batching nodes/edges in chunks of 500.
2. **Second bottleneck:** SigNoz API rate limits or slow clickhouse queries for full topology extraction. Fix by requesting only recent telemetry window (e.g., last 1h).

## Anti-Patterns

### Anti-Pattern 1: Bare External Payloads

**What people do:** Save the raw JSON response from SigNoz directly into Memgraph node properties.
**Why it's wrong:** Violates the Entity Metadata Principle. Makes it impossible to know where the data came from, when it was fetched, or how to map it to future DataDog data.
**Do this instead:** Plugins must map the external data into the canonical `ServiceNode` / `ServiceEdge` models, attaching `source`, `external_id`, `fetched_at`, and `schema_version`.

### Anti-Pattern 2: Hardcoding Provider Logic in the Manager

**What people do:** Writing `if provider == 'signoz': do_signoz_stuff()` inside the `TopologyManager`.
**Why it's wrong:** Violates Open-Closed Principle. Adding a new provider requires modifying the core orchestration layer.
**Do this instead:** Use the Strategy Pattern. The Manager iterates over registered implementations of `TopologyPlugin` and calls `fetch_topology()`.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| SigNoz API/ClickHouse | REST/SQL via `SigNozPlugin` | Needs to handle authentication and connection pooling. Only the plugin should know about SigNoz internals. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Manager ↔ Plugins | Python Async Method Call | Plugins return standardized Pydantic models. |
| Manager ↔ `db.py` | Python Async Method Call | `db.py` requires canonical models to construct correct Cypher `MERGE` queries guaranteeing metadata. |

## Suggested Build Order

To properly handle dependencies and ensure smooth integration into the existing FastAPI backend, follow this sequence:

1. **Phase 1: Canonical Models (`topology/models.py`)** 
   - Define `ServiceNode` and `ServiceEdge` Pydantic models.
   - Enforce the Entity Metadata Principle (`source`, `external_id`, `fetched_at`, `schema_version`).
2. **Phase 2: Plugin Interface (`topology/plugins/base.py`)**
   - Create the abstract base class defining the contract for `fetch_topology()`.
3. **Phase 3: Data Access Layer (`db.py` modified)**
   - Add Cypher queries (`merge_topology`) to ingest canonical models into Memgraph.
   - Ensure the query sets the provenance fields.
4. **Phase 4: SigNoz Plugin (`topology/plugins/signoz.py`)**
   - Implement the interface. Connect to SigNoz, fetch topology, and translate it to the canonical models.
5. **Phase 5: Topology Manager (`topology/manager.py`)**
   - Build the orchestration logic that registers plugins, invokes them, and passes the result to `db.py`.
6. **Phase 6: API Integration (`main.py` modified)**
   - Wire the `TopologyManager` to a FastAPI endpoint (e.g., `/api/v1/topology/sync`) or a startup event for triggering the sync.

---
*Architecture research for: Plugin-based Service Topology Integration*
*Researched: 2026-08-06*
>>>>>>> Stashed changes
