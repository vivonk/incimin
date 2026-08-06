# Phase 08 Research: Core Abstraction Layer and Plugin Registry

## Objective
The goal of this phase is to establish the foundation for fetching topology data from various sources by implementing a standardized abstraction layer (CORE-02) and an internal plugin registry (CORE-03).

## Requirements Addressed
- **CORE-02**: Provide a Core Abstraction Layer (ABC) for topology providers to ensure standard interaction.
- **CORE-03**: Implement a Simple Plugin Registry to discover and load internal plugins.

## Implementation Details & Decisions

### 1. TopologyPlugin ABC
- **Standard Interface**: Must define an abstract method, typically `fetch_topology()`, which is asynchronous.
- **Streaming Design**: `fetch_topology()` should return an `AsyncIterator[ServiceNode | ServiceEdge]`. This streams items to maintain efficiency and low memory footprint.
- **Data Models**: Relies on the `ServiceNode` and `ServiceEdge` Pydantic models created in Phase 07 (located in `src/production/topology/models.py`), which enforce the required **Entity Metadata Principle**.

### 2. Plugin Configuration
- **Settings Management**: Use Pydantic `BaseSettings` to provide strongly-typed configuration via environment variables for each plugin.

### 3. TopologyManager & Plugin Registry
- **Loading Mechanism**: Use an **Explicit Mapping** approach (e.g., `PLUGINS = {'signoz': SigNozPlugin}`). This keeps the registry simple, secure, and easily traceable.
- **Out of Scope constraints**: Do **not** use an external plugin ecosystem mechanism like Python `entry_points`. The requirements explicitly state this is over-engineered for a single-org deployment and adds unnecessary overhead.
- **Validation**: The registry must actively validate that loaded plugins correctly implement the `TopologyPlugin` interface and reject those that do not.

## Key Takeaways for Planning
- **New Files Needed**: 
  - An interface definition file (e.g., `src/production/topology/plugin.py` or similar) for the `TopologyPlugin` ABC.
  - A registry/manager file (e.g., `src/production/topology/manager.py`) for the `TopologyManager` and the explicit `PLUGINS` mapping.
- **Tests Needed**: 
  - Unit tests verifying the ABC constraints.
  - Unit tests for the `TopologyManager` validating successful plugin registration, config loading, and rejection of invalid/improperly typed plugins.
- **Dependencies**: Ensure the Pydantic models from Phase 07 are imported and utilized correctly in type hints for the new ABC.
