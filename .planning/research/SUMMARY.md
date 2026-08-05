# Project Research Summary

**Project:** incimin.io — AI SRE Agent
**Domain:** AIOps / Autonomous Incident Response
**Researched:** 2026-08-05
**Confidence:** HIGH

## Executive Summary

incimin is an autonomous AI SRE agent that performs deterministic root-cause analysis by unifying three operational data planes: live service topology (Memgraph graph DB), high-velocity telemetry (SigNoz/ClickHouse), and human operational knowledge (Qdrant vector store). The central architectural insight validated by research is that graph-traversal-based RCA is a genuine differentiation from every competitor (PagerDuty AIOps, Datadog Watchdog, Grafana IRM) — all of which use statistical correlation or LLM inference for topology reasoning. By delegating topology traversal to Cypher BFS and SQL generation to structured tool functions, the agent avoids the hallucination problem that has historically caused enterprise distrust of AI SRE products. The LLM handles only two things: choosing which tool to call and composing the final synthesis — both are low-risk applications of LLM capability.

The recommended build approach is a 5-phase sequence gated by infrastructure readiness. The entire three-data-plane architecture must be standing and verified before any agent code is written. The most dangerous failure mode is building the agent against mock or assumed data while leaving the data pipeline integration for the end — when a live demo exposes that the OTel telemetry never reached SigNoz, or Memgraph lost its topology on restart, recovery takes 30+ minutes and is unrecoverable mid-demo. All data plane seeding (Memgraph topology, Qdrant runbooks, ClickHouse telemetry) is parallelizable across a 2-3 person team once Docker Compose is stable, which is the primary mechanism to hit the 48-hour build constraint.

The critical risks are infrastructure-level and well-documented: (1) SigNoz Foundry changed its UI port to 8080, colliding with the OTel demo's frontend-proxy — port assignments must be locked in the Compose file before Day 1 build begins; (2) Memgraph is in-memory by default and requires a Docker volume mount or all topology is lost on container restart; (3) ClickHouse timestamps in SigNoz are nanoseconds, not milliseconds — a wrong constant in the log query tool produces silently empty results; (4) LangGraph's ReAct loop will recurse to the limit if tools return empty results, surfacing a traceback in the Streamlit UI during the live demo if not explicitly guarded. All four are preventable with one-time infrastructure validation gates.

---

## Key Findings

### Recommended Stack

The stack is fully locked by the project constraints and all versions have been verified against live PyPI and Docker Hub APIs as of 2026-08-05. Python 3.12 is the required runtime — Python 3.13 triggers an untested numpy branch in GQLAlchemy. The single most important dependency constraint is the `numpy<2.0` pin: GQLAlchemy 1.10.0 declares `numpy>=1.26.4,<2.0` and will raise `ImportError` at runtime with numpy 2.x installed. The `neo4j` driver must also be locked at `<6.0.0` (5.28.1 is current) because GQLAlchemy depends on the 5.x API.

For the 3-day demo, `fastembed` with `BAAI/bge-small-en-v1.5` (384-dim, ~130MB download) eliminates the OpenAI embedding dependency entirely. The `MemorySaver` LangGraph checkpointer is sufficient for demo — no PostgreSQL needed. SigNoz must be deployed via `foundryctl` (Foundry v0.2.17); the old `deploy/docker-compose.yaml` path is deprecated as of SigNoz v0.130.0.

**Core technologies:**
- **Python 3.12** — runtime; full ecosystem support, avoids 3.13 lag
- **LangGraph 1.2.10 + langgraph-prebuilt 1.1.0** — agent state machine; `create_react_agent` + `ToolNode` provide the ReAct loop without manual graph wiring
- **memgraph/memgraph-mage:3.12.0** — topology plane; single image includes MAGE BFS/DFS Cypher procedures; must NOT use plain `memgraph/memgraph` (missing MAGE)
- **GQLAlchemy 1.10.0** — Memgraph ORM; pin `numpy<2.0` or import fails at runtime
- **qdrant/qdrant:v1.19.0 + qdrant-client 1.19.0 + fastembed 0.8.0** — knowledge plane; fastembed handles in-process embedding with no external API call
- **clickhouse-connect 1.6.0** — telemetry query; official ClickHouse HTTP client with async; never use legacy `clickhouse-driver`
- **SigNoz Foundry v0.2.17 (signoz v0.135.1)** — observability stack via `foundryctl cast`; ClickHouse pinned at `24.1.2.5`
- **Streamlit 1.61.0** — demo UI; `st.status` expanders provide glass-box tool-call visibility at zero frontend cost
- **Pydantic 2.13.4** — state schema validation; LangGraph requires Pydantic v2

