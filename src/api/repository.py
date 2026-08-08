"""Data access for incidents, agent steps, and approvals.

Every statement here is parameterized. This is not a style preference: the alert
payload is upstream-controlled text, and this repo has a demonstrated habit to
break with — `src/production/db.py::_insert_ch` f-string-builds a Python source
string and runs it through `subprocess.run([sys.executable, "-c", code])`, which
is arbitrary code execution rather than merely SQL injection. Nothing in this
package composes SQL from user data.
"""
from __future__ import annotations

import uuid
from typing import Any

from psycopg.types.json import Jsonb

from src.api.db import pool
from src.webhook.alert import AlertContext

# Statuses at which an incident is finished. The partial unique index in schema.sql
# uses the same set: repeat suppression applies only while an incident is live.
TERMINAL_STATUSES = ("done", "failed", "needs_human")


async def create_incident(ctx: AlertContext) -> tuple[dict[str, Any] | None, bool]:
    """Insert one incident, or detect that a live one already exists.

    Returns `(row, created)`. `created` is False when an active incident with this
    dedupe key was already present — the atomic "already existed" signal, taken from
    the database rather than from a process-local dict that cannot survive a restart
    and races between two concurrent deliveries of the same fingerprint.

    Timestamps are written from the already-parsed AlertContext fields. Re-parsing
    them out of `raw` would regress parse_time()'s handling of Go's RFC3339
    nanoseconds and Alertmanager's 0001-01-01 zero sentinel.
    """
    sql = """
        INSERT INTO incidents (
            id, dedupe_key, fingerprint, alertname, service, severity, message,
            generator_url, receiver, status, fired_at, resolved_at,
            labels, annotations, raw
        )
        VALUES (
            %(id)s, %(dedupe_key)s, %(fingerprint)s, %(alertname)s, %(service)s,
            %(severity)s, %(message)s, %(generator_url)s, %(receiver)s, 'open',
            %(fired_at)s, %(resolved_at)s, %(labels)s, %(annotations)s, %(raw)s
        )
        ON CONFLICT (dedupe_key) WHERE status NOT IN ('done', 'failed', 'needs_human')
        DO NOTHING
        RETURNING *
    """
    # The conflict target is written as index inference, not `ON CONSTRAINT <name>`:
    # incidents_active_dedupe_key is a *partial unique index*, and Postgres only
    # accepts real constraints by name there. The predicate must match the index's
    # exactly for inference to select it — keep the two in sync with schema.sql.
    params = {
        "id": uuid.uuid4(),
        "dedupe_key": ctx.dedupe_key,
        "fingerprint": ctx.fingerprint,
        "alertname": ctx.alertname,
        "service": ctx.service,
        "severity": ctx.severity,
        "message": ctx.message,
        "generator_url": ctx.generator_url,
        "receiver": ctx.receiver,
        "fired_at": ctx.fired_at,
        "resolved_at": ctx.resolved_at,
        "labels": Jsonb(ctx.labels),
        "annotations": Jsonb(ctx.annotations),
        "raw": Jsonb(ctx.raw),
    }
    async with pool().connection() as conn:
        cur = await conn.execute(sql, params)
        row = await cur.fetchone()
    return (row, True) if row else (None, False)


async def get_incident(incident_id: uuid.UUID) -> dict[str, Any] | None:
    async with pool().connection() as conn:
        cur = await conn.execute("SELECT * FROM incidents WHERE id = %s", (incident_id,))
        return await cur.fetchone()


