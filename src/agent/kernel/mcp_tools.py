"""Hypothesis generation's MCP grounding.

The kernel's own topology and telemetry access goes straight to Memgraph and
ClickHouse (`src/agent/subagents/topology.py`, `src/agent/probes/core/`). This
module is the one place the kernel talks over the actual MCP protocol, calling
both tools the `incimin-sre` server exposes — `get_service_topology` and
`get_system_events` — as part of hypothesis generation.

Why here and not as a probe: a probe answers a question a hypothesis already
raised (see `selection.py`). This runs unconditionally, before any hypothesis
exists to select for, because its job is to hand hypothesis generation a second,
protocol-mediated view of the same facts — in particular, a recent deploy is
itself grounds for a `deploy_regression` hypothesis, not just later corroboration
for one the topology tier already guessed.

Never raises, and never blocks the run for long: a dead or slow MCP server
degrades hypothesis generation to what the topology/LLM tiers already produce.
Gated by `deterministic_mode()` at the call site in `graph.py` — network calls
are exactly the non-determinism the golden path and the kernel test suite must
not have.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from src.agent.kernel.state import Evidence, Hypothesis, ProbeRun
from src.agent.mcp_client import MCPSession, ToolResult, mcp_url

log = logging.getLogger("incimin.kernel.mcp")

# The server is measured at 15-30s cold, sub-second warm (see the MCP Inspector
# capture in the repo root). These are generous enough for a warm server but
# short enough that a hung one does not stall an incident response for minutes —
# a timeout here degrades this one grounding step, not the whole investigation.
CONNECT_TIMEOUT = 10.0
CALL_TIMEOUT = 20.0

LOOKBACK_HOURS = 24
MAX_SERVICES = 5


def _iso(ns: int) -> str:
    return dt.datetime.fromtimestamp(ns / 1e9, tz=dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def gather(
    alert: dict[str, Any], candidates: list[str]
) -> tuple[list[Evidence], list[Hypothesis], list[ProbeRun]]:
    """Call both MCP tools once each (topology single, events fanned out).

    Returns `(evidence, hypotheses, probe_log)` — all three have `operator.add`
    reducers on `IncidentState`, so the caller only needs to append what this
    returns rather than merge it.
    """
    source = alert.get("service") or ""
    fired_ns = alert.get("fired_at_ns")
    now_ns = fired_ns if fired_ns else dt.datetime.now(dt.timezone.utc).timestamp() * 1e9
    start, end = _iso(int(now_ns - LOOKBACK_HOURS * 3600 * 1e9)), _iso(int(now_ns))

    services = [s for s in [source, *candidates] if s]
    # dict.fromkeys dedupes while keeping first-seen order (source first).
    services = list(dict.fromkeys(services))[:MAX_SERVICES]

    if not services:
        return [], [], []

    try:
        with MCPSession(url=mcp_url()) as session:
            evidence: list[Evidence] = []
            hypotheses: list[Hypothesis] = []
            probe_log: list[ProbeRun] = []

            if source:
                _topology(session, source, evidence, probe_log)

            _events(session, services, start, end, evidence, hypotheses, probe_log)
            return evidence, hypotheses, probe_log
    except Exception as e:  # noqa: BLE001 — a dead MCP server must degrade, not raise
        log.warning("MCP grounding unavailable (%s); continuing without it", e)
        return (
            [],
            [],
            [
                {
                    "probe_id": "mcp.session",
                    "dedup_key": "mcp:unreachable",
                    "status": "error",
                    "summary": f"{type(e).__name__}: {e}",
                    "evidence_count": 0,
                    "round_index": 0,
                }
            ],
        )


def _topology(
    session: MCPSession, source: str, evidence: list[Evidence], probe_log: list[ProbeRun]
) -> None:
    result = session.call_tool(
        "get_service_topology", {"service_name": source, "max_depth": 2}, timeout=CALL_TIMEOUT
    )
    edges = result.data if result.ok and isinstance(result.data, list) else []
    for i, edge in enumerate(edges[:20]):
        evidence.append(
            {
                "id": f"mcp-topo-{i}",
                "source": "mcp_topology",
                "service": edge.get("target") or edge.get("source") or source,
                "summary": f"{edge.get('source')} -{edge.get('rel_type', '->')}-> {edge.get('target')}",
                "raw": edge,
                "timestamp": None,
            }
        )
    probe_log.append(_run("mcp.get_service_topology", "mcp:topology:" + source, result, len(edges)))


def _events(
    session: MCPSession,
    services: list[str],
    start: str,
    end: str,
    evidence: list[Evidence],
    hypotheses: list[Hypothesis],
    probe_log: list[ProbeRun],
) -> None:
    calls = [("get_system_events", {"service_name": s, "start_time": start, "end_time": end}) for s in services]
    results = session.call_tool_many(calls, timeout=CALL_TIMEOUT)

    for service, result in zip(services, results):
        events = result.data if result.ok and isinstance(result.data, list) else []
        for i, event in enumerate(events):
            evidence.append(
                {
                    "id": f"mcp-events-{service}-{i}",
                    "source": "mcp_events",
                    "service": service,
                    "summary": f"{event.get('source', 'change')} {str(event.get('commit_sha', ''))[:7]} on {service} at {event.get('timestamp')}",
                    "raw": event,
                    "timestamp": None,
                }
            )
        probe_log.append(
            _run(f"mcp.get_system_events[{service}]", "mcp:events:" + service, result, len(events))
        )

        # A real recent change is grounds for a hypothesis, not just corroboration
        # for one the topology tier already guessed — this is the functional
        # payoff of calling the tool here rather than only from a later probe.
        if events:
            hypotheses.append(
                Hypothesis(
                    id=f"h-mcp-deploy-{service}",
                    kind="deploy_regression",
                    statement=(
                        f"A recent change to {service} caused this incident "
                        f"({len(events)} event(s) via MCP get_system_events)"
                    ),
                    subject_service=service,
                    origin="mcp",
                    prior=0.6,
                )
            )


def _run(probe_id: str, dedup_key: str, result: ToolResult, count: int) -> ProbeRun:
    return {
        "probe_id": probe_id,
        "dedup_key": dedup_key,
        "status": "ok" if result.ok else "error",
        "summary": (f"{count} row(s)" if result.ok else (result.error or "unknown error")),
        "evidence_count": count,
        "round_index": 0,
    }
