# Architecture Research

**Domain:** AI SRE Incident Response Agent — multi-plane observability + graph topology + vector knowledge
**Researched:** 2026-08-05
**Confidence:** HIGH (verified against LangGraph source, soul-bits/rca-agent production implementation, SigNoz source, Memgraph docs, Qdrant client source)

---

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PRESENTATION LAYER                            │
│  ┌──────────────────────────┐   ┌────────────────────────────────┐  │
│  │  Streamlit Chat UI        │   │  Memgraph Lab (port 3000)      │  │
│  │  st.status expanders      │   │  Live node-highlight via Bolt  │  │
│  │  Tool-call glass-box view │   │  WebSocket / Cypher WATCH      │  │
│  └────────────┬─────────────┘   └────────────────────────────────┘  │
└───────────────┼─────────────────────────────────────────────────────┘
                │  stream_mode="updates"+"messages"
┌───────────────┼─────────────────────────────────────────────────────┐
│                      AGENT ORCHESTRATION LAYER                       │
│  ┌────────────▼─────────────────────────────────────────────────┐   │
│  │              LangGraph StateGraph (Python)                    │   │
│  │                                                               │   │
│  │  START → [agent_node] ──(has tool_calls?)──► [tools_node]    │   │
│  │               ▲                                    │          │   │
│  │               └────────────────────────────────────┘          │   │
│  │                         ↓ (no tool_calls)                     │   │
│  │                       [synthesize_node] → END                 │   │
│  │                                                               │   │
│  │  State: AgentState { messages: Annotated[list, add_messages] │   │
│  │                       incident_context: IncidentContext }     │   │
│  └───────────────────────────────────────────────────────────────┘   │
│         Tools: graph_bfs_tool | clickhouse_log_tool | qdrant_tool    │
└───────────────────────────────────────────────────────────────────────┘
                │              │                │
         Bolt (7687)    HTTP (8123)       HTTP (6333)
┌──────────────┼──────────────┼────────────────┼──────────────────────┐
│                         DATA PLANE LAYER                              │
│  ┌───────────▼──────┐  ┌───▼───────────┐  ┌──▼──────────────────┐  │
│  │  Memgraph         │  │  ClickHouse   │  │  Qdrant             │  │
│  │  Topology Plane   │  │  Telemetry    │  │  Knowledge Plane    │  │
│  │                   │  │  Plane        │  │                     │  │
│  │  14 Service nodes │  │  (via SigNoz) │  │  Runbook vectors    │  │
│  │  DEPENDS_ON edges │  │  signoz_logs  │  │  Postmortem embeds  │  │
│  │  BFS traversal    │  │  .distributed │  │  metadata filter    │  │
│  │  + MAGE algos     │  │  _logs table  │  │  cosine similarity  │  │
│  └──────────────────┘  └───────────────┘  └─────────────────────┘  │
└───────────────────────────────────────────────────────────────────────┘
                                    ▲
                          OTLP gRPC (4317)
┌───────────────────────────────────┼──────────────────────────────────┐
│                     TELEMETRY INGESTION LAYER                         │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  SigNoz OTel Collector → ClickHouse Writer → signoz_logs DB     │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  OTel Astronomy Shop (14 instrumented microservices)             │ │
│  │  accounting | ad | cart | checkout | currency | email |          │ │
│  │  frontend | frontend-proxy | kafka | payment | product-catalog   │ │
│  │  quote | recommendation | shipping                               │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

