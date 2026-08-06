# Phase 08: Core Abstraction Layer and Plugin Registry - Context

**Gathered:** 2026-08-06
**Status:** Ready for planning

<domain>
## Phase Boundary
Core Abstraction Layer and Plugin Registry - Implementing the ABC and internal plugin manager.
</domain>

<decisions>
## Implementation Decisions

### Plugin Loading
- Explicit Mapping (`PLUGINS = {'signoz': SigNozPlugin}`) — Simple, secure, and traceable.

### TopologyPlugin ABC
- AsyncIterator (`AsyncIterator[ServiceNode | ServiceEdge]`) — Streams items for efficiency and low memory.

### Plugin Config
- Pydantic `BaseSettings` — Strongly typed config via environment variables per plugin.
</decisions>

<code_context>
## Existing Code Insights
- Pydantic models from Phase 07.
</code_context>

<specifics>
## Specific Ideas
No specific requirements — open to standard approaches
</specifics>

<deferred>
## Deferred Ideas
None — discussion stayed within phase scope
</deferred>
