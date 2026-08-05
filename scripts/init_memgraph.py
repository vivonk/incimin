import sys
from gqlalchemy import Memgraph

def main():
    try:
        memgraph = Memgraph(host="127.0.0.1", port=7687)
        # Ensure connection works
        memgraph.execute_and_fetch("RETURN 1")
        
        print("Seeding Memgraph with minimal graph...")
        # Idempotent seed using MERGE
        query = """
        MERGE (c:Service {name: 'checkout'})
        MERGE (p:Service {name: 'payment'})
        MERGE (c)-[:DEPENDS_ON]->(p)
        """
        memgraph.execute(query)
        print("Successfully seeded minimal graph.")
    except Exception as e:
        print(f"Error connecting or seeding Memgraph: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
