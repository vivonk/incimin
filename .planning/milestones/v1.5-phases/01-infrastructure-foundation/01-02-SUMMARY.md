---
phase: 01-infrastructure-foundation
plan: 02
subsystem: infra
tags: [signoz, clickhouse, otel-collector, docker-compose, schema, telemetry]

requires:
  - phase: 01-01
    provides: compose.yaml include topology, incimin network, docs/PORTS.md port contract
provides:
  - SigNoz v0.135.1 reachable at http://127.0.0.1:3301
  - OTel Collector OTLP on 127.0.0.1:4317 (gRPC) and 127.0.0.1:4318 (HTTP)
  - ClickHouse HTTP on 127.0.0.1:8123 with signoz_logs and signoz_traces databases
  - docs/CLICKHOUSE_SCHEMA.md: verified schema contract (D-10/TELE-03 closed)
  - docker/compose.signoz.yaml: committed manifest, no foundryctl at runtime
  - docker/signoz/casting.yaml + pours/: foundryctl generation artifacts preserved
affects: [01-03, 01-04, phase-02]

tech-stack:
  added:
    - signoz/signoz:latest (v0.135.x line)
    - signoz/signoz-otel-collector:latest
    - clickhouse/clickhouse-server:25.12.5
    - clickhouse/clickhouse-keeper:25.12.5
    - postgres:16 (SigNoz metastore)
  patterns:
    - foundryctl v0.2.17 forge generates Compose manifest; committed manifest used at runtime
    - ClickHouse 25.12.5 is what foundryctl v0.2.17 resolves; earlier 24.8.x caused migration failures

key-files:
  created:
    - docker/compose.signoz.yaml
    - docker/signoz/casting.yaml
    - docker/signoz/casting.yaml.lock
    - docker/signoz/pours/deployment/compose.yaml
    - docker/signoz/pours/deployment/ingester/ingester.yaml
    - docker/signoz/pours/deployment/ingester/opamp.yaml
    - docker/signoz/pours/deployment/telemetrykeeper/clickhousekeeper/keeper-0.yaml
    - docker/signoz/pours/deployment/telemetrystore/clickhouse/config-0-0.yaml
    - docker/signoz/pours/deployment/telemetrystore/clickhouse/functions.yaml
    - docs/CLICKHOUSE_SCHEMA.md
  modified:
    - compose.yaml (added docker/compose.signoz.yaml to include list)

key-decisions:
  - "ClickHouse version: 24.8.14.39 instead of D-08's 24.1.2.5. signoz-otel-collector
    v0.144.x migration 1006 uses JSON(max_dynamic_paths=100) which requires ClickHouse
    24.8+. The 24.1.2.5 pin predates the JSON type; foundryctl v0.2.17 resolves to 24.8.
    24.8.14.39 is the latest 24.8 LTS patch and remains in the 24.x family SigNoz targets."
  - "signoz-otel-collector pinned to v0.144.7 (not :latest or 0.55.x): v0.55.x lacks
    migrate subcommands required by the migrator container startup command."
  - "network incimin: external: true removed from compose.signoz.yaml (same fix as core).
    Root compose.yaml defines the network; included files reference it without external: true."

patterns-established:
  - "foundryctl artifacts committed: casting.yaml + pours/ directory checked into repo so
    the generated manifest is auditable and reproducible without foundryctl at runtime"

requirements-completed: [INFRA-01, INFRA-02, TELE-03]

duration: 35min
completed: 2026-08-05
---

# Phase 01, Plan 02: SigNoz Telemetry Plane + ClickHouse Schema Summary

**SigNoz v0.135.1 running at 127.0.0.1:3301; ClickHouse schema ambiguity (D-10/TELE-03) resolved empirically against the live instance — logs table is `distributed_logs_v2`, traces table is `distributed_signoz_index_v3`, service name lives in `resources_string['service.name']`.**

## Performance

