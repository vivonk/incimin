# Feature Research

**Domain:** AI SRE Agent / AIOps Incident Response Automation
**Researched:** 2026-08-05
**Confidence:** MEDIUM-HIGH (training data through Aug 2025 covers this domain; specific competitor versioning may lag)

---

## Feature Landscape

### Table Stakes (Enterprise Buyers Expect These)

Features that enterprise SRE and platform engineering teams assume exist. Missing these = product gets disqualified early in evaluation.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Alert ingestion from standard sources | PagerDuty, OpsGenie, Alertmanager, Datadog — buyers won't reroute existing alerting pipelines | LOW | Webhook receiver + normalization layer; OTel alert format as canonical |
| Correlated root cause summary | Core RCA narrative from correlated signals (logs, traces, metrics); buyers assume any "AI SRE" product does this | HIGH | incimin's LangGraph agent + ClickHouse SQL + Qdrant retrieval is the implementation; correctness is the hard part |
| Service dependency awareness | Who talks to whom — buyers know cascading failures are the norm in microservices and expect the tool to know too | HIGH | Memgraph BFS covers this; populating the graph accurately is the hard dependency |
| Runbook/KB retrieval | "What has this team done before in similar incidents?" — institutionalized knowledge surfaced at alert time | MEDIUM | Qdrant semantic search; quality degrades without runbook curation |
| Explainability / glass-box reasoning | Enterprise risk/audit requirement: "How did you arrive at that?" — black-box AI output is a blocker for enterprise buyers | MEDIUM | LangGraph tool-call traces + Streamlit `st.status` expanders cover this for demo; production needs a persistent audit log |
| Human-in-the-loop remediation workflow | Agent recommends; human approves; human executes — this is non-negotiable for enterprises with change management processes | LOW | Recommendation-only output is already the design; the risk is accidentally building auto-execute paths later |
| Alert noise reduction / deduplication | Operations teams drown in alert storms; buyers expect intelligent grouping before any other value | MEDIUM | Correlating alerts by topology proximity (same service cluster) and time window is the minimum viable implementation |
| Integration with existing observability stack | Buyers won't replace Datadog, Grafana, or PagerDuty; the AI layer must sit on top, not replace | MEDIUM | SigNoz + OTel collector is a good-citizen stack; production will need Datadog/Prometheus adapters |
| Incident timeline reconstruction | Ordered sequence of what changed/failed and when — SRE post-mortems require it; expected during live incidents too | MEDIUM | ClickHouse time-range queries over spans and logs; requires good timestamp indexing |
| RBAC / access control | Enterprise: different teams own different services; the agent must not show team B's runbooks to team A | HIGH | Not in v1 scope but will be a hard blocker for any production contract |

---

### Differentiators (Competitive Advantage vs PagerDuty AIOps, Datadog AIOps, Grafana IRM)

Features that set incimin apart. Most competitors do alert correlation; few do deterministic topology-grounded RCA.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Live service graph traversal (not static topology maps) | Competitors use static or inferred topology; incimin traverses the *live* graph state at incident time — capturing runtime deps, not just deploy-time config | HIGH | Memgraph + memgraph-mage is the core differentiator; requires continuous graph refresh from OTel service map data |
| Deterministic, hallucination-free RCA critical path | Topology reasoning via Cypher BFS, not LLM inference — LLM only synthesizes the explanation; buyers trust it because it can be audited step-by-step | HIGH | The zero-hallucination claim is verifiable because every traversal step is logged; competitors can't make this claim cleanly |
| Runbook grounding with semantic retrieval | RCA output cites the specific runbook section that applies — not generic advice; reduces mean-time-to-action (MTTA) | MEDIUM | Qdrant metadata filtering by service + incident type is the key; requires curated runbook ingestion pipeline |
| Glass-box tool-call trace UI | Every query the agent executed is visible — buyers in regulated industries (fintech, healthcare) require this for change-advisory-board sign-off | MEDIUM | Streamlit `st.status` is a demo-quality implementation; production needs a persistent queryable audit log |
| Sub-60-second RCA from alert to recommendation | Buyers measure MTTA; if the first-responder human takes 15 minutes to triage and the agent does it in 45 seconds, the value is quantifiable and demonstrable | HIGH | Latency is a product constraint, not just a feature; every tool call (graph, SQL, vector) must be optimized for cold-path execution |
| Context-aware incident similarity ("seen this before") | Agent surfaces past incidents with the same failure pattern + their resolution — not just runbooks but precedents | MEDIUM | Requires incident history indexed in Qdrant alongside runbooks; depends on runbook/KB quality |
| Topology-rooted blast radius estimation | When a service is degraded, the agent can enumerate all downstream dependents and their current health — tells the on-call team what *else* to watch | MEDIUM | BFS traversal with depth limit + health status join from telemetry; Memgraph makes this a natural extension |

