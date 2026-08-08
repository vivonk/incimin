"""Runs the meta-agent for one incident, recording each step as it happens.

This is the migrated body of `src/webhook/app.py`'s `run_meta_agent` / `run_alert`,
with three changes:

* every node entry and tool call is written to `agent_steps` instead of only being
  logged (the log lines are kept — they were the only observability there was);
* concurrency is an `asyncio.Semaphore` over tasks rather than a
  `BoundedSemaphore` over threads;
* incident status is driven through Postgres.

Langfuse tracing is carried over verbatim in behaviour: a per-incident trace config
whose session is the dedupe key, and an explicit `flush()` in a `finally`. Agent
tasks finish before the SDK's batch timer fires, so without that flush a completed
incident's trace can sit unsent.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from src.agent import tracing
from src.api import repository as repo
from src.api.settings import settings
from src.webhook.alert import AlertContext

log = logging.getLogger("incimin.api.runner")

_slots = asyncio.Semaphore(settings.webhook_max_concurrency)

# Bare asyncio tasks are only weakly referenced by the loop and can be garbage
# collected mid-run. Holding them here until they finish is what stops an agent
# run from vanishing silently.
_tasks: set[asyncio.Task] = set()


def spawn(incident_id: uuid.UUID, ctx: AlertContext) -> asyncio.Task:
    task = asyncio.create_task(run_incident(incident_id, ctx))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


async def drain(timeout: float = 30.0) -> None:
    """Wait for in-flight runs at shutdown."""
    if not _tasks:
        return
    await asyncio.wait(set(_tasks), timeout=timeout)


def trace_config(ctx: AlertContext, target: str) -> dict:
    """Langfuse config for one alert's run.

    Session is the dedupe key (the Alertmanager fingerprint where present), so every
    resend of a single firing incident groups into one Langfuse session rather than
    appearing as unrelated traces.
    """
    return tracing.trace_config(
        f"sre-alert:{ctx.alertname}",
        session_id=ctx.dedupe_key,
        tags=["incimin-api", target, ctx.severity, ctx.service],
        metadata={
            "alertname": ctx.alertname,
            "service": ctx.service,
            "severity": ctx.severity,
            "fingerprint": ctx.fingerprint,
            "fired_at": ctx.fired_at.isoformat(),
            "target": target,
            "max_steps": settings.webhook_max_steps,
        },
    )


def message_text(content: object) -> str:
    """Flatten LangChain message content to text.

    Reasoning-capable models return a list of blocks (thinking + text) rather than a
    bare string; str()-ing that would record raw block dicts.
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


class StepRecorder:
    """Turns graph stream updates into ordered `agent_steps` rows.

    Sequence numbers are assigned here rather than by the database so that a
    tool_call can reference the seq of the node that issued it — that parent link is
    what makes the step log a graph instead of a flat list.
    """

    def __init__(self, incident_id: uuid.UUID):
        self.incident_id = incident_id
        self.seq = 0

    async def record(self, kind: str, name: str, **kw: Any) -> int:
        self.seq += 1
        await repo.add_step(self.incident_id, self.seq, kind, name, **kw)
        return self.seq

    async def consume(self, node: str, state: dict) -> str:
        """Record one node's update. Returns any terminal text it carried."""
        messages = state.get("messages") or []
        node_seq = await self.record(
            "node", node, status="ok", ended=True, output=_summarize(state)
        )

        # The kernel dispatches probes by fan-out rather than by tool call, so a probe's
        # identity arrives in `probe_log` instead of on a ToolMessage. Each entry becomes a
        # child of the node that produced it, which is what keeps the step log a graph.
        for run in state.get("probe_log") or []:
            await self.record(
                "tool_result",
                run.get("probe_id", "probe"),
                parent_seq=node_seq,
                status=run.get("status", "ok"),
                ended=True,
                output={
                    "summary": str(run.get("summary", ""))[:4000],
                    "evidence_count": run.get("evidence_count", 0),
                    "round_index": run.get("round_index", 0),
                },
            )
            log.info(
                "[%s] probe %s -> %s (%s evidence)",
                self.incident_id,
                run.get("probe_id"),
                run.get("status"),
                run.get("evidence_count"),
            )

        calls = getattr(messages[-1], "tool_calls", None) if messages else None
        for call in calls or []:
            await self.record(
                "tool_call",
                call["name"],
                parent_seq=node_seq,
                status="ok",
                ended=True,
                input=dict(call.get("args") or {}),
            )
            log.info("[%s] sub-agent call %s(%s)", self.incident_id, call["name"], call["args"])

        await repo.set_current_step(self.incident_id, node)

        # Terminal text is taken as the last AI message carrying text, from whichever
        # node emitted it. The graph has more than one exit (finalize, graceful_exit),
        # and extraction keyed to a fixed set of node names silently returns nothing
        # on the paths it does not know about.
        from langchain_core.messages import AIMessage

        text = ""
        for msg in messages:
            if isinstance(msg, AIMessage) and (t := message_text(msg.content)):
                text = t
        return text