async def list_incidents(
    status: str | None = None,
    severity: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """List incidents, newest first, optionally filtered.

    Filters are bound parameters with a NULL-means-no-filter guard rather than a
    dynamically assembled WHERE clause — one prepared statement shape, no string
    building.
    """
    sql = """
        SELECT * FROM incidents
        WHERE (%(status)s::text   IS NULL OR status   = %(status)s)
          AND (%(severity)s::text IS NULL OR severity = %(severity)s)
        ORDER BY fired_at DESC, created_at DESC
        LIMIT %(limit)s
    """
    async with pool().connection() as conn:
        cur = await conn.execute(
            sql, {"status": status, "severity": severity, "limit": limit}
        )
        return list(await cur.fetchall())


async def set_status(
    incident_id: uuid.UUID,
    status: str,
    current_step: str | None = None,
) -> None:
    await _update(
        incident_id,
        "status = %(status)s, current_step = %(current_step)s",
        {"status": status, "current_step": current_step},
    )


async def set_current_step(incident_id: uuid.UUID, current_step: str) -> None:
    await _update(incident_id, "current_step = %(current_step)s", {"current_step": current_step})


async def set_result(
    incident_id: uuid.UUID,
    *,
    status: str,
    final_answer: str | None = None,
    root_cause_service: str | None = None,
    confidence: str | None = None,
    evidence_refs: list[str] | None = None,
    error: str | None = None,
) -> None:
    await _update(
        incident_id,
        """
        status = %(status)s,
        current_step = NULL,
        final_answer = %(final_answer)s,
        root_cause_service = %(root_cause_service)s,
        confidence = %(confidence)s,
        evidence_refs = %(evidence_refs)s,
        error = %(error)s
        """,
        {
            "status": status,
            "final_answer": final_answer,
            "root_cause_service": root_cause_service,
            "confidence": confidence,
            "evidence_refs": Jsonb(evidence_refs) if evidence_refs is not None else None,
            "error": error,
        },
    )


async def mark_orphans() -> int:
    """Flip incidents left mid-run by a crash to 'orphaned'.

    Called at startup. An incident in a running state with no live task behind it
    would otherwise sit there forever claiming to be in progress — a visibly wrong
    state in a dashboard whose entire job is showing accurate status.
    """
    async with pool().connection() as conn:
        cur = await conn.execute(
            """
            UPDATE incidents
               SET status = 'orphaned', updated_at = now()
             WHERE status IN ('agent_running', 'executing_remediation')
            RETURNING id
            """
        )
        return len(await cur.fetchall())


async def _update(incident_id: uuid.UUID, set_clause: str, params: dict[str, Any]) -> None:
    """Run an UPDATE whose SET clause is a module-local literal.

    `set_clause` is only ever a constant defined in this file — never built from
    caller input. Values are always bound.
    """
    async with pool().connection() as conn:
        await conn.execute(
            f"UPDATE incidents SET {set_clause}, updated_at = now() WHERE id = %(id)s",
            {**params, "id": incident_id},
        )


# -- agent steps -----------------------------------------------------------


async def add_step(
    incident_id: uuid.UUID,
    seq: int,
    kind: str,
    name: str,
    *,
    parent_seq: int | None = None,
    status: str = "running",
    input: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    ended: bool = False,
) -> dict[str, Any] | None:
    sql = """
        INSERT INTO agent_steps (
            incident_id, seq, parent_seq, kind, name, status, input, output, ended_at
        )
        VALUES (
            %(incident_id)s, %(seq)s, %(parent_seq)s, %(kind)s, %(name)s,
            %(status)s, %(input)s, %(output)s,
            CASE WHEN %(ended)s THEN now() ELSE NULL END
        )
        ON CONFLICT ON CONSTRAINT agent_steps_unique_seq DO NOTHING
        RETURNING *
    """
    async with pool().connection() as conn:
        cur = await conn.execute(
            sql,
            {
                "incident_id": incident_id,
                "seq": seq,
                "parent_seq": parent_seq,
                "kind": kind,
                "name": name,
                "status": status,
                "input": Jsonb(input) if input is not None else None,
                "output": Jsonb(output) if output is not None else None,
                "ended": ended,
            },
        )
        return await cur.fetchone()


async def list_steps(incident_id: uuid.UUID) -> list[dict[str, Any]]:
    async with pool().connection() as conn:
        cur = await conn.execute(
            "SELECT * FROM agent_steps WHERE incident_id = %s ORDER BY seq",
            (incident_id,),
        )
        return list(await cur.fetchall())
