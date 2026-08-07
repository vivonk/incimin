---
phase: quick
plan: 01
status: complete
date: 2026-08-07
requirements: [QUICK-VVK]
files_modified:
  - "src/agent/mcp_client.py"
  - "src/agent/diagnosis.py"
  - "src/agent/llm.py"
  - "src/webhook/__init__.py"
  - "src/webhook/alert.py"
  - "src/webhook/app.py"
  - "tests/test_webhook.py"
---

# Quick VVK — SigNoz webhook -> meta-agent

## What shipped

A SigNoz alert POSTed to `/webhook/signoz` now triggers the LangGraph **meta-agent**
(`src/agent/graph.py`) with the alert message and its metadata.

- `src/webhook/alert.py` — payload -> `AlertContext` (alertname, service, severity, status, fire
  time, message, labels, annotations, generatorURL, fingerprint, raw). `to_prompt()` renders all of
  it into the human turn the Coordinator receives, ending with an explicit
  `topology_tool with source="<service>"` instruction so the fixed sub-agent order starts correctly.
- `src/webhook/app.py` — Starlette receiver. Parses, filters, and dispatches to the meta-agent on a
  background thread. `INCIMIN_WEBHOOK_TARGET=diagnosis` switches to the MCP change-log flow
  (`src/agent/diagnosis.py`) instead.
- `src/agent/mcp_client.py`, `src/agent/diagnosis.py`, `src/agent/llm.py` — Tasks 1 and 2 of the plan
  (MCP client with parallel fanout, diagnosis flow, llm.py timeout/temperature fixes).
- `tests/test_webhook.py` — 18 tests, all passing, no API key or data plane needed.

## Design decisions

- **Always 200, never blocking.** Measured: response in 0.02s while an 18s agent run continued in the
  background. Alert senders retry on slow responses; a retry storm would multiply LLM cost.
- **Lazy import of `src.agent.graph`.** That module builds an LLM at import time and raises without
  an API key. Importing it inside the worker keeps the receiver serving (and the app importable in
  tests) so a config error is one log line per alert, not a dead process.
- **Repeat suppression** on `fingerprint` (`WEBHOOK_DEDUPE_SECONDS`, default 300). Alertmanager
  re-sends firing alerts every `repeat_interval`; without this each resend starts another agent run.
- **Concurrency cap** (`WEBHOOK_MAX_CONCURRENCY`, default 2). An alert storm should queue, not fan
  out into N concurrent LLM-bound runs.
- **Defensive service extraction** across seven label spellings, labels before annotations. Still
  unconfirmed against a real fired SigNoz alert (SigNoz API is 403 — plan fact 8); a miss is a
  logged skip, not a crash.

## Verified

End-to-end against a live alert payload: 200 in 0.02s, then the meta-agent called all three
sub-agents in the prescribed order with the alert's service —
`graph_bfs_tool(source=paymentservice)`, `clickhouse_log_tool(paymentservice)`,
`qdrant_runbook_tool("paymentservice high 5xx error rate")`. Each sub-agent returned a connection
error because the Docker data plane was not running, which is the intended degrade path.

## Open items

- **`.env` still has `LLM_PROVIDER=openrouter` with an empty key** (plan fact 6), so the first run
  failed with `OPENROUTER_API_KEY is required`. The verification run above used
  `LLM_PROVIDER=anthropic ANTHROPIC_MODEL=claude-sonnet-5`. `.env`/`.env.example` are outside this
  session's file permissions — flip them by hand.
- **The final-answer log read `meta-agent produced no final message`** on the verification run. Every
  sub-agent had errored, so the graph took the `synthesis=None` -> verifier -> `graceful_exit` path;
  the `graceful_exit` AIMessage did not surface in the `stream(stream_mode="updates")` output the
  webhook reads. Sub-agent dispatch is confirmed working; the terminal-node extraction needs one more
  pass against a live data plane.
