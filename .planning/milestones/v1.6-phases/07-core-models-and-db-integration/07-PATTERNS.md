# Phase 07: Core Models and DB Integration - Patterns

Based on the requirements established in `07-CONTEXT.md` and `07-RESEARCH.md`, the following files will be created or modified. 

## 1. `src/production/topology/models.py`
- **Role:** Domain Models
- **Data Flow:** Validates raw topological external payloads -> Internal strictly-typed Pydantic structures enforcing the Entity Metadata Principle.
- **Closest Analog:** `WebhookPayload` in `src/production/main.py`
- **Concrete Code Excerpt:**
  ```python
  class WebhookPayload(BaseModel):
      repository_url: str
      commit_sha: str
      service_name: str
  ```
  *(Pattern to follow: Using Pydantic models for strict structural validation of data inputs before processing or persisting.)*

## 2. `src/production/topology/repository.py`
- **Role:** Repository Layer (Database Access)
- **Data Flow:** Receives validated Pydantic models -> Translates models to Cypher `MERGE` queries -> Persists idempotent structures to Memgraph.
- **Closest Analog:** `merge_deployment_event` in `src/production/db.py`
- **Concrete Code Excerpt:**
  ```python
  async def merge_deployment_event(repo_url: str, service_name: str):
      now_str = datetime.datetime.now().isoformat()
      query = f"""
      MERGE (r:Repository {{url: $repo}})
      SET r.source = 'webhook_simulation',
          r.external_id = '{str(uuid.uuid4())}',
          r.fetched_at = '{now_str}',
          r.schema_version = '1.0'
          
      MERGE (s:Service {{name: $service}})
      ...
      """
      driver = AsyncGraphDatabase.driver("bolt://127.0.0.1:7687", auth=("", ""))
      async with driver.session() as session:
          await session.run(query, repo=repo_url, service=service_name)
      await driver.close()
  ```
  *(Pattern to follow: Encapsulating Cypher MERGE queries within specific data-access asynchronous functions using the Neo4j/Memgraph driver, keeping this out of Pydantic models entirely.)*

## 3. `tests/test_topology.py`
- **Role:** Validation & Testing
- **Data Flow:** Unit / integration testing of models and db operations against expected outcomes.
- **Closest Analog:** Testing interactions like `test_db2.py` combined with Pytest model tests.
- **Concrete Code Excerpt:**
  ```python
  from src.production.db import init_clickhouse, insert_webhook_event, merge_deployment_event
  
  # DB Interaction Testing
  print("merge")
  merge_deployment_event("repo", "service")
  print("merge done")
  ```
  *(Pattern to follow: Simulating data flow through the application boundaries and ensuring queries execute successfully, while also verifying strict validation failures for incomplete metadata.)*
