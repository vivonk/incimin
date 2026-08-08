"""SigNoz alert webhook -> meta-agent.

    POST /webhook/signoz    Alertmanager-format alert; triggers the meta-agent
    GET  /health            liveness

An incoming alert is parsed into an `AlertContext` (message + metadata) and handed to the
LangGraph meta-agent in `src.agent.graph`, which delegates to the topology / telemetry / knowledge
sub-agents and returns a verified root cause.

Three deliberate choices:

* **Always 200, always fast.** Alert senders retry on non-2xx and on slow responses, and an agent
  run takes tens of seconds. The handler acknowledges immediately and runs the agent on a
  background thread, so a malformed payload or a broken data plane produces a log line, never a
  retry storm.
* **Repeat suppression.** Alertmanager re-sends a firing alert every `repeat_interval`. Without a
  suppression window each resend would start another full agent run against the same incident.
* **Lazy agent import.** `src.agent.graph` builds an LLM at import time and raises without an API
  key. Importing it inside the worker keeps the receiver up (and importable in tests) so the
  failure is logged per-alert instead of killing the process at startup.

Environment:
    INCIMIN_WEBHOOK_TARGET   `agent` (default) — the meta-agent graph;
                             `diagnosis` — the MCP topology + change-log flow in agent/diagnosis.py
    WEBHOOK_MAX_STEPS        meta-agent step budget (default 10)
    WEBHOOK_DEDUPE_SECONDS   repeat-suppression window; 0 disables (default 300)
    WEBHOOK_MAX_CONCURRENCY  concurrent agent runs (default 2)

Run:  uvicorn src.webhook.app:app --host 127.0.0.1 --port 8080
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from src.agent import tracing
from src.webhook.alert import SERVICE_LABEL_KEYS, AlertContext, parse_alerts

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("incimin.webhook")

MAX_STEPS = int(os.getenv("WEBHOOK_MAX_STEPS", "10"))
DEDUPE_SECONDS = float(os.getenv("WEBHOOK_DEDUPE_SECONDS", "300"))

# The agent is LLM-bound and slow; an alert storm should queue, not fan out into N concurrent runs.
_slots = threading.BoundedSemaphore(int(os.getenv("WEBHOOK_MAX_CONCURRENCY", "2")))

_recent: dict[str, float] = {}
_recent_lock = threading.Lock()


def _is_duplicate(ctx: AlertContext) -> bool:
    """True when this alert was already accepted inside the suppression window."""
    if DEDUPE_SECONDS <= 0:
        return False
    now = time.monotonic()
    with _recent_lock:
        for key, seen in list(_recent.items()):
            if now - seen > DEDUPE_SECONDS:
                del _recent[key]
        if now - _recent.get(ctx.dedupe_key, float("-inf")) <= DEDUPE_SECONDS:
            return True
        _recent[ctx.dedupe_key] = now
    return False


# -- targets ---------------------------------------------------------------


def trace_config(ctx: AlertContext, target: str) -> dict:
    """Langfuse config for one alert's run.

    Session is the dedupe key (the Alertmanager fingerprint where one is present), so every
    resend of a single firing incident groups into one Langfuse session instead of appearing as
    unrelated traces — that is the view you want when asking "what did the agent conclude about
    *this* incident, across all the times it fired".
    """
    return tracing.trace_config(
        f"sre-alert:{ctx.alertname}",
        session_id=ctx.dedupe_key,
        tags=["incimin-webhook", target, ctx.severity, ctx.service],
        metadata={
            "alertname": ctx.alertname,
            "service": ctx.service,
            "severity": ctx.severity,
            "fingerprint": ctx.fingerprint,
            "fired_at": ctx.fired_at.isoformat(),
            "target": target,
            "max_steps": MAX_STEPS,
        },
    )


def message_text(content: object) -> str:
    """Flatten LangChain message content to text.

    Reasoning-capable models return a list of blocks (thinking + text) rather than a bare string;
    str()-ing that would log raw block dicts.
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p).strip()
    return str(content).strip() if content else ""


