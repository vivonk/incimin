# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.5 — v1.5 Milestone

**Shipped:** 2026-08-06
**Phases:** 5 | **Plans:** 11 | **Tasks:** 19

### What Was Built
- Full Docker Compose local stack with OTel Astronomy Shop, SigNoz, Memgraph, and Qdrant
- Data planes initialized and smoke-tested independently (Topology, Telemetry, Knowledge)
- LangGraph state machine with deterministic tools for BFS traversal, SQL logging, and runbook search
- Real-time Streamlit chat UI with glass-box visibility and chaos injection setup

### What Worked
- Strict sequential wave execution kept dependencies clean
- Docker Compose approach enabled predictable local environments
- Memgraph BFS eliminated LLM hallucination risks in root-cause traversal

### What Was Inefficient
- Some initial port conflicts with SigNoz/frontend-proxy required rework
- Handling multi-service orchestration locally strains memory limits

### Patterns Established
- Agent deterministic tool-use interface (Graph traversal, SQL query, Semantic search)
- Idempotent seeding scripts for databases

### Key Lessons
1. Keeping LLM out of critical topology traversal (relying on Memgraph BFS) is vital for deterministic demos
2. Telemetry and Knowledge planes require strict schema verification before agent integration

### Cost Observations
- Notable: Fast prototyping within 48-hour build sprint required intensive local testing

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.5 | - | 5 | Established baseline data planes and agent state machine |

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|-------------------|
| v1.5 | - | - | 14 services |

### Top Lessons (Verified Across Milestones)

1. Determinism over dynamic LLM inference for infrastructure workflows
