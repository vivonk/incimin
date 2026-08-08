"""MCP tools bound to the Meta-Agent (`src/agent/kernel/mcp_tools.py`), plus the
graph-level wiring that uses them: `ground_node`'s LLM tool-calling pass,
`seed_node`'s evidence-mining tier, and `synthesize_node`'s narrative call.

`MCPSession` talks real sockets, so every test replaces it with a stand-in
rather than touching the network. `build_llm()` talks a real API, so every
test that reaches a model call replaces that too — these are unit tests for
the wiring, not integration tests of either external system.
"""
from __future__ import annotations

import json
from unittest import mock

from src.agent.kernel import graph as kernel
from src.agent.kernel import mcp_tools
from src.agent.kernel.state import Hypothesis
from src.agent.mcp_client import ToolResult


class _FakeSession:
    def __init__(self, result: ToolResult):
        self.result = result
        self.calls: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def call_tool(self, name, args, timeout=None):
        self.calls.append((name, args))
        return self.result


def _patched(result: ToolResult):
    return mock.patch("src.agent.kernel.mcp_tools.MCPSession", return_value=_FakeSession(result))


# -- the tools themselves ----------------------------------------------------


def test_get_service_topology_returns_json_on_success():
    with _patched(ToolResult(ok=True, data=[{"source": "checkout", "target": "payment"}])):
        raw = mcp_tools.get_service_topology.invoke({"service_name": "checkout", "max_depth": 2})

    assert json.loads(raw) == [{"source": "checkout", "target": "payment"}]


def test_get_service_topology_reports_a_dead_server_as_an_error_string():
    """The model must see this as a normal tool answer, not a crash — a `@tool`
    is not allowed to raise back into `bind_tools().invoke(...)`."""
    with mock.patch(
        "src.agent.kernel.mcp_tools.MCPSession", side_effect=ConnectionError("refused")
    ):
        raw = mcp_tools.get_service_topology.invoke({"service_name": "payment"})

    assert raw.startswith("error:")


def test_get_system_events_returns_json_on_success():
    with _patched(ToolResult(ok=True, data=[{"commit_sha": "abc1234"}])):
        raw = mcp_tools.get_system_events.invoke(
            {"service_name": "payment", "start_time": "2026-08-07 00:00:00", "end_time": "2026-08-08 00:00:00"}
        )

    assert json.loads(raw) == [{"commit_sha": "abc1234"}]


def test_tools_list_exposes_both():
    """The literal ask: hypothesis generation's evidence must be able to come
    from every MCP tool the server has, not just one."""
    assert {t.name for t in mcp_tools.TOOLS} == {"get_service_topology", "get_system_events"}


# -- lookback_window -----------------------------------------------------


def test_lookback_window_ends_at_the_alert_not_now():
    fired_ns = 1_754_600_000_000_000_000  # an arbitrary fixed instant
    start, end = mcp_tools.lookback_window(fired_ns, hours=24)
    assert end == "2025-08-07 20:53:20"
    assert start == "2025-08-06 20:53:20"  # exactly 24h earlier, not "now minus 24h"


# -- tool_result_to_evidence ---------------------------------------------


def test_topology_result_becomes_evidence():
    raw = json.dumps([{"source": "checkout", "rel_type": "CALLS", "target": "payment"}])
    evidence = mcp_tools.tool_result_to_evidence("get_service_topology", {"service_name": "checkout"}, raw)

    assert len(evidence) == 1
    assert evidence[0]["source"] == "mcp_topology"
    assert "checkout" in evidence[0]["summary"] and "payment" in evidence[0]["summary"]


def test_events_result_becomes_evidence():
    raw = json.dumps([{"timestamp": "2026-08-08 09:00:00", "commit_sha": "abc1234", "source": "deploy"}])
    evidence = mcp_tools.tool_result_to_evidence("get_system_events", {"service_name": "payment"}, raw)

    assert len(evidence) == 1
    assert evidence[0]["source"] == "mcp_events"
    assert evidence[0]["service"] == "payment"


def test_error_result_yields_no_evidence():
    assert mcp_tools.tool_result_to_evidence("get_system_events", {"service_name": "x"}, "error: boom") == []


def test_tool_result_to_evidence_never_builds_a_hypothesis():
    """Hypothesis formation belongs to `hypotheses_from_evidence` alone — this
    function's return type doesn't even have room for one."""
    raw = json.dumps([{"commit_sha": "abc1234"}])
    evidence = mcp_tools.tool_result_to_evidence("get_system_events", {"service_name": "payment"}, raw)
    assert all("kind" not in e for e in evidence)  # Evidence dicts, never Hypothesis objects


