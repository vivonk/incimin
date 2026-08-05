# Pitfalls Research

**Domain:** AI SRE agent — LangGraph + Memgraph + SigNoz/ClickHouse + Qdrant on Docker Compose
**Researched:** 2026-08-05
**Confidence:** HIGH (all critical items verified against official docs, source code, or confirmed GitHub issues)

---

## Critical Pitfalls

### Pitfall 1: SigNoz Port 8080 Collision with OTel Demo Frontend

**What goes wrong:**
SigNoz Foundry (the current supported install method, replacing the deprecated `deploy/` Compose files as of v0.130.0) runs its UI on port 8080. The OTel Astronomy Shop's Envoy frontend-proxy also binds to host port 8080. Both cannot bind simultaneously. The stack silently fails to start one of them.

**Why it happens:**
The old SigNoz Docker Compose used port 3301 for its UI. The new Foundry-based deployment changed to 8080. Anyone working from old tutorials or training data will miss this. The OTel demo's `.env` hardcodes `ENVOY_PORT=8080`.

**How to avoid:**
In the SigNoz casting.yaml, override the UI port to 3301 (or any unused port). In the OTel demo `.env`, change `ENVOY_PORT` to 8090. Assign ports explicitly in the master `docker-compose.override.yml` that glues all stacks together. Audit all port bindings before Day 1 build starts using `docker ps --format "{{.Ports}}"`.

**Warning signs:**
`bind: address already in use` errors during `docker compose up`. One service starts but shows connection refused at the expected URL. Running `lsof -i :8080` shows two competing processes.

**Phase to address:** Phase 1 (Infrastructure Setup) — resolve all port assignments before any other work begins.

**Demo risk:** During a live demo, if the presenter switches browser tabs between SigNoz and the OTel demo frontend, only one will load. If not pre-tested on the exact demo machine, this kills the demo.

---

### Pitfall 2: OTel Demo Telemetry Does Not Reach SigNoz Without Explicit Pipeline Configuration

**What goes wrong:**
The OTel Astronomy Shop has its own internal OTel Collector (`otel-collector` service). By default, this collector exports to Jaeger and OpenSearch (its bundled observability stack), not to SigNoz. Simply running both stacks side-by-side produces zero telemetry in SigNoz.

**Why it happens:**
The OTel demo's `compose.observability.yaml` overlays configure exporters for Jaeger/Prometheus/OpenSearch only. The OTel Collector config merge behavior (documented in `otelcol-config-observability.yml`) **replaces** arrays rather than appending, so adding a SigNoz exporter requires explicitly repeating all existing exporters in the new config layer. Most teams assume the OTel demo "just sends telemetry" to any OTel endpoint they stand up.

**How to avoid:**
Create a custom `otelcol-config-signoz.yml` that adds a `otlp_grpc/signoz` exporter pointing to `signoz-otel-collector:4317` and re-declares all pipelines with all required exporters. Mount this as an additional `--config` layer. Verify telemetry arrives in SigNoz within 5 minutes of startup using the SigNoz Services page before writing any agent code.

**Warning signs:**
SigNoz Services page shows no services after 10+ minutes of the OTel demo running. ClickHouse `distributed_logs_v2` table returns zero rows. No traces visible in SigNoz Trace Explorer.

**Phase to address:** Phase 1 (Infrastructure Setup) — telemetry pipeline must be proven end-to-end before Phase 2 begins.

**Demo risk:** The entire demo narrative depends on the agent finding logs for the `paymentservice`. If no telemetry reaches SigNoz, the agent returns empty results and the RCA fails silently. This is an invisible failure unless you pre-test.

---

### Pitfall 3: ClickHouse Timestamp Is in Nanoseconds, Not Milliseconds

**What goes wrong:**
The agent's ClickHouse log query tool constructs dynamic SQL with time range filters. If the timestamp comparison uses Unix milliseconds (Python's `datetime.timestamp() * 1000`), zero rows are returned because SigNoz's `distributed_logs_v2.timestamp` column stores nanoseconds. The query succeeds with no error but returns empty results.

**Why it happens:**
Confirmed in SigNoz source: `NANOSECOND = 1000000000` is the conversion constant applied to input timestamps. The column is `timestamp` (not `timestamp_ns`), but its values are nanosecond-epoch integers. Python's `time.time()` returns seconds; multiplying by 1e3 gives milliseconds, but the correct multiplier is 1e9.

