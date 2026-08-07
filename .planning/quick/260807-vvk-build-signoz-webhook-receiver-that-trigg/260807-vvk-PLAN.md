---
phase: quick
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - "src/agent/mcp_client.py"
  - "src/agent/diagnosis.py"
  - "src/webhook/__init__.py"
  - "src/webhook/app.py"
  - "src/agent/llm.py"
  - ".env"
  - ".env.example"
autonomous: true
requirements: [QUICK-VVK]
must_haves:
  truths:
    - A SigNoz alert POSTed to /webhook/signoz triggers the meta-agent and returns 200 immediately
    - The meta-agent names a root cause from topology + change-log evidence, or says "insufficient evidence"
    - get_system_events is fanned out in parallel over a single MCP session
  artifacts:
    - src/agent/mcp_client.py
    - src/agent/diagnosis.py
    - src/webhook/app.py
  key_links: []
---

<objective>
Wire a SigNoz alert into the existing meta-agent so that an incoming alert autonomously produces a root-cause diagnosis.

Purpose: close the loop between alerting and diagnosis — today the agent must be invoked by hand.
Output: an HTTP webhook receiver, a reusable MCP client with parallel fanout, and the diagnosis flow that ties them together.
</objective>

<context>
@.planning/STATE.md
@CLAUDE.md
</context>

<verified_facts>
Established empirically in session 2026-08-07. Ground truth — do not re-derive.

1. **MCP server** `incimin-sre` at `https://nirmal-mcp.ngrok.app/mcp/sse`, legacy HTTP+SSE:
   `GET /mcp/sse` → SSE stream whose first `event: endpoint` carries `/mcp/messages?session_id=<hex>`.
   JSON-RPC is POSTed there; responses return on the SSE stream, matched by `id`.
   Tools: `get_service_topology(service_name, max_depth=3)`, `get_system_events(service_name, start_time, end_time)`.
   No resources, no prompts.
   - topology → `[{"source": str, "rel_type": "DEPENDS_ON"|"CALLS", "target": str}]`
   - events → `[{"timestamp","repository_url","commit_sha","source"}]`

2. **Parallel fanout is the main latency lever.** All `get_system_events` calls issued concurrently over one
   session and collected by id: 8 components in 3.7s, versus ~25s *each* serially.

3. **Topology edges are duplicated** across `DEPENDS_ON` and `CALLS` — 14 raw edges collapse to 7 unique.
   Merge on `(source, target)` or every dependency is double-weighted.

4. **Change events are duplicated per deploy** — the same `commit_sha` appears under both
   `source: "webhook_simulation"` and `source: "github_webhook"`. Dedupe on `commit_sha`, else a
   double-recorded service outranks a singly-recorded one.

5. **`src/agent/llm.py:43` hardcodes `temperature=0`**, which Claude 5 rejects with
   `400 invalid_request_error: "temperature is deprecated for this model"`. Verified working without it.
   `timeout=10.0` is also too tight for an agent turn.

6. **`.env` is misconfigured**: `LLM_PROVIDER=openrouter` with an empty key, while `ANTHROPIC_API_KEY` is
   populated and valid. `ANTHROPIC_MODEL=claude-3-5-sonnet-20240620` is retired (404).
   Working: `claude-sonnet-5`, `claude-opus-5`.

7. **`starlette` 1.3.1 and `uvicorn` 0.52.1 are already installed.** `fastapi`/`flask` are not, and must not
   be added — CLAUDE.md locks the stack.

8. **SigNoz telemetry is unavailable.** The API key authenticates but resolves to user
   `00000000-0000-0000-0000-000000000000`; every data endpoint 403s. Nothing here may depend on reading
   SigNoz logs, traces, or alert rules.
</verified_facts>

<tasks>

