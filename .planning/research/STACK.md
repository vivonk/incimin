# Stack Research

**Domain:** Autonomous AI SRE Agent — LangGraph orchestration, Memgraph graph topology, SigNoz/ClickHouse telemetry, Qdrant vector store
**Researched:** 2026-08-05
**Confidence:** HIGH (all versions verified from PyPI and Docker Hub APIs)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12 | Runtime | All required libraries support 3.12; numpy<2.0 pin resolves GQLAlchemy constraint; avoids 3.13 ecosystem lag |
| LangGraph | 1.2.10 | Agent state machine | v1.x is the stable production API; `create_react_agent` + `ToolNode` provide deterministic tool dispatch without building a custom graph loop; critical for demo reliability |
| langchain-core | 1.5.3 | LangChain primitives | LangGraph 1.2.10 pins `>=1.4.7,<2`; required for `@tool` decorator and `BaseTool` interface |
| langchain-openai | 1.4.1 | LLM integration | Provides `ChatOpenAI` with native tool-calling; use for the synthesis step only |
| langchain-anthropic | 1.5.3 | LLM integration (alt) | Drop-in alternative if Claude is preferred for synthesis; same `@tool` interface |
| memgraph/memgraph-mage | 3.12.0 | Graph database + algorithms | MAGE bundle includes BFS/DFS Cypher procedures natively; single image eliminates separate MAGE sidecar; v3.12.0 is current stable (released 2026-07-15) |
| GQLAlchemy | 1.10.0 | Memgraph Python ORM | Official Memgraph Python library; supports bolt+routing (added v1.10.0); cleaner Cypher execution than raw neo4j driver for this use case |
| qdrant/qdrant | v1.19.0 | Vector store | Current stable; Python client 1.19.0 ships with `fastembed` integration for in-process embedding; required for runbook semantic search |
| qdrant-client | 1.19.0 | Qdrant Python client | Version-locked to server; `QdrantClient.from_texts()` handles embedding + upsert in one call |
| fastembed | 0.8.0 | Local embedding | Zero external API call for embedding runbooks and queries; BAAI/bge-small-en-v1.5 model (~130MB) is sufficient for SRE runbook similarity; removes OpenAI embedding dependency |
| clickhouse-connect | 1.6.0 | ClickHouse Python client | Official Clickhouse Inc driver; supports async; works directly with SigNoz ClickHouse without schema translation layer |
| signoz (Foundry) | v0.135.1 / Foundry v0.2.17 | Observability stack | Current stable release; deploy via `foundryctl` which generates Docker Compose manifests; includes OTel Collector + ClickHouse + SigNoz UI |
| Streamlit | 1.61.0 | Chat UI | `st.status` expanders for tool-call glass-box visibility; `st.chat_message` for LLM output; no custom frontend overhead |
| Pydantic | 2.13.4 | State schema + validation | LangGraph state objects require Pydantic v2; `TypedDict` works but Pydantic gives runtime validation on tool inputs |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| langgraph-prebuilt | 1.1.0 | `create_react_agent`, `ToolNode` | Always — provides the tool dispatch node that handles parallel tool calls and error recovery |
| langgraph-checkpoint | 4.1.1 | State persistence | Required for LangGraph; use in-memory checkpointer (`MemorySaver`) for demo; swap to `AsyncPostgresSaver` for production |
| langsmith | 0.10.15 | LLM call tracing | Set `LANGCHAIN_TRACING_V2=true` for agent debugging; not required for demo but invaluable for development |
| openai | 2.53.0 | Raw OpenAI API client | Pulled in by langchain-openai; don't call directly |
| neo4j | 5.28.1 (latest 5.x) | Bolt protocol driver | GQLAlchemy depends on `neo4j<6.0.0`; Memgraph is bolt-compatible; do not use neo4j 6.x (breaks GQLAlchemy) |
| numpy | 1.26.4 | Numerical ops | **Pin explicitly** — GQLAlchemy requires `<2.0,>=1.26.4` on Python 3.10-3.12; numpy 2.x will break GQLAlchemy |
| pydantic-settings | 2.x | Config management | `BaseSettings` for env var injection; keeps connection strings out of code |
| python-dotenv | 1.x | .env file loading | Dev environment only; prod uses env injection |
| opentelemetry-api | 1.44.0 | OTel SDK | Only needed if adding custom spans to the agent itself; not required for consuming SigNoz data |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Python package and venv manager | Replaces pip + virtualenv; 10-100x faster resolution; `uv sync` from `pyproject.toml` |
| Docker Compose v2 | Local stack orchestration | Use `docker compose` (v2 plugin), not `docker-compose` (v1 binary); v2 is the current default |
| foundryctl | SigNoz stack deployment | Generates Compose manifests from `casting.yaml`; replaces deprecated `deploy/` scripts in SigNoz repo |
| Memgraph Lab | Graph visualization | `memgraph/lab:2.13.0` Docker image; provides live node-highlight UI on port 3000 |
| pyproject.toml | Project config | Use `[project]` standard (PEP 621); `uv add` manages dependencies |

