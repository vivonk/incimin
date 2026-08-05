# SigNoz v0.135.1 ClickHouse Schema Contract

**Verified against:** live `clickhouse/clickhouse-server:24.8.14.39` instance running with SigNoz v0.135.1
**Resolved:** 2026-08-05 — closes D-10 / TELE-03 / Research Flag 1

This document is the authoritative schema contract consumed by Phase 2 tools (TELE-01, TELE-02).
Do not edit manually — re-run `SHOW TABLES` / `DESCRIBE TABLE` against the live instance to update.

---

## Resolution of Schema Ambiguities

Three research documents disagreed. This table records the empirical truth:

| Question | PITFALLS.md | ARCHITECTURE.md | STACK.md | **Actual (v0.135.1)** |
|----------|-------------|-----------------|----------|-----------------------|
| Logs table | `distributed_logs_v2` | `distributed_logs` | `signoz_logs.logs` | **`signoz_logs.distributed_logs_v2`** |
| Traces table | — | `distributed_signoz_index_v2` | `distributed_trace_summary` | **`signoz_traces.distributed_signoz_index_v3`** (v3 is current; v2 also exists) |
| `ts_bucket_start` exists on logs? | yes (perf trap) | — | — | **yes** — `UInt64`, first column |
| Service name location | — | `resources_string['service.name']` | — | **`resources_string['service.name']`** (Map column) |
| Timestamp unit for logs | — | — | — | **nanoseconds** (`UInt64` — divide by 1e9 for seconds) |
| Timestamp unit for traces | — | — | — | **`DateTime64(9)`** — nanosecond precision natively |

---

## Logs: `signoz_logs.distributed_logs_v2`

Query entry point for the agent's log query tool (Phase 2 TELE-01).

```sql
-- All logs for a service in the last N minutes:
SELECT timestamp, severity_text, body
FROM signoz_logs.distributed_logs_v2
WHERE resources_string['service.name'] = 'paymentservice'
  AND timestamp >= toUnixTimestamp64Nano(now64() - INTERVAL 5 MINUTE)
ORDER BY timestamp DESC
LIMIT 100
```

### Schema (DESCRIBE TABLE signoz_logs.distributed_logs_v2)

| Column | Type | Notes |
|--------|------|-------|
| `ts_bucket_start` | UInt64 | SigNoz query optimizer filter — include in WHERE for perf (see PITFALLS.md) |
| `resource_fingerprint` | String | Internal resource dedup key |
| `timestamp` | UInt64 | **Nanoseconds since epoch.** Use `toUnixTimestamp64Nano()` for comparisons |
| `observed_timestamp` | UInt64 | Nanoseconds — when collector received it |
| `id` | String | Unique log record ID |
| `trace_id` | String | Correlated trace ID |
| `span_id` | String | Correlated span ID |
| `trace_flags` | UInt32 | |
| `severity_text` | LowCardinality(String) | e.g. `ERROR`, `WARN`, `INFO` |
| `severity_number` | UInt8 | OTel severity number |
| `body` | String | Log message body |
| `attributes_string` | Map(LowCardinality(String), String) | Span/log attributes (string values) |
| `attributes_number` | Map(LowCardinality(String), Float64) | Span/log attributes (numeric values) |
| `attributes_bool` | Map(LowCardinality(String), Bool) | Span/log attributes (boolean values) |
| `resources_string` | Map(LowCardinality(String), String) | **Service name:** `resources_string['service.name']` |
| `scope_name` | String | OTel instrumentation scope |
| `scope_version` | String | |
| `scope_string` | Map(LowCardinality(String), String) | |
| `_retention_days` | UInt16 | Default: 15 |
| `_retention_days_cold` | UInt16 | Default: 0 |

### Key access patterns

