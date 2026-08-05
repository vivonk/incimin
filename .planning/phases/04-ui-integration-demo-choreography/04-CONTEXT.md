# Phase 4: UI Integration & Demo Choreography - Context

**Gathered:** 2026-08-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Streamlit chat UI delivers real-time glass-box agent output and chaos injection scripts are deterministic and rehearsed.

</domain>

<decisions>
## Implementation Decisions

### Streamlit UI 
- Use standard Streamlit chat components (`st.chat_message`, `st.chat_input`) paired with `st.status` for rendering intermediate tool calls in real-time.
- Store session history in `st.session_state` to maintain conversation context across query repaints.

### Chaos Injection
- Implement a standalone Python script `chaos_inject.py` with arguments `--mode stop` and `--mode recover` to target the `paymentservice` container in the existing Docker Compose stack.
- Make the script idempotent (e.g. running stop twice doesn't crash, recovering when already running is a no-op).

### Async Handling
- Ensure LangGraph's async execution is handled correctly within Streamlit's synchronous event loop to prevent `RuntimeError: This event loop is already running`. 

### the agent's Discretion
Any further technical implementation details are at the agent's discretion as per the user's request to proceed autonomously without pausing for manual decisions.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Agent Core from Phase 3

### Established Patterns
- Streamlit's chat elements
- Docker Python SDK (or subprocess calls to `docker compose`) for chaos injection

### Integration Points
- LangChain / LangGraph callback handlers for emitting tool events to the Streamlit UI

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches as requested by the user.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
