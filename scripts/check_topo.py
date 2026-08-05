import sys
from gqlalchemy import Memgraph

def main():
    try:
        memgraph = Memgraph(host="127.0.0.1", port=7687)
        # Verify connection
        memgraph.execute_and_fetch("RETURN 1")
        
        print("Checking topology...")
        # Check node count
        nodes = list(memgraph.execute_and_fetch("MATCH (n:Service) RETURN count(n) as count"))
        node_count = nodes[0]['count']
        print(f"Node count: {node_count}")
        
        # Check BFS path from checkout to payment
        bfs_query = """
        MATCH path = (start:Service {name: 'checkout'})-[:DEPENDS_ON *BFS]->(end:Service {name: 'payment'})
        RETURN nodes(path) as path_nodes
        """
        path_results = list(memgraph.execute_and_fetch(bfs_query))
        
        if not path_results:
            print("Failed to find BFS path from checkout to payment")
            sys.exit(1)
            
        path_nodes = path_results[0]['path_nodes']
        names = [node.properties['name'] for node in path_nodes]
        print(f"Found path: {' -> '.join(names)}")
        
        print("Topology check passed.")
    except Exception as e:
        print(f"Error checking topology: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
