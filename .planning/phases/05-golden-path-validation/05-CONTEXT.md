# Phase 5: Golden Path Validation - Context

**Gathered:** 2026-08-05
**Status:** Ready for planning

<domain>
## Phase Boundary

The full demo scenario runs end-to-end, deterministically, within the 60-second SLA, with all known pitfalls verified closed.

</domain>

<decisions>
## Implementation Decisions

### End-to-End Test
- Create an automated end-to-end test script `scripts/verify_golden_path.py` that verifies the "Checkout latency is spiking" query produces the expected root cause, runbook, and recommendation within the 60-second SLA.
- Verify all checklist items in PITFALLS.md programmatically or through documentation sign-off.

### Demo Rehearsal Documentation
- Create a `docs/demo/DEMO_SCRIPT.md` that outlines the exact steps to perform the split-screen demo (Streamlit + Memgraph Lab).

### the agent's Discretion
Any further technical implementation details are at the agent's discretion as per the user's request to proceed autonomously without pausing for manual decisions.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/ui/app.py`
- `scripts/verify_data_planes.py`

### Established Patterns
- Streamlit application structure
- End-to-end testing of LangGraph workflows

### Integration Points
- Connecting the LangGraph core agent end-to-end with the data planes for final validation.

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches as requested by the user.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>
