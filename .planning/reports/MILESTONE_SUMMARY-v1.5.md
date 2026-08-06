# Milestone v1.5 Summary: AI SRE Agent Prototype & Architecture Definition

## 1. Overview
Milestone v1.5 successfully delivered a fully functional, deterministic prototype of the AI SRE (Site Reliability Engineering) Agent. The project unifies three operational data planes — service topology (Memgraph), high-velocity telemetry (SigNoz/ClickHouse), and operational knowledge (Qdrant runbooks).

During this milestone, the local Docker Compose demo stack was built around the OpenTelemetry Astronomy Shop, proving the core value proposition: the agent autonomously traverses the live service graph, queries correlated telemetry, and retrieves relevant runbooks to diagnose incidents without human intervention.

Crucially, the milestone concluded with a pivotal architectural shift, defining the production-ready architecture required to scale this prototype into an enterprise-grade platform.

## 2. Architecture (Prototype & Production Path)
The initial prototype relied on a localized stack (Streamlit, LangGraph, Memgraph, ClickHouse, Qdrant). As part of this milestone's completion, a robust production architecture was designed and documented in `docs/ARCHITECTURE.md`.

**The Three Production Data Planes:**
1. **The Structural Plane (Service Topology):** Uses Memgraph to calculate blast radius, sourced from pre-computed Service Map APIs provided by SaaS APMs (e.g., SigNoz, Datadog).
2. **The Temporal/Changes Plane (Events):** Uses ClickHouse as an immutable log for CI/CD deployments, GitHub Actions, AWS CloudTrail, and Feature Flags.
3. **The Symptoms Plane (Telemetry):** Uses ClickHouse (via OTel/SigNoz) for anomaly detection.

**Identity Resolution & Triage Flow:**
To avoid manual catalog configurations (like `catalog-info.yaml`), the production architecture implicitly links Code (GitHub) to Deployments (ArgoCD/GitHub Actions) to Services using the **Golden Thread** (repository tags and deployment labels). The agent's triage flow is hybrid: it queries ClickHouse for fast, mass metadata retrieval, and only uses MCP (Model Context Protocol) servers for deep-dive investigations (e.g., fetching a specific live PR diff), ensuring stability and avoiding rate limits during Sev-1 incidents.

## 3. Phases Executed
- **Phase 1: Infrastructure Foundation:** Deployed the full local stack (SigNoz, Memgraph, Qdrant) alongside the OTel Astronomy Shop victim app.
- **Phase 2: Data Plane Initialization:** Seeded Memgraph with 14 microservice nodes/edges, pre-hydrated Qdrant with semantic runbooks, and built ClickHouse telemetry querying capabilities.
- **Phase 3: Agent Core:** Implemented the LangGraph state machine with deterministic tools for Graph Traversal (BFS), Log Querying (SQL), and Runbook Retrieval (Semantic Search).
- **Phase 4: UI Integration & Demo Choreography:** Built the Streamlit chat UI with real-time `st.status` tool execution visibility and integrated a chaos injection script for the demo.
- **Phase 5: Golden Path Validation:** Verified the end-to-end incident response flow, ensuring the agent delivers root cause and remediation recommendations in <60 seconds.

## 4. Key Decisions
- **LangGraph over raw LLM loops:** Adopted a state machine approach to ensure deterministic control flow, eliminating LLM hallucinations in the critical path (topology traversal is pure Cypher BFS, not LLM inference).
- **Hybrid Discovery Flow (Production):** Decided against live-querying MCP servers for general discovery during incidents; instead, metadata is aggregated into ClickHouse for fast SQL querying, reserving MCPs for targeted deep-dives.
- **Recommendations Only:** The agent is scoped to recommend remediations, deliberately omitting auto-remediation execution to reduce blast radius risk for enterprise adoption.
- **SSL Context Fix:** Implemented a global `ssl` module context bypass in the LLM initialization to gracefully handle corporate proxies and macOS network hangs without breaking `httpx` async timeouts.

## 5. Requirements Satisfied
- Built a functional 3-tool LangGraph agent.
- Created an end-to-end P1 failure simulation (chaos injection script).
- Developed a Streamlit UI with glass-box visibility into agent reasoning and tool usage.
- Generated the foundational `docs/ARCHITECTURE.md` to guide the transition from local prototype to production SaaS.

## 6. Technical Debt & Known Issues
- The current prototype hardcodes the local demo stack configurations. Transitioning to production requires implementing the abstract audit log ingestors (GitHub Actions, CloudTrail) outlined in the architecture doc.
- The `src/agent/llm.py` relies on an SSL bypass for local macOS development which must be managed properly with true CAs in a production Kubernetes deployment.

## 7. Getting Started
To spin up the milestone prototype locally:
1. Ensure Docker Desktop is running.
2. Run `docker compose up -d` to launch the OTel Astronomy Shop, SigNoz, Memgraph, and Qdrant.
3. Run `python scripts/init_memgraph.py` and `python scripts/init_qdrant.py` to seed the data planes.
4. Export your LLM API keys (e.g., `export ANTHROPIC_API_KEY="..."`).
5. Run the UI: `streamlit run src/ui/app.py`.
6. Trigger an incident: `python scripts/chaos_inject.py --mode start`.
