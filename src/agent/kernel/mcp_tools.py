"""MCP tools bound to the Meta-Agent.

The kernel's own topology and telemetry access goes straight to Memgraph and
ClickHouse (`src/agent/subagents/topology.py`, `src/agent/probes/core/`) — that
stays deterministic and unconditional, per the project's standing rule that
topology traversal is never LLM-inferred. These two tools are the one place the
*model* decides whether and how to reach for a second, protocol-mediated source
of the same kind of facts: `get_service_topology` and `get_system_events` on the
`incimin-sre` MCP server. Ground node (Meta-Agent) binds both and lets an LLM
call zero, one, or both — see `META_AGENT_SYSTEM_PROMPT` in `graph.py`.

Never raises. A dead or slow MCP server means the tool call returns an error
string the model sees and can reason about (or ignore); it does not break
Meta-Agent's evidence gathering, which already has the deterministic BFS pass
to fall back on.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any

from langchain_core.tools import tool

from src.agent.kernel.state import Evidence, Hypothesis, ProbeRun
from src.agent.mcp_client import MCPSession, mcp_url

log = logging.getLogger("incimin.kernel.mcp")

# The server is measured at 15-30s cold, sub-second warm (see the MCP Inspector
# capture in the repo root). Generous enough for a warm server, short enough
# that a hung one degrades this one tool call rather than the whole run.
CALL_TIMEOUT = 20.0


@tool
def get_service_topology(service_name: str, max_depth: int = 2) -> str:
    """Look up the live upstream/downstream dependency graph for a service.

    Calls the incimin-sre MCP server's get_service_topology tool. Use this to
    corroborate or extend the deterministic topology traversal already
    performed — for example, to check a service one hop further out than the
    candidate list already covers.
    """
    try:
        with MCPSession(url=mcp_url()) as session:
            result = session.call_tool(
                "get_service_topology",
                {"service_name": service_name, "max_depth": max_depth},
                timeout=CALL_TIMEOUT,
            )
    except Exception as e:  # noqa: BLE001 — the model sees this as the tool's answer
        return f"error: {type(e).__name__}: {e}"
    if not result.ok:
        return f"error: {result.error}"
    return json.dumps(result.data or [])


@tool
def get_system_events(service_name: str, start_time: str, end_time: str) -> str:
    """Look up recent deploys, PR merges, and config changes for a service.

    Calls the incimin-sre MCP server's get_system_events tool. `start_time` and
    `end_time` are 'YYYY-MM-DD HH:MM:SS' in UTC. A recent event here is direct
    evidence the alerting service (or something it depends on) just changed.
    """
    try:
        with MCPSession(url=mcp_url()) as session:
            result = session.call_tool(
                "get_system_events",
                {"service_name": service_name, "start_time": start_time, "end_time": end_time},
                timeout=CALL_TIMEOUT,
            )
    except Exception as e:  # noqa: BLE001
        return f"error: {type(e).__name__}: {e}"
    if not result.ok:
        return f"error: {result.error}"
    return json.dumps(result.data or [])


TOOLS = [get_service_topology, get_system_events]


def lookback_window(fired_at_ns: int | None, hours: int = 24) -> tuple[str, str]:
    """A `(start, end)` pair suitable for `get_system_events`'s arguments, ending
    at the alert's own fired time rather than "now" — a call made minutes after
    the alert fired should still look backward from when it fired, not forward
    past it."""
    now_ns = fired_at_ns if fired_at_ns else int(dt.datetime.now(dt.timezone.utc).timestamp() * 1e9)
    fmt = "%Y-%m-%d %H:%M:%S"
    end = dt.datetime.fromtimestamp(now_ns / 1e9, tz=dt.timezone.utc).strftime(fmt)
    start = dt.datetime.fromtimestamp(now_ns / 1e9 - hours * 3600, tz=dt.timezone.utc).strftime(fmt)
    return start, end


def tool_result_to_evidence(tool_name: str, args: dict[str, Any], raw: str) -> list[Evidence]:
    """Turn one tool call's raw string result into Evidence.

    Deliberately does not build a Hypothesis here, even for a real deploy found
    via `get_system_events` — that decision belongs to hypothesis generation
    (`hypotheses_from_evidence`, called from `seed_node`), which scans whatever
    evidence exists in state regardless of which node produced it. Ground node's
    job is evidence, not hypothesis formation.
    """
    if raw.startswith("error:"):
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []

    service = args.get("service_name", "")

    if tool_name == "get_service_topology":
        return [
            {
                "id": f"mcp-topo-{i}",
                "source": "mcp_topology",
                "service": edge.get("target") or edge.get("source") or service,
                "summary": f"{edge.get('source')} -{edge.get('rel_type', '->')}-> {edge.get('target')}",
                "raw": edge,
                "timestamp": None,
            }
            for i, edge in enumerate(data[:20])
        ]

    # get_system_events
    return [
        {
            "id": f"mcp-events-{service}-{i}",
            "source": "mcp_events",
            "service": service,
            "summary": f"{event.get('source', 'change')} {str(event.get('commit_sha', ''))[:7]} on {service} at {event.get('timestamp')}",
            "raw": event,
            "timestamp": None,
        }
        for i, event in enumerate(data)
    ]


def hypotheses_from_evidence(evidence: list[Evidence]) -> list[Hypothesis]:
    """One `deploy_regression` hypothesis per service with `mcp_events` evidence.

    Called from `seed_node`: "use the evidence, then create hypothesis." A real
    recent change is grounds for a hypothesis in its own right, not just later
    corroboration for one another tier already guessed — it is wired into
    belief updates and probe selection exactly like any other hypothesis.
    """
    by_service: dict[str, int] = {}
    for e in evidence:
        if e.get("source") == "mcp_events":
            by_service[e["service"]] = by_service.get(e["service"], 0) + 1

    return [
        Hypothesis(
            id=f"h-mcp-deploy-{service}",
            kind="deploy_regression",
            statement=(
                f"A recent change to {service} caused this incident "
                f"({count} event(s) found via MCP get_system_events)"
            ),
            subject_service=service,
            origin="mcp",
            prior=0.6,
        )
        for service, count in by_service.items()
    ]


def tool_result_to_probe_run(tool_name: str, args: dict[str, Any], raw: str) -> ProbeRun:
    service = args.get("service_name", "")
    probe_id = f"mcp.{tool_name}" + (f"[{service}]" if service else "")
    ok = not raw.startswith("error:")
    count = 0
    if ok:
        try:
            data = json.loads(raw)
            count = len(data) if isinstance(data, list) else 0
        except json.JSONDecodeError:
            pass
    return {
        "probe_id": probe_id,
        "dedup_key": f"mcp:{tool_name}:{service}",
        "status": "ok" if ok else "error",
        "summary": f"{count} row(s)" if ok else raw,
        "evidence_count": count,
        "round_index": 0,
    }
