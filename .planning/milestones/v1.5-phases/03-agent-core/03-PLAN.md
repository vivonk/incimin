---
phase: 03-agent-core
plan: 01
subsystem: agent
tags: [langgraph, python, llm, tools]
requires:
  - phase: 02-data-plane-initialization
provides:
  - Agent state machine
  - 3 isolated tools
  - Graceful recursion guard
  - Unit tests with mocked clients
affects: []
autonomous: true
---

# Phase 3: Agent Core Plan

## Goal
LangGraph state machine with three isolated, tested tools is assembled and guarded against recursion failures

## Artifacts this phase produces
- `SREAgentState` TypedDict
- `RemainingSteps` guard logic
- `@tool graph_bfs_tool`
- `@tool clickhouse_log_tool`
- `@tool qdrant_runbook_tool`
- `tests/test_agent_tools.py`

## Requirements Covered
AGENT-01, AGENT-02, AGENT-03, AGENT-04, AGENT-05, AGENT-06

## Planner Assumptions (from Specless Probe)
- AGENT-01: unclassified — review manually
- AGENT-02: When two things are exactly equal or just touch, do they merge, collide, or separate?
- AGENT-02: What is the result for empty, single-element, or null input?
- AGENT-02: When elements compare equal, is output order specified and stable?
- AGENT-03: unclassified — review manually
- AGENT-04: unclassified — review manually
- AGENT-05: unclassified — review manually
- AGENT-06: When two things are exactly equal or just touch, do they merge, collide, or separate?
- AGENT-06: What is the result for empty, single-element, or null input?
- AGENT-06: When elements compare equal, is output order specified and stable?

## Tasks

<task>
<description>Implement SREAgentState and basic LangGraph setup</description>
<read_first>
- src/agent/state.py
- .planning/phases/03-agent-core/03-RESEARCH.md
</read_first>
<action>
Create `src/agent/state.py` containing `SREAgentState` TypedDict with `messages` (using `add_messages` reducer) and `remaining_steps` (int).
Create basic `src/agent/graph.py` compiling a `StateGraph` with a dummy LLM node and a router that checks `remaining_steps <= 2` to route to a graceful exit node returning "insufficient data to determine root cause".
Use `langchain-anthropic` `ChatAnthropic` configured for Sonnet.
Set standard system prompt enforcing that the agent only identifies root cause and retrieves next steps, NEVER outputs or suggests remediation actions.
</action>
<acceptance_criteria>
`python -c "from src.agent.state import SREAgentState"` succeeds.
</acceptance_criteria>
</task>

<task>
<description>Implement three isolated data plane tools</description>
<read_first>
- src/agent/tools.py
- scripts/check_tele.py
- scripts/init_qdrant.py
</read_first>
<action>
Create `src/agent/tools.py`.
Implement `@tool graph_bfs_tool(source: str)`: connects via `neo4j` driver, executes BFS query, returns path string.
Implement `@tool clickhouse_log_tool(service_name: str, window_mins: int = 30)`: connects via `clickhouse_connect`, queries `signoz_logs.distributed_logs_v2` for ERROR logs.
Implement `@tool qdrant_runbook_tool(query: str)`: connects via `QdrantClient`, embeds query with `fastembed`, searches `runbooks` collection.
Each tool must handle connection logic independently.
</action>
<acceptance_criteria>
`python -c "from src.agent.tools import graph_bfs_tool, clickhouse_log_tool, qdrant_runbook_tool"` succeeds.
</acceptance_criteria>
</task>

<task>
<description>Unit tests with mocked clients</description>
<read_first>
- tests/test_agent_tools.py
- src/agent/tools.py
</read_first>
<action>
Create `tests/test_agent_tools.py`.
Write `unittest.TestCase` class testing `graph_bfs_tool`, `clickhouse_log_tool`, and `qdrant_runbook_tool`.
Use `@patch` to mock `neo4j.GraphDatabase.driver`, `clickhouse_connect.get_client`, and `qdrant_client.QdrantClient`.
For each tool, test the happy path (mock returns data -> tool formats correctly) and error path (mock raises Exception -> tool returns graceful error string).
</action>
<acceptance_criteria>
`python -m unittest tests/test_agent_tools.py` exits 0.
</acceptance_criteria>
</task>

<task>
<description>Assemble and bind tools to LangGraph</description>
<read_first>
- src/agent/graph.py
- src/agent/tools.py
</read_first>
<action>
Update `src/agent/graph.py` to bind the three tools to the `ChatAnthropic` LLM instance using `llm.bind_tools()`.
Add the `ToolNode` to the graph for executing tool calls.
Compile the graph and ensure it exports the runnable `app` or `agent`.
</action>
<acceptance_criteria>
`python -c "from src.agent.graph import app"` succeeds without errors.
</acceptance_criteria>
</task>

## must_haves
truths:
- StateGraph runs end-to-end against live data without hitting recursion limit
- RemainingSteps guard routes to a graceful response when remaining_steps <= 2
- Each of the three tools executes in isolation and touches exactly one data plane
- All three tools pass unit tests with mock clients
prohibitions:
