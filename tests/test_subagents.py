import unittest
from unittest.mock import MagicMock, patch

from src.agent.subagents.knowledge import RerankSelection, run_knowledge_subagent
from src.agent.subagents.telemetry import EscalationDecision, run_telemetry_subagent
from src.agent.subagents.topology import run_topology_subagent


class FakeNode:
    def __init__(self, name):
        self._name = name

    def get(self, key, default=None):
        return self._name if key == "name" else default


class FakePath:
    def __init__(self, node_names):
        self.nodes = [FakeNode(n) for n in node_names]

    def __str__(self):
        return " -> ".join(n._name for n in self.nodes)


class TestTopologySubagent(unittest.TestCase):
    @patch("src.agent.subagents.topology.neo4j.GraphDatabase.driver")
    def test_ranks_candidates_by_first_appearance(self, mock_driver):
        mock_session = MagicMock()
        mock_driver.return_value.session.return_value.__enter__.return_value = mock_session
        mock_session.run.return_value = [
            {"path": FakePath(["checkoutservice", "paymentservice"])},
            {"path": FakePath(["checkoutservice", "cartservice"])},
        ]

        result = run_topology_subagent("checkoutservice")

        self.assertEqual(result.candidate_services, ["paymentservice", "cartservice"])
        self.assertEqual(len(result.evidence), 2)
        self.assertEqual(result.evidence[0]["source"], "topology")
        self.assertIsNone(result.evidence[0]["timestamp"])

    @patch("src.agent.subagents.topology.neo4j.GraphDatabase.driver")
    def test_no_path_found(self, mock_driver):
        mock_session = MagicMock()
        mock_driver.return_value.session.return_value.__enter__.return_value = mock_session
        mock_session.run.return_value = []

        result = run_topology_subagent("checkoutservice")

        self.assertEqual(result.candidate_services, [])
        self.assertEqual(result.evidence, [])
        self.assertEqual(result.summary, "No path found.")

    @patch("src.agent.subagents.topology.neo4j.GraphDatabase.driver")
    def test_connection_error(self, mock_driver):
        mock_driver.side_effect = Exception("DB connection failed")

        result = run_topology_subagent("checkoutservice")

        self.assertIn("Error executing topology query", result.summary)
        self.assertEqual(result.evidence, [])


class TestTelemetrySubagent(unittest.TestCase):
    def test_no_candidates_short_circuits(self):
        result = run_telemetry_subagent([])
        self.assertEqual(result.evidence, [])
        self.assertEqual(result.summary, "No candidate services to investigate.")

    @patch("src.agent.subagents.telemetry.build_llm")
    @patch("src.agent.subagents.telemetry.clickhouse_connect.get_client")
    def test_fast_path_finds_errors_skips_llm(self, mock_get_client, mock_build_llm):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_result = MagicMock()
        mock_result.result_rows = [(123456789000, "trace-1", "NullPointerException")]
        mock_client.query.return_value = mock_result

        result = run_telemetry_subagent(["paymentservice"])

        self.assertEqual(len(result.evidence), 1)
        self.assertEqual(result.evidence[0]["service"], "paymentservice")
        mock_build_llm.assert_not_called()

    @patch("src.agent.subagents.telemetry.build_llm")
    @patch("src.agent.subagents.telemetry.clickhouse_connect.get_client")
    def test_escalation_broadens_when_fast_path_empty(self, mock_get_client, mock_build_llm):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        empty_result = MagicMock()
        empty_result.result_rows = []
        broad_result = MagicMock()
        broad_result.result_rows = [(123456789000, "trace-2", "WARN: retrying")]
        mock_client.query.side_effect = [empty_result, broad_result]

        mock_structured = MagicMock()
        mock_structured.invoke.return_value = EscalationDecision(action="broaden", reason="widen severity")
        mock_build_llm.return_value.with_structured_output.return_value = mock_structured

        result = run_telemetry_subagent(["paymentservice"])

        self.assertEqual(len(result.evidence), 1)
        self.assertIn("broadened scan", result.summary)

    @patch("src.agent.subagents.telemetry.build_llm")
    @patch("src.agent.subagents.telemetry.clickhouse_connect.get_client")
    def test_escalation_checks_next_candidate(self, mock_get_client, mock_build_llm):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        empty_result = MagicMock()
        empty_result.result_rows = []
        next_result = MagicMock()
        next_result.result_rows = [(123456789000, "trace-3", "boom")]
        mock_client.query.side_effect = [empty_result, next_result]

        mock_structured = MagicMock()
        mock_structured.invoke.return_value = EscalationDecision(
            action="next_candidate", target_service="cartservice", reason="check upstream"
        )
        mock_build_llm.return_value.with_structured_output.return_value = mock_structured

        result = run_telemetry_subagent(["paymentservice", "cartservice"])

        self.assertEqual(result.evidence[0]["service"], "cartservice")

    @patch("src.agent.subagents.telemetry.build_llm")
    @patch("src.agent.subagents.telemetry.clickhouse_connect.get_client")
    def test_escalation_llm_failure_fails_closed_to_broaden(self, mock_get_client, mock_build_llm):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        empty_result = MagicMock()
        empty_result.result_rows = []
        broad_result = MagicMock()
        broad_result.result_rows = []
        mock_client.query.side_effect = [empty_result, broad_result]
        mock_build_llm.side_effect = Exception("LLM unavailable")

        result = run_telemetry_subagent(["paymentservice"])

        self.assertIn("LLM escalation unavailable", result.summary)

    @patch("src.agent.subagents.telemetry.clickhouse_connect.get_client")
    def test_connection_error(self, mock_get_client):
        mock_get_client.side_effect = Exception("CH connection failed")

        result = run_telemetry_subagent(["paymentservice"])

        self.assertIn("Error executing telemetry query", result.summary)


