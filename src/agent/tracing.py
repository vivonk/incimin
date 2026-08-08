"""Langfuse tracing for the meta-agent.

Every agent entry point routes its run through `trace_config()`, which returns a
`RunnableConfig` carrying a Langfuse `CallbackHandler`. LangChain propagates that config down
through the graph, so one call at the top produces the whole tree: the Coordinator's
tool-calling turns, the structured-output synthesis step, and the LLM calls the telemetry and
knowledge sub-agents make inside their tools (those inherit the handler through LangChain's
config contextvar — they take no config argument of their own).

**Tracing never breaks an agent run.** The package may be missing, the keys may be absent, the
Langfuse host may be unreachable behind a corporate proxy. Each of those degrades to a config
with no callbacks, logged once, and the run proceeds untraced. An un-triaged incident is a far
worse outcome than a missing trace.

The handler is built once and shared. It is resolved lazily rather than at import so that
importing this module stays free of side effects — `src.agent.graph` is deliberately imported
late (see `src/webhook/app.py`) and must not acquire a new import-time failure mode.

Environment:
    LANGFUSE_PUBLIC_KEY      required to enable tracing
    LANGFUSE_SECRET_KEY      required to enable tracing
    LANGFUSE_BASE_URL        Langfuse host (default https://cloud.langfuse.com)
    LANGFUSE_HOST            legacy alias for LANGFUSE_BASE_URL; read by the SDK itself
    LANGFUSE_TRACING_ENABLED set to `false` to disable without removing the keys
    LANGFUSE_VERIFY_SSL      set to `false` for a TLS-intercepting corporate proxy
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Iterable

from dotenv import load_dotenv

load_dotenv(override=False)

log = logging.getLogger("incimin.tracing")

# Resolution is cached behind a lock: the webhook runs agents on concurrent threads, and
# building two clients would emit two independent OTel exporters for the same project.
_handler: Any = None
_resolved = False
_lock = threading.Lock()


def _falsey(value: str | None) -> bool:
    return (value or "").strip().lower() in {"false", "0", "no", "off"}


def tracing_enabled() -> bool:
    """True when both keys are present and tracing has not been explicitly switched off.

    Mirrors the SDK's own gate so callers (and `scripts/verify_langfuse.py`) can report *why*
    tracing is inactive without constructing a client first.
    """
    if _falsey(os.getenv("LANGFUSE_TRACING_ENABLED")):
        return False
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def _build_handler() -> Any:
    """Construct the client and its callback handler, or return None with a reason logged."""
    if not tracing_enabled():
        log.info(
            "Langfuse tracing disabled — set LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY to enable"
        )
        return None

    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler
    except ImportError as exc:
        log.warning("Langfuse tracing disabled — import failed: %s", exc)
        return None

    kwargs: dict[str, Any] = {}
    # `src.agent.llm` disables certificate verification process-wide for TLS-intercepting
    # proxies, but it does so by patching `ssl.create_default_context`, which Langfuse's httpx
    # client does not route through. Hence an explicit opt-out rather than an inherited one.
    if _falsey(os.getenv("LANGFUSE_VERIFY_SSL")):
        try:
            import httpx

            kwargs["httpx_client"] = httpx.Client(verify=False, timeout=10)
        except Exception as exc:  # pragma: no cover - httpx is a hard dependency
            log.warning("could not build an unverified httpx client for Langfuse: %s", exc)

    try:
        # Constructing the client registers it as the process singleton; CallbackHandler()
        # then picks it up via get_client(). Base URL, keys and the LANGFUSE_HOST fallback are
        # all resolved from the environment by the SDK itself.
        Langfuse(**kwargs)
        handler = CallbackHandler()
    except Exception as exc:
        log.warning("Langfuse tracing disabled — client setup failed: %s", exc)
        return None

    log.info("Langfuse tracing enabled (host=%s)", langfuse_host())
    return handler


def get_handler() -> Any:
    """The shared CallbackHandler, or None when tracing is unavailable. Resolved once."""
    global _handler, _resolved
    if _resolved:
        return _handler
    with _lock:
        if not _resolved:
            _handler = _build_handler()
            _resolved = True
    return _handler


def langfuse_host() -> str:
    return (
        os.getenv("LANGFUSE_BASE_URL")
        or os.getenv("LANGFUSE_HOST")
        or "https://cloud.langfuse.com"
    )


def _clean_tags(tags: Iterable[str | None] | None) -> list[str]:
    """Drop blanks and duplicates, preserving order.

    None is skipped rather than stringified: callers build tag lists straight from optional
    alert fields (`ctx.severity`, `ctx.service`), and a literal "None" tag in the Langfuse UI is
    worse than no tag at all.
    """
    seen: list[str] = []
    for tag in tags or []:
        if tag is None:
            continue
        text = str(tag).strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def trace_config(
    name: str,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    tags: Iterable[str | None] | None = None,
    metadata: dict[str, Any] | None = None,
    base: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the RunnableConfig for one traced agent run.

    Returns a plain config (merely `base`, or `{}`) when tracing is off, so call sites pass the
    result to `.invoke()` / `.stream()` unconditionally and never branch on whether tracing is
    configured.

    Trace-level attributes travel as `langfuse_*` metadata keys, which the handler lifts off and
    strips before recording the remaining metadata on the trace.
    """
    config: dict[str, Any] = dict(base or {})

    handler = get_handler()
    if handler is None:
        return config

    combined: dict[str, Any] = dict(metadata or {})
    combined["langfuse_trace_name"] = name
    if session_id:
        combined["langfuse_session_id"] = str(session_id)
    if user_id:
        combined["langfuse_user_id"] = str(user_id)
    cleaned = _clean_tags(tags)
    if cleaned:
        combined["langfuse_tags"] = cleaned

    # Merge rather than overwrite: a caller passing `base` may already carry its own callbacks
    # (LangSmith, for one) and dropping them here would silently disable that integration.
    callbacks = config.get("callbacks") or []
    if not isinstance(callbacks, list):
        callbacks = [callbacks]
    config["callbacks"] = [*callbacks, handler]
    config["run_name"] = name
    config["metadata"] = {**config.get("metadata", {}), **combined}
    return config


def flush() -> None:
    """Push buffered spans now.

    The SDK batches on a timer, which is wrong for both of our shapes: the webhook's agent
    threads finish long before the next interval, and short-lived scripts exit before it fires.
    """
    if not _resolved or _handler is None:
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception as exc:
        log.debug("Langfuse flush failed: %s", exc)


def reset() -> None:
    """Drop the cached handler so the next call re-resolves. Tests only."""
    global _handler, _resolved
    with _lock:
        _handler = None
        _resolved = False