def run_meta_agent(ctx: AlertContext) -> str:
    """Drive the LangGraph meta-agent to a final answer, logging each node as it runs.

    The final answer is taken as the last AI message carrying text, whichever node emitted it,
    rather than by naming the terminal nodes. The graph has more than one exit — `finalize` and
    `graceful_exit` in the meta-agent build, a conditional `agent -> END` in the v1.5 build — and
    an extraction keyed to a fixed set of node names silently returns nothing on the paths it does
    not know about. Updates arrive in execution order, so last-write-wins is the terminal message.
    """
    from langchain_core.messages import AIMessage, HumanMessage

    from src.agent.graph import app as meta_agent

    inputs = {
        "messages": [HumanMessage(content=ctx.to_prompt())],
        "remaining_steps": MAX_STEPS,
        "evidence": [],
        "candidate_services": [],
        "synthesis": None,
        "verification_result": None,
    }

    final, final_node = "", ""
    for update in meta_agent.stream(inputs, stream_mode="updates", config=trace_config(ctx, "agent")):
        for node, state in update.items():
            if not isinstance(state, dict):
                continue
            messages = state.get("messages") or []

            # Glass-box logging. Each guard is independent: the meta-agent build emits
            # synthesis/verification updates that the v1.5 build does not, and vice versa.
            if node == "tools":
                for msg in messages:
                    log.info("[%s] sub-agent result %s: %s", ctx.service, msg.name, msg.content)
            else:
                calls = getattr(messages[-1], "tool_calls", None) if messages else None
                for call in calls or []:
                    log.info("[%s] sub-agent call %s(%s)", ctx.service, call["name"], call["args"])
            if state.get("synthesis") is not None:
                log.info("[%s] draft synthesis: %s", ctx.service, state["synthesis"])
            if state.get("verification_result") is not None:
                log.info("[%s] verifier: %s", ctx.service, state["verification_result"])

            for msg in messages:
                if isinstance(msg, AIMessage) and (text := message_text(msg.content)):
                    final, final_node = text, node

    if not final:
        return "meta-agent produced no final message"
    log.debug("[%s] final message came from node %r", ctx.service, final_node)
    return final


def run_diagnosis(ctx: AlertContext) -> str:
    """Fallback target: the deterministic MCP topology + change-log flow."""
    from src.agent.diagnosis import diagnose

    result = diagnose(
        ctx.service,
        ctx.message or f"{ctx.alertname}: {ctx.service} is alerting",
        # diagnose() formats naive local wall-clock times for the MCP server.
        alert_time=ctx.fired_at.astimezone().replace(tzinfo=None),
        config=trace_config(ctx, "diagnosis"),
    )
    log.info(
        "[%s] evidence: related=%d changed=%s errors=%s",
        ctx.service,
        len(result.related_services),
        result.services_with_changes,
        result.errors,
    )
    return result.synthesis


TARGETS = {"agent": run_meta_agent, "diagnosis": run_diagnosis}


def run_alert(ctx: AlertContext) -> None:
    """Background worker. Must never raise — nothing is waiting to catch it."""
    name = os.getenv("INCIMIN_WEBHOOK_TARGET", "agent").strip().lower() or "agent"
    target = TARGETS.get(name)
    if target is None:
        log.error("unknown INCIMIN_WEBHOOK_TARGET %r; expected one of %s", name, sorted(TARGETS))
        return

    with _slots:
        started = time.monotonic()
        try:
            log.info("[%s] %s -> %s (severity=%s)", ctx.service, ctx.alertname, name, ctx.severity)
            answer = target(ctx)
            log.info(
                "[%s] ROOT CAUSE ANALYSIS (%.1fs)\n%s", ctx.service, time.monotonic() - started, answer
            )
        except Exception:
            log.exception("[%s] %s failed", ctx.service, name)
        finally:
            # These runs happen on short-lived threads that finish well inside the SDK's batch
            # interval; without an explicit flush the trace for a completed incident sits in a
            # buffer instead of appearing in Langfuse.
            tracing.flush()


# -- routes ----------------------------------------------------------------


async def signoz_webhook(request: Request) -> JSONResponse:
    try:
        payload = await request.json()
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
        if _is_duplicate(ctx):
            log.info("[%s] %s suppressed — already running/seen", ctx.service, ctx.alertname)
            skipped.append({"alert": ctx.alertname, "reason": "duplicate"})
            continue

        threading.Thread(target=run_alert, args=(ctx,), daemon=True).start()
        accepted.append({"alert": ctx.alertname, "service": ctx.service})

    return JSONResponse({"status": "accepted" if accepted else "ignored", "accepted": accepted, "skipped": skipped})


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


app = Starlette(
    routes=[
        Route("/webhook/signoz", signoz_webhook, methods=["POST"]),
        Route("/health", health, methods=["GET"]),
    ]
)
