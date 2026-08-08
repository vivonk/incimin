# Agent Instructions

Project conventions for all coding agents (Cursor, Claude Code, Codex, and others).

## Conventions

Follow [CONVENTIONS.md](./CONVENTIONS.md). Summary of the primary backend principle:

### Entity Metadata Principle

When an entity is retrieved from an external system and persisted or modeled internally, it must always include provenance metadata. Never store a bare external payload as an internal entity.

**Required minimum fields:** `source`, `external_id`, `fetched_at`, `schema_version`

**Rules:**
1. External → internal always wraps into an internal model.
2. Missing provenance is a design bug.
3. Keep dual identity (`external_id` + internal id when we own the record).
4. Prefer our `fetched_at` / `ingested_at`; store source clocks as `source_updated_at` if needed.
5. Persisted agent/tool results must carry the same metadata.

See `CONVENTIONS.md` for full examples and applicability (Memgraph, SigNoz/ClickHouse, Qdrant, tool state, future integrations).
