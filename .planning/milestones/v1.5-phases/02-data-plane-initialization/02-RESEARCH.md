# Phase 2: Data Plane Initialization - Research

**Goal:** Understand the technical requirements, constraints, and necessary steps to successfully plan Phase 2. The phase focuses on seeding, verifying, and querying the three data planes: Memgraph (Topology), ClickHouse (Telemetry), and Qdrant (Knowledge).

## What do I need to know to PLAN this phase well?

### 1. Topology Plane (Memgraph)
- **Service Graph Data:** We need to accurately list the 14 OTel Astronomy Shop services and their dependency edges to seed Memgraph. This topology must be hardcoded in the seed script.
- **Idempotent Seeding (TOPO-01):** The seed script must use `MERGE` Cypher queries to ensure that running it multiple times does not duplicate nodes or edges.
- **GQLAlchemy Integration:** We need to use `GQLAlchemy==1.10.0` for ORM/Connection management, adhering to the Python 3.12 and `numpy==1.26.4` constraints specified in `CLAUDE.md`.
- **BFS Traversal (TOPO-02):** We must write and test the `[*BFS]` Cypher query that traverses the graph (e.g., finding the path from `checkoutservice` to `paymentservice`). The `memgraph/memgraph-mage:3.12.0` image provides this native capability.
- **Persistence Verification (TOPO-03):** Need a testing strategy to confirm that restarting the `memgraph` container doesn't wipe the topology data (validating Phase 1's volume mount).

### 2. Telemetry Plane (ClickHouse)
- **Schema Validation (TELE-03):** We need to explicitly check whether SigNoz v0.135.1 uses `signoz_logs.distributed_logs` or `signoz_logs.distributed_logs_v2` for storing logs. The query script must target the correct table.
- **Log Query Tool (TELE-01 & TELE-02):** 
  - Must use `clickhouse-connect==1.6.0` to connect to ClickHouse.
  - Queries need to use nanosecond timestamps (SigNoz convention).
  - Must correctly filter for `ERROR` level logs and extract `trace_id` for a specified service (e.g., `paymentservice`).
- **Connection Details:** ClickHouse connection details (`host`, `port`, `user`, `password`, `database`) need to be managed via `.env` (already partially outlined in `.env.example`).

### 3. Knowledge Plane (Qdrant)
- **Runbooks Generation (KNOW-01):** We need to draft 3 Markdown runbooks (paymentservice crash, checkoutservice high-latency, frontendservice 5xx errors) to be ingested into Qdrant.
- **Embedding Configuration (KNOW-02):** 
  - Must configure `qdrant-client==1.19.0` with `fastembed==0.8.0`.
  - The exact model must be `BAAI/bge-small-en-v1.5` (384-dimensional).
  - Ensure fastembed runs locally/in-process and does not make external API calls.
- **Search Tool Setup (KNOW-03):** Must construct the Qdrant search tool to use semantic similarity combined with payload filtering (e.g., filtering by the service name).

### 4. Code Organization & Verification Strategy
- **Script Locations:** We should plan to create initialization and verification scripts in the `scripts/` directory (e.g., `scripts/init_memgraph.py`, `scripts/init_qdrant.py`, `scripts/verify_data_planes.py`).
- **Development Workflow:** Since Phase 1 provided `scripts/verify_stack.py` as the definitive gate, Phase 2 should follow this pattern, potentially augmenting the verify script or creating a new one specifically for data plane readiness.
- **Local Port Mapping:** Host-side tooling must use `127.0.0.1` with the mapped host ports since Docker service names (e.g., `memgraph:7687`) are only valid inside the Docker network.

## Next Steps for Planning
1. Define the exact Python scripts and classes needed for data plane interaction.
2. Outline the Cypher, ClickHouse SQL, and Qdrant Python client commands needed to fulfill the success criteria.
3. Establish the testing/verification steps to confirm each Track (A, B, C) works independently.
