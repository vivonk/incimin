"""HTTP contract, step recording, and tracing for the incident API.

Carries over the behaviour `tests/test_webhook.py` used to guard for the retired
Starlette receiver. Three things changed in the move and are reflected here:

* **Dedupe is the database's job now.** The old suite asserted an in-process dict
  suppressed a resend; that dict is gone. What the handler owes us is that it
  reports the database's "already existed" answer correctly, so `create_incident`
  is the seam these tests drive.
* **`run_meta_agent` became `run_incident`**, which returns nothing and writes to
  Postgres. The behaviour worth keeping — terminal text is the last text-bearing
  AI message from *whichever* node emitted it — now lives in `StepRecorder`, and
  is tested there directly.
* **Tracing moved to `src/api/runner.py`** but must behave identically: session
  keyed on the fingerprint, no `None` tags, flushed even when the run fails.

No Postgres is required: the repository seam is monkeypatched, keeping these fast
unit tests rather than integration tests.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage
from starlette.testclient import TestClient

from src.agent import tracing
from src.api import main as api_main
from src.api import runner
from src.webhook.alert import parse_alerts

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
def stub_db(monkeypatch):
    """Replace the repository seam and capture what the handler tried to persist.

    Returns `(created, spawned, control)`. `control["duplicate"] = True` makes the
    next insert report that a live incident already existed — the signal the
    partial unique index produces in the real database.
    """
    created: list = []
    spawned: list = []
    control = {"duplicate": False}

    async def fake_create(ctx):
        if control["duplicate"]:
            return None, False
        created.append(ctx)
        return {"id": uuid.uuid4()}, True

    monkeypatch.setattr(api_main.repo, "create_incident", fake_create)
    monkeypatch.setattr(api_main.runner, "spawn", lambda i, c: spawned.append((i, c)))
    return created, spawned, control


@pytest.fixture
def client():
    # Not used as a context manager on purpose: entering it would run the lifespan,
    # which opens a real Postgres pool. These tests exercise routing, not startup.
    return TestClient(api_main.app)


def _post(client, payload):
    return client.post("/webhook/signoz", json=payload)


# -- HTTP contract ---------------------------------------------------------


def test_firing_alert_creates_incident_and_starts_a_run(client, stub_db):
    created, spawned, _ = stub_db

    response = _post(client, FIRING_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["accepted"][0]["service"] == "paymentservice"
    assert body["accepted"][0]["incident_id"]
    assert created[0].service == "paymentservice"
    assert len(spawned) == 1


def test_resolved_alert_is_ignored(client, stub_db):
    created, spawned, _ = stub_db
    payload = {"alerts": [dict(FIRING_PAYLOAD["alerts"][0], status="resolved")]}

    response = _post(client, payload)

    assert response.status_code == 200
    assert response.json()["skipped"][0]["reason"] == "resolved"
    assert created == [] and spawned == []


def test_alert_without_service_is_skipped_not_crashed(client, stub_db):
    created, spawned, _ = stub_db

    response = _post(client, {"alerts": [{"labels": {"alertname": "Mystery"}}]})

    assert response.status_code == 200
    assert response.json()["skipped"][0]["reason"] == "no service label"
    assert created == [] and spawned == []


def test_malformed_body_returns_200(client, stub_db):
    """A non-2xx would make a real alert sender retry a payload that can never parse."""
    created, spawned, _ = stub_db

    response = client.post("/webhook/signoz", content=b"not json at all")

    assert response.status_code == 200
    assert response.json()["reason"] == "invalid json"
    assert created == [] and spawned == []


def test_duplicate_reported_by_the_database_is_suppressed(client, stub_db):
    _, spawned, control = stub_db
    control["duplicate"] = True

    response = _post(client, FIRING_PAYLOAD)

    assert response.json()["skipped"][0]["reason"] == "duplicate"
    assert spawned == [], "a suppressed alert must not start a second agent run"


def test_bare_alert_without_envelope_is_accepted(client, stub_db):
    created, _, _ = stub_db

    response = _post(client, FIRING_PAYLOAD["alerts"][0])

    assert response.json()["status"] == "accepted"
    assert created[0].alertname == "PaymentServiceHighErrorRate"


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


# -- step recording --------------------------------------------------------


@pytest.fixture
def recorded(monkeypatch):
    """Capture the rows StepRecorder would write, without a database."""
    rows: list[dict] = []

    async def fake_add_step(incident_id, seq, kind, name, **kw):
        rows.append({"seq": seq, "kind": kind, "name": name, **kw})
        return None

    async def noop(*_a, **_k):
        return None

    monkeypatch.setattr(runner.repo, "add_step", fake_add_step)
    monkeypatch.setattr(runner.repo, "set_current_step", noop)
    return rows


def _consume(recorder, node, state):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        recorder.consume(node, state)
    )


def test_node_and_probe_results_are_recorded_with_parent_links(recorded):
    """A probe result must hang off the node that produced it — that link is what
    makes the step log a graph rather than a flat list."""
    rec = runner.StepRecorder(uuid.uuid4())

    _consume(
        rec,
        "probe",
        {
            "messages": [],
            "probe_log": [
                {"probe_id": "signoz.error_logs", "status": "empty", "summary": "none", "evidence_count": 0},
            ],
        },
    )

    assert [r["kind"] for r in recorded] == ["node", "tool_result"]
    assert recorded[0]["name"] == "probe"
    assert recorded[1]["name"] == "signoz.error_logs"
    assert recorded[1]["parent_seq"] == recorded[0]["seq"]


def test_terminal_text_is_taken_from_any_node(recorded):
    """The kernel has several exits (`report`, `graceful_exit`). Extraction keyed to a
    fixed set of node names silently returns nothing on the paths it does not know."""
    rec = runner.StepRecorder(uuid.uuid4())

    text = _consume(rec, "graceful_exit", {"messages": [AIMessage(content="insufficient evidence")]})

    assert text == "insufficient evidence"


def test_reasoning_content_blocks_are_flattened(recorded):
    """Reasoning models return a list of blocks; str()-ing it would store raw dicts."""
    rec = runner.StepRecorder(uuid.uuid4())

    text = _consume(
        rec,
        "report",
        {
            "messages": [
                AIMessage(
                    content=[
                        {"type": "thinking", "thinking": "hidden"},
                        {"type": "text", "text": "Root cause: paymentservice"},
                    ]
                )
            ]
        },
    )

    assert text == "Root cause: paymentservice"


# -- tracing ---------------------------------------------------------------


class _Handler(BaseCallbackHandler):
    pass


@pytest.fixture(autouse=True)
def no_real_langfuse(monkeypatch):
    """Keep the suite off the network — a populated .env would otherwise post test
    traces into a developer's real Langfuse project."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    tracing.reset()
    yield
    tracing.reset()


