# Phase 2 Pattern Mapping

## 1. `scripts/init_memgraph.py`
- **Role**: Seed script for the Topology Plane.
- **Data Flow**: Connects to Memgraph via `GQLAlchemy` on `127.0.0.1:7687`, executing Cypher `MERGE` statements to idempotently seed 14 OTel Astronomy Shop services and their dependency edges.
- **Analog**: `scripts/verify_stack.py` (Memgraph connection pattern)
- **Code Excerpt**:
  ```python
  from gqlalchemy import Memgraph
  
  memgraph = Memgraph(host="127.0.0.1", port=7687)
  # Example query execution
  results = list(memgraph.execute_and_fetch("RETURN 1 as value"))
  ```

## 2. `scripts/init_qdrant.py`
- **Role**: Seed script for the Knowledge Plane.
- **Data Flow**: Reads 3 Markdown runbooks, generates 384-dimensional embeddings using `fastembed==0.8.0` (`BAAI/bge-small-en-v1.5`), and upserts vector points and payload metadata into Qdrant.
- **Analog**: `scripts/verify_stack.py` (QdrantClient initialization pattern)
- **Code Excerpt**:
  ```python
  from qdrant_client import QdrantClient
  
  client = QdrantClient("http://127.0.0.1:6333", timeout=5.0)
  collections = client.get_collections()
  ```

## 3. `scripts/verify_data_planes.py`
- **Role**: Verification gate for Phase 2 readiness.
- **Data Flow**: Executes specific tests against Memgraph (BFS traversals `[*BFS]`, data persistence), ClickHouse (nanosecond-based log queries, SigNoz schema validation), and Qdrant (semantic similarity search combined with payload filtering). Output is a pass/fail summary.
- **Analog**: `scripts/verify_stack.py` (Verification script layout, exception-based checks, and ClickHouse queries)
- **Code Excerpt**:
  ```python
  import clickhouse_connect
  
  # ClickHouse connection pattern
  client = clickhouse_connect.get_client(host='127.0.0.1', port=8123, username='default', password='')
  
  CHECKS = [
      ("TOPO-02", check_topo_02),
      ("TELE-01", check_tele_01),
  ]
  
  def main():
      fail_count = 0
      for cid, func in CHECKS:
          try:
              func()
              print(f"PASS  {cid}  OK")
          except Exception as e:
              fail_count += 1
              print(f"FAIL  {cid}  {type(e).__name__}: {str(e)}")
      if fail_count > 0:
          sys.exit(1)
  ```

## 4. Runbook Documents (`docs/runbooks/*.md`)
- **Role**: Source knowledge documents for Qdrant ingestion.
- **Data Flow**: Authored in Markdown (covering paymentservice crash, checkoutservice high-latency, frontendservice 5xx errors) and parsed by `init_qdrant.py` before being chunked/embedded.
- **Analog**: `docs/PORTS.md` and `docs/OTEL_DEMO_SERVICES.md` (Static Markdown documentation used as data sources)
- **Code Excerpt**:
  ```python
  # Example of parsing a markdown file as seen in verify_stack.py
  from pathlib import Path
  content = Path('docs/runbooks/paymentservice_crash.md').read_text()
  ```
