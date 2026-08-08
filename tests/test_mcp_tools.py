"""Hypothesis generation's MCP grounding (`src/agent/kernel/mcp_tools.py`).

`MCPSession` itself talks real sockets, so every test here replaces it with a
stand-in rather than touching the network — these are unit tests for what
`gather()` does with a session's responses, not integration tests of the
transport (that already has its own coverage via the live server).
"""
from __future__ import annotations

from unittest import mock

from src.agent.kernel import graph as kernel
from src.agent.kernel import mcp_tools
from src.agent.kernel.state import Hypothesis
from src.agent.mcp_client import ToolResult


class _FakeSession:
    """A session whose `call_tool` / `call_tool_many` return canned results,
    usable as the context manager `gather()` expects."""

    def __init__(self, topology: ToolResult, events: dict[str, ToolResult]):
        self.topology = topology
        self.events = events
        self.calls: list[tuple] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def call_tool(self, name, args, timeout=None):
        self.calls.append((name, args))
        assert name == "get_service_topology"
        return self.topology

    def call_tool_many(self, calls, timeout=None):
        self.calls.extend(calls)
        return [self.events[args["service_name"]] for _, args in calls]


def _patched(topology: ToolResult, events: dict[str, ToolResult]):
    return mock.patch(
        "src.agent.kernel.mcp_tools.MCPSession",
        return_value=_FakeSession(topology, events),
    )


def test_calls_both_tools_the_server_exposes():
    """The literal ask: hypothesis generation must use every MCP tool available,
    not just one."""
    topology = ToolResult(ok=True, data=[])
    events = {"payment": ToolResult(ok=True, data=[])}

    with _patched(topology, events) as session_cls:
        mcp_tools.gather({"service": "payment"}, [])

    fake = session_cls.return_value
    names = {c[0] for c in fake.calls}
    assert names == {"get_service_topology", "get_system_events"}


def test_a_recent_event_becomes_a_deploy_regression_hypothesis():
    """The functional payoff: a real change found via MCP is grounds for a
    hypothesis, not just later corroboration for one another tier guessed."""
    topology = ToolResult(ok=True, data=[])
    events = {
        "payment": ToolResult(
            ok=True,
            data=[{"timestamp": "2026-08-08 09:00:00", "commit_sha": "abc1234", "source": "deploy"}],
        )
    }

    with _patched(topology, events):
        evidence, hypotheses, probe_log = mcp_tools.gather({"service": "payment"}, [])

    assert len(hypotheses) == 1
    h = hypotheses[0]
    assert h.kind == "deploy_regression"
    assert h.subject_service == "payment"
    assert h.origin == "mcp"
    assert any(e["source"] == "mcp_events" and e["service"] == "payment" for e in evidence)
    assert any(r["probe_id"] == "mcp.get_system_events[payment]" and r["status"] == "ok" for r in probe_log)


def test_no_events_yields_no_hypothesis_but_still_logs_the_call():
    """An empty result is a real, useful answer — it must show up in the step
    log even though it produced nothing to reason from."""
    topology = ToolResult(ok=True, data=[])
    events = {"payment": ToolResult(ok=True, data=[])}

    with _patched(topology, events):
        evidence, hypotheses, probe_log = mcp_tools.gather({"service": "payment"}, [])

    assert hypotheses == []
    assert any(r["probe_id"] == "mcp.get_system_events[payment]" for r in probe_log)


def test_topology_result_becomes_evidence():
    topology = ToolResult(
        ok=True, data=[{"source": "checkout", "rel_type": "CALLS", "target": "payment"}]
    )
    events = {"checkout": ToolResult(ok=True, data=[])}

    with _patched(topology, events):
        evidence, _, probe_log = mcp_tools.gather({"service": "checkout"}, [])

    topo_evidence = [e for e in evidence if e["source"] == "mcp_topology"]
    assert len(topo_evidence) == 1
    assert "checkout" in topo_evidence[0]["summary"] and "payment" in topo_evidence[0]["summary"]