@pytest.fixture
def traced(monkeypatch):
    handler = _Handler()
    monkeypatch.setattr(tracing, "_handler", handler)
    monkeypatch.setattr(tracing, "_resolved", True)
    return handler


def test_trace_config_carries_alert_attributes(traced):
    ctx = parse_alerts(FIRING_PAYLOAD)[0]

    config = runner.trace_config(ctx, "agent")

    metadata = config["metadata"]
    assert config["callbacks"] == [traced]
    assert metadata["langfuse_trace_name"] == "sre-alert:PaymentServiceHighErrorRate"
    # The fingerprint is stable across Alertmanager resends, so one incident is one session.
    assert metadata["langfuse_session_id"] == "abc123fingerprint"
    assert set(metadata["langfuse_tags"]) == {"incimin-api", "agent", "critical", "paymentservice"}
    assert metadata["service"] == "paymentservice"


def test_untraced_run_gets_an_empty_config():
    """No credentials: the run still happens, just uninstrumented."""
    ctx = parse_alerts(FIRING_PAYLOAD)[0]

    assert runner.trace_config(ctx, "agent") == {}


def test_tags_omit_absent_alert_fields(traced):
    """severity and service are optional; neither may become a "None" tag."""
    ctx = parse_alerts({"alerts": [{"labels": {"alertname": "Bare"}}]})[0]

    config = runner.trace_config(ctx, "agent")

    assert config["metadata"]["langfuse_tags"] == ["incimin-api", "agent"]


def test_spans_are_flushed_even_when_the_run_fails(monkeypatch):
    """Agent tasks finish before the SDK's batch timer; without an explicit flush a
    completed incident's trace never ships."""
    flushed: list[bool] = []
    monkeypatch.setattr(tracing, "flush", lambda: flushed.append(True))

    async def boom(*_a, **_k):
        raise RuntimeError("data plane down")

    async def noop(*_a, **_k):
        return None

    monkeypatch.setattr(runner.repo, "set_status", boom)
    monkeypatch.setattr(runner.repo, "set_result", noop)

    ctx = parse_alerts(FIRING_PAYLOAD)[0]
    asyncio.run(runner.run_incident(uuid.uuid4(), ctx))

    assert flushed == [True]
