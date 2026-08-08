# Technology Stack

<<<<<<< Updated upstream
**Project:** incimin.io — AI SRE Agent, v1.7 Incident Dashboard milestone
**Researched:** 2026-08-08

**Scope note:** This file covers ONLY the new additions required for this milestone (Postgres access, LangGraph Postgres checkpointing, the React frontend, and SSE streaming). The existing validated stack (LangGraph 1.2.10, GQLAlchemy/Memgraph, ClickHouse, FastAPI, numpy<2.0 pin, tensorflow override, Langfuse, etc.) is unchanged and NOT re-litigated here — see `pyproject.toml` and prior research for that.
=======
**Domain:** Plugin Architecture & API Integration
**Researched:** 2026-08-06
**Confidence:** HIGH
>>>>>>> Stashed changes

## Recommended Stack

### Postgres Driver (async, FastAPI-facing)

<<<<<<< Updated upstream
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `psycopg[binary,pool]` | `>=3.2.0,<4` (currently resolves 3.3.4) | Async Postgres driver + connection pool | Official psycopg3 line is async-native (`psycopg.AsyncConnection`, `from psycopg_pool import AsyncConnectionPool`), ships prebuilt binary wheels (`binary` extra removes the need for `libpq`/build toolchain in Docker), and — critically — is the **same driver `langgraph-checkpoint-postgres` requires**. Using one driver avoids running two separate connection pools (asyncpg + psycopg) against the same Postgres instance. |
=======
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `typing.Protocol` (Built-in) | Python 3.10+ | Plugin Interface Definition | Structural subtyping (duck typing) without forcing deep inheritance hierarchies. Keeps plugins decoupled from the core codebase. |
| `importlib.metadata` (Built-in) | Python 3.10+ | Plugin Discovery via Entry Points | Standardized, performant way to load plugins distributed as independent packages (`pip install my-plugin`), avoiding fragile directory scanning. |
| `httpx` | ^0.27.0 | Async HTTP Client | Needed to fetch topology data from SigNoz/DataDog APIs. It integrates natively with FastAPI's async event loop, unlike `requests`. |
>>>>>>> Stashed changes

**Async pool API shape** (psycopg 3.2+):
```python
from psycopg_pool import AsyncConnectionPool

<<<<<<< Updated upstream
pool = AsyncConnectionPool(conninfo="postgresql://...", min_size=1, max_size=10, open=False)
await pool.open()
async with pool.connection() as conn:
    async with conn.cursor() as cur:
        await cur.execute("SELECT 1")
```
Use `pool.connection()` as an async context manager per-request in FastAPI (e.g. via a dependency), not one connection held for the app lifetime.

### LangGraph Postgres Checkpointing

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `langgraph-checkpoint-postgres` | `>=3.1.0,<4` (currently resolves 3.1.2) | Postgres-backed checkpointer for LangGraph state persistence | Its PyPI metadata declares `langgraph-checkpoint<5.0.0,>=4.1.0` — this is an **exact match** to the already-declared (currently unused) `langgraph-checkpoint>=4.1.0,<5` pin in `pyproject.toml`. No version bump needed on that existing dependency; this package simply activates it. |

**Driver confirmation:** `langgraph-checkpoint-postgres` 3.1.2 declares `psycopg>=3.2.0` and `psycopg-pool>=3.2.0` as direct dependencies — it requires **psycopg3**, not asyncpg. This confirms the choice above: adding `psycopg[binary,pool]` satisfies both this package's requirement and the app's own Postgres access, so only one driver enters the dependency tree.

**`.setup()` is required and must be called explicitly.** `AsyncPostgresSaver.setup()` creates the checkpoint tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`) and runs schema migrations — it is **not** run automatically on connect. Call it once at startup (e.g. app lifespan) before the checkpointer is used:
```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async with AsyncPostgresSaver.from_conn_string(DATABASE_URL) as checkpointer:
    await checkpointer.setup()
