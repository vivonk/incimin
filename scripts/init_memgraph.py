import sys
from gqlalchemy import Memgraph

def main():
    try:
        memgraph = Memgraph(host="127.0.0.1", port=7687)
        # Ensure connection works
        memgraph.execute_and_fetch("RETURN 1")
        
        print("Seeding Memgraph with full 14-node OTel Astronomy Shop graph...")
        
        # Idempotent seed using MERGE
        nodes = [
            "frontend", "checkout", "payment", "cart", "currency",
            "email", "product-catalog", "recommendation", "shipping",
            "quote", "ad", "image-provider", "astronomy-db", "valkey-cart"
        ]
        
        edges = [
            ("frontend", "ad"),
            ("frontend", "cart"),
            ("frontend", "checkout"),
            ("frontend", "currency"),
            ("frontend", "image-provider"),
            ("frontend", "product-catalog"),
            ("frontend", "quote"),
            ("frontend", "recommendation"),
            ("frontend", "shipping"),
            ("checkout", "cart"),
            ("checkout", "currency"),
            ("checkout", "email"),
            ("checkout", "payment"),
            ("checkout", "product-catalog"),
            ("checkout", "shipping"),
            ("product-catalog", "astronomy-db"),
            ("cart", "valkey-cart"),
            ("recommendation", "product-catalog"),
            ("shipping", "quote"),
        ]
        
        # Merge nodes
        for node in nodes:
            memgraph.execute(f"MERGE (:Service {{name: '{node}'}})")
            
        # Merge edges
        for src, dst in edges:
            query = f"""
            MATCH (s:Service {{name: '{src}'}})
            MATCH (d:Service {{name: '{dst}'}})
            MERGE (s)-[:DEPENDS_ON]->(d)
            """
            memgraph.execute(query)
            
        print("Successfully seeded full graph.")
    except Exception as e:
        print(f"Error connecting or seeding Memgraph: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
