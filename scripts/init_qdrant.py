import os
import glob
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
from fastembed import TextEmbedding

def init():
    client = QdrantClient("http://127.0.0.1:6333", timeout=5.0)
    collection_name = "runbooks"
    
    embedding_model = TextEmbedding("BAAI/bge-small-en-v1.5")
    
    try:
        collections = client.get_collections().collections
        exists = any(c.name == collection_name for c in collections)
    except Exception:
        exists = False
        
    if not exists:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
    
    md_files = glob.glob("docs/runbooks/*.md")
    points = []
    
    for i, file_path in enumerate(md_files):
        with open(file_path, "r") as f:
            content = f.read()
            
        embeddings = list(embedding_model.embed([content]))
        
        point = PointStruct(
            id=i+1,
            vector=embeddings[0].tolist(),
            payload={
                "filename": os.path.basename(file_path),
                "content": content
            }
        )
        points.append(point)
    
    client.upsert(
        collection_name=collection_name,
        points=points
    )
    print(f"Successfully ingested {len(points)} runbooks.")

if __name__ == "__main__":
    init()
