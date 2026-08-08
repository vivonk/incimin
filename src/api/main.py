"""Incident dashboard API.

    POST /webhook/signoz            SigNoz/Alertmanager alert -> incident row -> agent run
    GET  /api/incidents             list, filterable by status and severity
    GET  /api/incidents/{id}        one incident, including the verbatim payload
    GET  /api/incidents/{id}/steps  the ordered agent step log
    GET  /health

Replaces the Starlette receiver that used to live in `src/webhook/app.py`. Two of
that module's properties are deliberately preserved:

* **Always fast, always 2xx.** Alert senders retry on non-2xx and on slow responses,
  and an agent run takes tens of seconds. The handler acknowledges immediately and
  runs the agent as a background task, so a malformed payload or a broken data plane
  produces a log line rather than a retry storm.
* **Lazy agent import.** `src.agent.graph` builds an LLM at import time and raises
  without an API key; that import stays inside the runner so the receiver survives.

What changed: repeat suppression is now a database constraint rather than an
in-process dict, so it survives a restart and cannot race between two concurrent
deliveries of the same fingerprint.
"""
from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse

from src.api import db
from src.api import repository as repo
from src.api import runner
from src.api.settings import settings
from src.webhook.alert import SERVICE_LABEL_KEYS, parse_alerts

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("incimin.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db.open_pool()
    await db.apply_schema()
    await db.setup_checkpointer_tables()
    if orphaned := await repo.mark_orphans():
        log.warning("marked %d incident(s) orphaned from a previous run", orphaned)
    try:
        yield
    finally:
        await runner.drain()
        await db.close_pool()


app = FastAPI(title="incimin incident API", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/webhook/signoz")
async def signoz_webhook(request: Request) -> JSONResponse:
    """Accept an Alertmanager-format alert. Always 200.

    The body is read and parsed by hand rather than declared as a typed parameter:
    the payload is legitimately either an envelope object or a bare list, and a
    malformed body must produce a 200 with a reason rather than FastAPI's 422 —
    a non-2xx here triggers sender retries.
    """
    try:
        payload = json.loads(await request.body())
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        log.warning("webhook received a non-JSON body — ignoring")
        return JSONResponse({"status": "ignored", "reason": "invalid json"})

    accepted, skipped = [], []
    for ctx in parse_alerts(payload):
        if not ctx.is_firing:
            skipped.append({"alert": ctx.alertname, "reason": "resolved"})
            continue
        if not ctx.service:
            log.warning(
                "no service label on %r; tried %s. labels=%s",
                ctx.alertname,
                list(SERVICE_LABEL_KEYS),
                ctx.labels,
            )
            skipped.append({"alert": ctx.alertname, "reason": "no service label"})
            continue

        row, created = await repo.create_incident(ctx)
        if not created:
            log.info("[%s] %s suppressed — already active", ctx.service, ctx.alertname)
            skipped.append({"alert": ctx.alertname, "reason": "duplicate"})
            continue

        runner.spawn(row["id"], ctx)
        accepted.append(
            {"alert": ctx.alertname, "service": ctx.service, "incident_id": str(row["id"])}
        )

    return JSONResponse(
        {
            "status": "accepted" if accepted else "ignored",
            "accepted": accepted,
            "skipped": skipped,
        }
    )


@app.get("/api/incidents")
async def list_incidents(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    limit: int = Query(default=200, le=1000),
) -> list[dict]:
    return [_serialize(r) for r in await repo.list_incidents(status, severity, limit)]


@app.get("/api/incidents/{incident_id}")
async def get_incident(incident_id: uuid.UUID) -> JSONResponse:
    row = await repo.get_incident(incident_id)
    if row is None:
        return JSONResponse({"detail": "not found"}, status_code=404)
    return JSONResponse(_serialize(row))


@app.get("/api/incidents/{incident_id}/steps")
async def get_steps(incident_id: uuid.UUID) -> list[dict]:
    return [_serialize(r) for r in await repo.list_steps(incident_id)]


def _serialize(row: dict) -> dict:
    """UUIDs and datetimes to JSON-safe values."""
    out = {}
    for key, value in row.items():
        if isinstance(value, uuid.UUID):
            out[key] = str(value)
        elif hasattr(value, "isoformat"):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out
