# Conventions

## Entity Metadata Principle

When an entity is retrieved from an external system and persisted or modeled internally, it must always include the metadata needed to understand origin, freshness, and identity. Never store a bare external payload as if it were a first-class internal entity.

### Required metadata (minimum)

| Field | Purpose |
|-------|---------|
| `source` | System of origin (e.g. `memgraph`, `signoz`, `qdrant`, `otel-demo`) |
| `external_id` | Stable ID in the source system |
| `fetched_at` | UTC timestamp when this snapshot was retrieved |
| `schema_version` | Version of our internal shape for this entity type |

Add more when the use case needs it: `ingested_by`, `etag`/`checksum`, `raw_ref`, `ttl`/`expires_at`, `sync_status`.

### Rules

1. **External → internal always wraps.** Map external fields into an internal model; do not pass through raw API/DB rows as domain objects.
2. **Provenance is not optional.** Missing `source` / `external_id` / `fetched_at` is a design bug.
3. **Identity is dual.** Keep both `external_id` (source key) and our own internal id when we own the record.
4. **Timestamps are ours.** Prefer our `fetched_at` / `ingested_at` over trusting only the source clock; store source timestamps separately if needed (`source_updated_at`).
5. **Tools and agents inherit this.** Agent tool results that become state or cache entries must carry the same metadata.

### Examples

```python
# ❌ BAD — bare external row treated as internal entity
service = {"name": row["name"], "status": row["status"]}

# ✅ GOOD — internal entity with required metadata
service = {
    "id": str(uuid4()),
    "name": row["name"],
    "status": row["status"],
    "source": "memgraph",
    "external_id": row["name"],
    "fetched_at": datetime.now(timezone.utc).isoformat(),
    "schema_version": "1",
}
```

```python
# ❌ BAD — cache tool output without provenance
state["topology"] = bfs_result

# ✅ GOOD
state["topology"] = {
    "data": bfs_result,
    "source": "memgraph",
    "external_id": f"bfs:{source_service}",
    "fetched_at": datetime.now(timezone.utc).isoformat(),
    "schema_version": "1",
}
```

### Applies to

Memgraph nodes/paths, SigNoz/ClickHouse query rows, Qdrant hit payloads, LLM/tool outputs we persist, and any future external integrations (Alertmanager, k8s, etc.).

### Agent distribution

Canonical source: this file. Also mirrored in:
- `AGENTS.md` (Cursor, Codex, and other AGENTS.md-aware tools)
- `CLAUDE.md` conventions block (Claude Code / GSD)
- `.cursor/rules/entity-metadata-principle.mdc` (Cursor always-on rule)
