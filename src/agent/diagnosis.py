"""Meta-agent diagnosis flow: alert in, root cause out.

    alerting service
        -> get_service_topology            what is related?
        -> get_system_events (parallel)    what changed?
        -> LLM synthesis                   why did it break?

The two gathering steps are deterministic; the LLM only interprets what they returned. It is
instructed to fail closed — when the evidence does not support a conclusion it says so rather than
naming the most plausible-sounding service.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from src.agent.llm import build_llm
from src.agent.mcp_client import MCPSession, get_service_topology, get_system_events_many

TIME_FMT = "%Y-%m-%d %H:%M:%S"
DEFAULT_WINDOW_HOURS = float(os.getenv("DIAGNOSIS_WINDOW_HOURS", "6"))

SYNTHESIS_PROMPT = """You are an SRE root-cause agent. Use ONLY the evidence below. Do not invent facts.

ALERT: {alert}
Alert time: {alert_time}
Change-log window searched: {window_start} to {window_end}

SERVICE TOPOLOGY (dependency graph around the alerting service):
{topology}

CHANGE LOGS (deployments / PR merges) per related component:
{events}

Answer in this exact structure:
1. ROOT CAUSE — name the service, or state that evidence is insufficient to name one.
2. REASONING — tie each claim to a specific piece of evidence above.
3. EVIDENCE GAPS — what is missing that would let you conclude confidently.

Be concise. If the evidence cannot support a root cause, say so plainly rather than guessing.
A deploy that merely coincides with the alert is correlation, not proof — say so when that is all you have."""


@dataclass
class Diagnosis:
    """Structured result, so callers can log and assert on it rather than regex a prose blob."""

    alerting_service: str
    alert_time: datetime
    related_services: list[str] = field(default_factory=list)
    edges: list[tuple[str, str, list[str]]] = field(default_factory=list)
    changes: dict[str, list[dict]] = field(default_factory=dict)
    synthesis: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def services_with_changes(self) -> list[str]:
        return sorted(s for s, e in self.changes.items() if e)


def _merge_edges(raw: list[dict]) -> list[tuple[str, str, list[str]]]:
    """Collapse the duplicate DEPENDS_ON / CALLS views into one edge per (source, target).

    The server returns both relationship types for the same pair, so 14 raw edges are really 7
    dependencies. Without this every dependency is counted twice during ranking.
    """
    merged: dict[tuple[str, str], set[str]] = {}
    for edge in raw:
        source, target = edge.get("source"), edge.get("target")
        if not source or not target:
            continue
        merged.setdefault((source, target), set()).add(edge.get("rel_type", "UNKNOWN"))
    return [(s, t, sorted(r)) for (s, t), r in sorted(merged.items())]


def _dedupe_events(events: list[dict]) -> list[dict]:
    """One entry per commit.

    The same deploy is recorded twice — once as `webhook_simulation`, once as `github_webhook`.
    Left as-is, a service that happens to be double-recorded outranks one that is not.
    """
    seen: set[str] = set()
    out: list[dict] = []
    for event in events:
        key = event.get("commit_sha") or f"{event.get('timestamp')}|{event.get('repository_url')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(event)
    return out


def diagnose(
    alerting_service: str,
    alert_text: str | None = None,
    alert_time: datetime | None = None,
    window_hours: float = DEFAULT_WINDOW_HOURS,
    max_depth: int = 1,
) -> Diagnosis:
    """Run the full flow. Never raises on evidence-gathering failure — partial evidence still
    produces a diagnosis, with the failures recorded in `errors`."""
    alert_time = alert_time or datetime.now()
    window_start = alert_time - timedelta(hours=window_hours)
    result = Diagnosis(alerting_service=alerting_service, alert_time=alert_time)

    with MCPSession() as session:
        topo = get_service_topology(session, alerting_service, max_depth=max_depth)
        if not topo.ok:
            result.errors.append(f"topology: {topo.error}")
        raw_edges: list[dict] = topo.unwrap([]) or []
        result.edges = _merge_edges(raw_edges)

        related = sorted({s for s, _, _ in result.edges} | {t for _, t, _ in result.edges})
        if alerting_service not in related:
            related.append(alerting_service)
        result.related_services = related

        if related:
            per_service = get_system_events_many(
                session,
                related,
                window_start.strftime(TIME_FMT),
                alert_time.strftime(TIME_FMT),
            )
            for service, tool_result in per_service.items():
                if tool_result.ok:
                    result.changes[service] = _dedupe_events(tool_result.unwrap([]) or [])
                else:
                    result.errors.append(f"events[{service}]: {tool_result.error}")
                    result.changes[service] = []

    result.synthesis = _synthesize(result, alert_text or f"{alerting_service} is alerting", window_start)
    return result


def _synthesize(result: Diagnosis, alert_text: str, window_start: datetime) -> str:
    topology = "\n".join(
        f"  {s} -[{'/'.join(r)}]-> {t}" for s, t, r in result.edges
    ) or "  (no topology returned)"
    events = "\n".join(
        f"  {service}: {evts if evts else '[]'}" for service, evts in sorted(result.changes.items())
    ) or "  (no components queried)"

    prompt = SYNTHESIS_PROMPT.format(
        alert=alert_text,
        alert_time=result.alert_time.strftime(TIME_FMT),
        window_start=window_start.strftime(TIME_FMT),
        window_end=result.alert_time.strftime(TIME_FMT),
        topology=topology,
        events=events,
    )
    try:
        return _text_of(build_llm().invoke(prompt).content)
    except Exception as exc:
        result.errors.append(f"synthesis: {exc}")
        return "Synthesis unavailable — see errors."


def _text_of(content: Any) -> str:
    """Flatten LangChain content to text.

    Reasoning-capable models return a list of blocks (thinking + text), not a bare string; taking
    `.content` directly would print raw block dicts.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p).strip() or str(content)
    return str(content)
