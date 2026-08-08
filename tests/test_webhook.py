"""Webhook receiver tests.

The meta-agent itself is not exercised here — `run_alert` is replaced with a recorder so these
stay fast and need no API key or data plane. What is under test is the contract the alert sender
sees (always 200, never blocking) and the AlertContext handed to the agent.
"""
import sys
import threading
import types

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, ToolMessage
from starlette.testclient import TestClient

from src.agent import tracing
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


# -- final-answer extraction -----------------------------------------------
#
# The graph has more than one exit and its shape differs between builds: the meta-agent build
# ends at `finalize` or `graceful_exit`, the v1.5 build has a conditional `agent -> END`. Each
# case below is one of those real exits.


@pytest.fixture
def fake_graph(monkeypatch):
    """Install a stand-in `src.agent.graph` whose stream yields canned node updates.

    Returns the recorder the installer captured the call kwargs into, so a test can assert on
    the config the run was given as well as on the answer it produced.
    """
    captured = {}

    def install(updates):
        def stream(inputs, stream_mode, config=None):
            captured["inputs"] = inputs
            captured["config"] = config
            return iter(updates)

        module = types.ModuleType("src.agent.graph")
        module.app = types.SimpleNamespace(stream=stream)
        monkeypatch.setitem(sys.modules, "src.agent.graph", module)
        return captured

    return install


def _run():
    return webhook_app.run_meta_agent(parse_alerts(FIRING_PAYLOAD)[0])


def test_final_from_finalize_node(fake_graph):
    fake_graph([{"finalize": {"messages": [AIMessage(content="Root cause: paymentservice")]}}])

    assert _run() == "Root cause: paymentservice"


def test_final_from_graceful_exit_node(fake_graph):
    fake_graph(
        [
            {"synthesize": {"synthesis": None}},
            {"verifier": {"verification_result": {"passed": False, "detail": "no evidence"}}},
            {"graceful_exit": {"messages": [AIMessage(content="insufficient data (no evidence)")]}},
        ]
    )

    assert _run() == "insufficient data (no evidence)"


def test_final_from_agent_node_when_graph_exits_there(fake_graph):
    """The v1.5 build's `agent -> END` edge — the path that used to return nothing."""
    fake_graph(
        [
            {"agent": {"messages": [AIMessage(content="", tool_calls=[
                {"name": "graph_bfs_tool", "args": {"source": "paymentservice"}, "id": "1"}
            ])]}},
            {"tools": {"messages": [ToolMessage(content="no path found", name="graph_bfs_tool", tool_call_id="1")]}},
            {"agent": {"messages": [AIMessage(content="Cannot determine a root cause.")]}},
        ]
    )

    assert _run() == "Cannot determine a root cause."


def test_final_flattens_reasoning_content_blocks(fake_graph):
    """Reasoning models return blocks, not a string; str() would log raw dicts."""
    fake_graph(
        [
            {
                "finalize": {
                    "messages": [
                        AIMessage(
                            content=[
                                {"type": "thinking", "thinking": "hmm"},
                                {"type": "text", "text": "Root cause: cart"},
                            ]
                        )
                    ]
                }
            }
        ]
    )

    assert _run() == "Root cause: cart"


def test_no_ai_message_reports_rather_than_returning_empty(fake_graph):
    fake_graph([{"tools": {"messages": [ToolMessage(content="x", name="t", tool_call_id="1")]}}])

    assert _run() == "meta-agent produced no final message"


def test_unknown_target_is_logged_not_raised(monkeypatch, caplog):
    monkeypatch.setenv("INCIMIN_WEBHOOK_TARGET", "nope")
    ctx = parse_alerts(FIRING_PAYLOAD)[0]

    webhook_app.run_alert(ctx)  # must not raise

    assert "unknown INCIMIN_WEBHOOK_TARGET" in caplog.text


# -- Langfuse tracing ------------------------------------------------------
#
# Whether a trace is emitted depends on credentials that CI does not have, so these assert on
# the config the alert produces rather than on anything reaching Langfuse. The tracing module's
# own behaviour is covered in tests/test_tracing.py.


class _Handler(BaseCallbackHandler):
    pass


@pytest.fixture(autouse=True)
def no_real_langfuse(monkeypatch):
    """Keep the suite off the network.

    A developer running `pytest` with a populated `.env` would otherwise construct a live
    handler and post test traces into their real Langfuse project. Tracing is off unless a test
    opts in via the `traced` fixture.
    """
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    tracing.reset()
    yield
    tracing.reset()


@pytest.fixture
def traced(monkeypatch):
    """Pretend Langfuse is configured, so trace_config() populates rather than no-ops."""
    handler = _Handler()
    monkeypatch.setattr(tracing, "_handler", handler)
    monkeypatch.setattr(tracing, "_resolved", True)
    return handler


def test_agent_run_is_traced_with_alert_attributes(fake_graph, traced):
    captured = fake_graph([{"finalize": {"messages": [AIMessage(content="done")]}}])

    _run()

    config = captured["config"]
    metadata = config["metadata"]
    assert config["callbacks"] == [traced]
    assert metadata["langfuse_trace_name"] == "sre-alert:PaymentServiceHighErrorRate"
    # The fingerprint is stable across Alertmanager resends, so one incident is one session.
    assert metadata["langfuse_session_id"] == "abc123fingerprint"
    assert set(metadata["langfuse_tags"]) == {
        "incimin-webhook",
        "agent",
        "critical",
        "paymentservice",
    }
    assert metadata["service"] == "paymentservice"


def test_untraced_run_passes_an_empty_config(fake_graph):
    """No credentials (see `no_real_langfuse`) — the run still happens, just uninstrumented."""
    captured = fake_graph([{"finalize": {"messages": [AIMessage(content="done")]}}])

    assert _run() == "done"
    assert captured["config"] == {}


def test_tags_omit_absent_alert_fields(traced):
    """severity and service are optional on an AlertContext; neither may become a "None" tag."""
    ctx = parse_alerts({"alerts": [{"labels": {"alertname": "Bare"}}]})[0]

    config = webhook_app.trace_config(ctx, "agent")

    assert config["metadata"]["langfuse_tags"] == ["incimin-webhook", "agent"]


def test_spans_are_flushed_after_each_run(monkeypatch):
    """Agent threads are short-lived; without an explicit flush the trace never ships."""
    flushed = []
    monkeypatch.setattr(tracing, "flush", lambda: flushed.append(True))
    monkeypatch.setattr(webhook_app, "TARGETS", {"agent": lambda ctx: "answer"})

    webhook_app.run_alert(parse_alerts(FIRING_PAYLOAD)[0])

    assert flushed == [True]


def test_flush_happens_even_when_the_agent_fails(monkeypatch):
    flushed = []
    monkeypatch.setattr(tracing, "flush", lambda: flushed.append(True))

    def explode(_ctx):
        raise RuntimeError("data plane down")

    monkeypatch.setattr(webhook_app, "TARGETS", {"agent": explode})

    webhook_app.run_alert(parse_alerts(FIRING_PAYLOAD)[0])  # must not raise

    assert flushed == [True]
