"""Deploy / change-event probe (ClickHouse `system_changes`).

The changes plane has existed since v1.6 but was only ever reachable through
`src/agent/diagnosis.py` — the MCP-based agent path that ran parallel to the LangGraph one and
shared no code with it. The meta-agent has never had access to deploy events at all, which is
why it could not distinguish "this service is broken" from "this service was just deployed".

That distinction is the whole point of having this probe: it discriminates `deploy_regression`
and `config_change`, which `signoz.error_logs` deliberately does not. Selection scores a probe
on exactly that asymmetry.

Queries ClickHouse directly with bound parameters rather than going through
`src/production/mcp_server.py`, whose `get_system_events` builds SQL by f-string interpolation
of LLM-supplied values.
"""
import asyncio
import datetime as dt
from typing import ClassVar

from src.agent.kernel.state import Evidence
from src.agent.probes.base import ProbeManifest, ProbeRequest, ProbeResult
from src.agent.probes.core._clickhouse import get_client
from src.agent.probes.registry import register

DEPLOY_EVENTS_QUERY = """
    SELECT timestamp, repository_url, commit_sha, source
    FROM system_changes
    WHERE service_name = {service_name:String}
      AND timestamp >= {start_time:DateTime64(3)}
      AND timestamp <= {end_time:DateTime64(3)}
    ORDER BY timestamp DESC
    LIMIT {row_limit:UInt32}
"""


def _to_datetime(ns: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(ns / 1e9, tz=dt.timezone.utc)


class DeployEventsProbe:
    manifest: ClassVar[ProbeManifest] = ProbeManifest(
        id="changes.deploys",
        source="changes",
        description="Deploys, PR merges and config changes recorded for a service.",
        owner="core",
        discriminates=["deploy_regression", "config_change"],
        cost_tier="cheap",
        max_evidence=10,
    )

    async def run(self, req: ProbeRequest) -> ProbeResult:
        if not req.services:
            return ProbeResult.nothing("No candidate services to investigate.")

        evidence: list[Evidence] = []
        errors: list[str] = []
        # Unlike logs, changes are worth checking across every candidate: a deploy to an
        # upstream service is a prime suspect for a downstream alert.
        for service in req.services[: self.manifest.max_evidence]:
            try:
                rows = await asyncio.to_thread(self._query, service, req)
            except Exception as e:  # noqa: BLE001 — a probe never raises into the graph
                errors.append(f"{service}: {type(e).__name__}")
                continue
            evidence.extend(self._to_evidence(rows, service, len(evidence)))

        if errors and not evidence:
            return ProbeResult.failed(f"Change-log query failed ({'; '.join(errors)}).")
        if not evidence:
            return ProbeResult.nothing("No deploys or config changes in the window.")

        summary = f"Found {len(evidence)} change event(s) across {len(req.services)} service(s)."
        if errors:
            summary += f" ({len(errors)} service(s) errored.)"
        return ProbeResult(evidence=evidence, summary=summary)

    def _query(self, service: str, req: ProbeRequest):
        client = get_client()
        result = client.query(
            DEPLOY_EVENTS_QUERY,
            parameters={
                "service_name": service,
                "start_time": _to_datetime(req.window.start_ns),
                "end_time": _to_datetime(req.window.end_ns),
                "row_limit": self.manifest.max_evidence,
            },
        )
        return result.result_rows

    def _to_evidence(self, rows, service: str, offset: int) -> list[Evidence]:
        seen: set[str] = set()
        out: list[Evidence] = []
        for row in rows:
            timestamp, repo_url, commit_sha, source = row[0], row[1], row[2], row[3]
            # The same deploy is recorded twice — once as `webhook_simulation`, once as
            # `github_webhook`. Carried over from `diagnosis.py:_dedupe_events`; without it a
            # single deploy counts as two pieces of corroborating evidence.
            if commit_sha in seen:
                continue
            seen.add(commit_sha)
            out.append(
                Evidence(
                    id=f"{self.manifest.id}/{offset + len(out)}",
                    source=self.manifest.source,
                    service=service,
                    summary=f"{timestamp}: deploy {str(commit_sha)[:12]} to {service} from {repo_url} ({source})",
                    raw={
                        "timestamp": str(timestamp),
                        "repository_url": repo_url,
                        "commit_sha": commit_sha,
                        "source": source,
                    },
                    timestamp=int(timestamp.timestamp() * 1e9)
                    if hasattr(timestamp, "timestamp")
                    else None,
                )
            )
        return out


register(DeployEventsProbe())