| Component | Responsibility | Key Interface |
|-----------|----------------|---------------|
| **LangGraph StateGraph** | Orchestrates the RCA loop: LLM reasoning → tool dispatch → result accumulation → synthesis | Python in-process; compiled graph called via `.stream()` |
| **agent_node** | Calls LLM with current messages + system prompt; LLM decides which tool to call next | LangChain ChatModel + bound tools |
| **tools_node** | Executes the tool the LLM selected; writes `ToolMessage` back to state | `ToolNode` from `langgraph.prebuilt` |
| **synthesize_node** | Final LLM call once all evidence is in state; emits structured RCA report | LLM with `response_format` structured output |
| **graph_bfs_tool** | Cypher BFS traversal on Memgraph to return affected service + upstream/downstream neighbors | `gqlalchemy` or raw `pymgclient` over Bolt 7687 |
| **clickhouse_log_tool** | SQL query to `signoz_logs.distributed_logs` filtered by service_name + time window | `clickhouse-connect` HTTP 8123 |
| **qdrant_tool** | Semantic vector search over embedded runbooks + postmortems; returns top-k with metadata filter | `qdrant-client` HTTP 6333 |
| **Memgraph** | In-memory graph DB storing service topology (nodes = services, edges = DEPENDS_ON); BFS source of truth | Bolt wire protocol; Cypher; MAGE modules |
| **ClickHouse** (via SigNoz) | Columnar log + trace storage; table `signoz_logs.distributed_logs` | HTTP SQL interface |
| **Qdrant** | Vector store for runbook/postmortem embeddings; `payload` filtering by `service` or `incident_type` | REST/gRPC |
| **SigNoz OTel Collector** | Receives OTLP from all services; routes to ClickHouse | OTLP gRPC 4317 |
| **Streamlit UI** | Chat interface; renders agent steps via `st.status` + `stream_mode="updates"` | Python `graph.stream()` |
| **Memgraph Lab** | Live graph visualization; highlights traversed nodes | Browser WebSocket to Bolt 7687; read-only Cypher |

---

## Data Flow

### Primary RCA Flow (End-to-End)

```
User types: "Checkout latency is spiking"
    │
    ▼
[Streamlit] calls graph.stream({"messages": [HumanMessage(query)]},
                               stream_mode=["updates", "messages"])
    │
    ▼
[agent_node] — LLM sees system prompt + incident message
              LLM emits: AIMessage(tool_calls=[graph_bfs_tool(service="checkout")])
    │
    ▼ (should_continue returns Send("tools", tool_call))
[tools_node] — executes graph_bfs_tool
              → Cypher BFS: MATCH path = (s:Service {name:"checkout"})-[:DEPENDS_ON*1..3]-(n) RETURN n
              → Returns: [checkout, payment, cart, currency, productcatalog]
              → Writes ToolMessage(result=service_list) to state.messages
    │
    ▼ (back to agent_node)
[agent_node] — LLM sees tool result
              LLM emits: AIMessage(tool_calls=[clickhouse_log_tool(services=[...], window_minutes=15)])
    │
    ▼
[tools_node] — executes clickhouse_log_tool
              → SQL: SELECT timestamp, body, severity_text, trace_id
                     FROM signoz_logs.distributed_logs
                     WHERE resources_string['service.name'] IN ('checkout','payment',...)
                       AND timestamp >= now() - INTERVAL 15 MINUTE
                       AND severity_text IN ('ERROR','WARN')
                     ORDER BY timestamp DESC LIMIT 50
              → Returns: error log rows as JSON
              → Writes ToolMessage(result=logs_json) to state.messages
    │
    ▼ (back to agent_node)
[agent_node] — LLM decides runbook lookup is needed
              LLM emits: AIMessage(tool_calls=[qdrant_tool(query="payment service crash checkout latency")])
    │
    ▼
[tools_tool] — executes qdrant_tool
              → Embeds query with sentence-transformers
              → client.search(collection="runbooks", query_vector=...,
                              query_filter=Filter(must=[FieldCondition(key="service", match=MatchValue("payment"))]),
                              limit=3)
              → Returns: [runbook chunks + metadata]
    │
    ▼ (back to agent_node)
[agent_node] — LLM has all evidence; no more tool_calls needed
              → routes to END path / synthesize_node
    │
    ▼
[synthesize_node OR final agent_node output]
              → Structured output: {root_cause, affected_services, evidence_chain, remediation_steps}
    │
    ▼
[Streamlit] renders each step as st.status expander as stream events arrive
            "graph_bfs_tool: traversed 5 services" → st.status(state="complete")
            "clickhouse_log_tool: 23 ERROR logs found" → st.status(state="complete")
            "qdrant_tool: runbook retrieved" → st.status(state="complete")
            Final answer rendered as st.markdown in main chat area
```

