"""SigNoz / Alertmanager payload -> the context handed to the meta-agent.

SigNoz posts alerts in the Alertmanager webhook shape:

    {"receiver": ..., "status": "firing", "alerts": [{"status", "labels", "annotations",
     "startsAt", "endsAt", "generatorURL", "fingerprint"}, ...]}

Parsing is deliberately defensive. Which label carries the service name depends on how the alert
query was written in SigNoz — a ClickHouse query grouping by `service.name` emits a different key
than a metric alert grouping by `k8s_deployment_name`. Rather than depend on one spelling, we try
the known variants in order and degrade to `service=None` (which the caller logs and skips) instead
of raising inside a webhook handler.

Everything that arrived is preserved on the `AlertContext` and rendered into `to_prompt()`, so the
meta-agent sees the operator-visible alert text *and* its metadata rather than just a service name.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Ordered by specificity — the first hit wins.
SERVICE_LABEL_KEYS = (
    "service",
    "service_name",
    "serviceName",
    "service.name",
    "k8s_deployment_name",
    "deployment",
    "job",
)

SEVERITY_LABEL_KEYS = ("severity", "priority", "urgency")
MESSAGE_KEYS = ("description", "summary", "message", "annotation")

# Go's RFC3339 carries nanoseconds; datetime.fromisoformat accepts at most 6 fractional digits.
_FRACTIONAL = re.compile(r"(\.\d{6})\d+")

# Alertmanager's zero value for an unset timestamp — treat as absent, not as year 1.
_ZERO_TIME_PREFIX = "0001-01-01"


def _clean(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _first(mapping: dict, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        found = _clean(mapping.get(key))
        if found:
            return found
    return None


def parse_time(raw: Any) -> datetime | None:
    """RFC3339 -> aware UTC datetime, or None when absent/unparseable."""
    text = _clean(raw)
    if not text or text.startswith(_ZERO_TIME_PREFIX):
        return None
    text = _FRACTIONAL.sub(r"\1", text.replace("Z", "+00:00"))
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    # A timestamp without an offset is by convention UTC here; assuming local would silently shift
    # the change-log search window by the host's offset.
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


@dataclass
class AlertContext:
    """One alert, normalised. `raw` is kept so nothing arriving is lost."""

    alertname: str = "unknown alert"
    status: str = "firing"
    service: str | None = None
    severity: str | None = None
    message: str = ""
    fired_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None
    labels: dict[str, Any] = field(default_factory=dict)
    annotations: dict[str, Any] = field(default_factory=dict)
    generator_url: str | None = None
    fingerprint: str | None = None
    receiver: str | None = None
    raw: dict = field(default_factory=dict)

    @property
    def is_firing(self) -> bool:
        return self.status.lower() != "resolved"

    @property
    def dedupe_key(self) -> str:
        """Identity for repeat suppression.

        Alertmanager re-sends the same firing alert every `repeat_interval`; the fingerprint is
        stable across those resends. Falling back to alertname+service keeps suppression working
        for senders that omit it.
        """
        return self.fingerprint or f"{self.alertname}|{self.service}"

    def to_prompt(self) -> str:
        """The human turn given to the meta-agent: the alert text plus its metadata."""
        lines = [
            "A production alert is firing. Investigate it and determine the root cause.",
            "",
            "=== ALERT ===",
            f"Alert name: {self.alertname}",
            f"Status: {self.status}",
            f"Alerting service: {self.service or 'unknown'}",
            f"Severity: {self.severity or 'unspecified'}",
            f"Fired at: {self.fired_at.isoformat()}",
            f"Message: {self.message or '(none provided)'}",
        ]
        if self.generator_url:
            lines.append(f"Source query: {self.generator_url}")
        if self.fingerprint:
            lines.append(f"Fingerprint: {self.fingerprint}")
        if self.labels:
            lines.append(f"Labels: {json.dumps(self.labels, sort_keys=True, default=str)}")
        if self.annotations:
            lines.append(f"Annotations: {json.dumps(self.annotations, sort_keys=True, default=str)}")
        lines += [
            "=== END ALERT ===",
            "",
            f'Begin by calling topology_tool with source="{self.service or "unknown"}".',
        ]
        return "\n".join(lines)


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def parse_alert(alert: dict, envelope: dict | None = None) -> AlertContext:
    envelope = envelope or {}
    labels = _as_dict(alert.get("labels"))
    annotations = _as_dict(alert.get("annotations"))

    return AlertContext(
        alertname=_first(labels, ("alertname",)) or _first(annotations, ("alertname",)) or "unknown alert",
        status=_clean(alert.get("status")) or _clean(envelope.get("status")) or "firing",
        # Labels first: annotations are prose templates and may interpolate the wrong thing.
        service=_first(labels, SERVICE_LABEL_KEYS) or _first(annotations, SERVICE_LABEL_KEYS),
        severity=_first(labels, SEVERITY_LABEL_KEYS),
        message=_first(annotations, MESSAGE_KEYS) or _first(labels, MESSAGE_KEYS) or "",
        fired_at=parse_time(alert.get("startsAt") or alert.get("startTime")) or datetime.now(timezone.utc),
        resolved_at=parse_time(alert.get("endsAt")),
        labels=labels,
        annotations=annotations,
        generator_url=_clean(alert.get("generatorURL")),
        fingerprint=_clean(alert.get("fingerprint")),
        receiver=_clean(envelope.get("receiver")),
        raw=alert,
    )


def parse_alerts(payload: Any) -> list[AlertContext]:
    """Alertmanager envelope, a bare single alert, or a bare list — all accepted."""
    if isinstance(payload, list):
        return [parse_alert(a) for a in payload if isinstance(a, dict)]
    if not isinstance(payload, dict):
        return []

    alerts = payload.get("alerts")
    if isinstance(alerts, list) and alerts:
        return [parse_alert(a, payload) for a in alerts if isinstance(a, dict)]
    # Not an envelope — treat the body itself as one alert.
    return [parse_alert(payload)]