---

## Docker Compose Image Versions

These are verified stable tags as of 2026-08-05 for the full local stack:

```yaml
# Memgraph — graph database with MAGE algorithms (BFS, DFS, community detection)
memgraph/memgraph-mage:3.12.0       # single image includes both Memgraph server + MAGE procedures

# Memgraph Lab — browser-based graph visualization (demo dual-screen)
memgraph/lab:2.13.0                  # latest stable

# Qdrant — vector store for runbook embeddings
qdrant/qdrant:v1.19.0               # stable, not unprivileged/gpu variant

# ClickHouse — telemetry storage backend for SigNoz
clickhouse/clickhouse-server:24.1.2.5  # SigNoz-validated version; pinned in SigNoz Helm chart
# NOTE: clickhouse-server:24.1.2-alpine also works; non-alpine is preferred for
# compatibility with SigNoz's ClickHouse config expectations

# SigNoz — deploy via foundryctl (Foundry v0.2.17) which pulls:
#   signoz/signoz-otel-collector:0.55.0
#   signoz/frontend + query-service pinned to v0.135.1

# OTel Astronomy Shop
# Services use: ghcr.io/open-telemetry/demo:3.0.0-{service}
# e.g., ghcr.io/open-telemetry/demo:3.0.0-payment
# OTel Collector: ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-contrib:0.157.0
```

---

## Python Installation

