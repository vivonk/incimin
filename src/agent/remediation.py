"""Allowlisted remediation actions.

The security boundary for the whole human-in-the-loop feature. Two rules hold
absolutely:

1. **The LLM never composes a command.** It may only select an action id that
   already exists in `ACTIONS`, and the arguments are validated here, not
   wherever the proposal came from.
2. **Nothing runs without a recorded human approval.** This module executes; it
   never decides. The caller is responsible for having claimed an approval row
   first (see `repository.claim_approval`).

`subprocess.run` is always called with a list argv and never `shell=True`, so a
service name cannot smuggle shell metacharacters even if validation were bypassed.
"""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger("incimin.remediation")

EXEC_TIMEOUT_SECONDS = 60

# Docker names this project must never touch: the observability stack the agent
# reasons *with*, and its own state. Restarting ClickHouse mid-incident would
# blind the agent; restarting Postgres would drop the checkpoint it resumes from.
PROTECTED = re.compile(
    r"^(signoz|clickhouse|incimin-postgres|incimin-memgraph|incimin-ingester|.*keeper).*",
    re.IGNORECASE,
)

# Container names are lowercase alphanumerics with dashes/underscores. Anything
# else is rejected before it reaches argv.
_VALID_NAME = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,62}$")


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    detail: str
    argv: list[str]
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "detail": self.detail,
            "argv": self.argv,
            "stdout": self.stdout[-4000:],
            "stderr": self.stderr[-4000:],
            "returncode": self.returncode,
        }


@dataclass(frozen=True)
class Action:
    id: str
    description: str
    # Human-readable statement of what will happen, shown before anyone approves.
    render: Callable[[str], str]
    build_argv: Callable[[str], list[str]]


def running_containers() -> set[str]:
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return {n.strip() for n in out.stdout.splitlines() if n.strip()}
    except Exception:  # noqa: BLE001
        log.exception("could not list containers")
        return set()


def resolve_target(service: str) -> tuple[str | None, str]:
    """Map a hypothesis's service name to a real container.

    Topology and container names mostly agree (`payment`, `cart`), but an alert's
    `service.name` label may carry the `-service` / `service` suffix convention
    (`paymentservice`). One suffix strip is attempted, and the result must still
    match a *running* container — resolution never invents a target.

    Returns `(container, reason)`; container is None when nothing safe matched.
    """
    if not service or not _VALID_NAME.match(service):
        return None, f"{service!r} is not a valid container name"

    running = running_containers()
    if not running:
        return None, "could not enumerate running containers"

    candidates = [service]
    for suffix in ("-service", "_service", "service"):
        if service.endswith(suffix) and len(service) > len(suffix):
            candidates.append(service[: -len(suffix)])

    for name in candidates:
        if name in running:
            if PROTECTED.match(name):
                return None, f"{name} is protected infrastructure and may not be restarted"
            return name, f"resolved {service} -> {name}"

    return None, f"no running container matches {service} (tried {candidates})"


ACTIONS: dict[str, Action] = {
    "restart_service": Action(
        id="restart_service",
        description="Restart the service's container.",
        render=lambda c: f"Restart container {c!r} (docker restart). Brief downtime for that service.",
        build_argv=lambda c: ["docker", "restart", c],
    ),
}


def propose(action_id: str, service: str) -> dict:
    """Build a proposal for a human to read. Does not execute anything.

    The resolved container and the exact argv are bound *now* and carried on the
    proposal, so what a human approves is what later runs — re-deriving the target
    at execution time would let live state change what was agreed to.
    """
    action = ACTIONS.get(action_id)
    if action is None:
        return {
            "action_id": action_id,
            "executable": False,
            "reason": f"{action_id!r} is not an allowlisted action",
        }

    container, reason = resolve_target(service)
    if container is None:
        return {
            "action_id": action_id,
            "service": service,
            "executable": False,
            "reason": reason,
        }

    return {
        "action_id": action_id,
        "service": service,
        "container": container,
        "argv": action.build_argv(container),
        "statement": action.render(container),
        "executable": True,
        "reason": reason,
    }


def execute(proposal: dict) -> ActionResult:
    """Run a previously-approved proposal.

    Re-validates rather than trusting the stored proposal: a row could have been
    written before the allowlist changed, and the cost of checking again is a
    dictionary lookup.
    """
    action_id = proposal.get("action_id", "")
    action = ACTIONS.get(action_id)
    if action is None:
        return ActionResult(False, f"{action_id!r} is not an allowlisted action", [])

    container = proposal.get("container") or ""
    if not _VALID_NAME.match(container):
        return ActionResult(False, f"{container!r} is not a valid container name", [])
    if PROTECTED.match(container):
        return ActionResult(False, f"{container} is protected infrastructure", [])

    # Rebuilt from the allowlist, never taken from the stored proposal — a stored
    # argv is data, and data must not become a command line.
    argv = action.build_argv(container)

    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=EXEC_TIMEOUT_SECONDS, check=False
        )
    except subprocess.TimeoutExpired:
        return ActionResult(False, f"timed out after {EXEC_TIMEOUT_SECONDS}s", argv)
    except Exception as e:  # noqa: BLE001
        return ActionResult(False, f"{type(e).__name__}: {e}", argv)

    ok = proc.returncode == 0
    return ActionResult(
        ok=ok,
        detail=("restarted " + container) if ok else f"exit {proc.returncode}",
        argv=argv,
        stdout=proc.stdout,
        stderr=proc.stderr,
        returncode=proc.returncode,
    )
