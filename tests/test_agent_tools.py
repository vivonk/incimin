import unittest
from unittest.mock import patch, MagicMock
from src.agent.tools import graph_bfs_tool, clickhouse_log_tool, qdrant_runbook_tool

class TestAgentTools(unittest.TestCase):
    @patch("src.agent.tools.neo4j.GraphDatabase.driver")
    def test_graph_bfs_tool_success(self, mock_driver):
        mock_session = MagicMock()
        mock_driver.return_value.session.return_value.__enter__.return_value = mock_session
        mock_session.run.return_value = [{"path": "ServiceA -> ServiceB"}]
        
        result = graph_bfs_tool.invoke({"source": "ServiceA"})
        self.assertEqual(result, "ServiceA -> ServiceB")

    @patch("src.agent.tools.neo4j.GraphDatabase.driver")
    def test_graph_bfs_tool_error(self, mock_driver):
        mock_driver.side_effect = Exception("DB connection failed")
        
        result = graph_bfs_tool.invoke({"source": "ServiceA"})
        self.assertTrue("Error executing topology query" in result)

    @patch("src.agent.tools.clickhouse_connect.get_client")
    def test_clickhouse_log_tool_success(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        mock_result = MagicMock()
        mock_result.result_rows = [
            (123456789, "trace-123", "NullPointerException")
        ]
        mock_client.query.return_value = mock_result
        
        result = clickhouse_log_tool.invoke({"service_name": "paymentservice"})
        self.assertTrue("NullPointerException" in result)

    @patch("src.agent.tools.clickhouse_connect.get_client")
    def test_clickhouse_log_tool_error(self, mock_get_client):
        mock_get_client.side_effect = Exception("CH connection failed")
        
        result = clickhouse_log_tool.invoke({"service_name": "paymentservice"})
        self.assertTrue("Error executing telemetry query" in result)

    @patch("src.agent.tools.QdrantClient")
    def test_qdrant_runbook_tool_success(self, mock_qdrant):
        mock_client = MagicMock()
        mock_qdrant.return_value = mock_client
        
        mock_results = MagicMock()
        mock_point = MagicMock()
        mock_point.payload = {"filename": "runbook.md", "content": "restart service"}
        mock_results.points = [mock_point]
        mock_client.query_points.return_value = mock_results
        
        # we also need to mock fastembed, but let's mock the TextEmbedding init
        with patch("src.agent.tools.TextEmbedding") as mock_embed:
            mock_embed_instance = MagicMock()
            mock_embed.return_value = mock_embed_instance
            mock_embed_instance.embed.return_value = [MagicMock(tolist=lambda: [0.1, 0.2])]
            
            result = qdrant_runbook_tool.invoke({"query": "crash"})
            self.assertTrue("restart service" in result)

    @patch("src.agent.tools.QdrantClient")
    def test_qdrant_runbook_tool_error(self, mock_qdrant):
        mock_qdrant.side_effect = Exception("Qdrant connection failed")
        
        result = qdrant_runbook_tool.invoke({"query": "crash"})
        self.assertTrue("Error executing knowledge query" in result)

if __name__ == "__main__":
    unittest.main()
