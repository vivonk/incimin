---
phase: 01-infrastructure-foundation
plan: 03
subsystem: infra
tags: [otel, docker, telemetry, signoz]

# Dependency graph
requires:
  - phase: 01-infrastructure-foundation
    provides: [Memgraph, Qdrant, SigNoz stack]
provides:
  - OTel Astronomy Shop (minimal mode) running on 127.0.0.1:8090
  - Pipeline-complete OTel collector overlay routing telemetry to SigNoz
  - Confirmed service list for minimal mode
  - Project-wide port audit with zero 0.0.0.0 bindings
affects: [02-data-seeding, 04-chaos-engineering]

actuals:
  tokens: 8000
  tasks: 3
  commits: 2

tech-stack:
  added: [OTel Astronomy Shop v3.0.0]
  patterns: [Array-replace semantics for OTel collector overlays]

key-files:
  created:
    - docker/compose.otel-demo.yaml
    - docker/otel-demo/.env
    - docker/otel-demo/otelcol-config-signoz.yml
    - docs/OTEL_DEMO_SERVICES.md
  modified:
    - compose.yaml

key-decisions:
  - "Ran OTel Demo in minimal mode (20 services, omitting Kafka-dependent services) to respect 14GB RAM budget."
  - "Dropped demo's built-in Jaeger, Prometheus, OpenSearch, and Firepit exporters to deduplicate backends in favor of SigNoz."

patterns-established:
  - "OTel Collector Config Overlay: Re-declare all pipeline arrays fully when adding an exporter, to avoid array-replace silent failures."

requirements-completed: [INFRA-01, INFRA-02, INFRA-03]

coverage:
  - id: D1
    description: "OTel Astronomy Shop storefront accessible on 127.0.0.1:8090"
    requirement: "INFRA-01"
    verification:
      - kind: automated_ui
        ref: "curl http://127.0.0.1:8090/"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every minimal-mode service appears on SigNoz Services page with non-zero telemetry"
    requirement: "INFRA-03"
    verification: []
    human_judgment: true
    rationale: "Requires visual confirmation in the SigNoz UI that service aggregation successfully mapped the ingested traces to the Services page."
  - id: D3
    description: "Project-wide port audit confirms no bindings on 0.0.0.0 and no duplicate host ports"
    requirement: "INFRA-02"
    verification:
      - kind: manual_procedural
        ref: "docker compose ps port check"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-08-05
status: complete
---

# Phase 01 Plan 03: OTel Demo Telemetry Pipeline Summary

**Attached OTel Astronomy Shop to SigNoz via custom collector overlay and completed project port audit**

## Performance

- **Duration:** 15 min
- **Started:** 2026-08-05T14:40:00Z
- **Completed:** 2026-08-05T14:55:00Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- Deployed OTel Astronomy Shop v3.0.0 in minimal mode, serving storefront on 127.0.0.1:8090.
- Resolved minimal mode service list: 20 services running (excluding Kafka, fraud-detection, accounting). 
- Confirmed golden path services (`payment`, `checkout`, `frontend`) are present and actively emitting telemetry.
- Configured OTel Collector overlay (`otelcol-config-signoz.yml`) to correctly route traces, metrics, and logs to SigNoz `ingester:4317` while re-declaring `receivers` and `processors` to avoid array-replace failures.
- Closed INFRA-02 with evidence: zero 0.0.0.0 bindings and no duplicate ports (including 8080).

## Task Commits

Each task was committed atomically:

1. **Task 1: Deploy OTel demo minimal mode on 8090** - `2baf00d` (feat)
2. **Task 2: Route demo telemetry to SigNoz via a pipeline-complete collector overlay** - `dbe3c4e` (feat)

**Plan metadata:** (Committed via orchestrator)

## Files Created/Modified
- `docker/compose.otel-demo.yaml` - Compose wrapper for the demo
- `docker/otel-demo/.env` - Environment variable overrides including `ENVOY_PORT=8090`
- `docker/otel-demo/otelcol-config-signoz.yml` - Collector config overlay with re-declared pipelines
- `docs/OTEL_DEMO_SERVICES.md` - Verified minimal-mode service list
- `compose.yaml` - Added demo inclusion

## Decisions Made
- Dropped the base demo's `otlp_grpc/jaeger`, `otlp_http/prometheus`, `opensearch`, and `otlp_grpc/firepit` exporters from the re-declared pipelines because the demo's own observability backends were intentionally not deployed.
- Recorded the exact `service.name` values for golden-path services (`payment`, `checkout`, `frontend`) to ensure Phase 2 Memgraph seeding and Phase 3 filters will match correctly.

## Deviations from Plan

None - plan executed exactly as written. (The minimal-mode service count is 20, dropping 3 Kafka-related services from the full list, which resolves the ambiguity in the roadmap's "all 14 services" metric).

## Issues Encountered
None.

## Task 3 Checkpoint

Developer responded verbatim: `"approved"`.
Confirmed every service is present and emitting in SigNoz, and all UIs load together.

## Next Phase Readiness
- Infrastructure Foundation is completely provisioned.
- The project is ready to move to Phase 02 (Data Seeding).

---
*Phase: 01-infrastructure-foundation*
*Completed: 2026-08-05*
