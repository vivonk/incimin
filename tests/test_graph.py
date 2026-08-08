import os
import time
import unittest
from unittest.mock import MagicMock, patch

if not os.environ.get("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = "test-placeholder"

from langchain_core.messages import AIMessage

from src.agent.state import Synthesis
from src.agent.subagents.telemetry import TelemetryResult
from src.agent.subagents.topology import TopologyResult

NOW_NS = time.time_ns()

TOPOLOGY_RESULT = TopologyResult(
    candidate_services=["paymentservice"],
    evidence=[{"id": "topology-0", "source": "topology", "service": "paymentservice", "summary": "checkoutservice -> paymentservice", "raw": {}, "timestamp": None}],
    summary="Traversed 1 path(s). Candidates: paymentservice",
)
TELEMETRY_RESULT = TelemetryResult(
    evidence=[{"id": "telemetry-err-0", "source": "telemetry", "service": "paymentservice", "summary": "NullPointerException", "raw": {}, "timestamp": NOW_NS}],
    summary="Found 1 ERROR log(s) for paymentservice.",
)


def tool_call_message(name, args, call_id):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


class TestMetaAgentGraph(unittest.TestCase):
    @patch("src.agent.tools.run_telemetry_subagent")
    @patch("src.agent.tools.run_topology_subagent")
    @patch("src.agent.graph.synthesis_llm")
    @patch("src.agent.graph.llm_with_tools")
    def test_golden_path_finalizes_with_grounded_synthesis(
        self, mock_llm_with_tools, mock_synthesis_llm, mock_topology, mock_telemetry
    ):
        from src.agent.graph import app

        mock_topology.return_value = TOPOLOGY_RESULT
        mock_telemetry.return_value = TELEMETRY_RESULT

        mock_llm_with_tools.invoke.side_effect = [
            tool_call_message("topology_tool", {"source": "checkoutservice"}, "call-1"),
            tool_call_message("telemetry_tool", {}, "call-2"),
            AIMessage(content="I have enough evidence."),
        ]
        mock_synthesis_llm.invoke.return_value = Synthesis(
            root_cause_service="paymentservice",
            evidence_refs=["topology-0", "telemetry-err-0"],
            confidence="high",
        )

        result = app.invoke(
            {
                "messages": [("user", "Checkout latency is spiking. Investigate.")],
                "remaining_steps": 10,
            }
        )

        final_message = result["messages"][-1]
        self.assertIn("paymentservice", final_message.content)
        self.assertIn("telemetry-err-0", final_message.content)
        self.assertTrue(result["verification_result"]["passed"])

    @patch("src.agent.tools.run_telemetry_subagent")
    @patch("src.agent.tools.run_topology_subagent")
    @patch("src.agent.graph.synthesis_llm")
    @patch("src.agent.graph.llm_with_tools")
    def test_ungrounded_synthesis_triggers_graceful_exit(
        self, mock_llm_with_tools, mock_synthesis_llm, mock_topology, mock_telemetry
    ):
        from src.agent.graph import app

        mock_topology.return_value = TOPOLOGY_RESULT
        mock_telemetry.return_value = TELEMETRY_RESULT

        mock_llm_with_tools.invoke.side_effect = [
            tool_call_message("topology_tool", {"source": "checkoutservice"}, "call-1"),
            tool_call_message("telemetry_tool", {}, "call-2"),
            AIMessage(content="I have enough evidence."),
        ]
        # cartservice was never seen by topology or telemetry -> Verifier must fail closed.
        mock_synthesis_llm.invoke.return_value = Synthesis(
            root_cause_service="cartservice",
            evidence_refs=["topology-0"],
            confidence="low",
        )

        result = app.invoke(
            {
                "messages": [("user", "Checkout latency is spiking. Investigate.")],
                "remaining_steps": 10,
            }
        )

        final_message = result["messages"][-1]
        self.assertIn("insufficient data to determine root cause", final_message.content)
        self.assertFalse(result["verification_result"]["passed"])
        self.assertIn("cross_modal_consistency", result["verification_result"]["failed_checks"])

    @patch("src.agent.tools.run_knowledge_subagent")
    @patch("src.agent.tools.run_telemetry_subagent")
    @patch("src.agent.tools.run_topology_subagent")
    @patch("src.agent.graph.synthesis_llm")
    @patch("src.agent.graph.llm_with_tools")
    def test_triage_errors_after_change(
        self, mock_llm_with_tools, mock_synthesis_llm, mock_topology, mock_telemetry, mock_knowledge
    ):
        from src.agent.graph import app

        mock_topology.return_value = TOPOLOGY_RESULT
        mock_telemetry.return_value = TELEMETRY_RESULT
        mock_knowledge.return_value = KNOWLEDGE_RESULT

        mock_llm_with_tools.invoke.side_effect = [
            tool_call_message("topology_tool", {"source": "checkoutservice"}, "call-1"),
            tool_call_message("telemetry_tool", {}, "call-2"),
            tool_call_message("knowledge_tool", {"query": "paymentservice crash"}, "call-3"),
            AIMessage(content="I have enough evidence."),
        ]
        mock_synthesis_llm.invoke.return_value = Synthesis(
            root_cause_service="paymentservice",
            evidence_refs=["topology-0", "telemetry-err-0"],
            remediation_runbook_id="knowledge-0",
            confidence="high",
        )

        result = app.invoke(
            {
                "messages": [("user", "We deployed a change to paymentservice 5 minutes ago, and now checkout is failing with 500 errors.")],
                "remaining_steps": 10,
            }
        )

        final_message = result["messages"][-1]
        self.assertIn("paymentservice", final_message.content)
        self.assertIn("Restart the paymentservice deployment", final_message.content)
        self.assertTrue(result["verification_result"]["passed"])

    @patch("src.agent.tools.run_knowledge_subagent")
    @patch("src.agent.tools.run_telemetry_subagent")
    @patch("src.agent.tools.run_topology_subagent")
    @patch("src.agent.graph.synthesis_llm")
    @patch("src.agent.graph.llm_with_tools")
    def test_triage_spontaneous_errors_without_change(
        self, mock_llm_with_tools, mock_synthesis_llm, mock_topology, mock_telemetry, mock_knowledge
    ):
        from src.agent.graph import app

        mock_topology.return_value = TOPOLOGY_RESULT
        mock_telemetry.return_value = TELEMETRY_RESULT
        
        spontaneous_knowledge = KnowledgeResult(
            evidence=[{"id": "knowledge-1", "source": "knowledge", "service": "paymentservice", "summary": "db_connection_loss.md", "raw": {"content": "1. Verify DB health. 2. Scale up connection pool."}, "timestamp": None}],
            summary="Top match: db_connection_loss.md (score=0.88).",
        )
        mock_knowledge.return_value = spontaneous_knowledge

        mock_llm_with_tools.invoke.side_effect = [
            tool_call_message("topology_tool", {"source": "checkoutservice"}, "call-1"),
            tool_call_message("telemetry_tool", {}, "call-2"),
            tool_call_message("knowledge_tool", {"query": "paymentservice database connection"}, "call-3"),
            AIMessage(content="I have enough evidence."),
        ]
        mock_synthesis_llm.invoke.return_value = Synthesis(
            root_cause_service="paymentservice",
            evidence_refs=["topology-0", "telemetry-err-0"],
            remediation_runbook_id="knowledge-1",
            confidence="high",
        )

        result = app.invoke(
            {
                "messages": [("user", "Checkout is returning errors, but there have been no recent changes or deployments in the cluster.")],
                "remaining_steps": 10,
            }
        )

        final_message = result["messages"][-1]
        self.assertIn("paymentservice", final_message.content)
        self.assertIn("Verify DB health", final_message.content)
        self.assertTrue(result["verification_result"]["passed"])


if __name__ == "__main__":
    unittest.main()
