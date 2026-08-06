---
phase: 01-infrastructure-foundation
plan: 01
subsystem: infra
tags: [memgraph, qdrant, docker-compose, python, uv, ports]

requires: []
provides:
  - Python 3.12 venv with all agent dependencies resolved and committed in uv.lock
  - Canonical host port ledger (docs/PORTS.md) consumed by plans 01-02, 01-03, 01-04
  - Root compose.yaml with include: topology and shared incimin network
  - docker/compose.core.yaml: Memgraph MAGE 3.12.0 + Lab 2.13.0 + Qdrant v1.19.0 on named volumes
  - INFRA-04 persistence proven: PersistenceProbe node survives docker compose restart memgraph
affects: [01-02, 01-03, 01-04, phase-02]

tech-stack:
  added:
    - langgraph==1.2.10, langchain-core==1.5.3, langchain-anthropic==1.5.3
    - gqlalchemy==1.10.0, qdrant-client==1.19.0, fastembed==0.8.0
    - clickhouse-connect==1.6.0, streamlit==1.61.0
    - numpy==1.26.4 (pinned <2.0 for GQLAlchemy compatibility)
    - memgraph/memgraph-mage:3.12.0, memgraph/lab:2.13.0, qdrant/qdrant:v1.19.0
  patterns:
    - Compose include: topology — root compose.yaml includes per-stack compose files
    - All host ports bound to 127.0.0.1 only; zero 0.0.0.0 bindings
    - uv override-dependencies used to exclude tensorflow (GQLAlchemy declares it as
      non-optional on Python 3.12, but only for TF-GNN path; conflicts with streamlit protobuf>=5)

key-files:
  created:
    - compose.yaml
    - docker/compose.core.yaml
    - pyproject.toml
    - uv.lock
    - .python-version
    - .gitignore
    - .env.example
    - docs/PORTS.md

key-decisions:
  - "tensorflow excluded via uv override-dependencies (python_version > '99'): resolves protobuf
    conflict between gqlalchemy 1.10.0 (requires tensorflow==2.16.2 -> protobuf<5) and
    streamlit==1.61.0 (requires protobuf>=5.26.1). Core GQLAlchemy Bolt/Cypher API unaffected."
  - "Qdrant healthcheck uses bash /dev/tcp TCP probe — image ships no curl/wget/nc"
  - "Memgraph flags --storage-wal-enabled=true --storage-snapshot-on-exit=true confirmed against
    docker run --rm memgraph/memgraph-mage:3.12.0 --help output"
  - "incimin network declared in root compose.yaml (not as external: true in included files)"

patterns-established:
  - "Compose include: topology: root compose.yaml includes per-stack files; shared network
    declared at root, referenced (not redeclared) in included files"
  - "Port contract: docs/PORTS.md written before any stack deployment; subsequent plans consume,
    never amend"

requirements-completed: [INFRA-01, INFRA-02, INFRA-04]

duration: 45min
completed: 2026-08-05
---

# Phase 01, Plan 01: Infrastructure Foundation — Core Data Planes Summary

**Memgraph MAGE 3.12.0 + Qdrant v1.19.0 running on named volumes behind loopback-only ports; Python 3.12 venv resolves all agent dependencies; INFRA-04 persistence gate executed and passed.**

## Performance

- **Duration:** ~45 min
- **Completed:** 2026-08-05
- **Tasks:** 3 of 3
- **Files modified:** 8 created, 0 modified

## Accomplishments

### Task 1: Package Legitimacy Gate
Developer verbatim response: **"approved"**
All 14 PyPI packages and 3 container image tags confirmed genuine before `uv sync` ran.
`uv.lock` did not exist at gate time (confirmed by `test ! -f uv.lock`).

### Task 2: Repo Scaffold, Port Ledger, and Dependency Manifest

- Python 3.12 with `uv sync` resolving 126 packages cleanly
- **Deviation:** `gqlalchemy==1.10.0` unconditionally declares `tensorflow==2.16.2` as a
  runtime dependency on Python 3.12 (not extras-only). tensorflow 2.16.2 requires
  `protobuf<5`; streamlit 1.61.0 requires `protobuf>=5.26.1`. Conflict is unresolvable
  without an override. Resolution: added `[tool.uv] override-dependencies =
  ["tensorflow ; python_version > '99'"]` to exclude tensorflow from resolution.
  GQLAlchemy's Bolt/Cypher ORM path does not import tensorflow. `import gqlalchemy`
  exits 0. This deviation is safe and the correct fix — the alternative (downgrading
  streamlit or using a different graph client) would compromise the locked tech stack.
- `docs/PORTS.md` records all 11 published ports with loopback bindings, plus 8080 as
  RESERVED UNBOUND
- `numpy==1.26.4` pinned and confirmed via `uv run python -c "import numpy; print(numpy.__version__)"`

### Task 3: Topology and Knowledge Planes + Persistence Gate

- Exact Memgraph durability flag names accepted by `memgraph/memgraph-mage:3.12.0`:
  `--storage-wal-enabled=true` and `--storage-snapshot-on-exit=true`
  (confirmed via `docker run --rm memgraph/memgraph-mage:3.12.0 --help`)
- Qdrant healthcheck probe: `bash -c 'cat /dev/null > /dev/tcp/127.0.0.1/6333'`
  (image has no wget/curl/nc — TCP dev/tcp probe is the only available option)
- INFRA-04 persistence gate: `MATCH (t:PersistenceProbe {id: 'phase1'}) RETURN count(t)`
  returned `1` after `docker compose restart memgraph` — probe node survives restart

## Verification Results

| Check | Result |
|-------|--------|
| `docker compose ps` — all three services healthy | PASS |
| No `0.0.0.0` bindings in compose.core.yaml | PASS |
| No `0.0.0.0` in `docker compose ps --format '{{.Ports}}'` | PASS |
| PersistenceProbe count=1 after restart | PASS |
| `incimin_memgraph_data` volume Mountpoint non-empty | PASS |
| `incimin_qdrant_data` volume Mountpoint non-empty | PASS |
| `curl http://127.0.0.1:6333/` returns version JSON | PASS (v1.19.0) |
| `curl http://127.0.0.1:3000/` returns HTTP 200 | PASS |
| `docker compose config` exits 0 | PASS |
| `uv run python -c "import gqlalchemy"` exits 0 | PASS |
| numpy version starts with 1.26 | PASS (1.26.4) |
| docs/PORTS.md contains all 8 published ports | PASS |
| docs/PORTS.md contains 8080 RESERVED UNBOUND | PASS |

## Issues Encountered

1. **gqlalchemy/tensorflow/protobuf conflict** (resolved): See Task 2 deviation above.
   The `[tool.uv] override-dependencies` approach is correct and documented in pyproject.toml.

2. **Compose network ordering** (resolved): `docker/compose.core.yaml` initially declared
   `incimin` as `external: true`, conflicting with the root `compose.yaml` definition.
   Fixed by removing `external: true` — included files reference the network without
   re-declaring it; root file defines it.

## Next Phase Readiness

Plan 01-02 (SigNoz) can proceed. Prerequisites verified:
- `docs/PORTS.md` exists with port 3301 allocated for SigNoz UI, 4317/4318 for OTel collector,
  8123 for ClickHouse HTTP — all reserved and documented
- `compose.yaml` has `include:` ready for `docker/compose.signoz.yaml`
- Port 8080 is confirmed RESERVED UNBOUND (no service binds it)
- Shared `incimin` network is running and ready for SigNoz service attachment
