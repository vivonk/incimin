---
must_haves:
  truths:
    - Async LangGraph event loop does not conflict with Streamlit's main thread event loop.
    - Chat history is persisted in st.session_state across reruns.
    - chaos_inject.py gracefully handles identical sequential operations idempotently.
  artifacts:
    - src/ui/app.py
    - scripts/chaos_inject.py
    - scripts/check_ui.py
  key_links:
    - "[Streamlit UI App](file:///Users/nsarswat/personal/incimin.io/src/ui/app.py)"
    - "[Chaos Injection Script](file:///Users/nsarswat/personal/incimin.io/scripts/chaos_inject.py)"
---

# Phase 4 Plan: UI Integration & Demo Choreography

## Objective
Streamlit chat UI delivers real-time glass-box agent output and chaos injection scripts are deterministic and rehearsed.

## Tasks

### Task 1: Build the Streamlit UI (app.py)
**Description:** Implement the Streamlit frontend that serves as the primary interface for the AI SRE Agent, rendering real-time tool calls and managing session state.
- **files:**
  - `src/ui/app.py`
  - `tests/test_ui.py`
- **action:**
  - Initialize `st.session_state.messages` to store chat history.
  - Implement a synchronous wrapper around the asynchronous LangGraph invocation to prevent event loop collision (`RuntimeError`).
  - Use `st.chat_message` to render the user and agent messages.
  - Use a custom callback handler (or parse LangGraph's streaming events) to render `st.status` expanders for intermediate tool calls (Topology, Telemetry, Knowledge) in real-time.
- **verify:**
  - Launch the UI locally and submit 3+ consecutive queries to verify history persistence and that no async loop errors occur.
- **done:** [ ]

### Task 2: Implement Chaos Injection Script (chaos_inject.py)
**Description:** Build the chaos engineering script used during the demo to simulate an incident in the OTel Astronomy Shop.
- **files:**
  - `scripts/chaos_inject.py`
  - `scripts/check_chaos.py`
- **action:**
  - Create a Python CLI with `argparse` supporting `--mode stop` and `--mode recover`.
  - Target the `paymentservice` Docker container. Use subprocess calls to `docker stop` and `docker start` (or Docker Python SDK).
  - Ensure operations are idempotent (e.g., stopping an already stopped container exits gracefully).
- **verify:**
  - Run `--mode stop` and verify in SigNoz that ERROR logs appear within 30 seconds. Run `--mode recover` and verify recovery.
- **done:** [ ]

### Task 3: Script Memgraph Lab BFS Query
**Description:** Prepare the exact Cypher query the demo operator will run in Memgraph Lab to visually demonstrate the agent's graph traversal.
- **files:**
  - `docs/demo/MEMGRAPH_QUERY.md`
- **action:**
  - Write a markdown file containing the rehearsed `[*BFS]` Cypher query that finds the shortest path between `checkoutservice` and `paymentservice`.
  - Include instructions for the demo operator on how to execute it in the Memgraph Lab UI.
- **verify:**
  - Open Memgraph Lab locally and run the documented query to ensure it successfully renders the correct dependency graph.
- **done:** [ ]