=======
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `tenacity` | ^9.0.0 | Retries & Resilience | Wrap `httpx` calls to provider APIs to handle rate limits, timeouts, and transient network errors gracefully. |
| `pydantic` | ^2.8.0 | Data Normalization | Already in stack (via FastAPI), but specifically use it here to strictly validate and normalize external provider data (e.g. SigNoz API responses) into the core `TopologyGraph` schema. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pytest-asyncio` | Async Testing | Essential for testing async HTTP clients and plugin resolution logic. |
| `respx` | Mocking HTTP APIs | Use to mock external provider APIs (SigNoz, DataDog) during tests without making real network requests. Integrates natively with `httpx`. |

## Installation

```bash
# Core & Supporting
pip install httpx tenacity

# Dev dependencies
pip install pytest-asyncio respx
>>>>>>> Stashed changes
```
If constructing the connection/pool manually instead of `from_conn_string`, the connections passed to `AsyncPostgresSaver` **must** be opened with `autocommit=True` and `row_factory=dict_row` — `.setup()` silently fails to persist its DDL without `autocommit=True`. This is the single most common integration mistake reported for this package; flag it explicitly in the phase plan.

<<<<<<< Updated upstream
**Transitive addition:** `orjson>=3.11.5` (pulled in by `langgraph-checkpoint-postgres` for fast checkpoint (de)serialization). Pure-Rust binary wheel, no numpy/protobuf entanglement — safe.

### Frontend Toolchain (new — replaces Streamlit)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `vite` | `^8.2.1` | Build tool / dev server | Current stable major; requires Node `^20.19.0 \|\| >=22.12.0` — pin CI/Docker Node image accordingly. |
| `react` / `react-dom` | `^19.2.8` | UI framework | React 19 is the current stable line; no React 20 exists yet. |
| `@vitejs/plugin-react` | `^6.0.5` | Vite React fast-refresh/JSX transform | Declares peer `vite: ^8.0.0` — matches the Vite pin above exactly. |
| `@types/react` / `@types/react-dom` | `^19.2.18` / `^19.2.4` | TS types for React 19 | Must track the React major; mismatched majors are a common source of JSX typing errors. |
| `typescript` | **`^5.9.3`** — do NOT use the `latest` npm tag | Type checking | See "TypeScript version — do not take `latest`" below. |

**TypeScript version — do not take `latest`.** `npm view typescript` currently resolves `latest` to **7.0.2**, a from-scratch Go-native compiler port (GA July 2026, ~10x faster builds). It is a hard incompatibility for this project: `typescript-eslint` 8.66.0 (the standard ESLint↔TS integration) declares a peer constraint of `typescript: ">=4.8.4 <6.1.0"` — it explicitly excludes TS 7.x. TS 7.0 also ships without a stable programmatic API (promised for 7.1), which is exactly the API typescript-eslint's type-aware linting depends on. **Pin `typescript` to `^5.9.3`** (the current, actively-maintained top of the 5.x line) until typescript-eslint and the rest of the tsc-API-consuming ecosystem publish TS7-compatible majors. Re-evaluate TS7 adoption in a later milestone once `typescript-eslint` bumps its peer range.

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `@xyflow/react` | `^12.11.2` | Graph/flow canvas for the incident/topology view | Current stable major of React Flow (rebrand under the `@xyflow` scope); peer deps are just `react`/`react-dom >=17`, satisfied by React 19. |
| `@dagrejs/dagre` | `^3.1.0` | Auto-layout for `@xyflow/react` node graphs | xyflow's own docs deliberately ship **no bundled layout engine** and point users at dagre, elkjs, or d3-hierarchy. Use `@dagrejs/dagre` (the actively maintained fork/successor), **not** the plain `dagre` package on npm — that one is stuck at `0.8.5` and effectively unmaintained. Dagre is the docs' recommendation "if you need to organize your flows into a tree" — appropriate for a service-topology/incident graph, which is fundamentally tree/DAG-shaped from a root incident node. Do not reach for `elkjs` unless a future requirement needs its much more configurable (and complex) layout algorithms; xyflow's own docs say they don't often recommend it for exactly that complexity reason. |

### Server-Sent Events (FastAPI → dashboard streaming)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `sse-starlette` | `>=3.0,<4` (currently resolves 3.4.8) | SSE response helper for FastAPI/Starlette | **Warranted, not overkill.** A plain `StreamingResponse(media_type="text/event-stream")` can emit bytes, but you'd hand-roll: correct `data:`/`event:`/`id:` framing, periodic keep-alive pings (needed because most reverse proxies and browsers time out an idle SSE connection), and server-side detection of client disconnects via `await request.is_disconnected()` polling. `sse-starlette`'s `EventSourceResponse` provides all three out of the box and is purpose-built for exactly this FastAPI use case. |

**Compatibility:** `sse-starlette` 3.4.8 declares `starlette>=0.49.1` and `anyio>=4.7.0` — both already satisfied by the project's existing `starlette<1.4.0` pin (current resolved starlette is well above 0.49) and FastAPI's own `anyio` requirement. No new transitive surface; it adds zero new dependencies beyond what FastAPI already pulls in.

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Postgres driver | `psycopg[binary,pool]` (psycopg3) | `asyncpg` | `langgraph-checkpoint-postgres` hard-requires psycopg3 (`psycopg>=3.2.0`, `psycopg-pool>=3.2.0`). Using asyncpg for app-level Postgres access alongside it would mean **two drivers, two pools, two failure modes** against the same database for no benefit — psycopg3's async API is equally capable. |
| Layout engine | `@dagrejs/dagre` | `dagre` (original npm package) | Original `dagre` is unmaintained (last stable `0.8.5`); the community/xyflow ecosystem has moved to `@dagrejs/dagre` as the maintained successor. |
| Layout engine | `@dagrejs/dagre` | `elkjs` | elkjs is far more configurable but a Java-to-JS port with a steep API surface; xyflow's own docs say they don't often recommend it due to support complexity. Reach for it only if dagre's tree-layout assumptions prove insufficient for the topology view. |
| SSE | `sse-starlette` | Raw `StreamingResponse` | Sufficient for a true one-shot text stream, but SSE needs framing + keepalive + disconnect handling that `StreamingResponse` doesn't provide; reimplementing it is pure yak-shaving `sse-starlette` already solved. |
| TypeScript | `^5.9.3` | `latest` (7.0.2) | TS7's Go-native compiler has no stable programmatic API yet and `typescript-eslint` explicitly excludes it (`<6.1.0` peer range) — adopting it now breaks lint tooling. Revisit once the ecosystem catches up. |

## Compatibility Verification Against Existing Pins
=======
*(Note: `typing.Protocol` and `importlib.metadata` are built into standard Python 3.10+)*

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `importlib.metadata` | `pluggy` | If plugins need to register complex lifecycle hooks (like pytest) or multiple plugins need to chain execution for a single operation. For simple "provider" abstractions, standard entry points are lighter. |
| `typing.Protocol` | Abstract Base Classes (ABCs) | If you need to provide default implementations for some plugin methods, though mixins or composition are usually better. |
>>>>>>> Stashed changes

| Existing pin | New dependency | Result |
|---|---|---|
| `numpy>=1.26.4,<2.0` (hard pin, gqlalchemy) | `psycopg[binary,pool]`, `langgraph-checkpoint-postgres`, `sse-starlette` | **No conflict.** None of these three declare a numpy dependency at all (verified via PyPI `requires_dist` for each). |
| `override-dependencies = ["tensorflow ; python_version > '99'"]` | same three packages | **Undisturbed.** None depend on tensorflow or protobuf; the override only needs to survive gqlalchemy's own declared (unused) dependency, which is untouched by this milestone. |
| `langgraph-checkpoint>=4.1.0,<5` (currently unused) | `langgraph-checkpoint-postgres>=3.1.0,<4` | **Exact match** — this package's own declared range is `langgraph-checkpoint<5.0.0,>=4.1.0`, identical to the existing pin. Adding it activates the existing dependency; no version change required on `langgraph-checkpoint` itself. |
| `langgraph>=1.2.10,<1.3` | `langgraph-checkpoint-postgres>=3.1.0,<4` | No direct constraint between them (checkpoint-postgres depends on `langgraph-checkpoint`, not `langgraph` directly) — safe. |
| `starlette<1.4.0` | `sse-starlette>=3.0,<4` (needs `starlette>=0.49.1`) | Satisfied — the project's resolved starlette (some 1.3.x, per the existing `<1.4.0` ceiling) is well above `0.49.1`. |
| `fastapi>=0.141.1` | `sse-starlette` | No FastAPI version constraint declared by `sse-starlette`; it only touches starlette/anyio, both already FastAPI dependencies. |

**Net effect on the resolver:** the only genuinely new transitive package introduced by this milestone's Python-side additions is `orjson` (via `langgraph-checkpoint-postgres`). Nothing forces a numpy or protobuf bump.

## Installation

```bash
# Backend additions (pyproject.toml [project.dependencies])
uv add "psycopg[binary,pool]>=3.2.0,<4"
uv add "langgraph-checkpoint-postgres>=3.1.0,<4"
uv add "sse-starlette>=3.0,<4"
```

Resulting `pyproject.toml` additions (paste-ready):
```toml
dependencies = [
    # ... existing entries unchanged ...
    "psycopg[binary,pool]>=3.2.0,<4",
    "langgraph-checkpoint-postgres>=3.1.0,<4",
    "sse-starlette>=3.0,<4",
]
```

Frontend `package.json` (new directory, e.g. `frontend/`):
```json
{
  "dependencies": {
    "react": "^19.2.8",
    "react-dom": "^19.2.8",
    "@xyflow/react": "^12.11.2",
    "@dagrejs/dagre": "^3.1.0"
  },
  "devDependencies": {
    "vite": "^8.2.1",
    "@vitejs/plugin-react": "^6.0.5",
    "typescript": "^5.9.3",
    "@types/react": "^19.2.18",
    "@types/react-dom": "^19.2.4"
  }
}
```

```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install @xyflow/react @dagrejs/dagre
npm install -D typescript@^5.9.3   # override whatever the scaffold pinned to latest
```

**Node requirement:** Vite 8 declares `engines.node: "^20.19.0 || >=22.12.0"` — ensure the dev container / CI image uses Node 20.19+ or 22.12+; Node 21 and pre-.19 Node 20 patch releases are explicitly excluded.

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
<<<<<<< Updated upstream
| `asyncpg` | Would create a second Postgres driver/pool alongside the one `langgraph-checkpoint-postgres` forces (psycopg3); doubles connection-pool surface for no gain | `psycopg[binary,pool]` |
| `dagre` (plain npm package, unscoped) | Unmaintained, frozen at `0.8.5` | `@dagrejs/dagre` |
| `typescript@latest` / unpinned `typescript` | Resolves to 7.0.2, which `typescript-eslint` 8.66.0 explicitly rejects (`<6.1.0` peer range) and which ships without a stable compiler API yet | `typescript@^5.9.3` |
| Hand-rolled SSE via bare `StreamingResponse` | Reimplements framing/keepalive/disconnect-detection that `sse-starlette` already provides correctly | `sse-starlette` |
| Calling `AsyncPostgresSaver` without `.setup()` | Checkpoint tables are never created; first checkpoint write fails at runtime, not at startup — easy to miss until first incident run | Call `await checkpointer.setup()` once during app lifespan startup |
| Manually-built psycopg connections passed to `AsyncPostgresSaver` without `autocommit=True, row_factory=dict_row` | `.setup()`'s DDL silently fails to commit; documented as the most common integration bug for this package | Prefer `AsyncPostgresSaver.from_conn_string(...)`, or set both kwargs explicitly if constructing connections manually |
| `elkjs` (for this milestone) | Correct but unnecessarily complex layout engine for a topology graph that's fundamentally tree/DAG-shaped; steep API, xyflow's own docs downplay it | `@dagrejs/dagre` |

## Sources

- PyPI JSON API (`pypi.org/pypi/{package}/json`) — `psycopg` 3.3.4, `langgraph-checkpoint-postgres` 3.1.2, `sse-starlette` 3.4.8, `starlette` 1.4.1, `fastapi` 0.141.1 (requires `starlette>=0.46.0`) — HIGH confidence (live API, `requires_dist` inspected directly for numpy/protobuf/driver constraints)
- npm registry API (`registry.npmjs.org/{package}/latest` and full version list) — `vite` 8.2.1 (engines `node ^20.19.0 || >=22.12.0`), `react`/`react-dom` 19.2.8, `typescript` dist-tags (`latest` 7.0.2, `rc` 7.0.1-rc, `next` 7.1.0-dev; highest stable 5.x line is 5.9.3), `@xyflow/react` 12.11.2 (peer `react/react-dom >=17`), `@dagrejs/dagre` 3.1.0 vs unmaintained `dagre` 0.8.5, `elkjs` 0.12.0, `@vitejs/plugin-react` 6.0.5 (peer `vite ^8.0.0`), `typescript-eslint`/`@typescript-eslint/eslint-plugin` 8.66.0 (peer `typescript >=4.8.4 <6.1.0`) — HIGH confidence (live API)
- WebSearch: LangChain reference docs (`reference.langchain.com/python/langgraph.checkpoint.postgres/...`) confirming `AsyncPostgresSaver.setup()` semantics, table names, and the `autocommit=True`/`row_factory=dict_row` requirement for manually-constructed connections — MEDIUM-HIGH confidence (official docs, corroborated by community blog posts describing the same failure mode)
- WebSearch: React Flow / xyflow docs (`reactflow.dev/learn/layouting/layouting`, `reactflow.dev/examples/layout/dagre`, `reactflow.dev/examples/layout/elkjs`) confirming xyflow ships no bundled layout engine and its own comparative guidance on dagre vs elkjs — HIGH confidence (official docs)
- WebSearch: TypeScript 7.0 GA coverage (InfoQ, "TypeScript 7.0 Is GA" — July 2026) corroborating the native Go-compiler rewrite and the missing stable programmatic API in 7.0 — MEDIUM confidence (secondary press coverage, cross-checked against the npm `dist-tags` showing `next: 7.1.0-dev...` which corroborates 7.1 as the still-unreleased version that would add the API back)
=======
| `requests` | It blocks the thread and will stall FastAPI's async event loop during slow API calls to observability providers. | `httpx` |
| Directory Scanning (e.g., `os.listdir` + `importlib.util.spec_from_file_location`) | Highly fragile, breaks in containerized/packaged environments, and hard to manage dependencies for plugins. | `importlib.metadata` (Entry points) |
| `stevedore` / `yapsy` | Too heavy, outdated, or unnecessarily complex for this scale. | Built-in standard library tools (`importlib.metadata`). |

## Stack Patterns by Variant

**If the plugin needs to run background polling (e.g., streaming topology updates):**
- Use FastAPI's background tasks or standard `asyncio.create_task` combined with `tenacity` for resilient polling.
- Because blocking the main request thread to update the Memgraph topology is anti-pattern.

**If the provider (like SigNoz) uses GraphQL instead of REST:**
- Use `httpx` with standard JSON payloads or `gql` (async client).
- Because `httpx` is capable of handling standard POST requests for GraphQL endpoints without needing a heavy specialized library for simple queries.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `httpx@^0.27.0` | `respx@^0.21.0` | Ensure `respx` matches the `httpx` major version to avoid breaking mock interceptions in tests. |

## Sources

- [Python Official Docs](https://docs.python.org/3/library/importlib.metadata.html) — `importlib.metadata` and Entry Points
- [Python Official Docs](https://docs.python.org/3/library/typing.html#typing.Protocol) — Structural subtyping with `Protocol`
- [HTTPX Documentation](https://www.python-httpx.org/) — Async HTTP standards
- [Pluggy GitHub](https://github.com/pytest-dev/pluggy) — Considered for complex hook management

---
*Stack research for: Plugin-based Architecture for Service Topology Integration*
*Researched: 2026-08-06*
>>>>>>> Stashed changes
