# Memgraph Lab Demo Query

During the demo, we will use Memgraph Lab to visualize the topology of the Astronomy Shop and demonstrate the Breadth-First Search (BFS) capability of Memgraph to find the shortest path between `checkoutservice` and `paymentservice`.

## Prerequisites

1. Ensure the Memgraph container is running.
2. Open Memgraph Lab in your browser (usually at `http://localhost:3000`).
3. Connect to the local Memgraph instance.

## The Query

In the **Query Execution** tab of Memgraph Lab, paste the following Cypher query:

```cypher
MATCH path = (start:Service {name: 'checkoutservice'})-[*BFS]->(end:Service {name: 'paymentservice'})
RETURN path;
```

## Instructions for the Demo Operator

1. **Paste the Query**: Copy the Cypher query above.
2. **Execute**: Click the **Run** button (or press `Ctrl+Enter` / `Cmd+Enter`).
3. **Visualize**: 
   - By default, Memgraph Lab will show the results in the "Data" view or "Graph" view.
   - Switch to the **Graph** view if not already selected.
   - You will see the nodes `checkoutservice` and `paymentservice` connected by the relationships representing the shortest path through the architecture.
4. **Explain**: Highlight to the audience how the agent uses this exact capability under the hood (via the `graph_bfs_tool`) to quickly understand the impact radius of a failing service.
