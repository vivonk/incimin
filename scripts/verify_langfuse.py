"""Confirm Langfuse tracing is actually wired up, before an incident is the thing that finds out.

    uv run python scripts/verify_langfuse.py

Four checks, each reporting the specific reason it failed rather than a bare traceback:

    1. credentials present in the environment
    2. handler constructs
    3. credentials are accepted by the host (auth_check)
    4. a real trace lands — one LLM-free span, flushed synchronously

Exit code is 0 only when all four pass. Check 4 emits a trace tagged `incimin-verify` that is
safe to delete from the Langfuse UI.
"""
from __future__ import annotations

import os
import sys
import uuid

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent import tracing

PASS, FAIL = "PASS", "FAIL"


def _report(check: str, ok: bool, detail: str = "") -> bool:
    print(f"[{PASS if ok else FAIL}] {check}" + (f" — {detail}" if detail else ""))
    return ok


def check_credentials() -> bool:
    missing = [
        name
        for name in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
        if not os.getenv(name)
    ]
    if missing:
        return _report("credentials", False, f"missing: {', '.join(missing)}")
    if not tracing.tracing_enabled():
        return _report("credentials", False, "LANGFUSE_TRACING_ENABLED is set to a false value")
    return _report("credentials", True, f"host={tracing.langfuse_host()}")


def check_handler() -> bool:
    handler = tracing.get_handler()
    if handler is None:
        return _report("handler", False, "get_handler() returned None — see the warning above")
    return _report("handler", True, type(handler).__name__)


def check_auth() -> bool:
    try:
        from langfuse import get_client

        get_client().auth_check()
    except Exception as exc:
        hint = ""
        if "certificate" in str(exc).lower() or "ssl" in str(exc).lower():
            hint = " (TLS-intercepting proxy? try LANGFUSE_VERIFY_SSL=false)"
        return _report("auth", False, f"{exc}{hint}")
    return _report("auth", True, "keys accepted")


def check_trace() -> bool:
    """Emit and flush one span, so a green run means traces genuinely arrive."""
    marker = uuid.uuid4().hex[:8]
    try:
        from langfuse import get_client

        client = get_client()
        with client.start_as_current_observation(name="incimin-verify", as_type="span") as span:
            span.update(input={"marker": marker}, output={"status": "ok"})
            trace_id = span.trace_id
        client.flush()
    except Exception as exc:
        return _report("trace delivery", False, str(exc))
    return _report("trace delivery", True, f"trace_id={trace_id} marker={marker}")


CHECKS = (
    ("credentials", check_credentials),
    ("handler", check_handler),
    ("auth", check_auth),
    ("trace delivery", check_trace),
)


def main() -> int:
    print(f"Verifying Langfuse tracing against {tracing.langfuse_host()}\n")
    for name, check in CHECKS:
        # Each check depends on the previous one having passed; stop at the first failure
        # rather than cascading four confusing errors from one missing key.
        if not check():
            print(f"\nFAILED at: {name}")
            return 1
    print("\nAll checks passed — agent runs will appear in Langfuse.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