```sql
-- Service name filter (CORRECT):
resources_string['service.name'] = 'paymentservice'

-- NOT: attributes_string['service.name'] — service name lives in resources_string

-- Timestamp window (CORRECT — include ts_bucket_start for SigNoz optimizer):
WHERE ts_bucket_start >= toUnixTimestamp(now() - INTERVAL 5 MINUTE)
  AND timestamp >= toUnixTimestamp64Nano(now64() - INTERVAL 5 MINUTE)

-- Error logs:
WHERE severity_text IN ('ERROR', 'FATAL')
  OR severity_number >= 17
```

---

## Traces: `signoz_traces.distributed_signoz_index_v3`

Query entry point for the agent's trace query tool (Phase 2 TELE-02). v3 is the current table.

```sql
-- Traces for a service with errors in the last N minutes:
SELECT trace_id, span_id, name, duration_nano, status_code_string
FROM signoz_traces.distributed_signoz_index_v3
WHERE resources_string['service.name'] = 'paymentservice'
  AND has_error = true
  AND timestamp >= now64() - INTERVAL 5 MINUTE
ORDER BY timestamp DESC
LIMIT 50
```

### Schema (DESCRIBE TABLE signoz_traces.distributed_signoz_index_v3)

| Column | Type | Notes |
|--------|------|-------|
| `ts_bucket_start` | UInt64 | Optimizer filter — include for perf |
| `resource_fingerprint` | String | |
| `timestamp` | DateTime64(9) | **Nanosecond DateTime** — use `now64()` for comparisons |
| `trace_id` | FixedString(32) | |
| `span_id` | String | |
| `parent_span_id` | String | |
| `name` | LowCardinality(String) | Span name / operation name |
| `kind` | Int8 | OTel span kind |
| `duration_nano` | UInt64 | Duration in nanoseconds |
| `status_code` | Int16 | |
| `status_code_string` | String | e.g. `STATUS_CODE_ERROR` |
| `has_error` | Bool | **Use this for error filtering** |
| `attributes_string` | Map(LowCardinality(String), String) | |
| `resources_string` | Map(LowCardinality(String), String) | Service name: `resources_string['service.name']` |
| `resource_string_service$$name` | LowCardinality(String) | Materialized column = `resources_string['service.name']` — faster for filters |
| `http_url` | LowCardinality(String) | |
| `http_method` | LowCardinality(String) | |
| `db_name` | LowCardinality(String) | |
| `db_operation` | LowCardinality(String) | |

---

## Trace Summary: `signoz_traces.distributed_trace_summary`

Lightweight aggregate — use for trace-level queries (duration, span count) without scanning index.

| Column | Type | Notes |
|--------|------|-------|
| `trace_id` | String | |
| `start` | SimpleAggregateFunction(min, DateTime64(9)) | Trace start time |
| `end` | SimpleAggregateFunction(max, DateTime64(9)) | Trace end time |
| `num_spans` | SimpleAggregateFunction(sum, UInt64) | Total span count |

---

## All Tables in signoz_logs

```
distributed_logs_attribute_keys
distributed_logs_resource_keys
distributed_logs_v2              ← PRIMARY query table
distributed_logs_v2_resource
distributed_schema_migrations_v2
distributed_usage
logs_attribute_keys
logs_resource_keys
logs_v2                          ← local shard (query distributed_logs_v2 instead)
logs_v2_resource
schema_migrations_v2
usage
```

## All Tables in signoz_traces

```
distributed_signoz_index_v2      ← older version (exists but use v3)
distributed_signoz_index_v3      ← PRIMARY query table for spans
distributed_trace_summary        ← trace-level aggregates
distributed_signoz_error_index_v2
distributed_signoz_spans
distributed_span_attributes
distributed_span_attributes_keys
distributed_tag_attributes_v2
distributed_top_level_operations
distributed_dependency_graph_minutes_v2
distributed_durationSort
distributed_traces_v3_resource
distributed_usage
distributed_usage_explorer
(+ local shard equivalents without distributed_ prefix)
```
