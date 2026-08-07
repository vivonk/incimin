# Phase 07: Core Models and DB Integration - Research

## Objective
To gather the necessary context, requirements, and design constraints to effectively plan the implementation of Phase 07: "Core Models and DB Integration".

## Key Concepts & Principles
1. **Entity Metadata Principle (CORE-01)**: 
   - External entities must be wrapped into internal Pydantic domain models.
   - **Required Metadata**: `source`, `external_id`, `fetched_at`, `schema_version`.
   - Missing provenance is considered a design bug.
2. **Dual Identity Provenance (ADV-01)**: 
   - Models must retain the provider's `external_id` (source key) alongside our internal ID.
   - **Internal ID Strategy**: Use a deterministic hash (e.g., UUID5 generated from `source` + `external_id`). This ensures idempotency and simplifies Memgraph `MERGE` queries since IDs can be calculated offline.
3. **Data Completeness**:
   - **Handling Missing Fields**: Use default placeholders (e.g., "unknown") instead of strict dropping to allow partial data to persist and aid in debugging.

## Architecture Guidelines
- **Domain Models**: Use Pydantic to strictly validate the structures of `ServiceNode` and `ServiceEdge`, enforcing metadata requirements.
- **Separation of Concerns**: 
   - Pydantic models must be completely clean of database interaction logic.
   - Cypher `MERGE` query generation and DB interactions must reside in a separate Repository Layer (e.g., `TopologyRepository.upsert(model)`).

## Prerequisites and Current State
- The Memgraph database is up and running, with volume mount persistence confirmed during Phase 02 (Data Plane Initialization).
- We are working towards Milestone v1.6 (Plugin-based Service Topology).

## Planning Considerations for Implementation
When creating the plan for this phase, the tasks should cover:
1. **Model Definition**: 
   - Create base mixins or base models for the Entity Metadata fields.
   - Implement `ServiceNode` and `ServiceEdge` Pydantic models.
   - Implement the UUID5 deterministic hashing for the internal ID.
2. **Repository Layer**:
   - Implement a `TopologyRepository` that abstracts Memgraph interactions.
   - Write logic to securely translate Pydantic models into Cypher `MERGE` statements.
3. **Validation & Testing**:
   - Tests to ensure Pydantic structural validation catches missing metadata.
   - Tests to verify the generation of correct `MERGE` queries for upserting nodes and edges idempotently.