---

### Anti-Features (Things Enterprise SRE Teams Actively Don't Want)

These are features that seem appealing in demos or sales conversations but create serious problems in production enterprise deployments.

| Feature | Why It Gets Requested | Why Enterprise Teams Don't Want It | What to Build Instead |
|---------|----------------------|-------------------------------------|----------------------|
| Automated remediation execution (auto-rollback, auto-restart, auto-scale) | "The AI should just fix it" — sounds like the ultimate productivity win | Change management processes (ITIL, SOC2, ISO27001) require human approval for production changes; auto-execution bypasses change advisory boards, creates audit failures, and causes trust destruction after the first false-positive auto-rollback takes down a healthy service | Recommendation-only output with structured remediation steps; optionally a one-click "approve and run" that still logs the human approval actor |
| Alert suppression without explanation | "Too many alerts, just silence the low-priority ones" | Suppressed alerts that turn out to be real incidents are career-ending for the on-call engineer who agreed to the suppression policy; unexplained suppression creates blind spots | Surface suppression candidates with explicit reasoning ("suppressing: checkout-worker-cpu-throttle because root cause is already identified as payment-service OOM; these are effects, not causes"); human confirms suppression |
| Single-pane-of-glass dashboard replacing existing tooling | Consolidation sounds good; vendors love it for lock-in | Enterprise observability stacks are $500K+ investments; forcing migration or parallel maintenance of a new dashboard tool is an adoption blocker; also your dashboard will never be as good as Datadog's | Embed in the workflow: agent outputs go into PagerDuty incident notes, Slack threads, Jira tickets — wherever the team already works |
| Predictive incident alerting (ML-based anomaly-as-alert) | "Catch problems before they happen" | ML anomaly detection in high-cardinality environments has a high false-positive rate that erodes trust rapidly; if the AI cries wolf 10 times before a real incident, on-call engineers start ignoring it | Reactive RCA excellence beats unreliable predictive alerts; add prediction only after the reactive path is trusted |
| LLM-inferred topology (asking the LLM "what depends on what") | Seems to avoid the graph population problem | LLM topology inference hallucinations cause catastrophic RCA errors — the agent confidently follows the wrong dependency chain; this is the exact failure mode that destroys trust in AI SRE products | Explicit topology from OTel service map data + Memgraph; the graph population problem is an engineering problem worth solving correctly |
| Auto-escalation policy changes | "Let the AI optimize who gets paged" | Escalation policies are human agreements about who is responsible for what; automated changes to paging rules violate those agreements and create accountability confusion during major incidents | Read-only access to escalation context; recommend escalation but never modify policies |
| Chat-only interface as the primary incident surface | LLM chatbots are familiar; buyers initially want a chat interface | During a live P1 incident, a chat interface requires the engineer to type queries while simultaneously firefighting; structured push-based output (incident report card delivered to Slack/PagerDuty automatically on alert fire) is higher value | Push-first, pull-optional: agent fires automatically on alert, pushes structured RCA to where the team already is; chat is available for follow-up questions |

---

## Feature Dependencies

```
Alert Ingestion
    └──requires──> Signal Normalization (canonical alert schema)
                       └──requires──> Service Topology Graph (populated)
                                          └──requires──> OTel Service Map → Memgraph ETL

Correlated RCA Narrative
    └──requires──> Service Topology Graph (traversal)
    └──requires──> Telemetry Query (ClickHouse SQL for logs/traces)
    └──requires──> Runbook Retrieval (Qdrant semantic search)

Runbook Retrieval
    └──requires──> Runbook Ingestion Pipeline (markdown → embeddings → Qdrant)
    └──enhances──> Incident Similarity ("seen this before")

Glass-box Audit Log
    └──requires──> LangGraph tool-call trace capture
    └──enhances──> RBAC (restrict which traces are visible to which teams)

Blast Radius Estimation
    └──requires──> Service Topology Graph
    └──enhances──> Correlated RCA Narrative

RBAC / Access Control
    └──requires──> Identity provider integration (SSO/SAML)
    └──blocks (if absent)──> Enterprise production deployment
```

