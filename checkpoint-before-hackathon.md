# Incimin.io - Pre-Hackathon Checkpoint

## Overview

Incimin.io is an autonomous AI SRE agent that performs real-time, deterministic root-cause analysis during infrastructure incidents. It traverses live service graphs, queries correlated telemetry, and retrieves runbooks to deliver root cause and remediation before a human opens a dashboard.

## Core Architecture & Components Built

### 1. AI SRE Agent (`src/agent/`)

- **LangGraph Coordinator (Meta-Agent)**: Uses a multi-agent state machine (`graph.py`) to orchestrate investigations.
- **Sub-agents**:
  - **Topology (**`src/agent/subagents/topology.py`**)**: Uses BFS to traverse Memgraph service dependencies to identify blast radius and upstream candidates.
  - **Telemetry (**`src/agent/subagents/telemetry.py`**)**: Queries SigNoz/ClickHouse directly for logs and traces. Features an escalation path (fast-path SQL -> LLM-assisted broadening).
  - **Knowledge (**`src/agent/subagents/knowledge.py`**)**: Performs semantic search in Qdrant for runbooks with LLM re-ranking for ambiguous queries.
  - **Verifier (**`src/agent/subagents/verifier.py`**)**: Deterministic layer to prevent ungrounded hallucinations in the final synthesis.



### 2. Data Plane & Persistence (`src/production/` & `src/webhook/`)

- **Webhook API**: A FastAPI service that ingests deployment events and PR merges, persisting them to both ClickHouse and Memgraph.
- **Entity Metadata Principle**: Strict adherence to `CONVENTIONS.md`. All external payloads are wrapped with `source`, `external_id`, `fetched_at`, and `schema_version`.



### 3. Infrastructure & Telemetry Stack (`docker/`)

- Fully dockerized local environment running:
  - **Memgraph** (Graph DB for topology).
  - **Qdrant** (Vector DB for runbooks).
  - **SigNoz** (OTel Collector, ClickHouse, and UI for APM/Logs/Traces).
  - **OpenTelemetry Astronomy Shop** (14-service microservice demo app).



### 4. Chaos Engineering & Simulation (`scripts/`)

- `simulate_scenarios.py`: A robust simulation script that not only injects fake webhook events (deployments/PRs) into the tracking databases but also **hot-modifies Flagd feature flags** (`demo.flagd.json`) to trigger *real* errors (memory leaks, timeouts, CPU spikes) in the live OTel demo services.
- **Supported Scenarios**: `payment_timeout`, `redis_leak`, `quote_logic`, `kafka_backup`, `noisy_neighbor`.



### 5. Test Coverage (`tests/`)

- Extensive `pytest` suite covering:
  - Subagent logic, escalation paths, and LLM fallbacks (`test_subagents.py`).
  - LangGraph tool wiring (`test_agent_tools.py`).
  - End-to-end triaging scenarios (`test_graph.py`), including complex cases like "errors following a deployment" and "spontaneous infrastructure failures".



## Current State & Readiness

- The system is fully operational locally. It is capable of ingesting simulated deployments, breaking live services via feature flags, capturing the resulting real errors in SigNoz, and having the LangGraph agent successfully diagnose the root cause and fetch the corresponding runbook.