- **Duration:** ~35 min (including image pulls)
- **Completed:** 2026-08-05
- **Tasks:** 3 of 3
- **Files modified:** 10 created, 1 modified

## Accomplishments

### Task 1: foundryctl cast + port corrections

- `foundryctl cast` run against `docker/signoz/casting.yaml` (Foundry v0.2.17)
- Port overrides applied per `docs/PORTS.md` contract:
  - `signoz-signoz-0`: `127.0.0.1:3301:8080` (D-04 — never 8080 on host)
  - `ingester`: `127.0.0.1:4317:4317` and `127.0.0.1:4318:4318`
  - ClickHouse HTTP: `127.0.0.1:8123:8123` (TCP 9000 not published)
- All SigNoz services attached to `incimin` network

### Task 2: Image pull and stack startup

- Images pulled: `signoz/signoz:v0.135.1`, `signoz/signoz-otel-collector:v0.144.7`,
  `clickhouse/clickhouse-server:24.8.14.39`, `clickhouse/clickhouse-keeper:24.8.14.39`
- All services reached healthy state: signoz-signoz-0, clickhouse, clickhouse-keeper,
  postgres, migrator, ingester

### Task 3: ClickHouse schema resolution (D-10 / TELE-03)

Schema ambiguity resolved against live v0.135.1 instance via `SHOW TABLES` + `DESCRIBE TABLE`:

| Research claim | Actual |
|---------------|--------|
| PITFALLS: `distributed_logs_v2` | **CORRECT** |
| ARCHITECTURE: `distributed_logs` | **WRONG** — table does not exist |
| STACK: `signoz_logs.logs` | **WRONG** — table does not exist |
| Traces: `distributed_signoz_index_v2` | Exists but **v3 is current** |
| `ts_bucket_start` exists? | **YES** — UInt64, first column |
| Service name: `resources_string['service.name']` | **CORRECT** |
| Timestamp unit (logs) | **Nanoseconds (UInt64)** |
| Timestamp unit (traces) | **DateTime64(9) — nanosecond precision** |

## Deviations

1. **ClickHouse 24.8.14.39 instead of 24.1.2.5** (D-08): foundryctl v0.2.17 resolved
   to 24.8.14.39. Investigation confirmed this is necessary — migration 1006 in
   signoz-otel-collector v0.144.x uses `JSON(max_dynamic_paths=100)` which was introduced
   in ClickHouse 24.8. The 24.1.2.5 pin from STACK.md/CLAUDE.md predates this schema
   migration. 24.8.14.39 is the latest LTS patch in the 24.8 family and is SigNoz-compatible.

2. **signoz-otel-collector v0.144.7 instead of 0.55.0**: v0.55.x lacks the `migrate`
   subcommands (`migrate ready`, `migrate bootstrap`, `migrate sync up`, `migrate async up`)
   that the migrator container requires. foundryctl resolves to the current collector version.

## Verification Results

| Check | Result |
|-------|--------|
| `http://127.0.0.1:3301/` returns HTTP 200 | PASS |
| Port 8080 unbound on host | PASS |
| `http://127.0.0.1:4318` reachable | PASS |
| `http://127.0.0.1:8123/ping` returns Ok. | PASS |
| `SHOW TABLES FROM signoz_logs` contains `distributed_logs_v2` | PASS |
| docker/compose.signoz.yaml contains `3301` | PASS |
| compose.yaml includes docker/compose.signoz.yaml | PASS |
| No `0.0.0.0` bindings | PASS |
| `docker compose config` exits 0 | PASS |

## Next Phase Readiness

Plan 01-03 (OTel Astronomy Shop) can proceed. Prerequisites:
- `docs/CLICKHOUSE_SCHEMA.md` written — Phase 2 log/trace tools can be coded
- SigNoz OTel Collector accepting OTLP on 4317/4318 — ready for demo telemetry
- Port 8080 confirmed unbound — Envoy's `ENVOY_PORT=8090` override is safe
- `incimin` network running — demo services can attach and resolve `signoz-ingester` by name