### Telemetry Ingestion Flow (OTel → ClickHouse)

```
OTel Astronomy Shop service
    │ OTLP gRPC (4317) → logs, traces, metrics
    ▼
SigNoz OTel Collector (otelcol-contrib)
    │ ClickHouse Exporter
    ▼
ClickHouse
    Tables: signoz_logs.distributed_logs
            signoz_traces.distributed_trace_index
            signoz_metrics.*
```

### ClickHouse Log Table Structure (MEDIUM confidence — sourced from SigNoz constants.go)

Key columns in `signoz_logs.distributed_logs`:
- `timestamp` — UInt64 nanoseconds
- `id` — String (log ID)
- `trace_id`, `span_id` — String (OTel correlation)
- `severity_text` — String (`INFO`, `WARN`, `ERROR`)
- `severity_number` — UInt8
- `body` — String (log message)
- `resources_string` — `Map(String, String)` — contains `service.name` key
- `attributes_string` — `Map(String, String)` — custom attributes
- `attributes_number` — `Map(String, Float64)`

**Agent log query pattern:**
```sql
SELECT timestamp, body, severity_text, trace_id, span_id,
       resources_string['service.name'] as service_name
FROM signoz_logs.distributed_logs
WHERE resources_string['service.name'] IN ('paymentservice', 'checkoutservice')
  AND timestamp >= toUnixTimestamp64Nano(now64() - toIntervalMinute(15))
  AND severity_text IN ('ERROR', 'WARN')
ORDER BY timestamp DESC
LIMIT 50
```

### Memgraph Topology Data Model

```cypher
// Nodes
(:Service {name: "checkoutservice", language: "go", version: "1.0"})
(:Service {name: "paymentservice", language: "java", version: "1.0"})

// Edges (dependency direction: A DEPENDS_ON B = A calls B)
(checkoutservice)-[:DEPENDS_ON]->(paymentservice)
(checkoutservice)-[:DEPENDS_ON]->(cartservice)
(checkoutservice)-[:DEPENDS_ON]->(currencyservice)
(checkoutservice)-[:DEPENDS_ON]->(productcatalogservice)
(checkoutservice)-[:DEPENDS_ON]->(shippingservice)
(checkoutservice)-[:DEPENDS_ON]->(emailservice)

// BFS query for agent traversal
MATCH path = (s:Service {name: $service_name})-[:DEPENDS_ON*1..3]-(n:Service)
RETURN DISTINCT n.name, length(path) as hop_distance
ORDER BY hop_distance
```

---

## LangGraph State Machine Design Patterns

### Pattern 1: Custom State with Incident Context (RECOMMENDED over bare AgentState)

The built-in `AgentState` (just `messages`) is sufficient for the demo but add a typed context field for clean evidence accumulation:

```python
from typing import Annotated, TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

class IncidentContext(TypedDict):
    query: str
    affected_services: list[str]       # populated by graph_bfs_tool
    log_evidence: list[dict]           # populated by clickhouse_log_tool
    runbook_context: str | None        # populated by qdrant_tool

class SREAgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    incident_context: IncidentContext  # structured evidence accumulation
```

**Why:** The `add_messages` reducer on `messages` handles message list merging automatically. The `incident_context` field gives nodes direct access to structured evidence without re-parsing tool messages. Do not use a plain dict — TypedDict gives IDE completion and Pydantic validation.

### Pattern 2: Tool Definition with @tool Decorator

```python
from langchain_core.tools import tool
from typing import Annotated

@tool
def graph_bfs_tool(
    service_name: Annotated[str, "The service to start BFS traversal from"],
    max_hops: Annotated[int, "Maximum hop distance, default 3"] = 3,
) -> str:
    """Traverse the service dependency graph using BFS. Returns all services
    reachable from the named service within max_hops. Use this first to
    identify blast radius before querying logs."""
    # Execute Cypher BFS against Memgraph
    results = memgraph_client.execute(
        "MATCH path=(s:Service {name:$svc})-[:DEPENDS_ON*1..$hops]-(n) "
        "RETURN DISTINCT n.name, length(path) as hop",
        {"svc": service_name, "hops": max_hops}
    )
    return json.dumps([{"service": r["n.name"], "hops": r["hop"]} for r in results])
```

