"""Shared ClickHouse access for core probes.

Host and port are env-driven. v1 hardcoded `127.0.0.1` in both sub-agents
(`subagents/telemetry.py:61`, `subagents/topology.py:26`) while every other connection in the
project came from settings — that inconsistency broke any deployment where the agent and the
data planes were not on the same host.
"""
import os

import clickhouse_connect

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "127.0.0.1")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))


def get_client():
    return clickhouse_connect.get_client(host=CLICKHOUSE_HOST, port=CLICKHOUSE_PORT)
