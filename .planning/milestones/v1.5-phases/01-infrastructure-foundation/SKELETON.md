# Walking Skeleton — incimin.io (AI SRE Agent)

**Phase:** 1
**Generated:** 2026-08-05

## Capability Proven End-to-End

> An operator runs `docker compose up -d` on a clean checkout, then `uv run python scripts/verify_stack.py`, and gets a green report proving all three operational planes are live and queryable from Python: the OTel Astronomy Shop storefront serves traffic on 127.0.0.1:8090, its traces/logs/metrics land in SigNoz's ClickHouse, Memgraph MAGE answers Cypher over Bolt with data that survived a container restart, and Qdrant accepts collection operations.

This is the infrastructure analogue of a walking skeleton. There is no agent, no seeded graph, no runbook corpus, and no UI. What exists is the full data substrate, reachable through the exact client libraries every later phase will use, with a single command that proves it is still true.

## Architectural Decisions

These are settled. Later phases build on them and do not renegotiate them.

| Decision | Choice | Rationale |
|---|---|---|
| Orchestration | Docker Compose v2 with a root `compose.yaml` using `include:` | Each concern owns one file under `docker/` (`compose.core.yaml`, `compose.signoz.yaml`, `compose.otel-demo.yaml`). One `docker compose up` from the repo root satisfies INFRA-01 while keeping the SigNoz-generated manifest unmodified and separately auditable. The v1 `docker-compose` binary is forbidden — its `depends_on` healthcheck semantics differ and cause startup-ordering bugs. |
| Network topology | Single shared bridge network named `incimin` | Cross-plane DNS by service name is the whole point: the OTel demo's collector must resolve `signoz-otel-collector`, and the agent must resolve `memgraph`, `qdrant`, and `clickhouse`. Per-plane networks would require explicit aliasing for no isolation benefit on a loopback-only local stack. |
| Network exposure | Every published port bound to `127.0.0.1` only; zero `0.0.0.0` bindings | Memgraph Bolt, Qdrant, and ClickHouse all run without authentication (see the accepted threats below). Loopback binding is the mitigation. The verification gate asserts this on every run, so a future change that widens exposure fails rather than shipping. |
| Port allocation | Canonical ledger in `docs/PORTS.md`, written in wave 1 before any colliding stack exists | The 8080 triple-collision (SigNoz Foundry default, Envoy default) is the phase's top-ranked pitfall. Structurally preventing it beats fixing it: 8080 is RESERVED UNBOUND, SigNoz UI is 3301, Envoy is 8090, and later plans conform to the ledger rather than amending it. |
| SigNoz deployment | `foundryctl cast` run ONCE at setup; generated manifest committed to `docker/compose.signoz.yaml` | The old `deploy/docker-compose.yaml` path was removed in SigNoz v0.130.0, so Foundry is the only supported route. But requiring `foundryctl` on every machine would violate INFRA-01 ("no manual steps beyond `docker compose up`"). Generate-once-commit-always resolves both. The raw generated output is committed first so the port-correction diff is reviewable. |
| Graph plane | `memgraph/memgraph-mage:3.12.0` with named volume `memgraph_data:/var/lib/memgraph`, WAL + snapshot-on-exit | Plain `memgraph/memgraph` lacks the MAGE BFS procedures Phase 3's topology traversal depends on. Default Memgraph storage is in-memory and loses everything on restart — the named volume is present from day one, and the restart-survival proof is an executable gate (`PersistenceProbe` node, written then read back across `docker compose restart`), not a documented intention. |
| Telemetry plane | SigNoz v0.135.1 + ClickHouse pinned to `24.1.2.5`; agent reads ClickHouse directly over HTTP on 8123 | SigNoz validates a specific ClickHouse version and warns against independent upgrades. Querying ClickHouse via SQL rather than SigNoz's API is what makes deterministic, reproducible telemetry retrieval possible for the agent. ClickHouse native TCP 9000 is deliberately unpublished. |
| Vector plane | `qdrant/qdrant:v1.19.0` with `fastembed` 0.8.0 (BAAI/bge-small-en-v1.5, 384-dim) in-process | Zero external embedding API call — no key, no latency, no rate limit, and full determinism for the demo. Model download is ~130MB, acceptable for an SRE runbook corpus of this size. |
| Victim application | OTel Astronomy Shop 3.0.0, **minimal mode**, with the demo's own Jaeger/Grafana/Prometheus/OpenSearch NOT deployed | Minimal mode is required by the 14GB budget (~3GB vs ~6GB for full). SigNoz replaces all four demo backends; Grafana's 3000 would additionally collide with Memgraph Lab. The demo's own collector stays unpublished because SigNoz's collector already owns host 4317/4318. |
| Telemetry routing | Custom overlay `docker/otel-demo/otelcol-config-signoz.yml` layered as an additional `--config` | Telemetry does not reach SigNoz without it. Critically, collector config overlay ARRAYS REPLACE rather than append — so all three pipelines (traces, logs, metrics) must be fully re-declared with complete receiver and exporter arrays. Omitting a pipeline block yields a collector that starts cleanly and exports nothing: the silent failure this project most needs to avoid. |
| Python runtime | Python 3.12 via `uv`, `uv.lock` committed, `numpy` HARD-PINNED `>=1.26.4,<2.0` | GQLAlchemy 1.10.0 raises ImportError with numpy 2.x. Python 3.13 triggers a less battle-tested GQLAlchemy dependency branch. `uv.lock` is committed so image builds use `uv sync --frozen` and are reproducible. |
| LLM provider | Anthropic via `langchain-anthropic`; `langchain-openai` deliberately EXCLUDED from `pyproject.toml` | AGENT-04 locks the synthesis LLM to Anthropic. Leaving the OpenAI integration out of the manifest makes an accidental provider mix a resolution failure rather than a silent runtime divergence. |
| Verification | Single Python gate `scripts/verify_stack.py`, 14 named checks, read-only, exits 0/non-zero | Settles the Claude's-Discretion item on verification tooling. Python rather than shell because the checks that matter most must run through the real client libraries (GQLAlchemy Bolt handshake, clickhouse-connect against the live schema, qdrant-client) — a curl-based script would prove reachability without proving the drivers work. Extensible by appending to a check list; Phase 2 adds its checks there. |
| Schema resolution | Empirically resolved and recorded in `docs/CLICKHOUSE_SCHEMA.md`, with CONFIRMED vs PROVISIONAL labels | The three research documents disagreed three ways on the SigNoz logs table name (`distributed_logs_v2` / `distributed_logs` / `logs`). Phase 1 resolves it against the running v0.135.1 instance rather than picking a winner, and records which document was wrong. |