**Critical constraint:** Tool functions must be synchronous OR the graph must be compiled for async with `astream()`. For the demo's Streamlit integration, sync tools with `graph.stream()` is simpler and avoids event loop nesting.

### Pattern 3: Routing via Conditional Edges (ReAct loop)

```python
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

def should_continue(state: SREAgentState) -> str:
    messages = state["messages"]
    last = messages[-1]
    # If LLM made tool calls → execute them
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    # Otherwise → done
    return END

builder = StateGraph(SREAgentState)
builder.add_node("agent", agent_node)
builder.add_node("tools", ToolNode(tools=[graph_bfs_tool, clickhouse_log_tool, qdrant_tool]))
builder.set_entry_point("agent")
builder.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
builder.add_edge("tools", "agent")
graph = builder.compile()
```

**Note:** As of LangGraph v0.2+, `create_react_agent` handles this automatically. Use it unless you need custom routing logic. The v2 API dispatches tool calls in parallel via `Send` — if the LLM emits multiple tool_calls in one step, all fire concurrently.

### Pattern 4: Streaming to Streamlit with st.status

```python
# In streamlit app
with st.chat_message("assistant"):
    for event in graph.stream(
        {"messages": [HumanMessage(content=user_query)]},
        stream_mode="updates",  # emits {node_name: state_delta} dicts
    ):
        for node_name, state_delta in event.items():
            if node_name == "tools":
                # Extract tool results from messages
                for msg in state_delta.get("messages", []):
                    if hasattr(msg, "name"):  # ToolMessage
                        with st.status(f"{msg.name}", state="complete"):
                            st.json(json.loads(msg.content)[:5])  # preview
            elif node_name == "agent":
                # Check if final answer (no tool calls)
                for msg in state_delta.get("messages", []):
                    if hasattr(msg, "content") and not getattr(msg, "tool_calls", []):
                        st.markdown(msg.content)
```

**stream_mode options (HIGH confidence — from LangGraph types.py):**
- `"updates"` — emits `{node_name: state_delta}` after each node completes; best for showing step progress
- `"messages"` — emits LLM tokens as they stream; best for streaming the final answer text
- `["updates", "messages"]` — combine both; use for the full glass-box experience

### Pattern 5: Tool Isolation (Determinism Guarantee)

The core architectural constraint from PROJECT.md: "Zero LLM hallucinations in the critical path." Enforce it structurally:

```
agent_node:    LLM decides WHAT to query (tool selection + parameters)
tools_node:    Executes the query DETERMINISTICALLY (no LLM in this path)
synthesize:    LLM interprets results (only place LLM reasons about data)
```

**Never:** Put Cypher generation inside the LLM's reasoning. The LLM passes `service_name` as a string; the tool function generates the Cypher programmatically.

**Never:** Put ClickHouse SQL generation inside the LLM's reasoning. The tool generates SQL from the service list returned by the graph tool.

---

## Recommended Project Structure

```
incimin.io/
├── agent/
│   ├── graph.py              # StateGraph definition, compiled graph export
│   ├── state.py              # SREAgentState TypedDict
│   ├── nodes/
│   │   ├── agent_node.py     # LLM call with bound tools; returns AIMessage
│   │   └── synthesize_node.py # Optional: final structured output node
│   └── tools/
│       ├── graph_tool.py     # graph_bfs_tool — Memgraph Cypher BFS
│       ├── logs_tool.py      # clickhouse_log_tool — signoz_logs SQL
│       └── runbook_tool.py   # qdrant_tool — vector search
│
├── clients/
│   ├── memgraph.py           # pymgclient/gqlalchemy singleton
│   ├── clickhouse.py         # clickhouse-connect singleton
│   └── qdrant.py             # qdrant-client singleton
│
├── data/
│   ├── seed_topology.cypher  # 14-service graph seed script
│   └── runbooks/             # Markdown runbooks for Qdrant ingestion
│       ├── payment_crash.md
│       ├── checkout_latency.md
│       └── cart_service_failure.md
│
├── scripts/
│   ├── ingest_runbooks.py    # Embeds .md files, upserts to Qdrant
│   ├── seed_memgraph.py      # Runs seed_topology.cypher
│   └── chaos_inject.py       # Docker kill paymentservice → deterministic P1
│
├── ui/
│   └── app.py                # Streamlit chat + st.status streaming
│
├── docker-compose.yml        # Full stack: OTel demo + SigNoz + Memgraph + Qdrant
└── pyproject.toml            # uv-managed; langgraph, langchain-anthropic, etc.
```

