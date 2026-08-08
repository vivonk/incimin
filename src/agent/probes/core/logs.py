"""Error-log probe (SigNoz / ClickHouse).

Carries over the deterministic fast path from `src/agent/subagents/telemetry.py` and drops that
module's bounded-LLM escalation. The escalation existed because a single-pass agent had no
other way to decide "look somewhere else"; the kernel loop makes that decision structurally, in
`selection.py`, from probe manifests rather than from a model call. One fewer unbudgeted LLM
call on the critical path.
"""
import asyncio
from typing import ClassVar

from src.agent.kernel.state import Evidence
from src.agent.probes.base import ProbeManifest, ProbeRequest, ProbeResult
from src.agent.probes.core._clickhouse import get_client
from src.agent.probes.registry import register

ERROR_LOGS_QUERY = """
    SELECT timestamp, trace_id, body
    FROM signoz_logs.distributed_logs_v2
    WHERE timestamp >= {start_time:UInt64}
      AND timestamp <= {end_time:UInt64}
      AND resources_string['service.name'] = {service_name:String}
      AND severity_text = 'ERROR'
    ORDER BY timestamp DESC
    LIMIT {row_limit:UInt32}
"""


class ErrorLogsProbe:
    manifest: ClassVar[ProbeManifest] = ProbeManifest(
        id="signoz.error_logs",
        source="telemetry",
        description="ERROR-severity application logs for a service in the alert window.",
        owner="core",
        # Error logs speak to a service failing under load or on bad input, and to a downstream
        # dependency timing out. They say nothing about whether a deploy caused it — that is
        # `changes.deploys`' job, and the asymmetry is exactly what makes the pair discriminating.
        discriminates=["resource_exhaustion", "dependency_failure", "data_issue"],
        cost_tier="cheap",
        max_evidence=10,
    )

    async def run(self, req: ProbeRequest) -> ProbeResult:
        if not req.services:
            return ProbeResult.nothing("No candidate services to investigate.")
        service = req.services[0]
        try:
            rows = await asyncio.to_thread(self._query, service, req)
        except Exception as e:  # noqa: BLE001 — a probe never raises into the graph
            return ProbeResult.failed(f"Error querying logs for {service}: {e}")

        if not rows:
            return ProbeResult.nothing(f"No ERROR logs for {service} in the window.")

        evidence = [
            Evidence(
                id=f"{self.manifest.id}/{i}",
                source=self.manifest.source,
                service=service,
                summary=f"{row[0]}: {str(row[-1])[:200]}",
                raw={"row": list(row)},
                timestamp=int(row[0]),
            )
            for i, row in enumerate(rows)
        ]
        return ProbeResult(
            evidence=evidence, summary=f"Found {len(rows)} ERROR log(s) for {service}."
        )

    def _query(self, service: str, req: ProbeRequest):
        client = get_client()
        result = client.query(
            ERROR_LOGS_QUERY,
            parameters={
                "start_time": req.window.start_ns,
                "end_time": req.window.end_ns,
                "service_name": service,
                "row_limit": self.manifest.max_evidence,
            },
        )
        return result.result_rows


register(ErrorLogsProbe())