# -- hypotheses_from_evidence ----------------------------------------------


def test_events_evidence_yields_a_deploy_regression_hypothesis():
    evidence = [
        {"id": "mcp-events-payment-0", "source": "mcp_events", "service": "payment", "summary": "x", "raw": {}, "timestamp": None},
        {"id": "mcp-events-payment-1", "source": "mcp_events", "service": "payment", "summary": "y", "raw": {}, "timestamp": None},
    ]
    hyps = mcp_tools.hypotheses_from_evidence(evidence)

    assert len(hyps) == 1
    assert hyps[0].kind == "deploy_regression"
    assert hyps[0].subject_service == "payment"
    assert hyps[0].origin == "mcp"
    assert "2 event(s)" in hyps[0].statement


def test_non_events_evidence_is_ignored():
    evidence = [{"id": "e1", "source": "topology", "service": "payment", "summary": "x", "raw": {}, "timestamp": None}]
    assert mcp_tools.hypotheses_from_evidence(evidence) == []


def test_one_hypothesis_per_service_not_per_event():
    evidence = [
        {"id": f"mcp-events-{s}-0", "source": "mcp_events", "service": s, "summary": "x", "raw": {}, "timestamp": None}
        for s in ["payment", "payment", "cart"]
    ]
    hyps = mcp_tools.hypotheses_from_evidence(evidence)
    assert {h.subject_service for h in hyps} == {"payment", "cart"}
    assert len(hyps) == 2


# -- tool_result_to_probe_run ----------------------------------------------


def test_probe_run_names_the_tool_and_service():
    run = mcp_tools.tool_result_to_probe_run(
        "get_system_events", {"service_name": "payment"}, json.dumps([{"a": 1}])
    )
    assert run["probe_id"] == "mcp.get_system_events[payment]"
    assert run["status"] == "ok"
    assert run["evidence_count"] == 1


def test_probe_run_reports_the_error_text():
    run = mcp_tools.tool_result_to_probe_run("get_service_topology", {"service_name": "x"}, "error: refused")
    assert run["status"] == "error"
    assert run["summary"] == "error: refused"


# =============================================================================
# ground_node's LLM + MCP tool-calling pass
# =============================================================================


class _FakeToolCallResponse:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


def test_ground_node_skips_mcp_pass_under_deterministic_mode():
    with mock.patch.dict("os.environ", {"INCIMIN_DETERMINISTIC": "1"}), mock.patch.object(
        kernel, "run_topology_subagent"
    ) as topo, mock.patch("src.agent.llm.build_llm") as build_llm:
        topo.return_value = mock.Mock(evidence=[], candidate_services=["payment"], summary="ok")
        kernel.ground_node({"alert": {"service": "payment"}})

    build_llm.assert_not_called()


def test_ground_node_executes_whatever_tool_calls_the_model_makes():
    """`get_system_events` is a Pydantic-backed LangChain StructuredTool — its
    methods can't be `mock.patch.object`ed directly, so the real tool function
    runs and `MCPSession` (its actual network boundary) is mocked instead. This
    exercises the real @tool wrapper code, not a stand-in for it."""
    with mock.patch.object(kernel, "run_topology_subagent") as topo, mock.patch.object(
        kernel, "deterministic_mode", return_value=False
    ), mock.patch("src.agent.llm.build_llm") as build_llm, _patched(
        ToolResult(ok=True, data=[{"commit_sha": "abc1234"}])
    ):
        topo.return_value = mock.Mock(evidence=[], candidate_services=["payment"], summary="ok")
        llm = mock.Mock()
        llm.bind_tools.return_value.invoke.return_value = _FakeToolCallResponse(
            [{"name": "get_system_events", "args": {"service_name": "payment", "start_time": "x", "end_time": "y"}}]
        )
        build_llm.return_value = llm

        out = kernel.ground_node({"alert": {"service": "payment", "alertname": "X"}})

    assert any(e["source"] == "mcp_events" for e in out["evidence"])
    assert any(r["probe_id"].startswith("mcp.get_system_events") for r in out["probe_log"])


def test_ground_node_ignores_a_tool_call_for_an_unknown_tool_name():
    """A model can only be trusted to name a tool, never to have invented one
    that exists — an unrecognized name must not raise."""
    with mock.patch.object(kernel, "run_topology_subagent") as topo, mock.patch.object(
        kernel, "deterministic_mode", return_value=False
    ), mock.patch("src.agent.llm.build_llm") as build_llm:
        topo.return_value = mock.Mock(evidence=[], candidate_services=["payment"], summary="ok")
        llm = mock.Mock()
        llm.bind_tools.return_value.invoke.return_value = _FakeToolCallResponse(
            [{"name": "delete_everything", "args": {}}]
        )
        build_llm.return_value = llm

        out = kernel.ground_node({"alert": {"service": "payment"}})

    assert out["evidence"] == []  # deterministic BFS evidence was also empty here


