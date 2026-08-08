-- Application state for the incident dashboard.
--
-- Applied idempotently at API startup (src/api/db.py::apply_schema). There is no
-- migration tool in this project; four tables do not justify adopting one, but the
-- DDL is committed rather than created out-of-band the way `system_changes` was.
--
-- Every timestamp is TIMESTAMPTZ and is written from an already-parsed AlertContext
-- field. Never re-parse them out of `raw` — src/webhook/alert.py::parse_time already
-- handles Go's RFC3339 nanoseconds and Alertmanager's 0001-01-01 zero sentinel.

CREATE TABLE IF NOT EXISTS incidents (
    id                  UUID PRIMARY KEY,

    -- Identity. dedupe_key is AlertContext.dedupe_key: the Alertmanager fingerprint
    -- when present, else "alertname|service".
    dedupe_key          TEXT        NOT NULL,
    fingerprint         TEXT,

    -- Parsed alert fields.
    alertname           TEXT        NOT NULL,
    service             TEXT        NOT NULL,
    severity            TEXT,
    message             TEXT        NOT NULL DEFAULT '',
    generator_url       TEXT,
    receiver            TEXT,

    -- Lifecycle. `status` is the coarse column the list renders; `current_step`
    -- carries the live detail (e.g. 'telemetry_tool') so the list shows progress
    -- without joining agent_steps.
    status              TEXT        NOT NULL DEFAULT 'open',
    current_step        TEXT,

    fired_at            TIMESTAMPTZ NOT NULL,
    resolved_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- The verbatim SigNoz payload, plus the parsed label/annotation maps.
    labels              JSONB       NOT NULL DEFAULT '{}'::jsonb,
    annotations         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    raw                 JSONB       NOT NULL DEFAULT '{}'::jsonb,

    -- Agent results, filled in as the run progresses.
    root_cause_service  TEXT,
    confidence          TEXT,
    evidence_refs       JSONB,
    final_answer        TEXT,
    error               TEXT,

    CONSTRAINT incidents_status_valid CHECK (status IN (
        'open',
        'agent_running',
        'awaiting_approval',
        'executing_remediation',
        'done',
        'needs_human',
        'orphaned',
        'failed'
    ))
);

-- Repeat suppression, enforced by the database rather than by process memory.
--
-- Alertmanager re-sends a firing alert every repeat_interval. The old in-memory
-- `_recent` dict could not survive a restart and raced between two concurrent
-- deliveries of the same fingerprint. A PARTIAL index is what makes this correct:
-- suppression applies only while an incident is still live, so the same alert
-- firing again after it was resolved legitimately opens a new incident.
CREATE UNIQUE INDEX IF NOT EXISTS incidents_active_dedupe_key
    ON incidents (dedupe_key)
    WHERE status NOT IN ('done', 'failed', 'needs_human');

CREATE INDEX IF NOT EXISTS incidents_status_idx    ON incidents (status);
CREATE INDEX IF NOT EXISTS incidents_severity_idx  ON incidents (severity);
CREATE INDEX IF NOT EXISTS incidents_fired_at_idx  ON incidents (fired_at DESC);


-- The ordered event log the step graph is built from.
--
-- `parent_seq` is what makes this a graph rather than a list: a tool_call hangs off
-- the node that issued it, while `node` rows chain in execution order.
CREATE TABLE IF NOT EXISTS agent_steps (
    id           BIGSERIAL PRIMARY KEY,
    incident_id  UUID        NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    seq          INTEGER     NOT NULL,
    parent_seq   INTEGER,
    kind         TEXT        NOT NULL,
    name         TEXT        NOT NULL,
    status       TEXT        NOT NULL DEFAULT 'running',
    input        JSONB,
    output       JSONB,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at     TIMESTAMPTZ,

    CONSTRAINT agent_steps_unique_seq UNIQUE (incident_id, seq),
    CONSTRAINT agent_steps_kind_valid CHECK (kind IN ('node', 'tool_call', 'tool_result', 'gate'))
);

CREATE INDEX IF NOT EXISTS agent_steps_incident_idx ON agent_steps (incident_id, seq);


-- Human approval gates. Created here so phase 11 finds the table ready; populated
-- by the HITL nodes it adds.
CREATE TABLE IF NOT EXISTS approvals (
    id                UUID PRIMARY KEY,
    incident_id       UUID        NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    step_seq          INTEGER,
    kind              TEXT        NOT NULL,
    proposal          JSONB       NOT NULL DEFAULT '{}'::jsonb,
    decision          TEXT        NOT NULL DEFAULT 'pending',
    decided_by        TEXT,
    decided_at        TIMESTAMPTZ,
    note              TEXT,
    execution_result  JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT approvals_kind_valid CHECK (kind IN ('remediation', 'escalation')),
    CONSTRAINT approvals_decision_valid CHECK (decision IN ('pending', 'approved', 'rejected', 'executing', 'executed'))
);

CREATE INDEX IF NOT EXISTS approvals_incident_idx ON approvals (incident_id);
-- At most one undecided gate per incident: the agent pauses at one gate at a time,
-- and this makes a double-open-gate bug impossible rather than merely unlikely.
CREATE UNIQUE INDEX IF NOT EXISTS approvals_one_pending
    ON approvals (incident_id)
    WHERE decision = 'pending';
