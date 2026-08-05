import sys
import time
from gqlalchemy import Memgraph
import clickhouse_connect
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from fastembed import TextEmbedding

def get_memgraph_with_retry(host="127.0.0.1", port=7687, retries=10, delay=2):
    for i in range(retries):
        try:
            memgraph = Memgraph(host=host, port=port)
            memgraph.execute_and_fetch("RETURN 1")
            return memgraph
        except Exception:
            if i < retries - 1:
                time.sleep(delay)
            else:
                raise

def check_topo_01():
    memgraph = get_memgraph_with_retry(host="127.0.0.1", port=7687)
    nodes = list(memgraph.execute_and_fetch("MATCH (n:Service) RETURN count(n) as count"))
    node_count = nodes[0]['count']
    if node_count != 14:
        raise Exception(f"Expected 14 nodes, found {node_count}")

def check_topo_02():
    memgraph = get_memgraph_with_retry(host="127.0.0.1", port=7687)
    bfs_query = """
    MATCH path = (start:Service {name: 'checkout'})-[:DEPENDS_ON *BFS]->(end:Service {name: 'payment'})
    RETURN nodes(path) as path_nodes
    """
    path_results = list(memgraph.execute_and_fetch(bfs_query))
    if not path_results:
        raise Exception("Failed to find BFS path from checkout to payment")

def check_tele_01():
    client = clickhouse_connect.get_client(host='127.0.0.1', port=8123)
    now_ns = int(time.time() * 1e9)
    hour_ago_ns = now_ns - int(3600 * 1e9)
    
    query = """
        SELECT count()
        FROM signoz_logs.distributed_logs_v2
        WHERE timestamp >= {start_time:UInt64}
          AND timestamp <= {end_time:UInt64}
          AND resources_string['service.name'] = {service_name:String}
          AND severity_text = 'ERROR'
    """
    
    parameters = {
        'start_time': hour_ago_ns,
        'end_time': now_ns,
        'service_name': 'paymentservice'
    }
    
    result = client.query(query, parameters=parameters)
    # Just verifying query execution with nanosecond timestamps succeeds

def check_know_01():
    client = QdrantClient("http://127.0.0.1:6333", timeout=5.0)
    embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5")
    
    tests = [
        ("Payment service is crashing", "paymentservice_crash.md"),
        ("Users are abandoning carts due to slowness", "checkoutservice_high_latency.md"),
        ("Storefront is showing 500 internal server error", "frontendservice_5xx_errors.md")
    ]
    
    for query, expected_filename in tests:
        query_vector = list(embedding_model.embed([query]))[0].tolist()
        
        results = client.query_points(
            collection_name="runbooks",
            query=query_vector,
            limit=1
        ).points
        
        if not results:
            raise Exception(f"No runbook found for query: {query}")
            
        retrieved_filename = results[0].payload["filename"]
        if retrieved_filename != expected_filename:
            raise Exception(f"Wrong runbook retrieved for '{query}'. Expected {expected_filename}, got {retrieved_filename}")

def check_know_02():
    client = QdrantClient("http://127.0.0.1:6333", timeout=5.0)
    embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5")
    query_vector = list(embedding_model.embed(["crash"]))[0].tolist()
    
    filter_results = client.query_points(
        collection_name="runbooks",
        query=query_vector,
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="filename",
                    match=MatchValue(value="paymentservice_crash.md")
                )
            ]
        ),
        limit=1
    ).points
    
    if not filter_results or filter_results[0].payload["filename"] != "paymentservice_crash.md":
        raise Exception("Payload filter test failed.")

CHECKS = [
    ("TOPO-01", check_topo_01),
    ("TOPO-02", check_topo_02),
    ("TELE-01", check_tele_01),
    ("KNOW-01", check_know_01),
    ("KNOW-02", check_know_02),
]

def main():
    fail_count = 0
    for cid, func in CHECKS:
        try:
            func()
            print(f"PASS  {cid}  OK")
        except Exception as e:
            fail_count += 1
            msg = str(e).split('\n')[0]
            print(f"FAIL  {cid}  {type(e).__name__}: {msg}")
    
    print(f"\nSummary: {len(CHECKS) - fail_count} PASS, {fail_count} FAIL")
    if fail_count > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