def test_a_dead_server_degrades_instead_of_raising():
    """The core promise: hypothesis generation must not fail because MCP is
    unreachable. It degrades to whatever the topology/LLM tiers already produce."""
    with mock.patch(
        "src.agent.kernel.mcp_tools.MCPSession", side_effect=ConnectionError("refused")
    ):
        evidence, hypotheses, probe_log = mcp_tools.gather({"service": "payment"}, [])

    assert evidence == []
    assert hypotheses == []
    assert probe_log[0]["status"] == "error"
    assert probe_log[0]["probe_id"] == "mcp.session"


def test_no_service_and_no_candidates_skips_the_call_entirely():
    with mock.patch("src.agent.kernel.mcp_tools.MCPSession") as session_cls:
        evidence, hypotheses, probe_log = mcp_tools.gather({}, [])

    session_cls.assert_not_called()
    assert (evidence, hypotheses, probe_log) == ([], [], [])


def test_services_list_is_deduped_and_bounded():
    """The source service is asked about once, even if it also appears in the
    candidate list, and the fan-out never exceeds the configured cap."""
    topology = ToolResult(ok=True, data=[])
    many = ["payment", "cart", "checkout", "shipping", "email", "currency", "ad"]
    events = {s: ToolResult(ok=True, data=[]) for s in many}

    with _patched(topology, events) as session_cls:
        mcp_tools.gather({"service": "payment"}, many)

    fake = session_cls.return_value
    event_calls = [args["service_name"] for name, args in fake.calls if name == "get_system_events"]
    assert event_calls[0] == "payment"
    assert len(event_calls) == len(set(event_calls))
    assert len(event_calls) <= mcp_tools.MAX_SERVICES


# -- seed_node wiring --------------------------------------------------------


def test_seed_node_skips_mcp_under_deterministic_mode():
    """The golden path and the kernel test suite must stay network-free."""
    with mock.patch.dict("os.environ", {"INCIMIN_DETERMINISTIC": "1"}), mock.patch.object(
        kernel.mcp_tools, "gather"
    ) as gather:
        kernel.seed_node({"alert": {"service": "payment"}, "candidate_services": ["payment"]})

    gather.assert_not_called()


def test_seed_node_folds_mcp_hypotheses_and_records_the_step_log():
    """The wiring point: seed_node's return carries the MCP evidence and
    probe_log through, which is what makes `get_service_topology` /
    `get_system_events` show up as recorded steps under Hypothesis Generation."""
    mcp_hypothesis = Hypothesis(
        id="h-mcp-deploy-payment",
        kind="deploy_regression",
        statement="a recent change to payment",
        subject_service="payment",
        origin="mcp",
        prior=0.6,
    )
    mcp_evidence = [
        {"id": "mcp-events-payment-0", "source": "mcp_events", "service": "payment", "summary": "x", "raw": {}, "timestamp": None}
    ]
    mcp_probe_log = [
        {"probe_id": "mcp.get_system_events[payment]", "dedup_key": "d", "status": "ok", "summary": "1 row", "evidence_count": 1, "round_index": 0}
    ]

    with mock.patch.object(
        kernel.mcp_tools, "gather", return_value=(mcp_evidence, [mcp_hypothesis], mcp_probe_log)
    ), mock.patch.object(kernel, "deterministic_mode", return_value=False):
        # Two candidate services give the topology tier 2 hypotheses; +1 from MCP
        # meets MIN_HYPOTHESES, so the LLM tier never fires — this test is about
        # the MCP wiring, not a live model call.
        out = kernel.seed_node(
            {"alert": {"service": "payment"}, "candidate_services": ["cart", "checkout"]}
        )

    assert any(h.id == "h-mcp-deploy-payment" for h in out["hypotheses"])
    assert out["evidence"] == mcp_evidence
    assert out["probe_log"] == mcp_probe_log
