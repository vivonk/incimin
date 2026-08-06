---
wave: 1
depends_on: []
files_modified:
  - src/production/topology/plugin.py
  - src/production/topology/manager.py
  - tests/test_plugin.py
autonomous: true
---

# Phase 08 Plan 01: Core Abstraction Layer and Plugin Registry

## Goal
Establish the foundation for fetching topology data by implementing a standardized abstraction layer (CORE-02) and an internal plugin registry (CORE-03).

## Context
**specless_probe_fallback:** disabled (workflow.specless_probe_fallback=false). No probe-derived predicates generated for SPEC-absent sections this run.

## Requirements
- CORE-02
- CORE-03

## Tasks

```xml
<task>
  <id>1</id>
  <name>TopologyPlugin ABC and Base Configuration</name>
  <description>Create the core abstraction layer for topology plugins and the base configuration model.</description>
  <read_first>
    - src/production/topology/models.py
    - CONVENTIONS.md
  </read_first>
  <action>
    Create src/production/topology/plugin.py containing a TopologyPlugin ABC. 
    It must define an abstract async method fetch_topology() returning AsyncIterator[ServiceNode | ServiceEdge]. 
    Create a base configuration class inheriting from pydantic_settings.BaseSettings for plugins.
  </action>
  <acceptance_criteria>
    - The file src/production/topology/plugin.py exists.
    - TopologyPlugin is an abstract base class (cannot be instantiated directly).
    - fetch_topology has a return type annotation of AsyncIterator[ServiceNode | ServiceEdge].
    - `python -c "from src.production.topology.plugin import TopologyPlugin; import inspect; assert inspect.isabstract(TopologyPlugin)"` passes.
  </acceptance_criteria>
</task>

<task>
  <id>2</id>
  <name>TopologyManager and Plugin Registry</name>
  <description>Implement the plugin registry and manager to discover, validate, and load internal plugins.</description>
  <read_first>
    - src/production/topology/plugin.py
  </read_first>
  <action>
    Create src/production/topology/manager.py containing a TopologyManager class and an explicit PLUGINS = {} dictionary mapping. 
    TopologyManager should provide a method to get a plugin by name. 
    It must actively validate that retrieved plugins subclass TopologyPlugin and raise an error otherwise.
  </action>
  <acceptance_criteria>
    - The file src/production/topology/manager.py exists.
    - PLUGINS dict is defined in the module.
    - TopologyManager can retrieve a plugin by name from PLUGINS.
    - TopologyManager raises a ValueError or TypeError if a requested plugin does not subclass TopologyPlugin.
  </acceptance_criteria>
</task>

<task>
  <id>3</id>
  <name>Unit Tests for Core Abstraction and Registry</name>
  <description>Write comprehensive tests to verify ABC constraints and registry validation.</description>
  <read_first>
    - src/production/topology/plugin.py
    - src/production/topology/manager.py
  </read_first>
  <action>
    Create tests/test_plugin.py to test the constraints of TopologyPlugin (cannot instantiate without fetch_topology) and validate that TopologyManager correctly registers valid plugins and rejects invalid ones.
  </action>
  <acceptance_criteria>
    - The file tests/test_plugin.py exists.
    - Tests cover ABC instantiation failure, valid plugin registration, and invalid plugin rejection.
    - `pytest tests/test_plugin.py -v` executes and passes.
  </acceptance_criteria>
</task>
```

## Verification

### must_haves
- [ ] `TopologyPlugin` ABC exists with an asynchronous `fetch_topology` method returning a stream of `ServiceNode` or `ServiceEdge`.
- [ ] `TopologyManager` strictly validates that registered plugins implement `TopologyPlugin`.
- [ ] Explicit mapping `PLUGINS` dictionary is used for the registry, avoiding external entry points.
- [ ] Unit tests verify both ABC constraints and registry validation logic.

### Artifacts this phase produces
- **File:** `src/production/topology/plugin.py`
- **File:** `src/production/topology/manager.py`
- **File:** `tests/test_plugin.py`
- **Class:** `TopologyPlugin` (ABC)
- **Class:** `TopologyManager`
- **Variable/Dict:** `PLUGINS` (in manager.py)
