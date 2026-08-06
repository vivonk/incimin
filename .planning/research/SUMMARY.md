# Project Research Summary

**Project:** incimin.io
**Domain:** Python Plugin Architecture & API Integration
**Researched:** 2026-08-06
**Confidence:** HIGH

## Executive Summary

We are building a Python plugin architecture to integrate with external observability providers (e.g. SigNoz, DataDog) and ingest service topology data into our Memgraph backend. The recommended approach utilizes a Strategy Pattern with an Object-Oriented Abstract Base Class (ABC) and a simple internal registry, bypassing heavy dynamic loading ecosystems since this is an internal, single-org deployment.

The primary risk revolves around leaking provider-specific concepts into the core system and losing data provenance. We mitigate this through strict Canonical Data Models enriched with metadata (`source`, `external_id`, `fetched_at`) fulfilling the backend Entity Metadata Principle. Fully async I/O ensures the core application does not stall during ingestion.

## Key Findings

### Recommended Stack

Our stack leverages standard Python capabilities augmented with modern, resilient async libraries. 

**Core technologies:**
- `typing.Protocol` / `abc.ABC`: Plugin Interface Definition — Structural subtyping or abstract classes without forcing deep inheritance hierarchies. Keeps plugins decoupled.
- `httpx`: Async HTTP Client — Integrates natively with FastAPI's async event loop.
- `tenacity`: Retries & Resilience — Wraps `httpx` calls to provider APIs to handle rate limits, timeouts, and transient network errors gracefully.
- `pydantic`: Data Normalization — Strictly validate and normalize external provider data into the core `TopologyGraph` schema.

### Expected Features

**Must have (table stakes):**
- Standardized Topology Data Model — Ensures downstream consumers (Memgraph ingestion) have a consistent internal schema.
- Core Abstraction Layer (ABC) — Ensures standard interaction and outputs across all providers.
- Simple Plugin Registry — Ability to dynamically load internal plugins via configuration.
- SigNoz Plugin (`SigNozServiceMap`) — Need at least one working plugin to prove the architecture.

**Should have (competitive):**
- Dual Identity Provenance — Complete traceability for auditability and debugging (`external_id` + internal ID).
- Plugin Failure Isolation — Fallbacks and circuit breakers so API timeouts don't crash the core system.

**Defer (v2+):**
- DataDog / Prometheus Plugins
- External Plugin Ecosystem (`entry_points`) — Unnecessary overhead for single-org.
- Automated Dependency Inference (LLM) — Banned due to hallucination risks.

### Architecture Approach

The architecture isolates external integration details from core domain logic using a Strategy Pattern.

**Major components:**
1. `TopologyManager` — Orchestrates fetching from plugins and handles background syncing tasks.
2. `PluginInterface` (ABC) — Defines the standard contract (`fetch_topology()`) for fetching topology data asynchronously.
3. Canonical Data Models — Pydantic models representing standard service nodes and edges, carrying mandatory metadata (`source`, `external_id`, etc.).
4. `db.py` (Data Access Layer) — Translates canonical models into async Memgraph Cypher `MERGE` queries.

### Critical Pitfalls

1. **Leaking Provider-Specific Concepts into Core** — Avoid by defining a strict, provider-agnostic internal Domain Model. Core must never import plugin-specific types.
2. **Missing Provenance / Bare External Payloads** — Avoid by strictly adhering to the Entity Metadata Principle. Require `source`, `external_id`, `fetched_at`, `schema_version`.
3. **Blocking I/O in the Ingestion Pipeline** — Avoid by using fully async HTTP requests (`httpx`) and explicit timeouts.
4. **Silent Failures on Provider Rate Limits** — Avoid by throwing specific custom exceptions and maintaining the last known good graph state instead of wiping.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Canonical Models
**Rationale:** The critical foundation to enforce the Entity Metadata Principle and ensure no provider concepts leak into core.
**Delivers:** `ServiceNode` and `ServiceEdge` Pydantic models in `topology/models.py`.
**Addresses:** Standardized Topology Data Model.
**Avoids:** Missing Provenance, Leaking Provider Concepts.

### Phase 2: Plugin Interface & Registry
**Rationale:** Establishes the contract for all providers and the manager that orchestrates them.
**Delivers:** `TopologyPlugin` ABC and `TopologyManager` in `topology/plugins/base.py` and `topology/manager.py`.
**Uses:** `abc.ABC`, `pydantic`.
**Implements:** Core Abstraction Layer and Dynamic Plugin Registry.
**Avoids:** Hardcoding Provider Logic in the Manager.

### Phase 3: Data Access Layer (DB Integration)
**Rationale:** Required to ingest the canonical models with proper provenance into Memgraph.
**Delivers:** Async Cypher `MERGE` query functions for topology in `db.py`.
**Implements:** Data Store Layer (Memgraph).

### Phase 4: SigNoz Plugin MVP
**Rationale:** Proves the architecture and provides the first real implementation for extracting topology.
**Delivers:** Concrete `SigNozPlugin` fetching data in `topology/plugins/signoz.py`.
**Uses:** `httpx`, `tenacity`.
**Addresses:** SigNoz Plugin MVP.
**Avoids:** Blocking I/O, Silent Failures on Provider Rate Limits.

### Phase 5: API Integration & Orchestration
**Rationale:** Wires the pipeline to be executable via FastAPI endpoints or background tasks.
**Delivers:** `/api/v1/topology/sync` endpoint or equivalent startup trigger in `main.py`.

### Phase Ordering Rationale

- We build Data Models and Core Abstractions first (Phases 1-2) to ensure the interface is completely insulated from specific provider idiosyncrasies.
- We implement the DB layer (Phase 3) next to verify the models correctly align with graph database requirements (metadata).
- Only then do we build the SigNoz specific plugin (Phase 4), forcing it to map into the robust, predefined core.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4:** Requires verification of exact SigNoz API payload structure, authentication methods, and endpoint documentation.

Phases with standard patterns (skip research-phase):
- **Phase 3:** Standard Cypher MERGE queries with `neo4j` async driver.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Uses well-understood, standard Python async ecosystem tools. |
| Features | HIGH | Clear boundary drawn around MVP requirements; explicit anti-features listed. |
| Architecture | HIGH | Strategy pattern properly decouples integration logic from core ingestion. |
| Pitfalls | HIGH | Known patterns related to graph DB metadata and API ingestion are addressed. |

**Overall confidence:** HIGH

### Gaps to Address

- **SigNoz API Details:** We know *what* we need (topology data) but not the *exact shape* of SigNoz's API response. This will need to be resolved during Phase 4 implementation.
- **Handling Large Graphs:** The initial implementation will use synchronous batched inserts. If the service graph grows to 1000+ nodes, we will need to revisit differential syncing.

## Sources

### Primary (HIGH confidence)
- `AGENTS.md` — Entity Metadata Principle, provenance requirements.
- `PROJECT.md` — Project constraints, zero LLM hallucinations philosophy, single-org deployment.

### Secondary (MEDIUM confidence)
- Python Standard Library (`abc`, `importlib`) — Standard plugin patterns.
- `httpx` & `tenacity` Documentation — Async HTTP and retry standards.

### Tertiary (LOW confidence)
- OpenTelemetry Plugin Architecture Best Practices — Evaluated but adapted for a simpler single-org scope.

---
*Research completed: 2026-08-06*
*Ready for roadmap: yes*