**How to avoid:**
Standardize all time generation in the agent tools to: `int(time.time() * 1e9)`. Add a unit test asserting that a query for the last 5 minutes against the live ClickHouse returns at least one row. Use `ts_bucket_start` in the WHERE clause alongside `timestamp` (SigNoz query builder uses both for primary key optimization).

**Warning signs:**
Queries that target recent time windows return 0 rows. The same query with no time filter returns rows. Manually running `SELECT max(timestamp) FROM signoz_logs.distributed_logs_v2` returns a large integer (~1.7e18).

**Phase to address:** Phase 2 (Agent Tool: ClickHouse log query) — validate the timestamp unit explicitly.

**Demo risk:** Empty log results make the agent's RCA narrative incomplete. The agent will synthesize a root cause without supporting log evidence, potentially hallucinating or producing a weak answer during the live demo.

---

### Pitfall 4: LangGraph Agent Loops Indefinitely When Tools Return Empty Results

**What goes wrong:**
When the ClickHouse query returns zero rows (wrong time range, wrong service name) or the Qdrant search finds no matching runbook, the LLM re-invokes tools in a retry loop rather than terminating. With the default `recursion_limit=25`, the graph hits `GraphRecursionError` mid-demo — which surfaces as an exception traceback in the Streamlit UI.

**Why it happens:**
Standard ReAct behavior: the LLM interprets empty tool results as a reason to try different queries. Without a hard termination condition (or proactive `RemainingSteps` monitoring), the agent will cycle through tool variants until the recursion limit. `GraphRecursionError` is raised as an uncaught exception if not wrapped.

**How to avoid:**
Set `recursion_limit=10` (sufficient for a 3-tool deterministic RCA). Implement a proactive `RemainingSteps` guard node that routes to a graceful "insufficient data" response when `remaining_steps <= 2`. Wrap `graph.invoke()` in a `try/except GraphRecursionError` at the Streamlit layer with a user-visible error message. Tool return types must include an empty-result signal (e.g., `{"rows": [], "status": "no_data"}`) rather than `None`.

**Warning signs:**
Agent appears to "think" indefinitely with repeated tool calls to the same endpoint. Streamlit spinner runs for >30 seconds. Tool call log shows the same Cypher query executed 3+ times.

**Phase to address:** Phase 2 (LangGraph state machine design) — set recursion limit and termination routing at graph construction time.

**Demo risk:** A RecursionError traceback is the most visually damaging failure during a live demo. It also exposes the implementation stack. Non-recoverable without restarting Streamlit.

---

### Pitfall 5: Memgraph Data Is Lost on Container Restart (Default In-Memory Mode)

**What goes wrong:**
Memgraph's default storage mode is `IN_MEMORY_TRANSACTIONAL`. The seed script that populates the 14-node service topology runs once during setup. If the Memgraph container is restarted (Docker Compose `restart: unless-stopped` doesn't prevent this during demo-machine reboots), all graph data is gone and the topology traversal tool returns empty.

**Why it happens:**
WAL files and snapshots are written to `/var/lib/memgraph` inside the container. Without a Docker volume mount, this path is ephemeral. The `memgraph/memgraph-mage` image does not persist data between container restarts by default.

**How to avoid:**
Mount a named Docker volume to `/var/lib/memgraph`: `volumes: - memgraph_data:/var/lib/memgraph`. Also make the seed script idempotent (use `MERGE` not `CREATE` for nodes) so it can be safely re-run without creating duplicates if data already exists. Verify with `MATCH (n) RETURN count(n)` immediately before demo starts.

**Warning signs:**
Agent's Cypher BFS query returns 0 nodes. `MATCH (n) RETURN count(n)` in Memgraph Lab returns 0. No service nodes visible in the Lab graph view.

**Phase to address:** Phase 1 (Infrastructure Setup) — volume mount must be in the compose file from the start.

**Demo risk:** If the demo machine was shut down the night before the demo, all topology data is gone. No volume = guaranteed demo failure.

---

### Pitfall 6: Streamlit AsyncIO Event Loop Conflict with LangGraph `.astream()`

**What goes wrong:**
When the LangGraph client is cached with `@st.cache_resource` and `.astream()` is used for streaming tool events, the second conversation turn raises `RuntimeError: Event loop is closed`. Streamlit creates a temporary event loop to handle async generators, then tears it down. Cached LangGraph clients retain references to the closed loop.