## Stack Touched in Phase 1

- [x] **Project scaffold** — `pyproject.toml` (PEP 621, `[tool.uv] package = false`), `.python-version` pinned to 3.12, committed `uv.lock`, `.gitignore` excluding `.env`, `.env.example` with empty values only
- [x] **Orchestration** — root `compose.yaml` (`name: incimin`) with three includes; every service on the shared `incimin` network; all bindings loopback
- [x] **Graph plane real read AND real write** — `MERGE (t:PersistenceProbe {id: 'phase1'})`, then `docker compose restart memgraph`, then `MATCH ... RETURN count(t)` returns 1. A MAGE procedure is invoked to prove the algorithm surface exists
- [x] **Telemetry plane real write AND real read** — a synthetic OTLP log POSTed to `127.0.0.1:4318/v1/logs` is queried back out of ClickHouse, which also empirically confirms the timestamp unit and the service-name accessor; then ~15 real demo services write traces, logs, and metrics, verified per signal type
- [x] **Vector plane reachable** — `qdrant-client` lists collections over 6333 (no collection is created; Phase 2 owns the runbook corpus)
- [x] **UI surfaces live** — SigNoz on 3301, Memgraph Lab on 3000, and the storefront on 8090 all render simultaneously (the dual-screen demo scenario, human-verified)
- [x] **Local full-stack run command documented** — `README.md` records prerequisites, one start command, one verify command, the loopback URL table, and both teardown forms
- [x] **Resource envelope measured** — `docs/RESOURCE_BASELINE.md` records per-container memory after a 10-minute loaded soak, total, headroom against the real Docker allocation, top three consumers, and a headroom verdict for Phase 4/5
- [x] **Reproducibility proven** — full teardown (volumes preserved) and restart reaches a green gate with no manual step