### Expected Features

**Must have (v1 demo and pilot):**
- Correlated RCA narrative from alert to recommendation — the core product without which nothing else matters
- Deterministic Memgraph BFS topology traversal — the hallucination-free differentiator; auditable step-by-step
- Qdrant runbook grounding — elevates output from generic advice to team-specific next action
- Glass-box tool-call trace UI (`st.status` expanders) — enterprise trust and audit requirement
- Recommendation-only enforcement — explicit constraint; must be enforced in code, not convention
- Sub-60-second end-to-end latency — the quantifiable metric that makes value concrete in a demo

**Should have (v1.x after pilot validation):**
- Alert deduplication / noise grouping
- Blast radius estimation (BFS + health join) — natural Memgraph extension, low cost
- Incident timeline reconstruction — required for post-mortem artifacts
- Slack/PagerDuty push integration — required when pilot team needs agent output in existing workflow
- Incident similarity / precedent retrieval — valuable after 3-6 months of history accumulates

**Defer (v2+):**
- RBAC / access control — design schema with RBAC hooks from day one even if enforcement defers
- Predictive anomaly flagging — defer until reactive RCA is trusted
- Multi-tenant SaaS — strategic post-PMF decision
- Automated remediation execution — only after ITIL/CAB change management integration is designed

**Hard anti-features (never build):**
- LLM-inferred service topology — hallucinated dependencies cause catastrophic RCA errors
- Alert suppression without explicit reasoning
- Replacement observability dashboard

### Architecture Approach

The architecture follows a strict four-layer design: Presentation (Streamlit + Memgraph Lab), Agent Orchestration (LangGraph StateGraph ReAct loop), Data Plane (three-plane separation: topology/telemetry/knowledge), and Telemetry Ingestion (SigNoz OTel Collector from OTel Astronomy Shop). The critical structural rule is tool isolation: each of the three tools touches exactly one data store. The LLM selects which tool to call and passes string parameters; all query construction is programmatic inside tool functions. This is the architectural mechanism that delivers the hallucination-free guarantee.

**Major components:**
1. **LangGraph StateGraph** — `SREAgentState` TypedDict with `add_messages` reducer + typed `IncidentContext`; `recursion_limit=10`; sync `.stream(stream_mode="updates")` for Streamlit
2. **graph_bfs_tool** — Memgraph Cypher BFS using `[*BFS]` syntax (NOT Neo4j `shortestPath()`); programmatic Cypher from service name string
3. **clickhouse_log_tool** — parameterized SQL against `signoz_logs.distributed_logs` with nanosecond timestamps (`int(time.time() * 1e9)`)
4. **qdrant_tool** — semantic search over `runbooks` collection with payload metadata filtering; fastembed in-process embedding
5. **Streamlit app** — sync `graph.stream()` for-loop with `st.status` expanders; never `.astream()` (event loop conflict)
6. **Docker Compose stack** — explicit version tags; named volume for Memgraph persistence; port audit pre-Day 1

### Critical Pitfalls

1. **SigNoz port 8080 collision with OTel demo frontend** — assign SigNoz UI to 3301, OTel `ENVOY_PORT` to 8090; run `docker ps` port audit as Phase 1 gate before any other work

2. **OTel telemetry does not flow to SigNoz without explicit pipeline config** — OTel Collector config arrays REPLACE on overlay (not append); create custom `otelcol-config-signoz.yml` re-declaring all pipeline exporters plus `otlp_grpc/signoz`; verify SigNoz Services page shows 14 services before Phase 2