**Why it happens:**
Confirmed in Streamlit GitHub issue #12076 (open as of 2026-08): when `st.write_stream` receives an async generator, it creates a temporary event loop. On the second execution, `@st.cache_resource` returns the same LangGraph graph object, whose internal HTTP client (for LLM calls) holds a reference to the now-closed loop.

**How to avoid:**
Use synchronous `.stream()` (not `.astream()`) with `@st.cache_resource`. If streaming token-by-token is required, use a sync generator wrapper around `.stream()` with `stream_mode="messages"`. Do not mix `@st.cache_resource` with async generators. Alternatively, recreate the graph object per session using `st.session_state` instead of `@st.cache_resource`.

**Warning signs:**
Works on first user message, fails on second. `RuntimeError: Event loop is closed` in Streamlit logs. The app requires a page refresh after every agent invocation.

**Phase to address:** Phase 3 (Streamlit UI integration) — validate multi-turn conversation before declaring the UI complete.

**Demo risk:** A live demo always involves at least two queries: the setup question and the incident question. The second query will fail if this is not resolved.

---

### Pitfall 7: Memgraph BFS Syntax Is Not Compatible with Neo4j/Standard Cypher

**What goes wrong:**
The agent's topology traversal tool uses Cypher. Queries written using Neo4j-style `shortestPath()` or `allShortestPaths()` functions fail silently or raise syntax errors in Memgraph. The demo's Cypher queries must use Memgraph's native BFS syntax.

**Why it happens:**
Memgraph implements `*BFS` as a relationship pattern modifier, not as a function. Neo4j uses `shortestPath((:A)-[*]-(:B))`. Memgraph uses `MATCH p = (:A)-[*BFS]->(:B) RETURN p`. LLM-generated Cypher (if the agent ever generates queries dynamically) defaults to Neo4j syntax from training data.

**How to avoid:**
All Cypher queries in the agent tools must be static, pre-written strings (not dynamically generated by the LLM). Use Memgraph's `[*BFS]` syntax for topology traversal. Include a smoke test: run the BFS query against the live Memgraph instance during the Phase 1 infrastructure validation step. Document the exact query strings in the codebase with a comment explaining why Neo4j syntax does not apply.

**Warning signs:**
`SyntaxError: Invalid input 'shortestPath'` from Memgraph. Traversal returns zero paths between nodes that are demonstrably connected. Cypher queries work in a Neo4j instance but fail in Memgraph.

**Phase to address:** Phase 2 (Cypher BFS tool implementation) — test against live Memgraph, not a Neo4j sandbox.

**Demo risk:** Topology traversal is the first and most visually impressive tool call in the demo. A syntax error here breaks the entire RCA chain.

---

### Pitfall 8: Qdrant Collection Recreation Fails if Vector Dimension Changes

**What goes wrong:**
If the runbook embedding script is run twice — once with one embedding model (e.g., OpenAI `text-embedding-3-small` at 1536 dims) and once with a different model (e.g., a local model at 768 dims) — Qdrant rejects the upsert with a dimension mismatch error. Worse, if the collection name stays the same but dimensions change, all subsequent queries silently return garbage results or raise errors.

**Why it happens:**
Qdrant collections lock their vector size at creation time. Changing the embedding model requires deleting and recreating the collection. In a 3-day sprint where models might be swapped for cost/latency reasons, this is a common mid-sprint breakage.

**How to avoid:**
Pin the embedding model in a single configuration constant and never change it mid-sprint. Include `recreate_collection=True` (or delete-then-create) in the hydration script so it is idempotent. After hydration, verify: `client.get_collection("runbooks").vectors_count` should match the number of runbook files seeded.

**Warning signs:**
`ValueError: Vector dimension mismatch` from Qdrant. Semantic search returns irrelevant results or empty sets. Collection shows correct point count but searches return wrong runbooks.

**Phase to address:** Phase 2 (Qdrant hydration) — pin embedding model before writing the hydration script.

**Demo risk:** Wrong runbook returned during the live incident scenario breaks the remediation narrative. The agent will recommend the wrong fix for the chaos-injected failure.

---

### Pitfall 9: Total Stack RAM Exceeds 16GB on Demo Machine

