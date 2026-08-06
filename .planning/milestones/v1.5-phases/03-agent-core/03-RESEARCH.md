# Phase 3: Agent Core - Research

**Goal**: LangGraph state machine with three isolated, tested tools is assembled and guarded against recursion failures

## Implementation Details & Technical Approaches

### 1. State Management (`SREAgentState`)
The core state for LangGraph should be defined as a `TypedDict`. It must include:
- `messages`: A list of LangChain messages, managed using the `add_messages` reducer from `langgraph.graph.message`.
- `remaining_steps`: An integer to track the recursion guard, starting from the maximum allowed steps.

```python
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class SREAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    remaining_steps: int
```

### 2. Recursion Guard (`RemainingSteps`)
LangGraph has a built-in `recursion_limit` parameter during compilation, but hitting it throws an exception (`GraphRecursionError`). To meet the success criteria of a "graceful response", the state machine must enforce the limit internally:
- The main conditional edge (router) will inspect `state["remaining_steps"]`.
- If `state["remaining_steps"] <= 2`, it routes to a special node (e.g., `graceful_exit_node`) instead of back to the LLM.
- The `graceful_exit_node` will append an "insufficient data to determine root cause" message to the state and route to `END`.
- The `remaining_steps` should be decremented on each pass through the LLM node or tool node.

### 3. Tool Isolation & Data Planes
Each tool must strictly access only its respective data plane. The connections and queries were proven in Phase 2 scripts.
1. **`graph_bfs_tool`**:
   - Queries Memgraph using the `neo4j` driver.
   - Executes Cypher: `MATCH path = (s:Service {name: $source})-[*BFS]->(target) RETURN path` or similar based on Phase 2 `TOPO-02`.
2. **`clickhouse_log_tool`**:
   - Connects via `clickhouse_connect`.
   - Queries `signoz_logs.distributed_logs_v2` for ERROR-level logs using `resources_string['service.name']` as established in Phase 2.
3. **`qdrant_runbook_tool`**:
   - Connects via `qdrant_client`.
   - Uses `fastembed` `BAAI/bge-small-en-v1.5` for embedding the user's query and performs `query_points` on the `runbooks` collection.

### 4. LLM Integration
- Use `langchain_anthropic.ChatAnthropic` (Sonnet model).
- The LLM will be bound to the tools: `llm_with_tools = llm.bind_tools(tools)`.
- System prompt for the LLM must explicitly enforce **AGENT-05**: The agent never outputs or suggests remediation actions itself; it only identifies the root cause and retrieves the recommended next steps from the runbook for the human to execute.

### 5. Unit Testing & Mocking
To fulfill **AGENT-06**, `unittest` and `unittest.mock` will be used:
- `@patch` the data plane clients (`clickhouse_connect.get_client`, `neo4j.GraphDatabase.driver`, `QdrantClient`).
- Test happy path (mock returns valid data, tool parses and returns formatted string).
- Test error handling (mock raises exception, tool catches and returns a graceful error string rather than crashing the graph).

## Pre-Planning Checklist
- [x] State schema is clear.
- [x] Mechanism for graceful recursion exit is defined.
- [x] Tool interfaces and boundaries are defined.
- [x] Testing strategy (mocks) is defined.
