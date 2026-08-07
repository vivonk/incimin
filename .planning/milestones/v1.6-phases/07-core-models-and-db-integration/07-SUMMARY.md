---
phase: 07-core-models-and-db-integration
plan: 01
subsystem: topology
tags: [pydantic, memgraph, cypher, neo4j, python]

# Dependency graph
requires:
  - phase: 02-data-plane-initialization
    provides: [Memgraph instance running locally on 7687]
provides:
  - Pydantic models for ServiceNode and ServiceEdge enforcing Entity Metadata Principle
  - TopologyRepository for upserting validated models into Memgraph
affects: [08-topology-plugin-signoz]

actuals:
  tokens: 2800
  tasks: 3
  commits: 3

tech-stack:
  added: [neo4j]
  patterns: [Pydantic domain models for metadata enforcement, Repository pattern for Cypher queries]

key-files:
  created: [src/production/topology/models.py, src/production/topology/repository.py, tests/test_topology.py]
  modified: []

key-decisions:
  - "Used UUID5 hashing (source + external_id) for deterministic internal IDs to enable idempotent Memgraph MERGEs."
  - "Separated Cypher MERGE queries into a dedicated TopologyRepository to keep Pydantic models pure."
  - "Used 'unknown' as a default placeholder for missing optional external payload fields."

patterns-established:
  - "Entity Metadata Principle enforcement via Pydantic model mixins."
  - "Asynchronous Neo4j driver interactions via a Repository class."

requirements-completed:
  - CORE-01
  - ADV-01

coverage:
  - id: D1
    description: "End-to-end Topology Models and Upsert"
    requirement: "CORE-01"
    verification:
      - kind: integration
        ref: "tests/test_topology.py::test_topology_upsert_end_to_end"
        status: pass
    human_judgment: false
  - id: D2
    description: "Model Validation and Provenance Requirements"
    requirement: "CORE-01"
    verification:
      - kind: unit
        ref: "tests/test_topology.py::test_model_validation_failures"
        status: pass
    human_judgment: false
  - id: D3
    description: "Repository Cypher MERGE Logic Testing"
    requirement: "ADV-01"
    verification:
      - kind: integration
        ref: "tests/test_topology.py::test_idempotent_upsert"
        status: pass
    human_judgment: false

duration: 15 min
completed: 2026-08-06
status: complete
---

# Phase 07: Core Models and DB Integration Summary

**Pydantic domain models enforcing entity metadata and a Memgraph repository layer for idempotent upserts**

## Performance

- **Duration:** 15 min
- **Started:** 2026-08-06T23:06:00Z
- **Completed:** 2026-08-06T23:15:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Implemented `ServiceNode` and `ServiceEdge` Pydantic models with `EntityMetadataMixin` to strictly enforce the Entity Metadata Principle.
- Created `TopologyRepository` for translating validated models into Cypher `MERGE` statements using the asynchronous Neo4j driver.
- Verified idempotent upserts and structural validation failures through comprehensive pytest coverage.

## Task Commits

Each task was committed atomically:

1. **Task 1: End-to-end Topology Models and Upsert** - `hash` (feat)
2. **Task 2: Model Validation and Provenance Requirements** - `hash` (test)
3. **Task 3: Repository Cypher MERGE Logic Testing** - `hash` (feat)

**Plan metadata:** `hash` (docs: complete plan)

## Files Created/Modified
- `src/production/topology/models.py` - Pydantic models for topology nodes and edges enforcing provenance.
- `src/production/topology/repository.py` - Memgraph database interaction layer.
- `tests/test_topology.py` - Validation and integration tests for the topology subsystem.

## Decisions Made
- Used a deterministic UUID5 hash derived from `source` and `external_id` for the internal ID. This ensures idempotency and simplifies Memgraph `MERGE` operations without requiring read-before-write logic.
- Kept Cypher query generation and DB interactions out of Pydantic domain models by implementing a dedicated `TopologyRepository` layer.
- Used default placeholders ("unknown") for missing external payload fields (e.g., `name`) instead of strict failing, allowing partial topology graph data to be persisted for debugging.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
The core domain models and repository layer are fully implemented and verified. The topology subsystem is ready for the SigNoz integration plugin to begin fetching live data.
