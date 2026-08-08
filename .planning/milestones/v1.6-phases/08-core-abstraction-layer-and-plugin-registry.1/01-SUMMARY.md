---
phase: 08-core-abstraction-layer-and-plugin-registry
plan: 01
subsystem: topology
tags: [pydantic_settings, plugin-architecture, python, abc]

requires:
  - phase: 07-core-models-and-db-integration
    provides: [Pydantic domain models for metadata enforcement]
provides:
  - TopologyPlugin ABC for fetching topology data
  - TopologyManager and internal plugin registry
  - Validation of plugins on retrieval
affects: [08-topology-plugin-signoz]

actuals:
  tokens: 125
  tasks: 3
  commits: 3

tech-stack:
  added: [pydantic_settings]
  patterns: [Explicit mapping for plugin registry, ABC interface definition]

key-files:
  created: [src/production/topology/plugin.py, src/production/topology/manager.py, tests/test_plugin.py]
  modified: []

key-decisions:
  - "Used an explicit dictionary mapping for the plugin registry rather than dynamic entry_points to keep it simple and secure."
  - "Utilized pydantic_settings for the base plugin config definition."

patterns-established:
  - "Abstract base class pattern for plugins using ABC."
  - "Explicit manager registration with robust sub-class typing checks."

requirements-completed:
  - CORE-02
  - CORE-03

coverage:
  - id: D1
    description: "TopologyPlugin ABC and Base Configuration"
    requirement: "CORE-02"
    verification:
      - kind: integration
        ref: "python -c 'from src.production.topology.plugin import TopologyPlugin; import inspect; assert inspect.isabstract(TopologyPlugin)'"
        status: pass
    human_judgment: false
  - id: D2
    description: "TopologyManager and Plugin Registry"
    requirement: "CORE-03"
    verification:
      - kind: unit
        ref: "tests/test_plugin.py"
        status: pass
    human_judgment: false

duration: 10 min
completed: 2026-08-06
status: complete
---

# Phase 08 Plan 01: Core Abstraction Layer and Plugin Registry Summary

**Core abstraction layer using ABC and explicit plugin registry manager for topology fetchers**

## Performance

- **Duration:** 10 min
- **Started:** 2026-08-06T23:36:18+05:30
- **Completed:** 2026-08-06T23:38:00+05:30
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- Implemented `TopologyPlugin` ABC with an async `fetch_topology` method stream.
- Created `TopologyManager` maintaining an explicit mapping (`PLUGINS`) of topology fetchers.
- Implemented comprehensive type and subclass validation when retrieving plugins.
- Added a base configuration class using `pydantic_settings.BaseSettings`.

## Task Commits

Each task was committed atomically:

1. **Task 1: TopologyPlugin ABC and Base Configuration** - `e78fa8c` (feat)
2. **Task 2: TopologyManager and Plugin Registry** - `fdd5548` (feat)
3. **Task 3: Unit Tests for Core Abstraction and Registry** - `5f29928` (test)

**Plan metadata:** (docs: complete plan)

## Files Created/Modified
- `src/production/topology/plugin.py` - Core abstraction layer interface definition.
- `src/production/topology/manager.py` - Plugin registry manager.
- `tests/test_plugin.py` - Unit tests for abstract constraints and registry retrieval.

## Decisions Made
- Used an explicit dictionary mapping (`PLUGINS = {}`) to satisfy the simplicity and security constraint, avoiding heavy dynamic plugin loading via Python `entry_points`.
- Used `yield` internally in `fetch_topology` base method to implicitly type as AsyncGenerator without requiring complex implementation details for subclasses.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The core abstraction layer and manager are complete. Ready to implement concrete plugins (such as the SigNoz plugin) mapping into this architecture.

---
*Phase: 08-core-abstraction-layer-and-plugin-registry*
*Completed: 2026-08-06*
