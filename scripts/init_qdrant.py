import os
import glob
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
from fastembed import TextEmbedding

def init():
    client = QdrantClient("http://127.0.0.1:6333", timeout=5.0)
    collection_name = "runbooks"
    
    # Initialize embedding model
    embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5")
    
    # Create collection if it doesn't exist
    try:
        collections = client.get_collections().collections
        exists = any(c.name == collection_name for c in collections)
    except Exception:
        exists = False
        
    if not exists:
        # bge-small-en-v1.5 has vector size 384
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
    
    # Task 1: docs/runbooks/paymentservice_crash.md
    file_path = "docs/runbooks/paymentservice_crash.md"
    with open(file_path, "r") as f:
        content = f.read()
        
    embeddings = list(embedding_model.embed([content]))
    
    point = PointStruct(
        id=1,
        vector=embeddings[0].tolist(),
        payload={
            "filename": os.path.basename(file_path),
            "content": content
        }
    )
    
    client.upsert(
        collection_name=collection_name,
        points=[point]
    )
    print("Successfully ingested runbook.")

if __name__ == "__main__":
    init()