3. **Memgraph loses all topology on container restart** — add `volumes: - memgraph_data:/var/lib/memgraph` from day one; seed script must use `MERGE` not `CREATE`

4. **ClickHouse timestamps are nanoseconds, not milliseconds** — use `int(time.time() * 1e9)` in all time range filters; unit test that last-5-minute query returns rows against live ClickHouse

5. **LangGraph recursion loop on empty tool results** — `recursion_limit=10` at graph compile; `RemainingSteps` guard node routing to "insufficient data" when `remaining_steps <= 2`; wrap in `try/except GraphRecursionError`

6. **Streamlit async event loop destroyed between requests** — sync `.stream()` only with `@st.cache_resource`; validate 3+ consecutive queries before declaring UI complete

7. **Memgraph BFS syntax differs from Neo4j** — `[*BFS]` not `shortestPath()`; all Cypher strings must be static pre-written, never LLM-generated

8. **Stack RAM approaches 16GB** — OTel demo minimal mode; 14GB Docker Desktop allocation; validate on demo machine before Day 1

---

## Implications for Roadmap

### Phase 1: Infrastructure Foundation
**Rationale:** Port collision, missing telemetry pipeline, Memgraph without persistence, and RAM overcommit are all Phase 1 failures with no in-sprint recovery path. Zero code is written until all verification gates pass.
**Delivers:** Full Compose stack running; 14 OTel demo services sending telemetry to SigNoz; Memgraph and Qdrant reachable with persistent storage; port audit clean; memory baseline within limits.
**Verification gate:** SigNoz Services page shows all 14 services; `MATCH (n) RETURN count(n)` after `docker compose restart memgraph` returns 14; `docker ps` shows no port conflicts; `docker stats` shows no OOM kills.

### Phase 2: Data Plane Initialization (Parallel Tracks)
**Rationale:** All three data planes must be independently seeded and verified before any end-to-end agent testing. These tracks are independent and run simultaneously across the team.
**Delivers:** Memgraph: 14 nodes + edges, BFS smoke-tested with `[*BFS]` syntax. Qdrant: `runbooks` collection hydrated (≥3 runbooks, 384-dim fastembed, semantic search verified). ClickHouse: nanosecond timestamp arithmetic validated, ERROR log rows confirmed for paymentservice.

### Phase 3: Agent Core
**Delivers:** `SREAgentState` TypedDict; three `@tool` decorated functions; `StateGraph` with `recursion_limit=10` and `RemainingSteps` guard; unit tests for all three tools with mock clients.

### Phase 4: UI Integration and Demo Choreography
**Delivers:** `ui/app.py` with sync `graph.stream()` for-loop and `st.status` expanders; multi-turn validated (3+ consecutive queries); `chaos_inject.py`; Memgraph Lab BFS query scripted and rehearsed.

### Phase 5: Golden Path Validation
**Delivers:** Full golden path demo runnable; all PITFALLS.md checklist items verified; demo script written including the Memgraph Lab manual query step; <60s latency confirmed.

---

## Research Flags

- **ClickHouse table name discrepancy:** PITFALLS.md references `distributed_logs_v2`; ARCHITECTURE.md uses `distributed_logs`. Resolve with `SHOW TABLES FROM signoz_logs` against running SigNoz v0.135.1 in Phase 1.
- **OTel demo minimal mode service list:** Confirm paymentservice, checkoutservice, and frontendservice are present in minimal mode before committing to it.
- **Memgraph Lab automation vs manual:** If fully automated graph highlighting is required (vs rehearsed manual query), the `SET n.highlighted = true` side-effect approach needs prototyping in Phase 4.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified from live PyPI API and Docker Hub API on 2026-08-05 |
| Features | MEDIUM-HIGH | Enterprise SRE patterns HIGH; competitor feature versioning MEDIUM |
| Architecture | HIGH | Verified against LangGraph source, SigNoz constants.go, production RCA agent implementations |
| Pitfalls | HIGH | All critical pitfalls verified against official docs, GitHub issues, or source code |

**Overall confidence: HIGH**

---

*Research completed: 2026-08-05*
*Ready for roadmap: yes*
