---
wave: 1
depends_on: []
requirements: ["PLUG-01"]
files_modified:
  - pyproject.toml
  - src/production/topology/plugins/signoz.py
  - tests/test_signoz_plugin.py
autonomous: true
must_haves:
  truths:
    - "The SigNoz plugin implementation yields strictly Pydantic models (ServiceNode, ServiceEdge) rather than raw dictionaries."
    - "Entities are mapped with source='signoz', schema_version='1', external_id, and fetched_at according to the Entity Metadata Principle."
    - "Malformed payload elements result in logged warnings and are skipped, preserving the rest of the generator stream."
    - "Tenacity retries are applied with a maximum of 5 attempts and up to 30s backoff."
  prohibitions: []
  assumptions: []
---

# Phase 09 Plan: SigNoz Plugin MVP Implementation

## Artifacts this phase produces

- **New File Paths**:
  - `src/production/topology/plugins/signoz.py`
  - `tests/test_signoz_plugin.py`
- **Classes**:
  - `SigNozPluginConfig`
  - `SigNozServiceMap`
- **Functions / Methods**:
  - `SigNozServiceMap.fetch_topology`
- **CLI Flags**: None
- **Decorators**: None
- **Struct/Dataclass Fields**:
  - `SigNozPluginConfig.SIGNOZ_API_URL`
  - `SigNozPluginConfig.SIGNOZ_API_TOKEN`

## Assumptions Surface
- No specific boundary, precision, or concurrency edges were identified beyond standard API limits handled by tenacity.

## Tasks

<task>
<read_first>
- pyproject.toml
</read_first>
<action>
Run `uv add httpx tenacity` and `uv add --dev pytest-httpx` (or standard `pip` equivalent if not using `uv`) to append these libraries to the `pyproject.toml` dependencies.
</action>
<acceptance_criteria>
- `pyproject.toml` contains `httpx`
- `pyproject.toml` contains `tenacity`
</acceptance_criteria>
</task>

<task>
<read_first>
- src/production/topology/plugin.py
- src/production/topology/plugins/signoz.py
</read_first>
<action>
Create `src/production/topology/plugins/signoz.py`.
Import `PluginConfig` and `TopologyPlugin` from `src.production.topology.plugin`.
Define `class SigNozPluginConfig(PluginConfig)` with `SIGNOZ_API_URL` and `SIGNOZ_API_TOKEN` string fields.
Define `class SigNozServiceMap(TopologyPlugin)` initialized with the config.
</action>
<acceptance_criteria>
- `src/production/topology/plugins/signoz.py` contains `class SigNozPluginConfig(PluginConfig)`
- `src/production/topology/plugins/signoz.py` contains `class SigNozServiceMap(TopologyPlugin)`
</acceptance_criteria>
</task>

<task>
<read_first>
- src/production/topology/models.py
- src/production/topology/plugins/signoz.py
</read_first>
<action>
In `src/production/topology/plugins/signoz.py`, implement the `async def fetch_topology(self)` method in `SigNozServiceMap`.
Use `httpx.AsyncClient` to fetch data from the API endpoint based on `self.config.SIGNOZ_API_URL`, passing `self.config.SIGNOZ_API_TOKEN` in the headers for authentication.
Wrap the HTTP call logic in a `@retry` decorator from `tenacity` with `stop=stop_after_attempt(5)` and `wait=wait_exponential(max=30)`.
Parse the JSON response. If an individual entity lacks required fields, log a warning via `logging.warning` and `continue` to skip it.
Yield valid payload entities as instantiated `ServiceNode` or `ServiceEdge` objects. Ensure `source="signoz"`, `schema_version="1"`, `external_id` (mapped from the API payload), and `fetched_at` (current UTC time) are populated per the Entity Metadata Principle.
</action>
<acceptance_criteria>
- `src/production/topology/plugins/signoz.py` contains `@retry(stop=stop_after_attempt(5)`
- `src/production/topology/plugins/signoz.py` contains `logging.warning`
- `src/production/topology/plugins/signoz.py` uses `self.config.SIGNOZ_API_TOKEN` in headers
- `src/production/topology/plugins/signoz.py` contains `yield ServiceNode` and `yield ServiceEdge` initialized with all required metadata fields (`source`, `schema_version`, `external_id`, `fetched_at`)
</acceptance_criteria>
</task>

<task>
<read_first>
- src/production/topology/plugins/signoz.py
- tests/test_signoz_plugin.py
</read_first>
<action>
Create `tests/test_signoz_plugin.py`.
Write an async test case `test_signoz_plugin_fetch` using `pytest_httpx` (or standard async mock) to stub the HTTP response.
Mock a JSON response array containing both valid entities and malformed ones (e.g. missing `external_id`).
Assert that `fetch_topology()` iterates without raising an error, correctly yielding the valid `ServiceNode`/`ServiceEdge` objects and skipping the malformed entities.
</action>
<acceptance_criteria>
- `tests/test_signoz_plugin.py` contains `test_signoz_plugin_fetch`
- `pytest tests/test_signoz_plugin.py` exits 0
</acceptance_criteria>
</task>
