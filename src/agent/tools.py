from langchain_core.tools import tool
import clickhouse_connect
import neo4j
from qdrant_client import QdrantClient
from fastembed import TextEmbedding
import time

@tool
def graph_bfs_tool(source: str) -> str:
    """Connects via neo4j driver, executes BFS query, returns path string."""
    try:
        driver = neo4j.GraphDatabase.driver("bolt://127.0.0.1:7687", auth=("", ""))
        with driver.session() as session:
            result = session.run("MATCH path = (s:Service {name: $source})-[*BFS]->(target) RETURN path LIMIT 10", source=source)
            paths = []
            for record in result:
                paths.append(str(record["path"]))
            return "\n".join(paths) if paths else "No path found."
    except Exception as e:
        return f"Error executing topology query: {str(e)}"

@tool
def clickhouse_log_tool(service_name: str, window_mins: int = 30) -> str:
    """Connects via clickhouse_connect, queries signoz_logs.distributed_logs_v2 for ERROR logs."""
    try:
        client = clickhouse_connect.get_client(host='127.0.0.1', port=8123)
        now_ns = int(time.time() * 1e9)
        start_time_ns = now_ns - int(window_mins * 60 * 1e9)
        query = """
            SELECT timestamp, trace_id, body
            FROM signoz_logs.distributed_logs_v2
            WHERE timestamp >= {start_time:UInt64}
              AND timestamp <= {end_time:UInt64}
              AND resources_string['service.name'] = {service_name:String}
              AND severity_text = 'ERROR'
            ORDER BY timestamp DESC
            LIMIT 10
        """
        result = client.query(query, parameters={
            'start_time': start_time_ns,
            'end_time': now_ns,
            'service_name': service_name
        })
        if not result.result_rows:
            return "No ERROR logs found."
        
        logs = []
        for row in result.result_rows:
            logs.append(f"Timestamp: {row[0]}, Trace ID: {row[1]}, Body: {row[2]}")
        return "\n".join(logs)
    except Exception as e:
        return f"Error executing telemetry query: {str(e)}"

@tool
def qdrant_runbook_tool(query: str) -> str:
    """Connects via QdrantClient, embeds query with fastembed, searches runbooks collection."""
    try:
        client = QdrantClient("http://127.0.0.1:6333", timeout=5.0)
        embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5")
        embeddings = list(embedding_model.embed([query]))
        results = client.query_points(
            collection_name="runbooks",
            query=embeddings[0].tolist(),
            limit=3
        )
        if not results.points:
            return "No runbooks found."
        
        runbooks = []
        for point in results.points:
            payload = point.payload or {}
            filename = payload.get("filename", "unknown")
            content = payload.get("content", "")
            runbooks.append(f"--- {filename} ---\n{content}")
        return "\n\n".join(runbooks)
    except Exception as e:
        return f"Error executing knowledge query: {str(e)}"
