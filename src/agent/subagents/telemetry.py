"""Telemetry sub-agent (Diagnoser role). Deterministic fast path by default, with a bounded
(single-call, no loop) LLM escalation when the fast path is inconclusive — per
MULTI_AGENT_ARCHITECTURE.md §3.1's "deterministic-by-default, LLM as an escape hatch" recommendation.

On the golden-path demo, the fast path finds evidence and the LLM branch never fires.
"""
import time
from dataclasses import dataclass, field
from typing import Literal

import clickhouse_connect
from pydantic import BaseModel

from src.agent.llm import build_llm
from src.agent.state import Evidence

ERROR_LOGS_QUERY = """
    SELECT timestamp, trace_id, body
    FROM signoz_logs.distributed_logs_v2
    WHERE timestamp >= {start_time:UInt64}
      AND timestamp <= {end_time:UInt64}
      AND resources_string['service.name'] = {service_name:String}
      AND severity_text = 'ERROR'
    ORDER BY timestamp DESC
    LIMIT 10
"""

# Escalation template: broadens severity and window when the fast path finds nothing.
BROAD_SCAN_QUERY = """
    SELECT timestamp, trace_id, body
    FROM signoz_logs.distributed_logs_v2
    WHERE timestamp >= {start_time:UInt64}
      AND timestamp <= {end_time:UInt64}
      AND resources_string['service.name'] = {service_name:String}
      AND (severity_text IN ('ERROR', 'FATAL', 'WARN') OR severity_number >= 13)
    ORDER BY timestamp DESC
    LIMIT 25
"""


class EscalationDecision(BaseModel):
    """Bounded LLM output: pick ONE deterministic next action, don't free-reason about queries."""

    action: Literal["broaden", "next_candidate", "give_up"]
    target_service: str | None = None
    reason: str = ""


@dataclass
class TelemetryResult:
    evidence: list[Evidence] = field(default_factory=list)
    summary: str = ""


def run_telemetry_subagent(candidate_services: list[str], window_mins: int = 30) -> TelemetryResult:
    if not candidate_services:
        return TelemetryResult(summary="No candidate services to investigate.")

    primary = candidate_services[0]
    try:
        client = clickhouse_connect.get_client(host="127.0.0.1", port=8123)
    except Exception as e:
        return TelemetryResult(summary=f"Error executing telemetry query: {e}")

    try:
        rows = _run_query(client, ERROR_LOGS_QUERY, primary, window_mins)
    except Exception as e:
        return TelemetryResult(summary=f"Error executing telemetry query: {e}")

    if rows:
        return TelemetryResult(
            evidence=_rows_to_evidence(rows, primary, "err"),
            summary=f"Found {len(rows)} ERROR log(s) for {primary}.",
        )

    # Deterministic fast path was inconclusive. Ask for exactly one bounded decision — not a loop.
    decision = _decide_escalation(primary, candidate_services)

    if decision.action == "broaden":
        try:
            rows = _run_query(client, BROAD_SCAN_QUERY, primary, window_mins * 3)
        except Exception as e:
            return TelemetryResult(summary=f"Error executing telemetry query: {e}")
        return TelemetryResult(
            evidence=_rows_to_evidence(rows, primary, "broad"),
            summary=f"No ERROR logs for {primary}; broadened scan found {len(rows)} log(s). ({decision.reason})",
        )

    if decision.action == "next_candidate" and decision.target_service:
        try:
            rows = _run_query(client, ERROR_LOGS_QUERY, decision.target_service, window_mins)
        except Exception as e:
            return TelemetryResult(summary=f"Error executing telemetry query: {e}")
        return TelemetryResult(
            evidence=_rows_to_evidence(rows, decision.target_service, "err"),
            summary=(
                f"No ERROR logs for {primary}; checked next candidate {decision.target_service}, "
                f"found {len(rows)} log(s). ({decision.reason})"
            ),
        )

    return TelemetryResult(summary=f"No ERROR logs found for {primary}. ({decision.reason})")


def _run_query(client, query: str, service_name: str, window_mins: int):
    now_ns = int(time.time() * 1e9)
    start_ns = now_ns - int(window_mins * 60 * 1e9)
    result = client.query(
        query,
        parameters={"start_time": start_ns, "end_time": now_ns, "service_name": service_name},
    )
    return result.result_rows


def _rows_to_evidence(rows, service_name: str, prefix: str) -> list[Evidence]:
    evidence: list[Evidence] = []
    for i, row in enumerate(rows):
        body = str(row[-1])
        evidence.append(
            {
                "id": f"telemetry-{prefix}-{i}",
                "source": "telemetry",
                "service": service_name,
                "summary": f"{row[0]}: {body[:200]}",
                "raw": {"row": list(row)},
                "timestamp": int(row[0]),
            }
        )
    return evidence


def _decide_escalation(primary: str, candidate_services: list[str]) -> EscalationDecision:
    others = [s for s in candidate_services if s != primary]
    try:
        structured = build_llm().with_structured_output(EscalationDecision)
        prompt = (
            f"No ERROR-severity logs were found for service '{primary}' in the lookback window. "
            f"Other topology candidates in priority order: {others or 'none'}. "
            "Decide the single best next deterministic action: 'broaden' the log severity scan for "
            "the same service, check the 'next_candidate' service, or 'give_up' if neither is likely "
            "to help. If 'next_candidate', set target_service to one of the listed candidates."
        )
        return structured.invoke(prompt)
    except Exception as e:
        # Fail closed to the cheapest deterministic action rather than raising into the graph.
        return EscalationDecision(
            action="broaden", reason=f"LLM escalation unavailable ({e}); defaulting to broaden."
        )