**Structure rationale:**
- `agent/tools/` is decoupled from `clients/` — tools are LangChain `@tool` decorated functions; clients are connection singletons. This lets you mock clients in unit tests without touching tool definitions.
- `data/seed_topology.cypher` is idempotent (MERGE not CREATE) — safe to re-run on restart.
- `scripts/` are one-shot data bootstrappers, not part of the runtime path.

---

## Architectural Patterns

### Pattern 6: Three-Plane Separation

Each data plane has distinct access semantics and must not leak into other planes:

| Plane | Store | Access Pattern | LLM role |
|-------|-------|----------------|----------|
| Topology | Memgraph | Deterministic BFS; returns structured node list | Chooses starting node name |
| Telemetry | ClickHouse | Time-windowed SQL; returns log rows | Chooses time window and service filter (passed to tool) |
| Knowledge | Qdrant | Semantic vector search; returns doc chunks | Formulates the search query string |

**Do not mix planes in a single tool call.** The LLM orchestrates cross-plane reasoning via sequential tool calls, but each tool touches exactly one data store. This makes failures debuggable and tools unit-testable in isolation.

### Pattern 7: Memgraph Lab Visualization Coupling

Memgraph Lab runs as a separate container connecting to Memgraph's Bolt port (7687). There is **no programmatic API** to highlight nodes from the agent. The split-screen demo effect is achieved manually:

1. Pre-position Memgraph Lab in the browser showing the full graph
2. As the agent runs `graph_bfs_tool`, have the operator run the same BFS Cypher in Lab's query editor to highlight the path
3. For a fully automated approach: Lab supports **Style Scripts** — Cypher queries bound to visual properties. You can pre-configure a Style Script that colors nodes by a `highlighted` property, then the agent tool sets `SET n.highlighted = true` on traversed nodes as a side effect

**Caution:** Modifying graph data (setting `highlighted` property) as a side effect of a read tool violates the immutable-reads principle. Isolate this to a demo-specific flag if used.

### Pattern 8: ClickHouse Connection via clickhouse-connect

SigNoz uses ClickHouse's native HTTP interface. The recommended Python client is `clickhouse-connect` (officially maintained by ClickHouse):

```python
import clickhouse_connect

client = clickhouse_connect.get_client(
    host="localhost", port=8123,
    username="default", password="",
    database="signoz_logs"
)

def query_logs(services: list[str], window_minutes: int = 15) -> list[dict]:
    result = client.query(
        "SELECT timestamp, body, severity_text, resources_string['service.name'] as svc "
        "FROM distributed_logs "
        "WHERE resources_string['service.name'] IN {services:Array(String)} "
        "AND timestamp >= toUnixTimestamp64Nano(now64() - toIntervalMinute({window:Int32})) "
        "AND severity_text IN ('ERROR', 'WARN') "
        "ORDER BY timestamp DESC LIMIT {limit:Int32}",
        parameters={"services": services, "window": window_minutes, "limit": 50}
    )
    return result.named_results()
```

**Note on SigNoz port:** SigNoz's `docker-compose.yml` exposes ClickHouse HTTP on port `9001` internally (not `8123`). Verify with `docker-compose ps clickhouse`. The external port binding in SigNoz's compose may differ from the default ClickHouse port.

### Pattern 9: Qdrant Runbook Ingestion Pattern

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
client = QdrantClient(host="localhost", port=6333)

# Collection creation (idempotent)
client.recreate_collection(
    collection_name="runbooks",
    vectors_config=VectorParams(size=384, distance=Distance.COSINE)
)

