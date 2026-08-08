---
phase: 09-signoz-plugin-mvp-implementation
plan: 09
subsystem: topology
tags: [plugin, signoz, httpx, tenacity, pydantic, python]

# Dependency graph
requires:
  - phase: 08-core-abstraction-layer-and-plugin-registry
    provides: [TopologyPlugin ABC, PluginConfig]
provides:
  - SigNozServiceMap plugin implementation
affects: []

actuals:
  tokens: 1500
  tasks: 4
  commits: 3

tech-stack:
  added: [httpx, tenacity, pytest-httpx]
  patterns: [HTTP Client with Retries, Error Tolerance in Parsing]

key-files:
  created: [src/production/topology/plugins/signoz.py, tests/test_signoz_plugin.py]
  modified: [pyproject.toml, uv.lock]

key-decisions:
  - "Used a dynamic JSON parsing approach checking for a list or dict with nodes/edges to support varying SigNoz API responses."
  - "Wrapped HTTP logic in Tenacity for exponential backoff retries."

patterns-established:
  - "Entity Metadata Principle enforcement via yield statements of ServiceNode and ServiceEdge."

requirements-completed:
  - PLUG-01

duration: 10 min
completed: 2026-08-07
status: complete
---

# Phase 09: SigNoz Plugin MVP Implementation Summary

**SigNoz API fetcher implementing the TopologyPlugin interface yielding Pydantic entity models**

## Performance

- **Duration:** 10 min
- **Started:** 2026-08-07T00:04:38+05:30
- **Completed:** 2026-08-07T00:15:00+05:30
- **Tasks:** 4
- **Files modified:** 4

## Accomplishments
- Appended `httpx` and `tenacity` for production and `pytest-httpx` for dev in `pyproject.toml`.
- Implemented `SigNozServiceMap` inheriting from `TopologyPlugin` utilizing `httpx` to fetch topology JSON with exponential backoff powered by `tenacity`.
- Translated arbitrary node/edge JSON data into structured `ServiceNode` and `ServiceEdge` Pydantic models obeying the Entity Metadata Principle.
- Wrote async unit tests with `pytest-httpx` to verify retry behavior, entity formatting, and error tolerance with malformed records.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add dependencies** - `c1f08da` (chore)
2. **Task 2 & 3: Plugin Implementation** - `62b1fc0` (feat)
3. **Task 4: Tests** - `95e25c6` (test)

## Files Created/Modified
- `pyproject.toml` - Added httpx and tenacity
- `src/production/topology/plugins/signoz.py` - Core SigNoz topology plugin
- `tests/test_signoz_plugin.py` - Unit test for the plugin using pytest-httpx

## Decisions Made
- Used resilient JSON schema parsing that supports either a list or `data.nodes`/`data.edges` structures.
- Skipped malformed entities with a `logging.warning` to ensure resilience of the full graph sync even with partial API defects.

## Deviations from Plan

- Fix module not found in pytest by adding `PYTHONPATH=.`. Handled seamlessly during test execution.

## Issues Encountered
None.

## User Setup Required
- Define `SIGNOZ_API_URL` and `SIGNOZ_API_TOKEN` environment variables when initializing the plugin in production.

## Next Phase Readiness
The plugin implementation is complete and verified. It is ready for registration via the abstraction layer.
