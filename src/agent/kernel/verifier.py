"""Layer 1 verification gates — deterministic, pure, unbypassable.

Evolves `src/agent/subagents/verifier.py`. Three gates carried over, two added, one fixed:

  - `cross_source_consistency` **generalized.** v1 hardcoded "topology AND telemetry", which
    silently broke the moment a team added a third source. It now requires N distinct sources,
    which is the property the check was always really asserting.
  - `temporal_ordering` **fixed.** v1 compared against `now` because the alert timestamp never
    reached graph state, even though `AlertContext` carried it. A cause must predate its alert;
    comparing to wall-clock could not express that.
  - `refutation_integrity` and `budget_honesty` are new.

Still Layer 1 only. Layer 2 (an adversarial LLM judge) stays deliberately unimplemented — a
second call to the same model is not independent just because it runs in a different node.
"""
import time

from src.agent.kernel.beliefs import leader
from src.agent.kernel.state import Evidence, Hypothesis, VerificationResult

# How far before the alert evidence may reach back and still be considered causally relevant.
MAX_LOOKBACK_NS = 24 * 60 * 60 * 1_000_000_000  # 24h
# Symptoms keep arriving after an alert fires; a log line from 5 minutes later still describes
# the same failure. Causes must predate the alert, but evidence need not.
POST_ALERT_GRACE_NS = 15 * 60 * 1_000_000_000  # 15m

DEFAULT_MIN_DISTINCT_SOURCES = 2


def verify(
    hypotheses: list[Hypothesis],
    evidence: list[Evidence],
    *,
    alert_fired_at_ns: int | None = None,
    stop_reason: str = "",
    min_distinct_sources: int = DEFAULT_MIN_DISTINCT_SOURCES,
) -> VerificationResult:
    winner = leader(hypotheses)
    if winner is None:
        return {
            "passed": False,
            "failed_checks": ["no_surviving_hypothesis"],
            "detail": "Every hypothesis was refuted; nothing to verify.",
        }

    failed: list[str] = []
    details: list[str] = []
    by_id = {e["id"]: e for e in evidence}

    _check_evidence_grounding(winner, by_id, failed, details)
    _check_cross_source_consistency(winner, by_id, min_distinct_sources, failed, details)
    _check_temporal_ordering(winner, by_id, alert_fired_at_ns, failed, details)
    _check_refutation_integrity(winner, failed, details)
    _check_budget_honesty(stop_reason, failed, details)

    return {
        "passed": not failed,
        "failed_checks": sorted(set(failed)),
        "detail": " ".join(details) if details else "All checks passed.",
    }


def _check_evidence_grounding(
    winner: Hypothesis, by_id: dict[str, Evidence], failed: list[str], details: list[str]
) -> None:
    if not winner.supporting_refs:
        failed.append("evidence_grounding")
        details.append("Winning hypothesis cites no supporting evidence.")
        return

    missing = [r for r in winner.supporting_refs if r not in by_id]
    if missing:
        failed.append("evidence_grounding")
        details.append(f"supporting_refs not found in evidence: {missing}.")

    mismatched = [
        r
        for r in winner.supporting_refs
        if r in by_id and by_id[r]["service"] != winner.subject_service
    ]
    if mismatched:
        failed.append("evidence_grounding")
        details.append(
            f"supporting_refs belong to a service other than '{winner.subject_service}': {mismatched}."
        )


def _check_cross_source_consistency(
    winner: Hypothesis,
    by_id: dict[str, Evidence],
    min_distinct: int,
    failed: list[str],
    details: list[str],
) -> None:
    sources = {by_id[r]["source"] for r in winner.supporting_refs if r in by_id}
    if len(sources) < min_distinct:
        failed.append("cross_source_consistency")
        details.append(
            f"claim rests on {len(sources)} evidence source(s) {sorted(sources)}, "
            f"needs at least {min_distinct}."
        )


def _check_temporal_ordering(
    winner: Hypothesis,
    by_id: dict[str, Evidence],
    alert_fired_at_ns: int | None,
    failed: list[str],
    details: list[str],
) -> None:
    now_ns = time.time_ns()
    reference = alert_fired_at_ns or now_ns
    latest_allowed = min(now_ns, reference + POST_ALERT_GRACE_NS)
    earliest_allowed = reference - MAX_LOOKBACK_NS

    offending = [
        r
        for r in winner.supporting_refs
        if r in by_id
        and by_id[r]["timestamp"] is not None
        and not (earliest_allowed <= by_id[r]["timestamp"] <= latest_allowed)
    ]
    if offending:
        failed.append("temporal_ordering")
        details.append(
            f"evidence outside the causal window around the alert: {offending}."
        )


def _check_refutation_integrity(winner: Hypothesis, failed: list[str], details: list[str]) -> None:
    if winner.refuting_refs:
        failed.append("refutation_integrity")
        details.append(
            f"winning hypothesis still carries contradicting evidence: {winner.refuting_refs}."
        )


def _check_budget_honesty(stop_reason: str, failed: list[str], details: list[str]) -> None:
    """Not a correctness failure — a truthfulness one.

    Running out of rounds is a legitimate outcome and must not be dressed up as a confident
    answer. This does not fail the run; it records why confidence is capped.
    """
    if stop_reason and stop_reason != "converged":
        details.append(f"stopped on '{stop_reason}' rather than reaching the confidence threshold.")