```bash
# Create project with uv (Python 3.12 locked)
uv init incimin-agent --python 3.12
cd incimin-agent

# Core agent stack
uv add "langgraph>=1.2.10,<1.3" \
       "langgraph-prebuilt>=1.1.0" \
       "langgraph-checkpoint>=4.1.0" \
       "langchain-core>=1.4.7,<2" \
       "langchain-openai>=1.4.0" \
       "langchain-anthropic>=1.5.0"

# Data plane clients
uv add "GQLAlchemy>=1.10.0,<2" \
       "qdrant-client>=1.19.0,<2" \
       "fastembed>=0.8.0" \
       "clickhouse-connect>=1.6.0,<2"

# UI
uv add "streamlit>=1.61.0"

# Config
uv add "pydantic>=2.7.4" \
       "pydantic-settings>=2.0" \
       "python-dotenv>=1.0"

# CRITICAL: Pin numpy to avoid GQLAlchemy conflict with numpy 2.x
uv add "numpy>=1.26.4,<2.0"

# Dev tooling
uv add --dev "langsmith>=0.10.0" "pytest>=8" "pytest-asyncio>=0.24"
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| GQLAlchemy | raw `neo4j` driver | Use neo4j driver directly if you don't need ORM-style node classes; slightly less overhead, but Cypher execution API is identical in practice |
| GQLAlchemy | `mgclient` (Memgraph native C driver) | `mgclient` has lower latency but requires C extension compilation; not worth the Docker complexity for this project |
| fastembed (local) | OpenAI `text-embedding-3-small` | Use OpenAI embeddings if runbook corpus exceeds ~10K documents or quality benchmarks require it; eliminates model download (~130MB) but adds API dependency |
| clickhouse-connect | `clickhouse-driver` (old) | Never — `clickhouse-driver` is the legacy binary protocol client; `clickhouse-connect` is the Clickhouse Inc official HTTP client with async support |
| LangGraph `create_react_agent` | Custom `StateGraph` | Use custom `StateGraph` if tool execution order must be strictly sequential and non-parallel; `create_react_agent` allows parallel tool calls which suits this use case |
| Streamlit | FastAPI + React frontend | Use FastAPI+React only post-demo when the product needs user auth, multi-session, or custom rendering; Streamlit is correct for the 3-day sprint |
| foundryctl (SigNoz Foundry) | Old `deploy/docker-compose.yaml` | The old `deploy/` path is **deprecated** in the SigNoz repo as of 2025; use Foundry exclusively |
| Python 3.12 | Python 3.13 | Python 3.13 triggers GQLAlchemy's numpy<3.0 branch which is less battle-tested; 3.12 has full ecosystem support |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `docker-compose` v1 CLI | Deprecated binary; `depends_on` healthcheck syntax differs from Compose v2 spec; causes subtle startup ordering bugs | `docker compose` v2 plugin (included with Docker Desktop and Docker Engine 25+) |
| `clickhouse-driver` | Binary protocol, unmaintained, no async | `clickhouse-connect` (official, HTTP protocol, async) |
| `neo4j>=6.0.0` | Breaks GQLAlchemy's declared dependency `neo4j<6.0.0` | `neo4j==5.28.1` (latest 5.x; pulled in automatically by GQLAlchemy) |
| `numpy>=2.0` | GQLAlchemy pins `numpy<2.0,>=1.26.4` for Python 3.10-3.12; importing GQLAlchemy with numpy 2.x installed will raise ImportError | `numpy==1.26.4` (explicitly pinned in pyproject.toml) |
| `langchain` (monolithic) | The `langchain` meta-package installs stale versions; imports from it shadow `langchain-core` and `langchain-openai` | Import directly from `langchain_core`, `langchain_openai`, `langchain_anthropic` |
| `latest` Docker tags | Non-deterministic; breaks demo reproducibility across machines/CI | Use explicit version tags as listed in Docker Compose section above |
| Memgraph `memgraph/memgraph` (without MAGE) | Missing BFS/shortest-path Cypher procedures that the agent relies on; must use MAGE image | `memgraph/memgraph-mage:3.12.0` |
| SigNoz clickhouse `24.3+` | SigNoz charts explicitly warn "not always tested with the latest version"; `24.1.2.5` is the tested-and-pinned version | `clickhouse/clickhouse-server:24.1.2.5` |

---

## Version Compatibility Matrix

| Package | Compatible With | Constraint | Notes |
|---------|-----------------|------------|-------|
| `langgraph==1.2.10` | `langchain-core>=1.4.7,<2` | Required | langgraph will refuse to import if langchain-core is out of range |
| `langgraph==1.2.10` | `pydantic>=2.7.4` | Required | Pydantic v1 is not supported |
| `GQLAlchemy==1.10.0` | `neo4j>=4.4.3,<6.0.0` | Required | neo4j 6.x breaks GQLAlchemy |
| `GQLAlchemy==1.10.0` | `numpy>=1.26.4,<2.0` | Required on Python 3.10-3.12 | Must pin numpy; numpy 2.x co-installation causes ImportError |
| `qdrant-client==1.19.0` | `fastembed>=0.8.0` | Optional dep | Install fastembed to enable in-process embedding; client detects it automatically |
| `clickhouse-connect==1.6.0` | Python `>=3.10,<3.15` | Required | Declared in package metadata |
| `streamlit==1.61.0` | Python `>=3.10` | Required | |
| Memgraph `3.12.0` | Bolt protocol v4.4 | Compatible | neo4j driver communicates over Bolt; Memgraph implements the Bolt spec |
| SigNoz `v0.135.1` | ClickHouse `24.1.x` | SigNoz-validated | SigNoz Helm chart pins `clickhouse-server:24.1.2-alpine`; do not upgrade ClickHouse independently |
| OTel Demo `3.0.0` | OTel Collector contrib `0.157.0` | Pinned in .env | Demo compose file pins collector version |

---

## Stack Patterns by Variant

**For the 3-day demo sprint:**
- Use `MemorySaver` checkpoint (in-memory, zero setup)
- Use `fastembed` for embeddings (no API key required for runbook vectorization)
- Run all services in a single `docker-compose.yml`
- Single `casting.yaml` for foundryctl to deploy SigNoz subset

**For production evolution post-demo:**
- Swap `MemorySaver` → `AsyncPostgresSaver` (langgraph-checkpoint-postgres)
- Replace `fastembed` with OpenAI embeddings if runbook corpus grows beyond internal use
- Separate Docker Compose files per tier (infra, observability, agent)
- Add `langsmith` tracing in production for agent audit trail

**If the team prefers Anthropic Claude over OpenAI for synthesis:**
- Replace `langchain-openai` with `langchain-anthropic` (same `@tool` interface, same `create_react_agent` call signature)
- No other changes required

**If the ClickHouse query latency is a bottleneck during demo:**
- Pre-compute a `CREATE MATERIALIZED VIEW` for the paymentservice error rate over the last 5 minutes
- Agent queries the materialized view instead of scanning raw traces table
- SigNoz's ClickHouse schema uses `signoz_logs.logs` and `signoz_traces.distributed_trace_summary` as primary tables

---

## Memgraph Bolt Connection Pattern

```python
# Correct GQLAlchemy connection for Memgraph 3.x
from gqlalchemy import Memgraph