### Dependency Notes

- **Correlated RCA requires all three data planes simultaneously:** Graph traversal, telemetry query, and runbook retrieval must all succeed; a failure in any one degrades the output quality from authoritative to speculative. Design for graceful degradation — if Qdrant is unavailable, return RCA without runbook grounding rather than failing the whole request.
- **Service topology graph quality gates everything downstream:** A stale or incomplete graph produces wrong blast radius estimates and incorrect RCA paths. This is the highest-leverage investment in data quality.
- **Runbook ingestion is a customer onboarding problem:** The product can be technically perfect and still fail to deliver value if the customer's runbooks are not ingested and kept current. Runbook ingestion UX and freshness monitoring are product concerns, not just engineering.
- **RBAC conflicts with single-tenant simplicity:** v1 single-tenant design avoids RBAC complexity. Adding RBAC later is a significant refactor of the data layer (Qdrant collection partitioning, Memgraph namespace isolation). Design the schema with RBAC hooks from day one even if enforcement is deferred.

---

## MVP Definition

### Launch With (v1 — Demo Sprint)

Minimum set required to demonstrate differentiated value and close the first enterprise pilot.

- [ ] **Correlated RCA from alert to recommendation** — the core value proposition; without this there is no product
- [ ] **Deterministic topology traversal (Memgraph BFS)** — the hallucination-free differentiator; must be demonstrable and auditable
- [ ] **Runbook grounding (Qdrant semantic retrieval)** — elevates output from "generic advice" to "team-specific next action"
- [ ] **Glass-box tool-call trace UI (Streamlit st.status)** — required for enterprise trust; audit trail for every reasoning step
- [ ] **Recommendation-only output (no auto-remediation)** — explicit constraint; must be enforced in code, not just by convention
- [ ] **Sub-60-second end-to-end latency** — the quantifiable metric that makes the value proposition concrete in a demo

### Add After Validation (v1.x)

Add after first enterprise pilot confirms the RCA core is trusted.

- [ ] **Alert deduplication / noise grouping** — trigger: pilot team reports alert storm fatigue overwhelming the RCA output
- [ ] **Incident timeline reconstruction** — trigger: pilot team requests structured post-mortem artifacts
- [ ] **Blast radius estimation** — trigger: pilot team has experienced cascading failures and wants proactive scope awareness
- [ ] **Incident similarity / precedent retrieval** — trigger: pilot team has accumulated enough incident history for pattern matching to be meaningful (3-6 months)
- [ ] **Slack/PagerDuty push integration** — trigger: pilot team needs agent output in their existing workflow, not a Streamlit tab

### Future Consideration (v2+)

Defer until product-market fit is confirmed and a multi-customer dataset informs prioritization.

- [ ] **RBAC / access control** — deferred to v2 because v1 is single-tenant; required before expanding to second team/org within an enterprise
- [ ] **Predictive anomaly flagging** — defer until reactive RCA is trusted; unreliable prediction destroys the trust reactive builds
- [ ] **Multi-tenant SaaS** — strategic decision post-PMF; changes the entire data architecture
- [ ] **Automated remediation execution (with approval workflow)** — only after trust is established and change management integration is designed; not v1 for security and audit reasons
- [ ] **Custom alert routing / escalation recommendation** — defer until the team understands customer-specific escalation patterns

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Correlated RCA narrative | HIGH | HIGH | P1 |
| Deterministic topology traversal | HIGH | MEDIUM | P1 |
| Runbook grounding | HIGH | MEDIUM | P1 |
| Glass-box tool-call trace | HIGH | LOW | P1 |
| Recommendation-only enforcement | HIGH | LOW | P1 |
| Sub-60s latency | HIGH | MEDIUM | P1 |
| Alert deduplication | MEDIUM | MEDIUM | P2 |
| Incident timeline reconstruction | MEDIUM | MEDIUM | P2 |
| Blast radius estimation | HIGH | LOW | P2 |
| Slack/PagerDuty push integration | HIGH | MEDIUM | P2 |
| Incident similarity / precedent | MEDIUM | MEDIUM | P2 |
| RBAC / access control | HIGH | HIGH | P3 |
| Predictive anomaly flagging | MEDIUM | HIGH | P3 |
| Multi-tenant | LOW (v1) | HIGH | P3 |
| Auto-remediation with approval | MEDIUM | HIGH | P3 |