def _summarize(state: dict) -> dict:
    """Compact, JSON-safe view of a node's state delta.

    Hypothesis posteriors are recorded per step on purpose: replayed in order they are the
    belief trajectory, which is what makes "why did it conclude this?" answerable after the
    fact rather than a matter of re-reading a prompt.
    """
    out: dict[str, Any] = {}
    if (syn := state.get("synthesis")) is not None:
        out["synthesis"] = {
            "root_cause_service": getattr(syn, "root_cause_service", None),
            "confidence": getattr(syn, "confidence", None),
            "evidence_refs": list(getattr(syn, "evidence_refs", []) or []),
        }
    if (vr := state.get("verification_result")) is not None:
        out["verification_result"] = dict(vr)
    if candidates := state.get("candidate_services"):
        out["candidate_services"] = list(candidates)
    if evidence := state.get("evidence"):
        out["evidence_count"] = len(evidence)
    if hypotheses := state.get("hypotheses"):
        out["hypotheses"] = [
            {
                "id": h.id,
                "kind": h.kind,
                "service": h.subject_service,
                "posterior": round(h.posterior, 4),
                "status": h.status,
            }
            for h in hypotheses
        ]
    if (budget := state.get("budget")) is not None:
        out["budget"] = {
            "max_rounds": budget.max_rounds,
            "rounds_used": budget.rounds_used,
            "exit_reason": budget.exit_reason,
        }
    return out


async def run_incident(incident_id: uuid.UUID, ctx: AlertContext) -> None:
    """Drive the meta-agent for one incident. Must never raise — nothing awaits this."""
    async with _slots:
        started = time.monotonic()
        recorder = StepRecorder(incident_id)
        try:
            await repo.set_status(incident_id, "agent_running", "starting")
            log.info("[%s] %s -> agent (severity=%s)", ctx.service, ctx.alertname, ctx.severity)

            # Imported late: the kernel imports the LLM factory, which raises without an API
            # key. At module scope that would take the whole API down at startup instead of
            # failing this one incident.
            from langchain_core.messages import HumanMessage

            from src.agent.kernel.graph import DEFAULT_TEAM
            from src.agent.kernel.graph import app as meta_agent

            alert = ctx.to_kernel_alert()
            inputs = {
                # The rendered prompt rides along for tracing and the step log; the kernel
                # reasons over `alert`, not over this text.
                "messages": [HumanMessage(content=ctx.to_prompt())],
                "alert": alert,
                "team_id": alert.get("team") or DEFAULT_TEAM,
                "evidence": [],
                "probe_log": [],
                "seen_probe_keys": [],
                "candidate_services": [],
                "synthesis": None,
                "verification_result": None,
            }

            final = ""
            synthesis: Any = None
            async for update in meta_agent.astream(
                inputs, stream_mode="updates", config=trace_config(ctx, "agent")
            ):
                for node, state in update.items():
                    if not isinstance(state, dict):
                        continue
                    if state.get("synthesis") is not None:
                        synthesis = state["synthesis"]
                    if text := await recorder.consume(node, state):
                        final = text

            await repo.set_result(
                incident_id,
                status="done",
                final_answer=final or "meta-agent produced no final message",
                root_cause_service=getattr(synthesis, "root_cause_service", None),
                confidence=getattr(synthesis, "confidence", None),
                evidence_refs=list(getattr(synthesis, "evidence_refs", []) or []) or None,
            )
            log.info(
                "[%s] ROOT CAUSE ANALYSIS (%.1fs)\n%s",
                ctx.service,
                time.monotonic() - started,
                final,
            )
        except Exception as exc:
            log.exception("[%s] agent run failed", ctx.service)
            try:
                await repo.set_result(incident_id, status="failed", error=f"{type(exc).__name__}: {exc}")
            except Exception:
                log.exception("[%s] could not record failure", ctx.service)
        finally:
            # Agent tasks finish before Langfuse's batch timer fires; without this the
            # trace for a completed incident can sit unsent.
            tracing.flush()
