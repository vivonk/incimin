# Feature Research

<<<<<<< Updated upstream
**Domain:** Incident/alert-triage dashboard for an autonomous SRE agent (v1.7 milestone)
**Researched:** 2026-08-08
**Confidence:** MEDIUM (web search across official vendor docs — PagerDuty, incident.io, Grafana OnCall, AWS SSM, StackStorm, Temporal, Airflow, n8n, Langfuse, LangGraph — cross-checked but not primary-source verified against source code)

## Scope Note

This is **not** a general-purpose incident-management platform (PagerDuty/Opsgenie replacement). It is a dashboard over a *single autonomous agent's* execution against SigNoz-sourced alerts, for a single-org demo-scale deployment. Findings below are filtered through that lens: patterns from PagerDuty/incident.io/StackStorm/Airflow/etc. are surveyed for the *behavior SRE users expect*, then re-scoped to what actually matters at this project's scale. Full platform features (on-call scheduling, multi-tenant orgs, escalation paging infra) are explicitly anti-features here — see below.

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Alert list with status column, clear vocabulary | Every surveyed tool (PagerDuty, Grafana OnCall, incident.io) leads with a status column; SRE users scan for "what's still open" first | LOW | Postgres status column already decided (PROJECT.md). Recommend an agent-lifecycle vocabulary, not a human-response vocabulary — see Lifecycle section below |
| Severity indicator with color coding (red=critical/SEV1, yellow/orange=major/SEV2) | Universal convention across PagerDuty, incident.io, and general SRE practice; responders triage by color before reading text | LOW | SigNoz alert rules already carry a severity field on the webhook payload — surface it, don't invent a new taxonomy |
| Timestamps: created, last-updated, duration in current status | PagerDuty tracks "Created"; incident.io stamps every status transition (e.g. "Fixed At"); postmortem research shows responders need phase durations, not just a single timestamp | LOW | Derivable from the audit/event table already required for HITL |
| Service/source attribution per alert | PagerDuty's alert table always shows Source/Service/Component; responders need to know blast radius at a glance | LOW | Already available from SigNoz webhook metadata |
| Filterable/sortable list (by status, severity, service) | Baseline list hygiene in every tool surveyed; without it a growing alert list becomes unusable within days | LOW–MEDIUM | Trivial with Postgres-backed list + basic query params; no search engine needed at this scale |
| Per-alert detail view with distinct sections for findings vs. raw data | incident.io and PagerDuty both separate "what we know" from "raw event data"; matches the project's own planned Findings/Next Steps/Step Graph/Raw tabs | LOW | Already scoped in PROJECT.md's target features |
| Explicit "agent is running" / in-progress state, distinguishable from terminal states | Airflow (`running`), Temporal (in-flight event), n8n (`Running` execution status) all treat "in progress" as a first-class, visually distinct state — not a placeholder | LOW | Needed so the SSE-driven live UI has something meaningful to render before terminal state arrives |
| Chronological event/audit timeline per alert ("who/what did what, when") | Universal expectation confirmed across PagerDuty postmortem guidance, Grafana OnCall's `AlertGroupLogRecord`, and incident.io — responders reconstruct events from an ordered log, not from status alone | LOW–MEDIUM | Directly required by the project's own decision to write "every proposal, decision, and result" to an audit table |
| Approval action showing: proposed action, target, and rationale, before a human can approve | AWS SSM `aws:approve`, StackStorm `core.ask`, and LangGraph's `interrupt()` HITL pattern all agree: an approval gate is worthless if it doesn't show *what* is about to happen and *why* before the click | LOW–MEDIUM | Directly enabled by `interrupt()` + `AsyncPostgresSaver`, already a v1.7 decision. The "why" is the agent's own synthesized root-cause reasoning — no new capability needed, just surfacing it |
| Post-approval audit record: who approved/rejected, when, and the outcome | AWS SSM requires named approvers and timestamps by design; PagerDuty/incident.io timelines both treat approval-equivalent actions (ack, resolve) as audit events | LOW | Same audit table as above; add actor identity + decision + timestamp columns |
| Step-by-step visualization of the agent's fixed node sequence, with per-node status (pending/running/done/failed) | Direct analog to Airflow's Graph View and Temporal's Timeline view — both are considered baseline, not exotic, for any multi-step automated workflow | MEDIUM | Requires the agent to emit structured step events over SSE; graph topology itself is static (defined in code), so this is a *status overlay* on a fixed diagram, not a general graph renderer |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| First-class "paused, awaiting human approval" status in the alert lifecycle | None of PagerDuty/Opsgenie/incident.io model this — their state machines assume a *human* is the actor (triggered→acknowledged→resolved). This project's core novelty is an autonomous agent that pauses itself; making that pause a visible, named status (not just a UI spinner) is a genuine product differentiator that directly demonstrates the "human-in-the-loop" value proposition to the enterprise buyer | LOW–MEDIUM | Builds directly on the `interrupt()`/`AsyncPostgresSaver` decision already made; this is mostly a modeling/UX decision, not new infrastructure |
| Live SSE-driven step graph tied to the *actual* running agent (not polling, not a static diagram) | Matches what LangGraph Studio and Langfuse do for developer-facing agent debugging, but exposed to an SRE end user as *product* rather than a dev tool — this is close to the frontier of what any competitor in this exact space is currently shipping | MEDIUM | Depends on SSE plumbing (already planned) and an agent event schema; keep the graph itself fixed/static (see anti-features) to avoid Airflow/n8n-style complexity |
| Inline agent-authored root-cause narrative + recommended-next-step surfaced directly at the approval decision point | Off-the-shelf approval gates (SSM, StackStorm) show only *what* will run, not *why it's the right call* — this project's agent already produces that reasoning as its core value; surfacing it at the exact moment of highest attention (the approval click) makes the gate meaningfully more informative than any surveyed tool's equivalent | LOW | The reasoning already exists as agent output; this is a presentation decision, not new agent capability |
| Deterministic replay of a full historical run (fixture-driven), viewable start to finish exactly as it happened live | This is close to Temporal's/LangGraph Studio's "time travel" idea but scoped down to demo reliability rather than general debugging — valuable for enterprise demos where the story must replay identically every time | LOW–MEDIUM | Already explicitly scoped in PROJECT.md ("Replay script driving a committed SigNoz fixture end to end"); reuses the same SSE event schema as the live path, so it's mostly a data-source swap, not new UI |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Alert grouping/deduplication engine (Grafana OnCall–style Alert Groups with grouping-ID templates) | "Feels incomplete without it" once you've seen PagerDuty/OnCall bundle related alerts | Grouping logic is a project in itself (templated grouping IDs, merge/split UX, group-level state machine); at demo scale, one SigNoz webhook alert maps to one agent run — there is nothing to group yet | One alert row = one agent run row. Revisit only if/when multiple alerts routinely fire for the same root cause |
| On-call scheduling, escalation policies with paging (SMS/phone/push), and ack-timeout auto-re-escalation | PagerDuty's core value prop; feels like "the missing piece" next to a status column | This is an entire second product (rotation calendars, notification delivery infra, timeout timers) with zero overlap with the agent's actual job — root cause + remediation, not who gets paged | The agent's own "escalation" action *is* the allowlisted remediation-adjacent action already in scope (v1.7 Key Decisions) — it stops at "flag for human," it doesn't need to own paging infrastructure |
| Multi-approver quorum / approval delegation (AWS SSM's N-of-M approvers, notification routing via SNS) | Looks more "enterprise-grade" | Massively over-engineered for a single-org, 2–3-engineer demo; adds identity/notification infrastructure with no current user story | Single named approver clicks Approve/Reject in the SPA; the audit row already captures who/when — that satisfies the stated security/audit rationale in PROJECT.md's Key Decisions without building a quorum system |
| Full postmortem/retrospective authoring tool (Rootly/incident.io-style collaborative doc editor, templates, blameless-review workflow) | Adjacent and "obviously good practice" | A document editor and review workflow is unrelated to the agent's execution and is a multi-week feature on its own | The chronological audit/event timeline already table-stakes above *is* the raw material for a human-written postmortem later — don't build the authoring surface |
| Graph *authoring* UI — drag nodes, edit edges, build new workflows visually (n8n, Airflow DAG editors, StackStorm workflow definitions) | Once you're rendering a step graph, "let me edit it" feels like a natural next step | The agent's graph topology is defined in code (LangGraph `StateGraph`), and PROJECT.md's own constraint says tool/topology changes must not require rewriting the state machine casually — a visual editor implies runtime-mutable topology, which reintroduces exactly the non-determinism the project explicitly forbids | Step graph is read-only: a fixed diagram (from the compiled graph) with a live status overlay per node. No editing capability |
| Full "time travel" debugging — fork execution from an arbitrary historical checkpoint and re-run (LangGraph Studio's flagship feature) | Genuinely useful for agent development, and it's right there in the tooling already in the stack (`AsyncPostgresSaver` checkpoints make it *possible*) | It's a developer/debugging capability, not something the target SRE end user needs during a live incident; building fork-and-resume UI is materially more work than a linear replay | Ship the linear replay script (already scoped) for demo determinism; defer checkpoint-forking UI to a future internal-tooling milestone, not this one |
| Nested/expandable trace-tree rendering with aggregate vs. expanded toggle (Langfuse-style, needed when agents have deep/looping tool-call trees) | Langfuse is the closest analog tool in the existing stack decisions (Langfuse is already used for tracing per recent commits) | This agent has a shallow, fixed depth of tool calls (3 deterministic tools + synthesis + verifier) — building a generalized collapsible nested-span tree is solving a problem this agent doesn't have | A flat, ordered step list is sufficient; reserve Langfuse itself (already integrated for tracing) as the place to go deep on LLM-call-level nesting if ever needed — don't duplicate that in the dashboard |
| Customizable/configurable incident status lifecycle (incident.io lets orgs redefine triage/active/post-incident stages) | Feels "flexible," "enterprise-ready" | There is one agent, one fixed set of phases it goes through — configurability solves a multi-team/multi-workflow problem this single-agent product doesn't have | Hardcode the status enum (see Lifecycle Modeling below); revisit only if a second distinct agent/workflow type is added |
| Real-time collaborative multi-user presence (cursors, "so-and-so is viewing this incident") | Feels modern, matches Slack-integrated tools like incident.io | Significant added complexity (presence channels, conflict resolution) for a 2–3-person demo audience where only one person will realistically click Approve | SSE for status/data updates is enough; no presence layer needed |

## Incident Lifecycle / Status Modeling (Detail)

Table-stakes status transitions, informed by the PagerDuty/incident.io comparison, re-scoped for an agent-driven (not human-driven) lifecycle:

```
Received          — webhook ingested, persisted, agent run enqueued
  └─> Investigating   — agent traversing graph / querying logs (mirrors PagerDuty "Triggered" energy, but the *actor* is the agent, not a waiting human)
        └─> Awaiting Approval  — interrupt() fired; a remediation or escalation action is proposed and durable via AsyncPostgresSaver
              ├─> Approved -> Executing -> Resolved   (allowlisted action ran; verifier confirms)
              ├─> Rejected -> Investigating|Closed     (human declines; agent may re-propose or end)
              └─> (timeout/abandoned -> stays Awaiting Approval; no auto-escalation timers — explicitly deferred, see anti-features)
        └─> Resolved (no action needed — findings-only outcome)
  └─> Closed         — terminal, whether resolved, rejected-and-abandoned, or errored
```

**Why this differs from PagerDuty/incident.io:** those tools' vocabularies (triggered/acknowledged/resolved; declared/investigating/fixing/monitoring/closed) assume the *responder* is a human doing the work and the tool is tracking their progress. Here the agent is the actor for Investigating; the human only enters at Awaiting Approval. Reusing PagerDuty's "Acknowledged" would be misleading — nobody has acknowledged anything, an *agent* is investigating. Naming the mid-run states accurately is what makes this product's dashboard demonstrate its actual value rather than mimicking a paging tool it isn't.

**Dependency:** requires the Postgres status column (already decided) and the `interrupt()`/checkpointer plumbing (already decided) — no net-new infrastructure, this is a status-enum and UI-label decision.
=======
**Domain:** Python Plugin Architecture for Service Topology Integration
**Researched:** 2026-08-06
**Confidence:** HIGH

## Python Plugin Architectures: Expected Behavior

Typically in Python, plugin architectures are implemented via one of three patterns:

1. **Object-Oriented ABCs + Registry (Simple & Internal):** Define a base class (`abc.ABC`) and a registry dictionary. Plugins inherit from the base class and register themselves upon import.
2. `pluggy` **(Event-driven):** The pytest plugin system. Great for hook-based architectures where multiple plugins respond to the same event.
3. `setuptools entry_points` **(Third-party):** Allows external pip packages to register plugins for a core package.

**Expected Approach for Our App:** For a single-org enterprise deployment where plugins are maintained internally, **Pattern 1 (ABCs + Simple Registry)** is the expected behavior. It keeps complexity low, enforces strict contracts via abstract methods, and integrates easily into our LangGraph state machine.

## Feature Landscape



### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.


| Feature                                    | Why Expected                                                                 | Complexity | Notes                                                                                                                                        |
| ------------------------------------------ | ---------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| **Core Abstraction Layer (ABC)**           | Ensures standard interaction and outputs across all providers.               | LOW        | Implement `TopologyProvider` interface with methods like `fetch_topology()`.                                                                 |
| **Standardized Topology Data Model**       | Downstream consumers (Memgraph ingestion) need a consistent internal schema. | MEDIUM     | **CRITICAL:** Must include metadata fields `source`, `external_id`, `fetched_at`, and `schema_version` as per the Entity Metadata Principle. |
| **Dynamic Plugin Registry**                | Ability to dynamically load plugins via configuration.                       | LOW        | Use a simple dictionary registry or `importlib` to discover internal plugins.                                                                |
| **SigNoz Plugin (**`SigNozServiceMap`**)** | Need at least one working plugin to prove the architecture.                  | MEDIUM     | The first implementation. Will parse SigNoz API output into the standardized core format.                                                    |




### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.


| Feature                      | Value Proposition                                                                         | Complexity | Notes                                                                                                 |
| ---------------------------- | ----------------------------------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------------- |
| **Plugin Failure Isolation** | If a provider's API times out, the core system falls back gracefully instead of crashing. | HIGH       | Implement circuit breakers and strict timeout wrappers around plugin execution.                       |
| **Dual Identity Provenance** | Complete traceability for auditability and debugging.                                     | MEDIUM     | Retain both `external_id` (from provider) and internal ID. Aligns with backend metadata requirements. |




### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.


| Feature                                            | Why Requested                                                         | Why Problematic                                                                         | Alternative                                                                               |
| -------------------------------------------------- | --------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| **Automated Dependency Inference (LLM)**           | "Smart" topology generation when provider data is fuzzy.              | Introduces hallucination risk in the critical path, violating architecture constraints. | Strict Cypher BFS traversal on raw, deterministic dependency data provided by the plugin. |
| **External Plugin Ecosystem (**`entry_points`**)** | Allowing third-party devs to write custom pip packages for the agent. | Over-engineered for a single-org deployment; adds security and maintenance overhead.    | Keep plugins internal to the repository using a simple module registry.                   |



>>>>>>> Stashed changes

## Feature Dependencies

```
<<<<<<< Updated upstream
Alert persistence (Postgres, SigNoz metadata) [existing v1.7 scope]
    └──requires──> Alert list with status/severity/timestamps        [table stakes]
                       └──enhances──> Filter/sort on list             [table stakes]

SSE event stream from agent run [existing v1.7 scope: FastAPI + SSE]
    └──requires──> Live step graph with per-node status               [table stakes]
    └──requires──> Live status updates on alert list (no polling)     [differentiator]

interrupt() + AsyncPostgresSaver [existing v1.7 decision]
    └──requires──> Approval gate UI (proposed action + rationale)     [table stakes]
                       └──requires──> Audit row on decision (who/when/outcome) [table stakes]
                       └──enhances──> Inline root-cause narrative at approval [differentiator]

Audit/event table [existing v1.7 decision: "every proposal, decision, result"]
    └──requires──> Chronological timeline per alert                   [table stakes]

Fixed committed SigNoz fixture [existing v1.7 scope]
    └──requires──> Replay script over same SSE event schema           [differentiator]

Live step graph ──conflicts──> Graph authoring/editing UI (n8n/Airflow-style)
Approval gate (single approver) ──conflicts──> Multi-approver quorum (SSM-style)
Agent-lifecycle status enum ──conflicts──> Configurable/custom status lifecycle (incident.io-style)
=======
[Core Abstraction Layer]
    └──requires──> [Standardized Topology Data Model]

[SigNoz Plugin]
    └──requires──> [Core Abstraction Layer]
    └──requires──> [Existing SigNoz Webhook Infrastructure]

[Plugin Registry]
    └──requires──> [Core Abstraction Layer]
>>>>>>> Stashed changes
```



### Dependency Notes

<<<<<<< Updated upstream
- **Live step graph requires SSE event stream:** the graph is only "live" if the agent emits structured per-node start/end/error events as it runs; this is new work on the agent side (event emission), not just the frontend — flag for phase planning as agent-side instrumentation, not purely a UI task.
- **Approval gate requires `interrupt()` + `AsyncPostgresSaver`:** already decided in PROJECT.md; the dashboard work is additive UI/audit on top of durable HITL infrastructure, not a new mechanism.
- **Timeline requires the audit table:** don't build a separate "activity log" data model — the audit table already mandated for approvals should be the single source for the timeline view too (avoid two overlapping event stores).
- **Live step graph conflicts with graph-authoring UI:** deliberately keep the graph read-only; this is a scope boundary, not a missing feature — call it out explicitly if a stakeholder asks for "editable" workflows.

## MVP Definition

### Launch With (v1.7)

Minimum viable product for this milestone — what's needed to demonstrate the core "durable, observable, human-gated" value proposition.

- [ ] Alert list: status, severity, service, timestamps, sortable/filterable — table stakes, LOW complexity, depends only on existing Postgres persistence
- [ ] Agent-lifecycle status enum (Received/Investigating/Awaiting Approval/Approved/Rejected/Executing/Resolved/Closed) — table stakes + differentiator, LOW complexity
- [ ] Per-alert detail view: Findings / Next Steps / Step Graph / Raw tabs (already scoped) — table stakes, LOW–MEDIUM
- [ ] Live step graph with per-node status via SSE — table stakes, MEDIUM complexity, requires agent-side event emission
- [ ] Approval gate: proposed action + rationale + approve/reject, single approver — table stakes, LOW–MEDIUM, built on existing `interrupt()` decision
- [ ] Audit table + chronological timeline view per alert — table stakes, LOW–MEDIUM
- [ ] Replay script against committed SigNoz fixture, driving the same SSE/UI path — differentiator, LOW–MEDIUM, already scoped

### Add After Validation (v1.x)

- [ ] Live status updates without manual refresh (confirm SSE is snappy/reliable in practice before treating as done) — trigger: SSE plumbing proven stable under the replay + one live path
- [ ] Richer inline root-cause narrative styling at the approval decision point (currently just "surface existing agent output") — trigger: UX feedback from first demo audience

### Future Consideration (v2+)

- [ ] Alert grouping/deduplication — defer until multiple concurrent alerts for the same root cause is an observed real scenario, not hypothetical
- [ ] Checkpoint-fork/time-travel debugging UI — defer to an internal-tooling milestone; valuable for agent development, not for the SRE end-user demo
- [ ] Configurable status lifecycle — defer until a second distinct agent/workflow type exists
- [ ] On-call scheduling / paging integration — defer indefinitely; this is a different product (or an integration point with PagerDuty/Opsgenie, not a rebuild of them)

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Alert list (status/severity/timestamps) | HIGH | LOW | P1 |
| Agent-lifecycle status enum incl. "Awaiting Approval" | HIGH | LOW | P1 |
| Approval gate UI + audit record | HIGH | MEDIUM | P1 |
| Live step graph (SSE-driven) | HIGH | MEDIUM | P1 |
| Chronological audit timeline | MEDIUM–HIGH | LOW–MEDIUM | P1 |
| Replay script over fixture | HIGH (demo reliability) | LOW–MEDIUM | P1 |
| Inline root-cause narrative at approval | MEDIUM | LOW | P2 |
| Alert grouping/dedup | LOW (no current scenario) | HIGH | P3 |
| Checkpoint fork/time-travel UI | LOW (dev tool, not SRE-user need) | HIGH | P3 |
| Multi-approver quorum | LOW (single-org, small team) | MEDIUM–HIGH | P3 |
| Graph authoring/editing UI | NEGATIVE (violates determinism constraint) | HIGH | Do not build |

**Priority key:**
- P1: Must have for v1.7 launch
- P2: Should have, add when possible within v1.7 if time allows
- P3: Nice to have, explicitly deferred past v1.7

## Competitor/Analog Feature Analysis

| Feature | PagerDuty / incident.io | Airflow / Temporal / n8n | LangGraph Studio / Langfuse | This Project's Approach |
|---------|--------------------------|----------------------------|-------------------------------|--------------------------|
| Status vocabulary | Human-response-centric (triggered/acknowledged/resolved; declared/investigating/fixing/monitoring/closed) | Task-execution-centric (queued/running/success/failed/retry) | Run-centric (node visited/not, checkpoint states) | Hybrid: agent-execution states (Investigating/Executing) + a first-class human-gate state (Awaiting Approval) not present in either source family |
| Severity/priority | Explicit severity field, color-coded (red/yellow), drives escalation policy | Not applicable (pipeline tasks don't have "severity") | Not applicable | Surface SigNoz's own severity field directly, color-coded; no escalation-policy engine behind it |
| Step/workflow visualization | Not applicable (no execution graph) | Full graph view, click-through metadata, per-run state history | Live animated diagram, state diffs, time-travel replay | Fixed/static graph diagram (from compiled LangGraph) with live SSE status overlay — table-stakes visualization without authoring or time-travel |
| Human approval | Ack/resolve is the closest analog, but it's acknowledging a page, not approving a specific automated action | StackStorm has native `core.ask`; Rundeck notably lacks native approval (feature request territory); AWS SSM has formal N-of-M `aws:approve` | LangGraph's `interrupt()` is the exact mechanism already adopted by this project | Single-approver, rationale-forward approval gate — closer to SSM's formality (named actor, audit record) but without quorum overhead |
| Timeline/audit | Structured, timestamped, drives postmortems | Event history (Temporal) / task run history (Airflow) — technical, not narrative | Trace tree, technical | One audit table serving both the approval record and the human-readable timeline — narrower scope than PagerDuty's full postmortem tooling, but same underlying expectation (who/what/when) |

## Sources

- PagerDuty: Alerts Table, Navigate the Incidents Page, Incidents, Escalation Policy Basics — https://support.pagerduty.com/main/docs/alerts-table, https://support.pagerduty.com/main/docs/navigate-the-incidents-page, https://support.pagerduty.com/main/docs/incidents, https://support.pagerduty.com/main/docs/escalation-policies — MEDIUM confidence (official docs via web search synthesis)
- incident.io: Incident Lifecycle, Statuses guide — https://docs.incident.io/incidents/lifecycle, https://incident.io/guide/foundations/statuses — MEDIUM confidence
- Grafana OnCall: Alert Groups, Alert groups HTTP API — https://grafana.com/docs/oncall/latest/ — MEDIUM confidence
- AWS Systems Manager: `aws:approve` action reference — https://docs.aws.amazon.com/systems-manager/latest/userguide/automation-action-approve.html — MEDIUM confidence
- StackStorm: Inquiries (core.ask) — https://docs.stackstorm.com/inquiries.html — MEDIUM confidence
- Rundeck: GitHub issue #4288 "Workflow approval" (feature request, confirms no native approval gate) — https://github.com/rundeck/rundeck/issues/4288 — MEDIUM confidence
- Shoreline.io: product blog and third-party coverage on runbook automation with human-in-the-loop — https://shoreline.io/blog/why-i-built-shoreline-incident-automation, https://incident.io/blog/runbook-automation-tools-2026-the-complete-guide — MEDIUM confidence
- LangGraph: Human-in-the-loop docs, `interrupt()` pattern — https://docs.langchain.com/oss/python/langchain/human-in-the-loop — MEDIUM confidence
- LangGraph Studio: DeepWiki graph visualization reference — https://deepwiki.com/langchain-ai/langgraph-studio/5.2-graph-visualization — MEDIUM confidence (secondary source, cross-checked against LangGraph HITL docs)
- Temporal: Web UI, Timeline view blog post — https://docs.temporal.io/web-ui, https://temporal.io/blog/lets-visualize-a-workflow — MEDIUM confidence
- Apache Airflow: UI Overview, Best Practices — https://airflow.apache.org/docs/apache-airflow/stable/ui.html, https://airflow.apache.org/docs/apache-airflow/stable/best-practices.html — MEDIUM confidence
- n8n: Execution Data and History, Pin and mock data — https://docs.n8n.io/workflows/executions/debug/, https://docs.n8n.io/build/work-with-data/pin-and-mock-data — MEDIUM confidence
- Langfuse: AI Agent Observability blog, "Langfuse for Agents" changelog — https://langfuse.com/blog/2024-07-ai-agent-observability-with-langfuse, https://langfuse.com/changelog/2025-11-05-langfuse-for-agents — MEDIUM confidence
- Rootly: "Why Timeline Construction Matters in Retrospectives and Incident Postmortems" — https://rootly.com/incident-postmortems/timeline — MEDIUM confidence
- PagerDuty: Postmortem Documentation Guide — https://www.pagerduty.com/resources/insights/learn/how-to-write-postmortem/ — MEDIUM confidence
- General SRE practice: severity level / color-coding convention synthesis across multiple incident-management vendor blogs (Xurrent, InvGate, Runframe, UptimeRobot) — MEDIUM confidence (converging consensus across independent sources, no single canonical spec)
- Project context: `/Users/sanjay/incimin/.planning/PROJECT.md` — v1.7 milestone scope, existing Key Decisions (Postgres for state, `AsyncPostgresSaver`+`interrupt()` for HITL, React SPA tabs, allowlisted-action approval gate) — HIGH confidence (primary project source)

---
*Feature research for: incident/alert-triage dashboard UX, HITL approval UX, and agent-run visualization, scoped to incimin.io v1.7*
*Researched: 2026-08-08*
=======
- **[Core Abstraction Layer] requires [Standardized Topology Data Model]:** The interface methods must know what data model to return to ensure standardization.
- **[SigNoz Plugin] requires [Core Abstraction Layer]:** Must implement the defined base interface to integrate with the agent.
- **[SigNoz Plugin] requires [Existing SigNoz Webhook Infrastructure]:** Depends on the already built ClickHouse data pipeline to extract topology information.
- **[Plugin Registry] requires [Core Abstraction Layer]:** Needs to validate that registered modules conform to the required contract.



## MVP Definition



### Launch With (v1.6)

Minimum viable product — what's needed to validate the concept.

- [x] Standardized Topology Data Model — Needed to normalize outputs and enforce metadata provenance.
- [x] Core Abstraction Layer (ABC) — Defines the strict contract for plugins.
- [x] Simple Plugin Registry — To discover and load active plugins.
- [x] SigNoz Plugin (`SigNozServiceMap`) — To validate the architecture and fetch the initial topology graph.



### Add After Validation (v1.x)

Features to add once core is working.

- [ ] DataDog / Prometheus Plugins — To expand provider support.
- [ ] Plugin Isolation/Circuit Breakers — For resilience when calling third-party APIs.



### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] Hot-reloading Plugins — Overkill for current deployment strategy.
- [ ] Third-party External Plugin Support — Not needed for single-org deployment.



## Feature Prioritization Matrix


| Feature                          | User Value | Implementation Cost | Priority |
| -------------------------------- | ---------- | ------------------- | -------- |
| Standardized Topology Data Model | HIGH       | LOW                 | P1       |
| Core Abstraction Layer           | HIGH       | LOW                 | P1       |
| SigNoz Plugin                    | HIGH       | MEDIUM              | P1       |
| Simple Plugin Registry           | HIGH       | LOW                 | P1       |
| Dual Identity Provenance         | HIGH       | LOW                 | P1       |
| Plugin Failure Isolation         | MEDIUM     | HIGH                | P2       |
| DataDog Plugin                   | MEDIUM     | MEDIUM              | P2       |
| Third-party Extensibility        | LOW        | HIGH                | P3       |


**Priority key:**

- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

>>>>>>> Stashed changes
