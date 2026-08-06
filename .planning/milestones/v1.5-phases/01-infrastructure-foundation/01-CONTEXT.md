# Phase 1: Infrastructure Foundation - Context

**Gathered:** 2026-08-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Get the full Docker Compose stack running and all services reachable before any feature code is written. This phase delivers a verified platform: OTel Astronomy Shop telemetry flowing to SigNoz, Memgraph persistent, Qdrant reachable, port audit clean, RAM within budget, and the ClickHouse schema ambiguity resolved. No agent code, no seed scripts, no UI — just the platform standing.

</domain>

<decisions>
## Implementation Decisions

### Scope
- **D-01:** Gray areas deferred to planner's discretion — user skipped discussion, trusting research findings and planner judgment.
- **D-02:** All decisions default to the recommendations from `.planning/research/PITFALLS.md` and `.planning/research/STACK.md`.

### Key Constraints From Research (Locked)
- **D-03:** SigNoz deployed via `foundryctl cast` (Foundry v0.2.17) — the old `deploy/docker-compose.yaml` path is removed as of SigNoz v0.130.0.
- **D-04:** SigNoz UI port MUST be assigned to `3301`; OTel demo `ENVOY_PORT` MUST be `8090` — both defaults collide on `8080`.
- **D-05:** Memgraph image is `memgraph/memgraph-mage:3.12.0` (NOT plain `memgraph/memgraph` — missing MAGE BFS procedures).
- **D-06:** Memgraph requires a named Docker volume (`memgraph_data:/var/lib/memgraph`) from day one — default in-memory storage loses all data on container restart.
- **D-07:** OTel demo in minimal mode to stay within 14GB Docker Desktop allocation — must verify paymentservice, checkoutservice, and frontendservice are present in minimal mode before committing.
- **D-08:** ClickHouse version pinned at `clickhouse/clickhouse-server:24.1.2.5` — SigNoz locks this version explicitly.
- **D-09:** OTel telemetry does NOT flow to SigNoz without a custom OTel Collector pipeline config (`otelcol-config-signoz.yml`). OTel Collector config overlay arrays REPLACE (not append) — all exporters must be re-declared in the custom config.
- **D-10:** Phase 1 verification gate MUST confirm `SHOW TABLES FROM signoz_logs` resolves the `distributed_logs` vs `distributed_logs_v2` ambiguity before Phase 2 starts.

### Claude's Discretion
- Compose file organization (single `compose.yaml` wrapping all services, or override files per concern) — planner decides based on SigNoz Foundry constraints.
- Docker network topology (shared network vs per-plane bridge networks) — planner decides; either is acceptable.
- Whether to write a shared `verify.sh` script or keep verification as documented manual commands — planner decides based on team workflow.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` §Infrastructure (INFRA-01–05, TELE-03) — exact acceptance criteria for this phase

### Research (critical — read all three)
- `.planning/research/PITFALLS.md` — 10 verified pitfalls; Pitfalls 1–4 and 9 are Phase 1 blockers (port collision, telemetry pipeline, Memgraph persistence, ClickHouse timestamps, RAM)
- `.planning/research/STACK.md` — verified Docker image tags, SigNoz Foundry deployment model, port assignments, ClickHouse version pin
- `.planning/research/ARCHITECTURE.md` — component boundaries, data flow, build order; Phase 1 verification gates defined here

### Project Context
- `.planning/PROJECT.md` — constraints and key decisions (especially: 3-day sprint, 14GB RAM limit, Docker Compose local only)
- `.planning/research/SUMMARY.md` — executive synthesis; Phase 1 section has exact verification gate checklist

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- None — greenfield project, no existing code.

### Established Patterns
- None yet — this phase establishes the foundation all other phases build on.

### Integration Points
- Phase 2 depends entirely on Phase 1 completing: all three data planes (Memgraph 7687, ClickHouse 8123/9001, Qdrant 6333) must be reachable and the OTel telemetry pipeline confirmed before any seeding work starts.

</code_context>

<specifics>
## Specific Ideas

No specific requirements — user skipped discussion, deferring all implementation decisions to planner and research findings.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 1-Infrastructure Foundation*
*Context gathered: 2026-08-05*