def test_ground_node_degrades_when_the_model_call_itself_fails():
    with mock.patch.object(kernel, "run_topology_subagent") as topo, mock.patch.object(
        kernel, "deterministic_mode", return_value=False
    ), mock.patch("src.agent.llm.build_llm", side_effect=RuntimeError("no API key")):
        topo.return_value = mock.Mock(evidence=[], candidate_services=["payment"], summary="ok")
        out = kernel.ground_node({"alert": {"service": "payment"}})

    assert out["candidate_services"] == ["payment"]  # deterministic pass is untouched
    assert out["probe_log"][0]["status"] == "error"


# =============================================================================
# seed_node's evidence-mining tier
# =============================================================================


def test_seed_node_turns_mcp_events_evidence_into_a_hypothesis():
    mcp_evidence = [
        {"id": "mcp-events-payment-0", "source": "mcp_events", "service": "payment", "summary": "x", "raw": {}, "timestamp": None}
    ]
    with mock.patch.object(kernel, "deterministic_mode", return_value=True):
        out = kernel.seed_node(
            {"alert": {"service": "payment"}, "candidate_services": ["cart", "checkout"], "evidence": mcp_evidence}
        )

    assert any(h.id == "h-mcp-deploy-payment" for h in out["hypotheses"])


def test_seed_node_does_not_call_mcp_itself_anymore():
    """Hypothesis generation uses evidence that already exists; it does not go
    fetch its own — that's Meta-Agent's job now. Proven at the actual network
    boundary (MCPSession) rather than by patching the @tool wrappers, since
    those are Pydantic-backed and can't have their methods patched directly."""
    with mock.patch("src.agent.kernel.mcp_tools.MCPSession") as session_cls, mock.patch.object(
        kernel, "deterministic_mode", return_value=False
    ):
        kernel.seed_node({"alert": {"service": "payment"}, "candidate_services": ["cart", "checkout"], "evidence": []})

    session_cls.assert_not_called()


# =============================================================================
# synthesize_node
# =============================================================================


def _base_synthesize_state():
    from src.agent.kernel.state import Synthesis

    winner = Hypothesis(
        id="h-1", kind="dependency_failure", statement="payment is failing",
        subject_service="payment", origin="topology", prior=0.8, posterior=0.8,
        supporting_refs=["e1"],
    )
    return {
        "hypotheses": [winner],
        "synthesis": Synthesis(root_cause_service="payment", evidence_refs=["e1"], confidence="high"),
        "evidence": [{"id": "e1", "source": "telemetry", "service": "payment", "summary": "errors", "raw": {}, "timestamp": None}],
        "probe_log": [],
    }


def test_synthesize_node_skips_under_deterministic_mode():
    with mock.patch.object(kernel, "deterministic_mode", return_value=True), mock.patch(
        "src.agent.llm.build_llm"
    ) as build_llm:
        out = kernel.synthesize_node(_base_synthesize_state())

    build_llm.assert_not_called()
    assert out == {}


def test_synthesize_node_skips_when_there_is_no_synthesis():
    with mock.patch.object(kernel, "deterministic_mode", return_value=False):
        assert kernel.synthesize_node({"hypotheses": [], "synthesis": None}) == {}


def test_synthesize_node_appends_a_message_the_step_recorder_will_pick_up_as_final():
    class _Narrative:
        explanation = "payment is the root cause because of X."
        next_steps = ["roll back the last deploy", "check payment's error dashboard"]

    with mock.patch.object(kernel, "deterministic_mode", return_value=False), mock.patch(
        "src.agent.llm.build_llm"
    ) as build_llm:
        llm = mock.Mock()
        llm.with_structured_output.return_value.invoke.return_value = _Narrative()
        build_llm.return_value = llm

        out = kernel.synthesize_node(_base_synthesize_state())

    text = out["messages"][0].content
    assert "payment is the root cause" in text
    assert "roll back the last deploy" in text


def test_synthesize_node_degrades_silently_when_the_llm_call_fails():
    """report_node's deterministic message must be what a human sees if this fails —
    nothing about the incident's recorded outcome may depend on this succeeding."""
    with mock.patch.object(kernel, "deterministic_mode", return_value=False), mock.patch(
        "src.agent.llm.build_llm", side_effect=RuntimeError("rate limited")
    ):
        out = kernel.synthesize_node(_base_synthesize_state())

    assert out == {}