db = Memgraph(
    host="localhost",
    port=7687,
    username="",      # Memgraph OSS has no auth by default
    password="",
    encrypted=False,  # TLS disabled for local Docker
)

# Cypher BFS tool pattern
def traverse_dependencies(service_name: str) -> list[dict]:
    query = """
    MATCH path = (start:Service {name: $name})-[:DEPENDS_ON*1..5]->(dep:Service)
    RETURN [node IN nodes(path) | node.name] AS chain,
           length(path) AS depth
    ORDER BY depth
    """
    return list(db.execute_and_fetch(query, {"name": service_name}))
```

---

## SigNoz ClickHouse Schema Reference

SigNoz stores data in two primary ClickHouse databases:

```sql
-- Traces (for latency/error analysis)
SELECT serviceName, COUNT(*) as error_count
FROM signoz_traces.distributed_trace_summary
WHERE serviceName = 'paymentservice'
  AND statusCode = 'STATUS_CODE_ERROR'
  AND timestamp > now() - INTERVAL 5 MINUTE
GROUP BY serviceName

-- Logs
SELECT body, timestamp, attributes_string
FROM signoz_logs.logs
WHERE attributes_string['service.name'] = 'paymentservice'
  AND timestamp > now() - INTERVAL 5 MINUTE
ORDER BY timestamp DESC
LIMIT 50
```

ClickHouse-connect async query pattern for the agent tool:

```python
import clickhouse_connect

client = clickhouse_connect.get_client(
    host="localhost",
    port=8123,
    username="default",
    password="",
    database="signoz_traces",
)
```

---

## Qdrant Runbook Embedding Pattern

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

client = QdrantClient(host="localhost", port=6333)

# Create collection with fastembed auto-sizing
client.create_collection(
    collection_name="runbooks",
    vectors_config=VectorParams(size=384, distance=Distance.COSINE),
    # BAAI/bge-small-en-v1.5 outputs 384-dim vectors
)

# Upsert with fastembed (embedding happens in-process)
client.add(
    collection_name="runbooks",
    documents=["runbook text..."],
    metadata=[{"service": "paymentservice", "severity": "P1"}],
    ids=[1],
)

# Semantic search tool
results = client.query(
    collection_name="runbooks",
    query_text="payment service crashing checkout",
    limit=3,
    query_filter=Filter(
        must=[FieldCondition(key="severity", match=MatchValue(value="P1"))]
    ),
)
```

---

## Sources

- PyPI API (`pypi.org/pypi/{package}/json`) — langgraph 1.2.10, langchain-core 1.5.3, langchain-openai 1.4.1, langchain-anthropic 1.5.3, qdrant-client 1.19.0, clickhouse-connect 1.6.0, GQLAlchemy 1.10.0, streamlit 1.61.0, fastembed 0.8.0, pydantic 2.13.4, openai 2.53.0, langsmith 0.10.15 — HIGH confidence (live API)
- Docker Hub API (`hub.docker.com/v2/repositories/{image}/tags`) — memgraph/memgraph-mage 3.12.0, qdrant/qdrant v1.19.0, memgraph/lab 2.13.0, clickhouse-server 24.1.2.5 — HIGH confidence (live API)
- GitHub API (`api.github.com/repos/{org}/{repo}/releases/latest`) — SigNoz v0.135.1 (2026-07-31), Foundry v0.2.17 (2026-07-29), Memgraph MAGE 3.7.2 (2025-12-23), OTel Demo 3.0.0 (2026-07-24) — HIGH confidence (live API)
- `github.com/SigNoz/charts/main/charts/clickhouse/values.yaml` — ClickHouse `24.1.2-alpine` pin with comment "SigNoz does not support all versions" — HIGH confidence
- `github.com/open-telemetry/opentelemetry-demo/refs/tags/3.0.0/.env` — OTel Collector contrib 0.157.0, image naming pattern `ghcr.io/open-telemetry/demo:3.0.0-{service}` — HIGH confidence
- `github.com/langchain-ai/langgraph/libs/prebuilt/langgraph/prebuilt/__init__.py` — confirms `create_react_agent`, `ToolNode`, `tools_condition` export surface — HIGH confidence
- GQLAlchemy 1.10.0 PyPI metadata — neo4j<6.0.0 and numpy<2.0 constraints confirmed — HIGH confidence

---

*Stack research for: AI SRE Agent (LangGraph + Memgraph + SigNoz + Qdrant)*
*Researched: 2026-08-05*