**What goes wrong:**
The combined memory requirement of all services is approximately 13–16 GB:
- OTel Astronomy Shop (full mode): ~6 GB
- OTel Astronomy Shop (minimal mode, no Kafka): ~3 GB
- SigNoz (ClickHouse + ingestion + query service): ~4 GB
- Memgraph MAGE (demo scale): ~500 MB
- Qdrant: ~200 MB
- LangGraph agent + Streamlit: ~500 MB

On a 16 GB MacBook, running the full OTel demo + SigNoz simultaneously leaves ~2–3 GB free, causing ClickHouse to OOM-kill or ClickHouse Keeper to enter a segfault restart loop (a documented issue with Docker Desktop on macOS).

**How to avoid:**
Use OTel demo **minimal mode** (`docker compose -f compose.yaml -f compose.minimal.yaml up`) to reduce footprint to ~3 GB. This disables Kafka and dependent services. Verify the paymentservice is still included in minimal mode (it is; only Kafka-dependent services are dropped). Allocate at least 14 GB to Docker Desktop's memory limit under Preferences > Resources. The demo machine should have 32 GB RAM for comfort.

**Warning signs:**
ClickHouse container exits with code 137 (OOM). `docker stats` shows containers at memory limits. SigNoz ingestion falls behind. Streamlit responses are slow even before any agent logic runs.

**Phase to address:** Phase 1 (Infrastructure Setup) — validate stack memory footprint on the actual demo machine.

**Demo risk:** OOM failures are non-deterministic and tend to appear under load (i.e., when the chaos injection script fires and telemetry volume spikes). This is exactly the worst time for a container restart.

---

### Pitfall 10: Memgraph Lab "Live Graph Highlighting" Requires Manual Intervention

**What goes wrong:**
The PROJECT.md goal of "Memgraph Lab live node-highlighting as agent traverses" implies real-time graph updates in the browser as the agent's BFS runs. Memgraph Lab does not auto-refresh or subscribe to graph changes. It displays query results only when a query is explicitly executed.

**Why it happens:**
Memgraph Lab is a query-and-visualize tool, not a reactive graph visualization dashboard. There is no WebSocket subscription mechanism that pushes node highlights to an open browser tab. The "live" effect requires either: (a) polling from the Streamlit UI side, or (b) a post-traversal approach where the agent logs the traversal path and the user runs a highlighting query in Lab manually.

**How to avoid:**
Design the demo flow as: agent completes traversal → agent returns the list of traversed nodes → presenter runs a pre-written Cypher query in Memgraph Lab (`MATCH path = ...` using the identified service names) → Lab renders the highlighted subgraph. This is a 2-step visual that still reads well. Do not build a real-time streaming architecture just for demo aesthetics. Alternatively, embed a D3/pyvis graph in Streamlit itself using the traversal results.

**Warning signs:**
No automatic graph update in Memgraph Lab when the agent runs. Expecting `MATCH (n) WHERE n.highlighted = true RETURN n` to update in real time — it won't.

**Phase to address:** Phase 3 (Demo choreography) — the dual-screen visual must be rehearsed, not assumed to work automatically.

