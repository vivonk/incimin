# Milestone v1.6 Requirements

## Core Architecture

- [x] **CORE-01**: The system must define a standardized Topology Data Model carrying `source`, `external_id`, `fetched_at`, and `schema_version` metadata.
- [ ] **CORE-02**: The system must provide a Core Abstraction Layer (ABC) for topology providers to ensure standard interaction.
- [ ] **CORE-03**: The system must implement a Simple Plugin Registry to discover and load internal plugins.

## Plugins

- [ ] **PLUG-01**: The system must include a SigNoz Plugin (`SigNozServiceMap`) that fetches topology data from the SigNoz API and normalizes it into the standard data model.

## Advanced

- [x] **ADV-01**: The system must maintain Dual Identity Provenance by retaining both the provider's `external_id` and the internal ID.

## Future Requirements (Deferred)

- DataDog Plugin
- Prometheus Plugin
- Plugin Failure Isolation

## Out of Scope

- Automated Dependency Inference (LLM): Introduces hallucination risk in the critical path, violating architecture constraints.
- External Plugin Ecosystem (`entry_points`): Over-engineered for a single-org deployment; adds security and maintenance overhead.

## Traceability

- **CORE-01** -> Phase 07
- **CORE-02** -> Phase 08
- **CORE-03** -> Phase 08
- **PLUG-01** -> Phase 09
- **ADV-01** -> Phase 07
