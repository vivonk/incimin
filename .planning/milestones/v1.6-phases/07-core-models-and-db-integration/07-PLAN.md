---
phase: 07-core-models-and-db-integration
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/production/topology/models.py
  - src/production/topology/repository.py
  - tests/test_topology.py
autonomous: true
requirements: [CORE-01, ADV-01]

must_haves:
  truths:
    - Pydantic models for ServiceNode and ServiceEdge enforce Entity Metadata Principle fields
    - Dual identity provenance (external_id and internal ID) is structurally validated
    - Pydantic models can be successfully translated to Memgraph Cypher MERGE queries
    - Cypher query generation and DB interactions reside in a separate Repository Layer
  artifacts:
    - src/production/topology/models.py
    - src/production/topology/repository.py
  key_links:
    - Domain models strictly validate payloads before they reach the repository
---

<objective>
Standardize topology models and implement the database integration layer for Memgraph.
Purpose: Create strictly-typed Pydantic domain models for topology nodes and edges enforcing metadata requirements, and build a repository layer to persist these models into Memgraph idempotently.
Output: Validated Pydantic models and a TopologyRepository abstracting Memgraph interactions, fully tested.
</objective>

<execution_context>
@~/.gemini/antigravity/gsd-core/workflows/execute-plan.md
@~/.gemini/antigravity/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/phases/07-core-models-and-db-integration/07-CONTEXT.md
@.planning/phases/07-core-models-and-db-integration/07-RESEARCH.md
@.planning/phases/07-core-models-and-db-integration/07-PATTERNS.md
</context>

<tasks>

<task type="tracer">
  <name>End-to-end Topology Models and Upsert</name>
  <files>src/production/topology/models.py, src/production/topology/repository.py, tests/test_topology.py</files>
  <action>
    Create base mixins/models for Entity Metadata fields in `src/production/topology/models.py`. 
    Implement `ServiceNode` and `ServiceEdge` Pydantic models enforcing `source`, `external_id`, `fetched_at`, and `schema_version` (per CORE-01).
    Implement deterministic hashing for the internal ID (UUID5 from source + external_id) (per ADV-01).
    Use default placeholders like "unknown" for missing external fields rather than failing strictly.
    In `src/production/topology/repository.py`, create `TopologyRepository.upsert_node` and `TopologyRepository.upsert_edge` to translate these validated Pydantic models into Cypher `MERGE` queries and execute them against Memgraph.
    Ensure that DB interaction is fully encapsulated in the repository, leaving Pydantic models pure.
    Create an integration test in `tests/test_topology.py` that instantiates models and upserts them successfully to Memgraph.
  </action>
  <verify>
    <automated>pytest tests/test_topology.py</automated>
  </verify>
  <done>The single happy path works end-to-end: a topology node is instantiated with full metadata, strictly validated by Pydantic, and merged idempotently into Memgraph via the repository.</done>
</task>

<task type="auto" tdd="true">
  <name>Model Validation and Provenance Requirements</name>
  <files>src/production/topology/models.py, tests/test_topology.py</files>
  <behavior>
    - Test 1: ServiceNode instantiation fails if source, external_id, fetched_at, or schema_version are missing.
    - Test 2: Internal ID is correctly derived deterministically from source and external_id.
    - Test 3: Default placeholders ("unknown") are applied correctly for missing optional external payload fields.
  </behavior>
  <action>
    Enhance model testing to explicitly check Pydantic structural validation failures.
    Verify that the Entity Metadata Principle is strictly enforced at the model boundary.
    Ensure Dual Identity Provenance is validated by asserting both `external_id` and the deterministic internal ID exist on instantiated objects.
  </action>
  <verify>
    <automated>pytest tests/test_topology.py</automated>
  </verify>
  <done>Pydantic structural validation correctly enforces mandatory provenance metadata and generates deterministic internal IDs.</done>
</task>

<task type="auto" tdd="true">
  <name>Repository Cypher MERGE Logic Testing</name>
  <files>src/production/topology/repository.py, tests/test_topology.py</files>
  <behavior>
    - Test 1: TopologyRepository properly constructs cypher queries with all Entity Metadata Principle properties.
    - Test 2: Idempotent upserts don't create duplicate nodes on subsequent calls.
  </behavior>
  <action>
    Expand testing for `TopologyRepository` to verify that `MERGE` statements execute successfully via the Memgraph Python driver.
    Test subsequent upserts of the same `ServiceNode` (based on internal ID) to ensure nodes are merged rather than duplicated.
  </action>
  <verify>
    <automated>pytest tests/test_topology.py</automated>
  </verify>
  <done>TopologyRepository reliably converts validated models to Cypher and achieves idempotent graph persistence.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Domain Layer | Untrusted topological external payloads boundary |
| DB Layer | Application to Memgraph graph database |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-07-01 | Injection | repository.py | high | mitigate | Use parameterized queries for Memgraph via Neo4j driver |
| T-07-SC | Tampering | pip installs | high | mitigate | slopcheck + blocking human checkpoint for [ASSUMED]/[SUS] |
</threat_model>

<verification>
Run `pytest tests/test_topology.py` to verify structural validation rules and Memgraph persistence logic end-to-end.
</verification>

<success_criteria>
- Pydantic models for ServiceNode and ServiceEdge enforce Entity Metadata Principle fields.
- Dual identity provenance (`external_id` and internal ID) is structurally validated.
- Pydantic models can be successfully translated to Memgraph Cypher `MERGE` queries via a separate Repository layer.
</success_criteria>