class TestKnowledgeSubagent(unittest.TestCase):
    @patch("src.agent.subagents.knowledge.build_llm")
    @patch("src.agent.subagents.knowledge.TextEmbedding")
    @patch("src.agent.subagents.knowledge.QdrantClient")
    def test_high_confidence_match_skips_llm(self, mock_qdrant, mock_embed, mock_build_llm):
        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client
        mock_embed.return_value.embed.return_value = [MagicMock(tolist=lambda: [0.1, 0.2])]

        mock_point = MagicMock(payload={"filename": "paymentservice_crash.md", "content": "restart"}, score=0.9)
        mock_client.query_points.return_value = MagicMock(points=[mock_point])

        result = run_knowledge_subagent("payment crash")

        self.assertEqual(len(result.evidence), 1)
        self.assertEqual(result.evidence[0]["service"], "paymentservice")
        mock_build_llm.assert_not_called()

    @patch("src.agent.subagents.knowledge.build_llm")
    @patch("src.agent.subagents.knowledge.TextEmbedding")
    @patch("src.agent.subagents.knowledge.QdrantClient")
    def test_low_confidence_triggers_rerank(self, mock_qdrant, mock_embed, mock_build_llm):
        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client
        mock_embed.return_value.embed.return_value = [MagicMock(tolist=lambda: [0.1, 0.2])]

        points = [
            MagicMock(payload={"filename": "a.md", "content": "a"}, score=0.2),
            MagicMock(payload={"filename": "b.md", "content": "b"}, score=0.1),
        ]
        mock_client.query_points.return_value = MagicMock(points=points)

        mock_structured = MagicMock()
        mock_structured.invoke.return_value = RerankSelection(selected_ids=["knowledge-1"], reason="b fits better")
        mock_build_llm.return_value.with_structured_output.return_value = mock_structured

        result = run_knowledge_subagent("ambiguous query")

        self.assertEqual(len(result.evidence), 1)
        self.assertEqual(result.evidence[0]["id"], "knowledge-1")

    @patch("src.agent.subagents.knowledge.QdrantClient")
    def test_connection_error(self, mock_qdrant):
        mock_qdrant.side_effect = Exception("Qdrant connection failed")

        result = run_knowledge_subagent("crash")

        self.assertIn("Error executing knowledge query", result.summary)


if __name__ == "__main__":
    unittest.main()