## Out of Scope (Deferred to Later Slices)

Explicitly not in the skeleton. Later phases must not treat any of these as a Phase 1 regression:

- **No agent code.** No LangGraph state machine, no `create_react_agent`, no tools, no `MemorySaver`, no LLM call of any kind. `langchain-anthropic` is declared in `pyproject.toml` but never imported.
- **No Streamlit UI.** Port 8501 is reserved in the ledger; nothing binds it in Phase 1.
- **No seeded topology.** Memgraph contains exactly one node — the `PersistenceProbe`. No `:Service` nodes, no `:DEPENDS_ON` edges, no seed script. The probe uses a distinct label specifically so it cannot collide with Phase 2's seed.
- **No runbook corpus and no embeddings.** Qdrant has no collection. `fastembed` is declared but its model is not downloaded or exercised.
- **No chaos injection.** flagd is deployed (it ships with the demo) but no fault flag is enabled. Phase 4 owns latency injection.
- **No authentication anywhere.** Memgraph Bolt, Qdrant, ClickHouse, the OTLP endpoint, and SigNoz's first-run admin are all unauthenticated. Loopback-only binding is the accepted mitigation for a local synthetic-data demo. Tracked as v2 SEC-01.
- **No TLS.** All inter-service traffic is plaintext, including the collector's gRPC export to SigNoz (`tls: insecure: true`).
- **No cloud deployment, no CI, no multi-machine portability.** The resource baseline is valid only for the machine and Docker allocation it was measured on; the measurement conditions are recorded so a reader can judge applicability.
- **No production checkpointer.** LangGraph will use in-memory `MemorySaver`; the Postgres checkpointer swap is a documented v2 path, not a Phase 1 concern.
- **Not all 14 services.** Minimal mode drops Kafka and its dependents, so the real service count is below 14. `docs/OTEL_DEMO_SERVICES.md` records the true list; ROADMAP success criterion 2's "all 14 services" wording is superseded by that file.

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering any architectural decision above.

- **Phase 2 — Data plane seeding.** Seed the service topology into Memgraph as `:Service` nodes and `:DEPENDS_ON` edges matching the exact OTel `service.name` values recorded in `docs/OTEL_DEMO_SERVICES.md`; embed the SRE runbook corpus into Qdrant with `fastembed`; write the ClickHouse query layer against the table names and timestamp unit confirmed in `docs/CLICKHOUSE_SCHEMA.md`. Extends `scripts/verify_stack.py` with seed-integrity checks. Adds no new service and no new port.
- **Phase 3 — Agent tools and state machine.** The three read clients become LangGraph tools (graph traversal via MAGE BFS, telemetry query via clickhouse-connect, runbook retrieval via Qdrant semantic search) wired into a `create_react_agent` loop. First capability a human can exercise: ask a question and watch tool calls resolve against real data.
- **Phase 4 — Chaos injection and RCA loop.** Enable the demo's flagd fault flags to produce a real incident, and prove the agent's traversal reaches the correct root-cause service. Consumes the memory headroom measured in `docs/RESOURCE_BASELINE.md`; if that verdict flagged a shortfall, trimming happens here.
- **Phase 5 — Streamlit glass-box UI and the golden path.** Bind 8501 (already reserved), render tool calls in `st.status` expanders, and lock the deterministic end-to-end demo across the dual-screen setup (SigNoz on 3301, Memgraph Lab on 3000) that Phase 1 already proved can run simultaneously.