<task type="auto">
  <name>Task 1: MCP client with parallel fanout</name>
  <files>src/agent/mcp_client.py</files>
  <action>
  Implement a client for the legacy HTTP+SSE MCP transport:
  - `MCPSession` context manager: opens the SSE stream on a background thread, captures the session
    endpoint from the first `event: endpoint`, performs `initialize` + `notifications/initialized`.
  - `call_tool(name, args, timeout)` → parsed JSON result.
  - `call_tool_many([(name, args), ...])` → issues every request before awaiting any, collects by
    JSON-RPC id, returns results in input order. This is the fanout in fact 2.
  - Endpoint from `INCIMIN_MCP_URL`, defaulting to the ngrok URL, so it swaps to a local server
    with no code change.
  - Tool errors and timeouts return a structured error rather than raising, so one bad component
    cannot abort a whole diagnosis.
  </action>
  <verify>Call get_service_topology("checkout") and a multi-service get_system_events fanout against the live server; confirm the fanout completes in seconds rather than tens of seconds.</verify>
  <done>Both tools callable; fanout demonstrably concurrent.</done>
</task>

<task type="auto">
  <name>Task 2: Diagnosis flow + llm.py/.env fixes</name>
  <files>src/agent/diagnosis.py, src/agent/llm.py, .env, .env.example</files>
  <action>
  `diagnose(alerting_service, alert_time, window_hours)`:
  1. `get_service_topology(alerting_service, max_depth=1)`
  2. merge duplicate edges on `(source, target)` → related component set (fact 3)
  3. fan `get_system_events` across all related components in parallel (fact 2)
  4. dedupe events on `commit_sha` (fact 4)
  5. LLM synthesis → root cause, reasoning tied to specific evidence, evidence gaps.
     Must fail closed: say "insufficient evidence" rather than guess.
  Return a structured result, not a prose blob, so the caller can log/assert on it.

  Fix `llm.py`: drop `temperature=0`, raise the timeout.
  Fix `.env` and `.env.example`: `LLM_PROVIDER=anthropic`, `ANTHROPIC_MODEL=claude-sonnet-5`.
  </action>
  <verify>Run diagnose("checkout") end-to-end; confirm it names payment off the abc123badcommit deploy, and that removing the change evidence flips it to "insufficient evidence".</verify>
  <done>Diagnosis returns a grounded root cause; fail-closed path verified.</done>
</task>

<task type="auto">
  <name>Task 3: SigNoz webhook receiver</name>
  <files>src/webhook/__init__.py, src/webhook/app.py</files>
  <action>
  Starlette app, `POST /webhook/signoz`, Alertmanager-format payload.
  - Extract the alerting service defensively across `service`, `service_name`, `serviceName`,
    `service.name` in `labels`, falling back to `annotations`, then to an alertname heuristic.
  - Extract fire time from `startsAt`, falling back to now.
  - Ignore `status: "resolved"` payloads — only fire on active alerts.
  - Return 200 immediately and run the diagnosis on a background thread (fact: senders retry on slow
    responses; the flow takes ~10s).
  - An unparseable payload logs and still returns 200 — never crash the sender.
  - `GET /health` for liveness.
  </action>
  <verify>POST a captured Alertmanager payload at the running server; confirm immediate 200 and a diagnosis in the log. POST a malformed body; confirm 200 and no traceback.</verify>
  <done>Webhook accepts SigNoz alerts and triggers diagnosis without blocking the sender.</done>
</task>

</tasks>

<risks>
- The exact SigNoz service label key is unconfirmed against a real fired alert (SigNoz API is 403, fact 8).
  Mitigated by parsing defensively across the common variants and degrading to a logged 200. Tighten once a
  real payload is captured.
- The ngrok MCP URL rotates when Nirmal's tunnel restarts. Mitigated by `INCIMIN_MCP_URL`.
- Reaching this webhook from a remote SigNoz needs a public tunnel; none is installed locally. Out of scope
  here — the receiver is testable via localhost POST.
</risks>
