#!/usr/bin/env python
"""Create the ClickHouse tables this project owns.

`system_changes` has been read and written since phase 06 (`src/production/db.py`,
`src/production/mcp_server.py`, and now the `changes.deploys` probe) but its DDL
lived nowhere — it was created by hand on one machine. On any other machine the
probe fails with a bare `DatabaseError` and the agent silently loses an entire
evidence source, which reads as "no deploys found" rather than "the table is
missing".

Idempotent: safe to run repeatedly, and safe to run before the first write.

    uv run python scripts/init_clickhouse.py

Note this is the project's OWN table. Everything under `signoz_logs` / `signoz_traces`
belongs to SigNoz and is created by its migrator — do not add those here.
"""
from __future__ import annotations

import os
import sys

import clickhouse_connect

HOST = os.getenv("CLICKHOUSE_HOST_LOCAL") or os.getenv("CLICKHOUSE_HOST", "127.0.0.1")
PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
DATABASE = os.getenv("CLICKHOUSE_CHANGES_DB", "default")

# Column set is fixed by its existing readers and writers:
#   writer  src/production/db.py            timestamp, repository_url, commit_sha,
#                                           service_name, source, external_id,
#                                           fetched_at, schema_version
#   readers src/production/mcp_server.py    timestamp, repository_url, commit_sha, source
#           src/agent/probes/core/changes.py  ... WHERE service_name / timestamp range
#
# MergeTree ordered by (service_name, timestamp): every read filters on service_name
# and then a time range, so that order lets both predicates use the primary index.
DDL = f"""
CREATE TABLE IF NOT EXISTS {DATABASE}.system_changes (
    timestamp       DateTime64(3),
    service_name    String,
    repository_url  String,
    commit_sha      String,
    source          String,
    external_id     String,
    fetched_at      DateTime64(3) DEFAULT now64(3),
    schema_version  String DEFAULT '1'
)
ENGINE = MergeTree
ORDER BY (service_name, timestamp)
"""


def main() -> int:
    try:
        client = clickhouse_connect.get_client(host=HOST, port=PORT)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: cannot reach ClickHouse at {HOST}:{PORT} — {type(e).__name__}: {e}")
        return 1

    client.command(DDL)

    exists = client.command(f"EXISTS TABLE {DATABASE}.system_changes")
    if str(exists).strip() != "1":
        print(f"FAIL: {DATABASE}.system_changes still absent after CREATE")
        return 1

    rows = client.command(f"SELECT count() FROM {DATABASE}.system_changes")
    print(f"OK: {DATABASE}.system_changes ready at {HOST}:{PORT} ({rows} row(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
