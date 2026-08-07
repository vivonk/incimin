# Roadmap: incimin.io — AI SRE Agent

## Milestones

- ✅ **v1.5 Milestone** — Phases 1-5 (shipped 2026-08-06)

## Phases

<details>
<summary>✅ v1.5 Milestone (Phases 1-5) — SHIPPED 2026-08-06</summary>

- [x] Phase 1: Infrastructure Foundation (4/4 plans) — completed 2026-08-05
- [x] Phase 2: Data Plane Initialization (4/4 plans) — completed 2026-08-06
- [x] Phase 3: Agent Core (1/1 plans) — completed 2026-08-06
- [x] Phase 4: UI Integration & Demo Choreography (1/1 plans) — completed 2026-08-06
- [x] Phase 5: Golden Path Validation (1/1 plans) — completed 2026-08-06

</details>

## Active

### Phase 07: Core Models and DB Integration

  - **Requirements:** CORE-01, ADV-01
  - **Success Criteria:**
    - Pydantic models for ServiceNode and ServiceEdge enforce Entity Metadata Principle fields.
    - Dual identity provenance (`external_id` and internal ID) is structurally validated.
    - Pydantic models can be successfully translated to Memgraph Cypher `MERGE` queries.

### Phase 08: Core Abstraction Layer and Plugin Registry

  - **Requirements:** CORE-02, CORE-03
  - **Success Criteria:**
    - `TopologyPlugin` ABC defines a standard asynchronous `fetch_topology` interface.
    - `TopologyManager` can discover and load internal plugins from configuration.
    - Plugin registry rejects plugins that do not implement the `TopologyPlugin` interface correctly.

### Phase 09: SigNoz Plugin MVP Implementation

  - **Requirements:** PLUG-01
  - **Success Criteria:**
    - `SigNozServiceMap` plugin is implemented using `httpx` and `tenacity`.
    - Plugin successfully fetches topology data from the SigNoz API.
    - Fetched data is normalized into the standardized canonical data models before yielding.

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Infrastructure Foundation | v1.5 | 4/4 | Complete | 2026-08-05 |
| 2. Data Plane Initialization | v1.5 | 4/4 | Complete | 2026-08-06 |
| 3. Agent Core | v1.5 | 1/1 | Complete | 2026-08-06 |
| 4. UI Integration & Demo Choreography | v1.5 | 1/1 | Complete | 2026-08-06 |
| 5. Golden Path Validation | v1.5 | 1/1 | Complete | 2026-08-06 |
| 6. Production Data Planes | v1.5 | 1/1 | Complete | 2026-08-06 |
| 07. Core Models and DB Integration | v1.6 | 1/1 | Complete    | 2026-08-06 |
| 08. Core Abstraction Layer and Plugin Registry | v1.6 | 1/1 | Complete    | 2026-08-06 |
| 09. SigNoz Plugin MVP Implementation | v1.6 | 1/1 | Complete    | 2026-08-07 |
