from qdrant_client import QdrantClient
from fastembed import TextEmbedding

def check():
    client = QdrantClient("http://127.0.0.1:6333", timeout=5.0)
    embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5")
    
    query = "crash incident in paymentservice"
    query_vector = list(embedding_model.embed([query]))[0].tolist()
    
    results = client.query_points(
        collection_name="runbooks",
        query=query_vector,
        limit=1
    ).points
    
    if not results:
        raise Exception("No runbook found.")
        
    if "paymentservice" not in results[0].payload["filename"]:
        raise Exception(f"Wrong runbook retrieved: {results[0].payload['filename']}")
        
    print("Successfully found correct runbook:", results[0].payload["filename"])

if __name__ == "__main__":
    check()
