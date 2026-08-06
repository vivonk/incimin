"""Tool-wiring tests. LangGraph's ToolNode resolves InjectedToolCallId/InjectedState via a
graph-task Runtime that only exists once a StateGraph is compiled and invoked (bare
ToolNode(...).invoke() outside a compiled graph raises ValueError: "Missing required config
key" for the same reason) — so each test wraps the tool in a minimal one-node graph.
"""
import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.agent.state import SREAgentState
from src.agent.subagents.knowledge import KnowledgeResult
from src.agent.subagents.telemetry import TelemetryResult
from src.agent.subagents.topology import TopologyResult
from src.agent.tools import knowledge_tool, telemetry_tool, topology_tool


def tool_call(name, args, call_id="call-1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


def invoke_single_tool(tool_fn, initial_state):
    graph = StateGraph(SREAgentState)
    graph.add_node("tools", ToolNode([tool_fn]))
    graph.set_entry_point("tools")
    graph.add_edge("tools", END)
    return graph.compile().invoke(initial_state)


class TestTopologyTool(unittest.TestCase):
    @patch("src.agent.tools.run_topology_subagent")
    def test_updates_evidence_and_candidate_services(self, mock_run):
        mock_run.return_value = TopologyResult(
            candidate_services=["paymentservice"],
            evidence=[{"id": "topology-0", "source": "topology", "service": "paymentservice", "summary": "s", "raw": {}, "timestamp": None}],
            summary="Traversed 1 path(s).",
        )

        result = invoke_single_tool(
            topology_tool, {"messages": [tool_call("topology_tool", {"source": "checkoutservice"})]}
        )

        mock_run.assert_called_once_with("checkoutservice")
        self.assertEqual(result["candidate_services"], ["paymentservice"])
        self.assertEqual(len(result["evidence"]), 1)
        tool_msg = result["messages"][-1]
        self.assertIsInstance(tool_msg, ToolMessage)
        self.assertEqual(tool_msg.content, "Traversed 1 path(s).")


class TestTelemetryTool(unittest.TestCase):
    @patch("src.agent.tools.run_telemetry_subagent")
    def test_reads_candidate_services_from_state(self, mock_run):
        mock_run.return_value = TelemetryResult(
            evidence=[{"id": "telemetry-err-0", "source": "telemetry", "service": "paymentservice", "summary": "s", "raw": {}, "timestamp": 1}],
            summary="Found 1 ERROR log(s).",
        )

        result = invoke_single_tool(
            telemetry_tool,
            {"messages": [tool_call("telemetry_tool", {})], "candidate_services": ["paymentservice"]},
        )

        mock_run.assert_called_once_with(["paymentservice"], window_mins=30)
        self.assertEqual(len(result["evidence"]), 1)

    @patch("src.agent.tools.run_telemetry_subagent")
    def test_defaults_to_empty_candidates_when_topology_has_not_run(self, mock_run):
        mock_run.return_value = TelemetryResult(summary="No candidate services to investigate.")

        invoke_single_tool(telemetry_tool, {"messages": [tool_call("telemetry_tool", {})]})

        mock_run.assert_called_once_with([], window_mins=30)


class TestKnowledgeTool(unittest.TestCase):
    @patch("src.agent.tools.run_knowledge_subagent")
    def test_returns_evidence_command(self, mock_run):
        mock_run.return_value = KnowledgeResult(
            evidence=[{"id": "knowledge-0", "source": "knowledge", "service": "paymentservice", "summary": "paymentservice_crash.md", "raw": {}, "timestamp": None}],
            summary="Top match: paymentservice_crash.md (score=0.90).",
        )

        result = invoke_single_tool(
            knowledge_tool, {"messages": [tool_call("knowledge_tool", {"query": "payment crash"})]}
        )

        mock_run.assert_called_once_with("payment crash")
        self.assertEqual(len(result["evidence"]), 1)


if __name__ == "__main__":
    unittest.main()
