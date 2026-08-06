# incimin.io — AI SRE Agent

Autonomous AI SRE agent that performs real-time, deterministic root-cause analysis during infrastructure incidents. Traverses the live service graph (Memgraph), queries correlated telemetry (SigNoz/ClickHouse), and retrieves runbooks (Qdrant) to deliver root cause and remediation before a human opens a dashboard.

## Prerequisites

- Docker + Docker Compose v2 (`docker compose`, not `docker-compose`)
- Python 3.12 (`python --version`)
- [`uv`](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Setup

```bash
# 1. Clone and enter the repo
git clone <repo-url> incimin.io && cd incimin.io

# 2. Install Python dependencies
uv sync --all-groups

# 3. Create the shared Docker network (one-time)
docker network create incimin || true

# 4. Start the full stack
docker compose up -d
```

This starts: Memgraph + MAGE, Qdrant, SigNoz (OTel Collector + ClickHouse + UI), and the OTel Astronomy Shop (14-service demo app).

## Verify the stack

```bash
uv run python scripts/verify_stack.py
```

All 14 checks should show `PASS`.

## Running the production system

### Webhook ingestion API

Receives deployment events and persists them to ClickHouse + Memgraph.

```bash
uv run uvicorn src.production.main:app --host 0.0.0.0 --port 8000 --reload
```

Endpoint: `POST http://localhost:8000/webhook`

```json
{
  "repository_url": "https://github.com/org/repo",
  "commit_sha": "abc123",
  "service_name": "paymentservice"
}
```

### Topology plugin (SigNoz)

Fetch live service topology from SigNoz and stream normalized entities:

```python
import asyncio
from src.production.topology.manager import TopologyManager
from src.production.topology.plugins.signoz import SigNozPluginConfig

async def main():
    config = SigNozPluginConfig()  # reads SIGNOZ_API_URL + SIGNOZ_API_TOKEN from env
    plugin_cls = TopologyManager.get_plugin_class("signoz")
    plugin = plugin_cls(config)
    async for entity in plugin.fetch_topology():
        print(entity)

asyncio.run(main())
```

### Running tests

```bash
uv run pytest
```

## Service ports

| Service | Port | URL |
|---------|------|-----|
| Memgraph Bolt | 7687 | `bolt://localhost:7687` |
| Memgraph Lab (UI) | 3000 | http://localhost:3000 |
| Qdrant | 6333 | http://localhost:6333 |
| SigNoz UI | 3301 | http://localhost:3301 |
| ClickHouse HTTP | 8123 | http://localhost:8123 |
| OTel Collector (gRPC) | 4317 | — |
| Webhook API | 8000 | http://localhost:8000 |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SIGNOZ_API_URL` | `http://localhost:3301` | SigNoz query service base URL |
| `SIGNOZ_API_TOKEN` | — | SigNoz API token (optional for local) |

Copy `.env.example` (if present) or export directly:

```bash
export SIGNOZ_API_URL=http://localhost:3301
```

## Project layout

```
src/production/
  main.py                    # FastAPI webhook ingestion API
  db.py                      # ClickHouse + Memgraph persistence
  topology/
    models.py                # ServiceNode, ServiceEdge (Pydantic + entity metadata)
    plugin.py                # TopologyPlugin ABC
    manager.py               # TopologyManager plugin registry
    plugins/signoz.py        # SigNoz topology provider
scripts/
  verify_stack.py            # 14-check infrastructure gate
  init_qdrant.py             # Seed runbooks into Qdrant
  check_tele.py              # Telemetry query smoke test
docker/
  compose.core.yaml          # Memgraph + Qdrant
  compose.signoz.yaml        # SigNoz stack
  compose.otel-demo.yaml     # OTel Astronomy Shop
```
