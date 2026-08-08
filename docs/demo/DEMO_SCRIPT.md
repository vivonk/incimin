# AI SRE Agent Demo Script

## Preparation

1. Open two windows side-by-side:
   - **Right Window:** Streamlit App (`http://localhost:8501`)
   - **Left Window:** Memgraph Lab (`http://localhost:3000`)
2. Ensure the full Docker Compose stack is running (`docker compose up -d`).
3. Set `ANTHROPIC_API_KEY` in the environment if not already set.

## Execution

1. **Initial Setup:**
   - In Memgraph Lab (Left Window), navigate to the "Query Execution" tab.
   - Paste the following Cypher query to visualize the topology:
     ```cypher
     MATCH path = (s:Service {name: 'frontendservice'})-[*BFS]->(target) RETURN path
     ```
   - Run the query to show the live dependency graph.

2. **Trigger the Incident:**
   - In a terminal, run the chaos injection script:
     ```bash
     python scripts/inject_chaos.py
     ```
   - This script creates a determinist P1 failure (paymentservice crash leading to checkout latency spikes).

3. **Agent Interaction:**
   - In the Streamlit App (Right Window), enter the following prompt:
     `"Checkout latency is spiking. Investigate and give me a recommendation."`
   - Hit **Enter** to submit.

4. **Observe the Agent:**
   - Watch the `st.status` expanders in Streamlit as the agent executes its plan.
   - The agent will autonomously:
     1. Traverse the topology in Memgraph.
     2. Query SigNoz/ClickHouse telemetry for `ERROR` logs related to the affected services.
   - The agent should complete these steps within 60 seconds.

5. **Final Output:**
   - The agent will display a root cause summary (specifically naming `paymentservice`).
   - It will list the supporting topology and telemetry evidence behind that claim.

## Pitfalls Verification Sign-off

The following critical risks have been addressed and validated during development:

- [x] **Port collisions:** All service ports are mapped to avoid conflicts with local developer tools (e.g., ClickHouse on 8123, Memgraph on 7687).
- [x] **Memgraph persistence:** Memgraph volumes are properly mounted, ensuring topology data survives container restarts.
- [x] **Nanosecond timestamps:** ClickHouse queries correctly handle OpenTelemetry's nanosecond timestamp formats in `signoz_logs.distributed_logs_v2`.
- [x] **Recursion guard:** The LangGraph state machine uses a `remaining_steps` limit to prevent infinite loops.
- [x] **Async event loop:** Streamlit's async runtime is properly managed to prevent "event loop is already running" errors when invoking the LangGraph agent.
- [x] **BFS syntax:** The Neo4j driver connects to Memgraph successfully and executes standard `[*BFS]` queries.
- [x] **RAM baseline:** The Docker Compose stack is optimized to run within standard local developer machine constraints (verified memory bounds).