**Demo risk:** The split-screen demo visual is a centerpiece. If the presenter expects Lab to auto-update and it doesn't, there's an awkward pause. Pre-scripting the Lab query execution as a step in the demo script eliminates this risk.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hardcoded Cypher query strings in tool functions | No query builder needed for demo | Fragile when service names or schema change; no parameter injection safety | Acceptable for 3-day demo if strings are extracted to a constants file |
| `qdrant_client.QdrantClient(":memory:")` instead of server mode | No Docker service needed during development | Data lost on process restart; cannot test against prod-realistic Qdrant | Only in unit tests; use server mode from Day 1 for integration |
| Static `recursion_limit=10` | Prevents infinite loops | Will fail for multi-hop incidents requiring >10 steps | Acceptable for demo with known 3-tool flow |
| Single LangGraph graph instance in `st.session_state` | Simple code | No conversation isolation between users (single-user demo assumption) | Acceptable for single-org demo; must be revisited for multi-user |
| No retry logic on Bolt/ClickHouse/Qdrant tool calls | Simpler code | Network hiccup during demo = unhandled exception | Never — add 1-retry wrapper to all tool calls before demo day |
| Direct ClickHouse SQL without parameterization | Fast development | SQL injection risk if service names ever come from user input | Acceptable for agent-generated queries with validated service name inputs only |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|-----------------|
| OTel Demo → SigNoz | Assuming telemetry flows automatically because both use OTel | Add `otlp_grpc/signoz` exporter in a custom OTel Collector overlay config; repeat all pipeline exporters (arrays replace, don't merge) |
| Python → Memgraph (Bolt) | Using `neo4j` Python driver v4 without setting `--bolt-server-name-for-init` | Memgraph < 2.11 requires `--bolt-server-name-for-init=Neo4j/5.2.0`; use `neo4j` driver v5+ or `pymgclient` for compatibility |
| Python → ClickHouse | Using `clickhouse-driver` (TCP port 9000) vs `clickhouse-connect` (HTTP port 8123) | `clickhouse-connect` is the official modern client; TCP driver has known async compatibility issues in threaded environments |
| Python → Qdrant | Not setting `prefer_grpc=True` | gRPC (port 6334) has lower latency than HTTP for vector search; matters if search is in the agent's hot path |
| LangGraph → Streamlit | Using `.astream()` with `@st.cache_resource` | Use `.stream()` (sync) with `@st.cache_resource`, or use `.astream()` without caching |
| SigNoz ClickHouse → Agent SQL | Writing `WHERE timestamp >= time.time() * 1000` | ClickHouse `timestamp` column is nanoseconds: use `int(time.time() * 1e9)` |
| Memgraph → Agent Cypher | Using `shortestPath()` function from Neo4j docs | Use `[*BFS]` pattern: `MATCH p = (a)-[*BFS]->(b) RETURN p` |
| Docker Compose → SigNoz install | Using old `deploy/` compose files from SigNoz GitHub | Those are deprecated as of v0.130.0; use Foundry (`foundryctl cast`) |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| ClickHouse query without `ts_bucket_start` filter | Slow queries even on small datasets | Include `ts_bucket_start >= bucket AND ts_bucket_start <= bucket` alongside `timestamp` filter (SigNoz uses composite primary key) | At demo scale — ClickHouse full table scans on cold data take >5 seconds |
| Qdrant search without payload index | Slow filtered search on `metadata.service` field | Create payload index on filter fields before hydrating: `client.create_payload_index(collection_name, field_name, field_schema)` | Demo scale is small enough this may not surface, but adds 200ms+ per search |
| Memgraph BFS without index on `name` property | BFS requires full node scan to find start node | `CREATE INDEX ON :Service(name)` before seeding topology | With 14 nodes, this is microseconds; critical at production scale |
| LangGraph `graph.invoke()` in Streamlit main thread | Blocks all UI updates during LLM inference | Use `st.status` expander with `with st.status("Analyzing...") as status:` to give visual feedback; the blocking is inherent to sync invoke | Becomes visually broken at >10 second tool chains |

---

## "Looks Done But Isn't" Checklist

- [ ] **OTel telemetry pipeline:** Telemetry shows in SigNoz Services page after OTel demo starts — verify by querying `SELECT count(*) FROM signoz_traces.distributed_signoz_index_v2 WHERE timestamp > now() - INTERVAL 5 MINUTE`
- [ ] **Memgraph topology persistence:** After `docker compose restart memgraph`, `MATCH (n) RETURN count(n)` returns 14 (not 0)
- [ ] **Qdrant hydration:** After running the seed script, `client.count("runbooks").count` equals the number of runbook files; semantic search for "payment timeout" returns the correct runbook
- [ ] **LangGraph multi-turn:** Second agent query (after the first succeeds) does not raise `RuntimeError: Event loop is closed`
- [ ] **Chaos injection repeatability:** Running the chaos script twice produces the same telemetry signature — no state accumulation
- [ ] **Port audit:** `docker ps --format "table {{.Names}}\t{{.Ports}}"` shows no two services sharing a host port
- [ ] **Timestamp sanity:** ClickHouse time range query for "last 5 minutes" returns non-zero rows from `distributed_logs_v2`
- [ ] **Demo machine memory:** `docker stats --no-stream` shows all containers within their limits; no container has been OOM-killed since stack start

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Port collision discovered during demo | HIGH | Cannot fix live; requires pre-assigned fallback ports in the compose file |
| No telemetry in SigNoz | HIGH | Restart OTel demo with correct collector config overlay; takes 5–10 minutes to re-accumulate data |
| Empty Memgraph graph (no volume) | MEDIUM | Re-run seed script; takes ~30 seconds; add volume to compose before next restart |
| GraphRecursionError mid-demo | HIGH | Wrap in try/except at Streamlit layer with graceful "insufficient data" message; restart required to clear state |
| Async event loop error | MEDIUM | Refresh Streamlit page (F5); switch to sync `.stream()` to prevent recurrence |
| Wrong timestamp unit (empty results) | MEDIUM | Fix constant in tool code; no data loss, just a code fix and re-test |
| Qdrant dimension mismatch | MEDIUM | Delete collection, re-run hydration script with correct model; 2–5 minutes |
| OOM (ClickHouse killed) | HIGH | Switch to OTel demo minimal mode; increase Docker Desktop memory limit; requires full stack restart |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Port collision (SigNoz 8080 vs OTel 8080) | Phase 1: Infrastructure | `docker ps` shows no port collisions; both UIs load |
| No telemetry in SigNoz | Phase 1: Infrastructure | SigNoz Services page shows all 14 OTel demo services |
| ClickHouse nanosecond timestamps | Phase 2: Log query tool | Unit test: query for last 5 min returns rows |
| LangGraph recursion loop | Phase 2: State machine | Manually trigger empty-result tool scenario and verify graceful termination |
| Memgraph data loss on restart | Phase 1: Infrastructure | `docker compose restart memgraph && MATCH (n) RETURN count(n)` returns 14 |
| Async event loop (Streamlit + LangGraph) | Phase 3: UI integration | Run 3+ consecutive queries in the Streamlit UI without error |
| Memgraph BFS syntax | Phase 2: Cypher tool | BFS query against live Memgraph returns expected path |
| Qdrant dimension mismatch | Phase 2: Qdrant hydration | `client.count("runbooks").count` matches file count; search returns correct result |
| RAM overcommit | Phase 1: Infrastructure | `docker stats` baseline check on demo machine |
| Memgraph Lab not auto-refreshing | Phase 3: Demo choreography | Rehearse the manual Lab query step; document in demo script |

---

## Sources

- SigNoz install docs (Docker + Foundry): https://signoz.io/docs/install/docker/
- SigNoz ClickHouse table/column constants (verified from source): `pkg/query-service/constants/constants.go`, `pkg/query-service/app/logs/v4/query_builder.go` — DB: `signoz_logs`, table: `distributed_logs_v2`, timestamp: nanoseconds
- SigNoz traces DB: `signoz_traces`, table: `distributed_signoz_index_v2`
- OTel demo Docker deployment requirements: https://opentelemetry.io/docs/demo/docker-deployment/ — 6 GB full, 3 GB minimal
- OTel demo compose files and `.env`: https://github.com/open-telemetry/opentelemetry-demo — ENVOY_PORT=8080
- OTel demo collector config merge behavior (REPLACES arrays): `src/otel-collector/otelcol-config-observability.yml` inline comment
- LangGraph recursion handling (proactive vs reactive): LangGraph Graph API docs — `GraphRecursionError`, `RemainingSteps`
- Streamlit + LangGraph async event loop bug: https://github.com/streamlit/streamlit/issues/12076 (open)
- Memgraph Docker quickstart (ports 7687, 7444, Lab on 3000): https://memgraph.com/docs/getting-started/install-memgraph/docker
- Memgraph data durability (WAL + snapshots, default path `/var/lib/memgraph`): https://memgraph.com/docs/fundamentals/data-durability
- Memgraph storage modes (default: IN_MEMORY_TRANSACTIONAL): https://memgraph.com/docs/fundamentals/storage-memory-usage
- Memgraph vs Neo4j Cypher differences (BFS syntax): https://memgraph.com/docs/querying/differences-in-cypher-implementations — `[*BFS]` replaces `shortestPath()`
- Memgraph GitHub issue: `node_classification module fails to load due to collections.so name collision` (MAGE module loading issue)
- Qdrant Python client (local vs server mode): https://github.com/qdrant/qdrant-client
- Qdrant default config (storage path, no in-memory default): `config/config.yaml`
- SigNoz ClickHouse connection (Docker exec): https://signoz.io/docs/operate/clickhouse/connect-to-clickhouse/
- ClickHouse Keeper segfault on Docker Desktop (WSL note in SigNoz docs): https://signoz.io/docs/install/docker/

---
*Pitfalls research for: AI SRE agent — LangGraph + Memgraph + SigNoz/ClickHouse + Qdrant*
*Researched: 2026-08-05*
