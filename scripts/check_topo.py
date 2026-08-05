import sys
import time
from gqlalchemy import Memgraph

def get_memgraph_with_retry(host="127.0.0.1", port=7687, retries=10, delay=2):
    for i in range(retries):
        try:
            memgraph = Memgraph(host=host, port=port)
            memgraph.execute_and_fetch("RETURN 1")
            return memgraph
        except Exception:
            if i < retries - 1:
                print(f"Waiting for Memgraph... ({i+1}/{retries})")
                time.sleep(delay)
            else:
                raise

def main():
    try:
        memgraph = get_memgraph_with_retry(host="127.0.0.1", port=7687)

        
        print("Checking topology...")
        # Check node count
        nodes = list(memgraph.execute_and_fetch("MATCH (n:Service) RETURN count(n) as count"))
        node_count = nodes[0]['count']
        print(f"Node count: {node_count}")
        
        if node_count != 14:
            print(f"Expected 14 nodes, found {node_count}")
            sys.exit(1)
            
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
