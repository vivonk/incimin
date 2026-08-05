# Milestones

## v1.5 v1.5 (Shipped: 2026-08-06)

**Phases completed:** 5 phases, 11 plans, 19 tasks

**Key accomplishments:**

- Memgraph MAGE 3.12.0 + Qdrant v1.19.0 running on named volumes behind loopback-only ports; Python 3.12 venv resolves all agent dependencies; INFRA-04 persistence gate executed and passed.
- SigNoz v0.135.1 running at 127.0.0.1:3301; ClickHouse schema ambiguity (D-10/TELE-03) resolved empirically against the live instance — logs table is `distributed_logs_v2`, traces table is `distributed_signoz_index_v3`, service name lives in `resources_string['service.name']`.
- Attached OTel Astronomy Shop to SigNoz via custom collector overlay and completed project port audit
- Single-command verification gate `verify_stack.py` covers 14 mandatory infrastructure checks, with captured memory bounds and cold-start reproducibility confirmed.
- Idempotent graph seeding of 14 OTel Astronomy Shop services into Memgraph with BFS validation
- Python script connecting to ClickHouse to query SigNoz telemetry logs with parameterized SQL
- Runbook ingestion pipeline using fastembed and Qdrant with semantic search and payload filtering
- Single-command verification gate for Phase 2 readiness across topology, telemetry, and knowledge planes.
- LangGraph state machine with three isolated, tested tools is assembled and guarded against recursion failures.
- End-to-end demo scenario automated and documented, completing the golden path validation.

---
