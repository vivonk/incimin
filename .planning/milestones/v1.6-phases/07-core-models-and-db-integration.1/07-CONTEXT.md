# Phase 07: Core Models and DB Integration Context

## Domain
Core Models and DB Integration - Standardizing topology models and storing them into Memgraph.

## Locked Requirements
- Pydantic models for ServiceNode and ServiceEdge enforce Entity Metadata Principle fields.
- Dual identity provenance (`external_id` and internal ID) is structurally validated.
- Pydantic models can be successfully translated to Memgraph Cypher `MERGE` queries.

## Decisions

### Internal ID Strategy
- **Decision:** Use a deterministic hash (e.g., UUID5 generated from `source` + `external_id`).
- **Rationale:** Ensures idempotency and simplifies `MERGE` queries since the internal ID can be calculated offline without prior database lookups.

### Cypher Query Generation
- **Decision:** Implement a Separate Repository Layer (e.g., `TopologyRepository.upsert(model)`).
- **Rationale:** Keeps database interaction logic and Cypher queries completely out of the Pydantic domain models, maintaining clean separation of concerns.

### Handling Missing External Fields
- **Decision:** Use default placeholders (e.g., "unknown") instead of strict dropping.
- **Rationale:** Allows partial data to be persisted to the graph, which provides better visibility and helps with debugging data sources.

## Agent Instructions (from AGENTS.md)
- **Entity Metadata Principle:** External → internal always wraps into an internal model. Missing provenance is a design bug.
- **Required fields:** `source`, `external_id`, `fetched_at`, `schema_version`.
- **Identity:** Keep dual identity (`external_id` + internal ID).

## Canonical Refs
- `.planning/ROADMAP.md`
- `.planning/REQUIREMENTS.md`
- `AGENTS.md` (Entity Metadata Principle instructions)
