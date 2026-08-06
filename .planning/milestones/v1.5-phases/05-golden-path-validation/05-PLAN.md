---
must_haves:
  truths:
    - End-to-end prompt processing time is under 60 seconds.
    - The demo steps are fully documented and rehearsed.
  artifacts:
    - scripts/verify_golden_path.py
    - docs/demo/DEMO_SCRIPT.md
  key_links:
    - "[E2E Verification Script](file:///Users/nsarswat/personal/incimin.io/scripts/verify_golden_path.py)"
---

# Phase 5 Plan: Golden Path Validation

## Objective
The full demo scenario runs end-to-end, deterministically, within the 60-second SLA, with all known pitfalls verified closed.

## Tasks

### Task 1: Create Golden Path Test Script
**Description:** Automate the end-to-end performance and correctness test of the agent for the specific demo scenario.
- **files:**
  - `scripts/verify_golden_path.py`
- **action:**
  - Write a Python script that submits the query "Checkout latency is spiking. Investigate and give me a recommendation." to the agent directly (bypassing Streamlit).
  - Assert that the response contains references to `paymentservice`, the retrieved runbook, and a recommendation.
  - Assert that the total execution time is under 60 seconds.
- **verify:**
  - Run `python scripts/verify_golden_path.py` and ensure it passes within the SLA.
- **done:** [ ]

### Task 2: Write Demo Script and Pitfalls Sign-off
**Description:** Finalize the demo choreography instructions and verify PITFALLS.md is closed.
- **files:**
  - `docs/demo/DEMO_SCRIPT.md`
- **action:**
  - Write the step-by-step instructions for the split-screen demo (running the Streamlit app on the right, opening Memgraph Lab on the left, pasting the BFS query, running the chaos script).
  - Add a checklist verifying that all PITFALLS.md items (port collisions, Memgraph persistence, nanosecond timestamps, recursion guard, async event loop, BFS syntax, RAM baseline) have been addressed in earlier phases.
- **verify:**
  - Review the documentation for clarity and completeness.
- **done:** [ ]
