<!-- GSD:project-start source:PROJECT.md -->
## Project

**incimin.io — AI SRE Agent**

An autonomous AI SRE (Site Reliability Engineering) agent that performs real-time, deterministic root-cause analysis during infrastructure incidents. It unifies three operational planes — live service topology (Memgraph), high-velocity telemetry (SigNoz/ClickHouse), and human operational knowledge (Qdrant) — to replace the L1 first-responder triage role. Targeted at mid-size and large enterprises running distributed microservice architectures.

**Core Value:** When an incident fires, the agent autonomously traverses the live service graph, queries correlated telemetry, and retrieves the relevant runbook — delivering root cause and recommended remediation steps before any human has opened a dashboard.

### Constraints

- **Timeline:** 3-day / 48-hour build sprint — phases must be parallelizable across 2-3 engineers
- **Tech Stack (locked):** LangGraph (Python), Memgraph + memgraph-mage, SigNoz (OTel Collector + ClickHouse), Qdrant, Streamlit — no substitutions; demo context depends on these specific tools
- **Runtime:** Docker Compose local — no cloud dependencies during build/demo
- **Demo reliability:** Golden path must be fully deterministic. Any non-determinism (LLM topology reasoning, dynamic port assignment, etc.) is a blocker.
- **Extensibility:** Agent tool interface must be designed so adding new tools (e.g., alertmanager integration, k8s pod inspector) doesn't require rewriting the state machine
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

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
## Docker Compose Image Versions
# Memgraph — graph database with MAGE algorithms (BFS, DFS, community detection)
# Memgraph Lab — browser-based graph visualization (demo dual-screen)
# Qdrant — vector store for runbook embeddings
# ClickHouse — telemetry storage backend for SigNoz
# NOTE: clickhouse-server:24.1.2-alpine also works; non-alpine is preferred for
# compatibility with SigNoz's ClickHouse config expectations
# SigNoz — deploy via foundryctl (Foundry v0.2.17) which pulls:
#   signoz/signoz-otel-collector:0.55.0
#   signoz/frontend + query-service pinned to v0.135.1
# OTel Astronomy Shop
# Services use: ghcr.io/open-telemetry/demo:3.0.0-{service}
# e.g., ghcr.io/open-telemetry/demo:3.0.0-payment
# OTel Collector: ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-contrib:0.157.0
## Python Installation
# Create project with uv (Python 3.12 locked)
# Core agent stack
# Data plane clients
# UI
# Config
# CRITICAL: Pin numpy to avoid GQLAlchemy conflict with numpy 2.x
# Dev tooling
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
## Stack Patterns by Variant
- Use `MemorySaver` checkpoint (in-memory, zero setup)
- Use `fastembed` for embeddings (no API key required for runbook vectorization)
- Run all services in a single `docker-compose.yml`
- Single `casting.yaml` for foundryctl to deploy SigNoz subset
- Swap `MemorySaver` → `AsyncPostgresSaver` (langgraph-checkpoint-postgres)
- Replace `fastembed` with OpenAI embeddings if runbook corpus grows beyond internal use
- Separate Docker Compose files per tier (infra, observability, agent)
- Add `langsmith` tracing in production for agent audit trail
- Replace `langchain-openai` with `langchain-anthropic` (same `@tool` interface, same `create_react_agent` call signature)
- No other changes required
- Pre-compute a `CREATE MATERIALIZED VIEW` for the paymentservice error rate over the last 5 minutes
- Agent queries the materialized view instead of scanning raw traces table
- SigNoz's ClickHouse schema uses `signoz_logs.logs` and `signoz_traces.distributed_trace_summary` as primary tables
## Memgraph Bolt Connection Pattern
# Correct GQLAlchemy connection for Memgraph 3.x
# Cypher BFS tool pattern
## SigNoz ClickHouse Schema Reference
## Qdrant Runbook Embedding Pattern
# Create collection with fastembed auto-sizing
# Upsert with fastembed (embedding happens in-process)
# Semantic search tool
## Sources
- PyPI API (`pypi.org/pypi/{package}/json`) — langgraph 1.2.10, langchain-core 1.5.3, langchain-openai 1.4.1, langchain-anthropic 1.5.3, qdrant-client 1.19.0, clickhouse-connect 1.6.0, GQLAlchemy 1.10.0, streamlit 1.61.0, fastembed 0.8.0, pydantic 2.13.4, openai 2.53.0, langsmith 0.10.15 — HIGH confidence (live API)
- Docker Hub API (`hub.docker.com/v2/repositories/{image}/tags`) — memgraph/memgraph-mage 3.12.0, qdrant/qdrant v1.19.0, memgraph/lab 2.13.0, clickhouse-server 24.1.2.5 — HIGH confidence (live API)
- GitHub API (`api.github.com/repos/{org}/{repo}/releases/latest`) — SigNoz v0.135.1 (2026-07-31), Foundry v0.2.17 (2026-07-29), Memgraph MAGE 3.7.2 (2025-12-23), OTel Demo 3.0.0 (2026-07-24) — HIGH confidence (live API)
- `github.com/SigNoz/charts/main/charts/clickhouse/values.yaml` — ClickHouse `24.1.2-alpine` pin with comment "SigNoz does not support all versions" — HIGH confidence
- `github.com/open-telemetry/opentelemetry-demo/refs/tags/3.0.0/.env` — OTel Collector contrib 0.157.0, image naming pattern `ghcr.io/open-telemetry/demo:3.0.0-{service}` — HIGH confidence
- `github.com/langchain-ai/langgraph/libs/prebuilt/langgraph/prebuilt/__init__.py` — confirms `create_react_agent`, `ToolNode`, `tools_condition` export surface — HIGH confidence
- GQLAlchemy 1.10.0 PyPI metadata — neo4j<6.0.0 and numpy<2.0 constraints confirmed — HIGH confidence
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
