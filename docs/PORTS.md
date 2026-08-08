# Host Port Ledger

This file is the **single source of truth** for all host port assignments in the incimin.io project.
Plans 01-02 (SigNoz), 01-03 (OTel demo), and 01-04 (agent) conform to this ledger — they do not amend it.
Any port not listed here must remain unpublished (container-network access only).

## Published Ports (all bound to 127.0.0.1 only)

| Host Port | Bind Address | Container Service | Stack | Purpose | Source Decision |
|-----------|--------------|-------------------|-------|---------|-----------------|
| 3000 | 127.0.0.1 | memgraph-lab | core | Memgraph Lab web UI | — |
| 3301 | 127.0.0.1 | signoz-frontend | signoz | SigNoz web UI | D-04 — overrides Foundry default 8080 |
| 4317 | 127.0.0.1 | signoz-otel-collector | signoz | OTLP gRPC | — |
| 4318 | 127.0.0.1 | signoz-otel-collector | signoz | OTLP HTTP | — |
| 7444 | 127.0.0.1 | memgraph | core | Memgraph monitoring/WS | — |
| 7687 | 127.0.0.1 | memgraph | core | Memgraph Bolt | — |
| 8090 | 127.0.0.1 | otel-demo-frontend-proxy | otel-demo | Envoy HTTP frontend | D-04 — ENVOY_PORT=8090, avoids 8080 collision |
| 8123 | 127.0.0.1 | clickhouse | signoz | ClickHouse HTTP API | — |
| 8501 | 127.0.0.1 | agent | agent | Streamlit UI | — |

## Not Published (container-network access only)

| Port | Service | Reason |
|------|---------|--------|
| 4317/4318 | otel-demo otel-collector | Would collide with signoz-otel-collector on the host; demo services reach their collector by service name over the incimin Docker network |
| 9000 | clickhouse (native TCP) | Agent uses HTTP 8123 via clickhouse-connect; native TCP not needed on host |
| 8013 | flagd | Not needed on host |
| 8089 | otel-demo load-generator | Not needed on host |
| 16686 | Jaeger | Not deployed — SigNoz replaces it |
| 3000 (Grafana) | Grafana | Not deployed — SigNoz replaces it; port 3000 is taken by memgraph-lab |
| 9090 | Prometheus | Not deployed — SigNoz replaces it |
| 9200 | OpenSearch | Not deployed — SigNoz replaces it |

## Reserved Unbound

| Port | Reason |
|------|--------|
| 8080 | SigNoz Foundry default AND OTel demo Envoy default. Nothing in this project may bind this port. The port audit in plan 01-03 asserts nothing in the project listens on 8080. |
