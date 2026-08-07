# Phase 09: SigNoz Plugin MVP Implementation - Research

**Goal:** Answer "What do I need to know to PLAN this phase well?"

## 1. Requirements & Architecture (PLUG-01)
- The goal is to build a `SigNozServiceMap` plugin that implements the `TopologyPlugin` ABC (from `src/production/topology/plugin.py`).
- The plugin must fetch topology data from the SigNoz API using the `httpx` library.
- The fetched data must be normalized and yielded as `ServiceNode` and `ServiceEdge` Pydantic models (from `src/production/topology/models.py`).

## 2. The Entity Metadata Principle
As mandated by `CONVENTIONS.md`, any external data brought into the system must retain its provenance.
The plugin must map the SigNoz API payload to the internal Pydantic models with the following fields:
- `source`: e.g., `"signoz"`
- `external_id`: The stable ID from the SigNoz service/edge payload.
- `schema_version`: e.g., `"1"`
- `fetched_at`: Handled by the model defaults or injected explicitly at fetch time.

*Crucial rule*: Never yield a raw dictionary or raw API response; always yield the validated `ServiceNode` or `ServiceEdge`.

## 3. Configuration & Authentication
- **Environment Variables**: API URL and tokens should be injected via environment variables.
- We should define a `SigNozPluginConfig(PluginConfig)` using `pydantic_settings.BaseSettings` (since `PluginConfig` exists in `plugin.py`) to manage variables like `SIGNOZ_API_URL` and `SIGNOZ_API_TOKEN`.

## 4. Resilience & Error Handling
- **Retries**: Use `tenacity` for exponential backoff (max 5 tries, up to 30s) around the `httpx` calls to handle transient load or network drops.
- **Parsing Errors**: If a specific node or edge from the SigNoz API is malformed, log a warning and skip that entity. Do not fail the entire async generator loop, so the rest of the graph remains intact.

## 5. Development Strategy for the Plan
- **Dependencies**: Ensure `httpx` and `tenacity` are added to the project dependencies (via `uv add httpx tenacity` if not already present in `pyproject.toml`).
- **File Structure**: Create the plugin logic inside `src/production/topology/plugins/signoz.py` (or similar).
- **Testing**: We should mock the `httpx` responses using `pytest-httpx` or `respx` to test the normalization, retry logic, and error skipping without relying on a live SigNoz API.
