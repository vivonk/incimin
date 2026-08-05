from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from fastembed import TextEmbedding

def check():
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
            
        print(f"PASS: '{query}' -> {retrieved_filename}")

    # Test payload filtering explicitly as required by plan
    print("Testing payload filter...")
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
    print("PASS: Payload filtering works.")

if __name__ == "__main__":
    check()