**Priority key:**
- P1: Required for v1 demo and pilot
- P2: Add after pilot validation
- P3: Future roadmap / v2+

---

## Competitor Feature Analysis

| Feature | PagerDuty AIOps | Datadog AIOps | Grafana IRM | incimin Approach |
|---------|-----------------|---------------|-------------|-----------------|
| Alert correlation / noise reduction | ML-based event grouping across alert sources | Watchdog anomaly + alert correlation | Alert grouping by label | Topology-grounded correlation — alerts on the same blast radius path are co-grouped |
| Root cause identification | Probable cause suggestions (LLM-assisted, not deterministic) | Watchdog RCA (statistical, not graph-traversal) | Manual; no auto-RCA | Deterministic BFS on live service graph — auditable, not probabilistic |
| Runbook integration | Runbook links attached to incidents; no semantic retrieval | Similar incidents with links | Playbooks (manual) | Semantic runbook retrieval grounded to the specific incident context |
| Topology / service map | Static service catalog | Service Map (inferred from APM traces) | Service dependency (manual config) | Live Memgraph graph updated from OTel service map; traversable at query time |
| Explainability | Minimal — shows correlated alerts, not reasoning chain | Minimal — confidence score without trace | None | Full tool-call trace: which Cypher query, which SQL, which runbook chunk, in what order |
| Human approval workflow | Manual escalation / acknowledgment | Incident management UI | Manual | Recommendation-only by design; approval gate is explicit |
| Auto-remediation | Automation actions (runbook automation, webhooks) | Workflow automations | None | Explicitly out of scope for v1; reduces enterprise adoption friction |
| Integration model | Native + webhook | Native + many integrations | Native Grafana stack | OTel-native; bring-your-own observability stack |

---

## Enterprise-Specific Considerations

These are constraints that differ between SMB and enterprise buyers and materially affect feature priority.

**Change management (ITIL / CAB):** Enterprise buyers have formal change advisory boards. Any feature that modifies production state — even a restart — requires a change ticket and approval trail. Auto-remediation, even with a confirmation click, needs an auditable approval record linked to the change management system (ServiceNow, Jira Service Management). This is why auto-remediation is P3, not P2.

**Audit and compliance (SOC2 / ISO27001):** Every action the agent takes against production must be logged with actor, timestamp, and rationale. The LangGraph tool-call trace is the audit log. It must be durable (not just in-memory/Streamlit session state) for any production deployment.

**On-call fatigue:** The primary pain point is not "AI can replace my SREs" — it's "my SREs are paged 20 times a night and burned out." Features that reduce pages and reduce time-to-resolution per page are the value drivers. This means noise reduction and fast RCA matter more than sophisticated prediction.

**Trust ratchet:** Enterprise SRE teams adopt AI tooling incrementally. The trust ratchet is: read-only first, then recommendation, then assisted execution, then autonomous execution. Products that try to skip steps get rejected. incimin's recommendation-only v1 is correctly positioned at step 2. Never skip to step 4.

**Data residency:** Large enterprises (financial services, healthcare) will require on-premise or VPC deployment. The Docker Compose local architecture is a trust signal, not just a demo convenience — it demonstrates the product can run in a data-controlled environment.

---

## Sources

- Competitor product knowledge: PagerDuty AIOps, Datadog AIOps/Watchdog, Grafana IRM, Moogsoft (acquired by Dell), BigPanda, OpsRamp (HPE) — training data through Aug 2025, MEDIUM confidence on specific feature versioning
- Enterprise SRE adoption patterns: Site Reliability Engineering (Google SRE book), DORA metrics research, ITIL 4 change management requirements — HIGH confidence on enterprise process constraints
- incimin PROJECT.md constraints and design decisions — HIGH confidence (primary source)

---

*Feature research for: AI SRE Agent / AIOps Incident Response*
*Researched: 2026-08-05*
