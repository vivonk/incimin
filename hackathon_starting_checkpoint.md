# Hackathon Starting Checkpoint

**Project:** incimin.io — AI SRE agent. Alert fires → agent traverses the live service graph, correlates telemetry, returns root cause with supporting evidence.

**State as of 2026-08-08:** milestones v1.5 and v1.6 shipped (phases 1–9 complete). No milestone in progress.

## Infrastructure (running via `docker compose up -d`)

- `compose.yaml` includes three stacks: `compose.core.yaml` (Memgraph+MAGE, Memgraph Lab), `compose.signoz.yaml` (SigNoz + OTel Collector + ClickHouse, deployed via foundryctl `casting.yaml`), `compose.otel-demo.yaml` (OTel Astronomy Shop demo app).
- `scripts/verify_stack.py` — 13-check infrastructure gate.
- `scripts/verify_data_planes.py` — one-command check across topology + telemetry.

## Two data planes — both seeded and verified

| Plane | Store | Built |
|---|---|---|
| Topology | Memgraph | `scripts/init_memgraph.py`, `scripts/check_topo.py` |
| Telemetry | ClickHouse (`signoz_logs.distributed_logs_v2`) | `scripts/check_tele.py` |

## Agent (`src/agent/`)

- **Multi-agent LangGraph meta-agent** (`graph.py`): coordinator LLM ↔ tools loop → synthesize (structured output) → deterministic verifier → finalize / graceful_exit.
- **Two sub-agents** (`subagents/`): `topology.py` (BFS over Memgraph → candidate services), `telemetry.py` (ClickHouse error evidence). Wrapped as LangGraph tools returning `Command` state updates (`tools.py`).
- **Verifier** (`subagents/verifier.py`): pure deterministic Layer-1 gates — evidence grounding, cross-modal consistency, temporal ordering. Layer 2 (LLM judge) intentionally not implemented.
- **State schema** (`state.py`): `Evidence`, `Synthesis`, `VerificationResult`, `SREAgentState`.
- **Alternate flow** (`diagnosis.py`): alert → MCP `get_service_topology` + `get_system_events` → LLM synthesis, fail-closed prompt.
- **LLM provider** (`llm.py`): pluggable via `LLM_PROVIDER` — anthropic (default) / gemini / openrouter.

## Production services (`src/production/`)

- `main.py` — FastAPI ingestion API on :8000. `POST /webhook` (deploy events), `POST /webhook/pr-merge`; background topology sync loop on startup.
- `db.py` — ClickHouse + Memgraph persistence.
- `topology/` — plugin architecture: `models.py` (Pydantic `ServiceNode`/`ServiceEdge` with entity-metadata provenance, UUID5 deterministic IDs), `plugin.py` (ABC), `manager.py` (registry), `repository.py` (Cypher MERGE upserts), `plugins/signoz.py` (live SigNoz dependency-graph provider).
- `mcp_server.py` — MCP server exposing `get_service_topology` and `get_system_events`, mounted over SSE on the main app. Registered in `.mcp.json` (via ngrok remote).

## Webhook receiver (`src/webhook/`)

- `POST /webhook/signoz` — Alertmanager-format alerts → meta-agent. Always-200 + background thread, repeat suppression (`WEBHOOK_DEDUPE_SECONDS`), concurrency cap, lazy agent import. Target switchable between `agent` and `diagnosis` via `INCIMIN_WEBHOOK_TARGET`.

## UI (`src/ui/`)

- `app.py` — Streamlit chat with `st.status` glass-box tool-call visibility, streaming from the agent graph.

## Tests

- 66 tests across 10 files (`tests/`): agent tools, graph, subagents, verifier, webhook, topology, plugin, signoz plugin, llm provider, ui. Run with `uv run pytest`.
- 65 pass; `tests/test_signoz_plugin.py::test_signoz_plugin_fetch` fails (pre-existing — the plugin skips every fixture entity as "missing parent/child").

## Simulation / demo tooling

- `scripts/chaos_inject.py`, `scripts/simulate_events.py`, `scripts/simulate_scenarios.py`, `scripts/simulate_webhooks.py`, `scripts/verify_golden_path.py`.
- `docs/otel-demo-scenarios.md` — 8 triage scenarios; `docs/demo/DEMO_SCRIPT.md`, `DEMO.md`.
- Reference docs: `docs/ARCHITECTURE.md`, `docs/CLICKHOUSE_SCHEMA.md`, `docs/PORTS.md`, `docs/OTEL_DEMO_SERVICES.md`, `docs/RESOURCE_BASELINE.md`.

## Not built yet

- No milestone/roadmap defined beyond v1.6 — next phase is open.
- **No knowledge/runbook plane.** Qdrant, fastembed, the retriever sub-agent, and `docs/runbooks/` were removed on 2026-08-08 — the agent names a root cause and cites evidence, but does not recommend remediation.
- Verifier Layer 2 (LLM judgment) deferred.
- No auth, multi-session, or production checkpointer (still `MemorySaver`).
