"""Webhook receiver tests.

The meta-agent itself is not exercised here — `run_alert` is replaced with a recorder so these
stay fast and need no API key or data plane. What is under test is the contract the alert sender
sees (always 200, never blocking) and the AlertContext handed to the agent.
"""
import threading

import pytest
from starlette.testclient import TestClient

from src.webhook import app as webhook_app
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


@pytest.fixture
def dispatched(monkeypatch):
    """Capture the AlertContexts handed to the background worker."""
    seen = []
    arrived = threading.Event()

    def recorder(ctx):
        seen.append(ctx)
        arrived.set()

    monkeypatch.setattr(webhook_app, "run_alert", recorder)
    # Suppression state is module-level; a leftover entry would make the next test's alert a dup.
    webhook_app._recent.clear()
    yield seen, arrived
    webhook_app._recent.clear()


@pytest.fixture
def client():
    return TestClient(webhook_app.app)


def _post(client, payload):
    return client.post("/webhook/signoz", json=payload)


# -- parsing ---------------------------------------------------------------


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
    # The Coordinator's first sub-agent call needs the service name explicitly.
    assert 'topology_tool with source="paymentservice"' in prompt


def test_bare_alert_without_envelope_is_accepted():
    ctx = parse_alerts({"labels": {"alertname": "X", "service": "cart"}})[0]
    assert ctx.service == "cart"


# -- HTTP contract ---------------------------------------------------------


def test_firing_alert_triggers_agent(client, dispatched):
    seen, arrived = dispatched

    response = _post(client, FIRING_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert arrived.wait(timeout=5)
    assert seen[0].service == "paymentservice"


def test_resolved_alert_is_ignored(client, dispatched):
    seen, _ = dispatched
    payload = {"alerts": [dict(FIRING_PAYLOAD["alerts"][0], status="resolved")]}

    response = _post(client, payload)

    assert response.status_code == 200
    assert response.json()["skipped"][0]["reason"] == "resolved"
    assert seen == []


def test_alert_without_service_is_skipped_not_crashed(client, dispatched):
    seen, _ = dispatched

    response = _post(client, {"alerts": [{"labels": {"alertname": "Mystery"}}]})

    assert response.status_code == 200
    assert response.json()["skipped"][0]["reason"] == "no service label"
    assert seen == []


def test_malformed_body_returns_200(client, dispatched):
    seen, _ = dispatched

    response = client.post("/webhook/signoz", content=b"not json at all")

    assert response.status_code == 200
    assert response.json()["reason"] == "invalid json"
    assert seen == []


def test_repeat_send_is_suppressed(client, dispatched):
    seen, arrived = dispatched

    assert _post(client, FIRING_PAYLOAD).json()["status"] == "accepted"
    assert arrived.wait(timeout=5)
    second = _post(client, FIRING_PAYLOAD)

    assert second.json()["skipped"][0]["reason"] == "duplicate"
    assert len(seen) == 1


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_unknown_target_is_logged_not_raised(monkeypatch, caplog):
    monkeypatch.setenv("INCIMIN_WEBHOOK_TARGET", "nope")
    ctx = parse_alerts(FIRING_PAYLOAD)[0]

    webhook_app.run_alert(ctx)  # must not raise

    assert "unknown INCIMIN_WEBHOOK_TARGET" in caplog.text
