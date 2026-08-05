# Phase 3: Agent Core - Context

**Gathered:** 2026-08-05
**Status:** Ready for planning

<domain>
## Phase Boundary

LangGraph state machine with three isolated, tested tools is assembled and guarded against recursion failures

</domain>

<decisions>
## Implementation Decisions

### State Management
- Use `SREAgentState` TypedDict with `add_messages` reducer to track message history and tool invocations.

### Recursion Guard
- Implement a `RemainingSteps` guard that checks `remaining_steps <= 2` in the main router, intercepting and returning a graceful "insufficient data" message to the user rather than throwing an exception.

### Tool Isolation
- Each `@tool` function will be strictly isolated: Topology tool only queries Memgraph, Telemetry tool only queries ClickHouse, and Knowledge tool only queries Qdrant. No shared DB sessions across tools.

### the agent's Discretion
Any further technical implementation details are at the agent's discretion as per the user's request to proceed autonomously without pausing for manual decisions.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- N/A - first agent core phase

### Established Patterns
- LangGraph standard state machine structures
- Pydantic models for structured tool inputs

### Integration Points
- Data plane scripts written in Phase 2

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches as requested by the user.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