# Ingest a runbook
text = Path("data/runbooks/payment_crash.md").read_text()
embedding = model.encode(text).tolist()
client.upsert("runbooks", points=[
    PointStruct(
        id=1,
        vector=embedding,
        payload={"service": "paymentservice", "incident_type": "crash", "source": "payment_crash.md"}
    )
])

# Query with metadata filter (in qdrant_tool)
results = client.search(
    collection_name="runbooks",
    query_vector=model.encode(query_text).tolist(),
    query_filter=Filter(must=[FieldCondition(key="service", match=MatchValue(value=service_name))]),
    limit=3
)
```

---

## Data Flow: Build Order Dependencies

The build order is dictated by data plane readiness:

```
Phase 1: Infrastructure Foundation
  docker-compose.yml (all containers up)
      ↓ (required before any data seeding or code testing)

Phase 2: Data Plane Initialization (parallelizable across team)
  [Track A] Memgraph seed (seed_topology.cypher + 14 services)
  [Track B] Qdrant runbook ingestion (3+ runbooks embedded)
  [Track C] OTel Astronomy Shop → SigNoz receiving traces/logs

Phase 3: Agent Core (depends on all three data planes ready)
  client singletons (memgraph.py, clickhouse.py, qdrant.py)
      ↓
  tool functions (@tool wrappers around client queries)
      ↓
  StateGraph definition (state.py + graph.py)
      ↓
  Unit tests for each tool in isolation

Phase 4: UI + Streaming
  Streamlit app.py wiring graph.stream() → st.status
      ↓
  Chaos script (chaos_inject.py kills paymentservice)

Phase 5: End-to-End Golden Path Validation
  Full scenario: inject chaos → query → RCA output in <60s
```

**Critical dependency:** The agent cannot be tested end-to-end until all three data planes are seeded. This is the most common demo-day failure mode — plan for data seeding to complete early in Phase 2, with verification scripts.

---

## Integration Points

### External Service Boundaries

| Boundary | Protocol | Ports | Notes |
|----------|----------|-------|-------|
| Agent → Memgraph | Bolt (binary) | 7687 | Use `pymgclient` directly; `gqlalchemy` adds overhead for BFS queries |
| Agent → ClickHouse | HTTP | 8123 (or 9001 in SigNoz compose) | `clickhouse-connect`; parameterized queries required |
| Agent → Qdrant | REST/gRPC | 6333 (REST) / 6334 (gRPC) | `qdrant-client`; REST is fine for demo |
| OTel Apps → Collector | OTLP gRPC | 4317 | Astronomy Shop pre-configured |
| Streamlit → LangGraph | In-process | N/A | Same Python process; no network hop |
| Browser → Memgraph Lab | WebSocket/Bolt | 3000 (UI) → 7687 | Read-only for visualization |

### Internal Module Boundaries

| Boundary | Communication | Constraint |
|----------|---------------|------------|
| `agent/tools/` ↔ `clients/` | Direct function call | Clients are singletons; tools import from clients |
| `agent/graph.py` ↔ `agent/tools/` | LangChain `@tool` registration | Tools registered at graph compile time |
| `ui/app.py` ↔ `agent/graph.py` | `graph.stream()` iterator | UI imports compiled graph; no circular deps |
| Chaos script ↔ Docker | Docker SDK or `subprocess(docker stop)` | Isolated to `scripts/`; never called from agent |

---

## Anti-Patterns

### Anti-Pattern 1: LLM-Generated Cypher

**What people do:** Pass the incident description to the LLM and ask it to "write a Cypher query to find affected services."

**Why it's wrong:** Hallucinated node labels, wrong relationship names, injection risk, and non-deterministic output. In a demo, one bad Cypher query returning empty results cascades to an empty RCA.

**Do this instead:** The LLM calls `graph_bfs_tool(service_name="checkoutservice")`. The tool function programmatically constructs the BFS Cypher from the service name. The LLM's job is to identify the service name from the user query, not to write graph queries.

### Anti-Pattern 2: Monolithic Tool That Queries All Three Planes

**What people do:** Create a single `investigate_incident(service, time_window)` tool that internally runs the Memgraph query, the ClickHouse query, and the Qdrant search, then returns everything at once.

**Why it's wrong:** Eliminates the LLM's ability to reason about intermediate results. If the graph traversal shows only 2 affected services, the LLM should narrow the log query to those 2 — not pre-query all 14. Also eliminates glass-box visibility (you can't show individual tool steps in the UI).

**Do this instead:** Three separate tools with sequential invocation. The LLM uses the result of tool N to parameterize tool N+1.

### Anti-Pattern 3: Blocking Streamlit Main Thread with Synchronous LangGraph

**What people do:** Call `graph.invoke()` (blocking) in the Streamlit button handler.

**Why it's wrong:** Blocks the Streamlit rendering thread for the full 30-60 second RCA duration. The UI freezes. No streaming possible.

**Do this instead:** Use `graph.stream(stream_mode="updates")` in a for-loop inside the Streamlit render block. Streamlit re-renders on each iteration of the for-loop, enabling progressive disclosure of tool results.

### Anti-Pattern 4: Seeding Memgraph with CREATE Instead of MERGE

**What people do:** Use `CREATE` in the seed script.

**Why it's wrong:** Duplicate nodes on restart. The seed script must be idempotent.

**Do this instead:** Use `MERGE (s:Service {name: $name}) SET s += $props`. On second run, updates properties instead of creating duplicates.

### Anti-Pattern 5: Using `MemoryCheckpointer` Without Thread ID

**What people do:** Add a checkpointer but forget to pass `config={"configurable": {"thread_id": "demo"}}` to `graph.stream()`.

**Why it's wrong:** LangGraph raises a runtime error when checkpointer is present but thread_id is missing.

**Do this instead:** Either omit the checkpointer entirely (fine for demo) or always pass thread_id. For the demo, use a fixed `thread_id = "incident-demo"` and reset it between runs.

---

## Scaling Considerations

The demo is single-user local Docker Compose. These only apply post-demo when evolving toward production:

| Concern | At Demo Scale | At Team Scale (10-50 users) | At Enterprise Scale |
|---------|--------------|------------------------------|---------------------|
| LangGraph state | In-memory (no checkpointer needed) | SQLite checkpointer (`langgraph-checkpoint-sqlite`) | PostgreSQL checkpointer |
| Memgraph | Single node, in-memory | Same — Memgraph is designed for in-memory operation | Memgraph with on-disk storage + replication |
| ClickHouse | SigNoz bundled single-node | SigNoz Cloud or self-managed single-node | ClickHouse cluster with replication |
| Qdrant | Single-node Docker | Qdrant Cloud or single-node with persistence | Qdrant distributed |
| Agent concurrency | 1 concurrent run (Streamlit single-threaded) | FastAPI async endpoint per incident | Queue-backed (Celery/Temporal) |

---

## Sources

- **LangGraph source** — `langchain-ai/langgraph` `libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py`, `libs/langgraph/langgraph/types.py` (HIGH confidence)
- **soul-bits/rca-agent** — Production LangGraph RCA agent with OTel demo integration; architecture cross-validates all major patterns here (HIGH confidence, live implementation)
- **SigNoz source** — `pkg/query-service/constants/constants.go` for `LogsSQLSelect` and table name `signoz_logs.distributed_logs` (HIGH confidence)
- **GQLAlchemy docs** — `memgraph/gqlalchemy` README + query builder guide; confirmed Bolt 7687, MERGE patterns (HIGH confidence)
- **Qdrant Python client** — `qdrant/qdrant-client` README + API; confirmed REST port 6333, `payload` filtering API (HIGH confidence)
- **clickhouse-connect README** — ClickHouse/clickhouse-connect; confirmed HTTP interface, parameterized query API (HIGH confidence)
- **OTel Astronomy Shop** — `open-telemetry/opentelemetry-demo` GitHub API; confirmed 14+ service names (HIGH confidence)
- **qdmudong/SiliconBrain** — Memgraph + LangGraph architecture pattern for graph-backed agents (MEDIUM confidence — proof of concept)

---

*Architecture research for: AI SRE Incident Response Agent (incimin.io)*
*Researched: 2026-08-05*
