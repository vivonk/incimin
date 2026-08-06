# Production SRE Agent Architecture

This document outlines the finalized architectural decisions for transitioning the AI SRE Agent from a local demo to an enterprise-ready production environment.

## The Three Data Planes

To provide the AI Agent with fast, accurate context for triaging alerts, data is split into three planes:

### 1. The Structural Plane (Service Topology)
- **Store:** Memgraph (Graph Database)
- **Source of Truth:** Pre-computed Service Map APIs from SaaS APM vendors (e.g., SigNoz dependency graph, Datadog Topology API, New Relic NerdGraph).
- **Purpose:** Fast blast-radius calculation. 
- **Graph Schema:** `(Service A) -[:CALLS]-> (Service B)`

### 2. The Temporal/Changes Plane (Events)
- **Store:** ClickHouse (Time-Series/OLAP Database)
- **Source of Truth:** CI/CD Webhooks, GitHub Actions, AWS CloudTrail, Feature Flag logs.
- **Purpose:** Immutable append-only log of all infrastructure and code changes.
- **Schema Key:** All events are normalized with a timestamp, `service_name`, and `repository_url`.

### 3. The Symptoms Plane (Telemetry)
- **Store:** ClickHouse (via SigNoz/OTel)
- **Source of Truth:** OpenTelemetry traces, metrics, and logs.
- **Purpose:** Anomaly detection (latency spikes, 5xx errors).

---

## Identity Resolution (Connecting Code -> Deployment -> Service)

To avoid manual configuration (e.g., Backstage `catalog-info.yaml`), the system relies on automated identity resolution via CI/CD pipelines.

### The Mapping Strategy:
1. **Code to Service Name:** Git Webhooks (GitHub/GitLab) provide the repository URL and the target event (e.g., PR merged). The exact `service_name` is extracted from the **Repository Tags/Topics**.
2. **Deployment to Service Name:** Deployment Webhooks (GitHub Actions, ArgoCD, etc.) provide both the `repository_url` and the `service_name` (extracted from deployment labels/tags).
3. **Graph Reconciliation:** The backend ingests these webhooks and automatically bridges the graph in Memgraph:
   ```cypher
   (Repository {url: "..."}) -[:DEPLOYS_TO]-> (Service {name: "..."})
   ```

---

## The AI Agent Triage Flow

Instead of heavily relying on slow, live MCP (Model Context Protocol) calls for data discovery during a Sev-1 incident, the agent follows a Hybrid Flow:

1. **Trigger:** Alert fires for a specific service.
2. **Blast Radius (Memgraph):** Agent queries Memgraph to find all upstream/downstream services and their linked Git repositories.
3. **Event Discovery (ClickHouse):** Agent runs a single, fast SQL query against the ClickHouse *Changes Plane* to find any PR merges, Deployments, or Config changes for the impacted services within the incident window.
4. **Deep Dive (MCP Servers):** If ClickHouse reveals a specific PR or Deployment caused the issue, the agent uses external **MCP Servers** (e.g., GitHub MCP) to pull the live git diff or runbook for root cause analysis. 

### Why this approach?
- **Speed & Stability:** Querying a centralized ClickHouse index for metadata is infinitely faster and more stable than making dozens of live API calls to external SaaS tools during an incident.
- **No Rate Limits:** The agent is immune to GitHub/AWS rate limits during the discovery phase.
- **Zero Graph Bloat:** High-volume time-series events live in ClickHouse, keeping the Memgraph topology small, clean, and fast to traverse.
