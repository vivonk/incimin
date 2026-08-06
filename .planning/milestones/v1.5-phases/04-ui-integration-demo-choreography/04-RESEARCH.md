# Phase 04: UI Integration & Demo Choreography - Research

**Goal**: Implement a Streamlit chat UI that renders agent tool calls in real-time and create deterministic chaos injection scripts for demo choreography.

## What do I need to know to PLAN this phase well?

### 1. The Async Streamlit Constraint
Streamlit's execution model is fundamentally synchronous and repaints the entire app from top to bottom. LangGraph workflows often rely on asynchronous tool execution. 
- **Requirement UI-01** explicitly states: *Use synchronous `graph.stream(stream_mode="updates")` (not `.astream()`)*.
- **Why?** To prevent `RuntimeError: This event loop is already running` within Streamlit. The agent execution loop must block and yield tool execution states progressively without entering async event loop conflicts.

### 2. Glass-box UI Rendering 
- **Requirement UI-02** requires each tool call to be rendered as a `st.status` expander showing the tool name, input parameters, and raw output. 
- **How it affects planning:** We need to capture the chunked outputs from `graph.stream` and map intermediate states (when a tool is called vs. when it finishes) to `st.status`. We must store these interactions in `st.session_state` alongside standard user/assistant messages so they persist across Streamlit re-renders.

### 3. Session State Persistence
- **Requirement UI-03 and UI-04** require chat history persistence and robustness against consecutive queries.
- **How it affects planning:** We must define a message schema for `st.session_state.messages` that supports not just text but also tool invocations and their results. When Streamlit repaints, it needs to render the history exactly as it was, including re-rendering `st.status` elements for historical tool calls.

### 4. Chaos Injection Mechanics
- **Requirements CHAOS-01 to CHAOS-04** dictate building `chaos_inject.py`.
- **Targets:** `paymentservice`
- **Modes:** `--mode stop`, `--mode latency` (via toxiproxy), and `--recover`.
- **How it affects planning:** We need to interact with the local Docker Compose environment. We can use the Docker Python SDK (`docker` library) or standard `subprocess` calls to `docker compose`. The script must be idempotent (e.g., stopping an already stopped container shouldn't error out). We need to verify if `toxiproxy` is available in the stack or if we need to implement latency injection differently (e.g., via Docker network tools).

## Suggested Plan Outline for this Phase
When planning, the breakdown should be structured as follows:

1. **Plan 1: Chaos Injection Tool (`chaos_inject.py`)**
   - Implement idempotent CLI script to stop/recover the `paymentservice` container using `subprocess` or `docker` Python SDK.
   - Implement network latency injection (verifying toxiproxy integration).

2. **Plan 2: Streamlit Session State & History Foundation**
   - Set up `app.py` with `st.session_state.messages` structure.
   - Build rendering functions that handle standard text and mocked tool calls using `st.status`.

3. **Plan 3: LangGraph Integration (The tricky part)**
   - Wire `graph.stream(stream_mode="updates")` into the Streamlit input handler.
   - Parse the `stream` output events, updating the live `st.status` components as tools start and complete.
   - Append the final agent response to `st.session_state`.
