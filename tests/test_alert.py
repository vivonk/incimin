"""Alert payload parsing.

Guards `src/webhook/alert.py`, which survives unchanged from the retired Starlette
receiver and is now consumed by `src/api/main.py`. The fiddly parts it encodes —
Go's RFC3339 nanosecond timestamps, Alertmanager's `0001-01-01` zero-value
sentinel, and the order service labels are resolved in — are exactly the things a
rewrite would quietly get wrong, so they are pinned here.

The HTTP contract and agent wiring moved to `tests/test_api.py`.
"""
import pytest

from src.webhook.alert import parse_alerts, parse_time

FIRING_PAYLOAD = {
    "receiver": "incimin",
    "status": "firing",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "PaymentServiceHighErrorRate",
                "service.name": "paymentservice",
                "severity": "critical",
            },
            "annotations": {
                "summary": "Error rate 42% over 5m",
                "description": "paymentservice 5xx rate exceeded the 5% threshold",
            },
            "startsAt": "2026-08-07T10:15:30.123456789Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "https://signoz.example/alerts/7",
            "fingerprint": "abc123fingerprint",
        }
    ],
}


def test_parses_message_and_metadata():
    ctx = parse_alerts(FIRING_PAYLOAD)[0]

    assert ctx.alertname == "PaymentServiceHighErrorRate"
    assert ctx.service == "paymentservice"
    assert ctx.severity == "critical"
    assert ctx.message == "paymentservice 5xx rate exceeded the 5% threshold"
    assert ctx.generator_url == "https://signoz.example/alerts/7"
    assert ctx.fingerprint == "abc123fingerprint"
    assert ctx.receiver == "incimin"
    assert ctx.is_firing
    # Alertmanager's zero value must not be read as a real resolution time.
    assert ctx.resolved_at is None
    # Go emits 9 fractional digits; Python parses at most 6.
    assert ctx.fired_at.isoformat().startswith("2026-08-07T10:15:30.123456")


@pytest.mark.parametrize(
    "labels,expected",
    [
        ({"service": "cart"}, "cart"),
        ({"service_name": "cart"}, "cart"),
        ({"serviceName": "cart"}, "cart"),
        ({"service.name": "cart"}, "cart"),
        ({"k8s_deployment_name": "cart"}, "cart"),
        ({"job": "cart"}, "cart"),
        ({"unrelated": "cart"}, None),
    ],
)
def test_service_label_variants(labels, expected):
    assert parse_alerts({"alerts": [{"labels": labels}]})[0].service == expected


def test_unparseable_start_time_falls_back_to_now():
    assert parse_time("not a timestamp") is None
    ctx = parse_alerts({"alerts": [{"labels": {"service": "cart"}, "startsAt": "nonsense"}]})[0]
    assert ctx.fired_at is not None


def test_prompt_carries_message_and_metadata():
    prompt = parse_alerts(FIRING_PAYLOAD)[0].to_prompt()

    assert "paymentservice 5xx rate exceeded the 5% threshold" in prompt
    assert "PaymentServiceHighErrorRate" in prompt
    assert "critical" in prompt
    assert "https://signoz.example/alerts/7" in prompt


def test_bare_alert_without_envelope_is_accepted():
    ctx = parse_alerts({"labels": {"alertname": "X", "service": "cart"}})[0]
    assert ctx.service == "cart"


def test_dedupe_key_prefers_fingerprint():
    """The fingerprint is stable across Alertmanager resends; the fallback keeps
    suppression working for senders that omit it."""
    assert parse_alerts(FIRING_PAYLOAD)[0].dedupe_key == "abc123fingerprint"

    bare = parse_alerts({"alerts": [{"labels": {"alertname": "X", "service": "cart"}}]})[0]
    assert bare.dedupe_key == "X|cart"


def test_kernel_projection_exposes_structured_fields():
    """The v2 kernel reasons over structured fields, not the rendered prompt.
    `fired_at_ns` is load-bearing: the verifier's temporal gate checks that a cause
    predates its alert."""
    k = parse_alerts(FIRING_PAYLOAD)[0].to_kernel_alert()

    assert k["service"] == "paymentservice"
    assert k["severity"] == "critical"
    assert isinstance(k["fired_at_ns"], int)
    assert k["fired_at_ns"] > 0
    assert k["fingerprint"] == "abc123fingerprint"
