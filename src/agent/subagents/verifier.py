"""Verifier sub-agent — Layer 1 only (deterministic gates), per MULTI_AGENT_ARCHITECTURE.md §6 and
§9's Non-goals: Layer 1 always runs and is never bypassed; Layer 2 (optional LLM judgment) is
deliberately NOT implemented in this pass — recommended off for the golden-path demo.

Pure function, no I/O, no LLM. Runs unconditionally right before the graph can end successfully.
"""
import time

from src.agent.state import Evidence, Synthesis, VerificationResult

# Generous window for demo/dev use — this project has no formal "alert time" input yet
# (MULTI_AGENT_ARCHITECTURE.md §8 flags this as a simplification vs. the K8s-paper's
# "cause must predate the alert" check, which assumes a known alert timestamp).
MAX_EVIDENCE_AGE_NS = 24 * 60 * 60 * 1_000_000_000  # 24h


def verify(
    evidence: list[Evidence],
    candidate_services: list[str],
    synthesis: Synthesis | None,
) -> VerificationResult:
    if synthesis is None:
        return {
            "passed": False,
            "failed_checks": ["missing_synthesis"],
            "detail": "No synthesis was produced to verify.",
        }

    failed: list[str] = []
    details: list[str] = []

    _check_evidence_grounding(synthesis, evidence, failed, details)
    _check_cross_modal_consistency(synthesis, evidence, candidate_services, failed, details)
    _check_temporal_ordering(evidence, failed, details)

    passed = not failed
    return {
        "passed": passed,
        "failed_checks": sorted(set(failed)),
        "detail": " ".join(details) if details else "All checks passed.",
    }


def _check_evidence_grounding(
    synthesis: Synthesis, evidence: list[Evidence], failed: list[str], details: list[str]
) -> None:
    evidence_by_id = {e["id"]: e for e in evidence}

    if not synthesis.evidence_refs:
        failed.append("evidence_grounding")
        details.append("Synthesis cites no evidence_refs.")
        return

    missing_refs = [ref for ref in synthesis.evidence_refs if ref not in evidence_by_id]
    if missing_refs:
        failed.append("evidence_grounding")
        details.append(f"evidence_refs not found in evidence: {missing_refs}.")

    mismatched_refs = [
        ref
        for ref in synthesis.evidence_refs
        if ref in evidence_by_id and evidence_by_id[ref]["service"] != synthesis.root_cause_service
    ]
    if mismatched_refs:
        failed.append("evidence_grounding")
        details.append(
            f"evidence_refs belong to a different service than the claim ({synthesis.root_cause_service}): "
            f"{mismatched_refs}."
        )


def _check_cross_modal_consistency(
    synthesis: Synthesis,
    evidence: list[Evidence],
    candidate_services: list[str],
    failed: list[str],
    details: list[str],
) -> None:
    topology_agrees = synthesis.root_cause_service in candidate_services
    telemetry_agrees = any(
        e["service"] == synthesis.root_cause_service for e in evidence if e["source"] == "telemetry"
    )
    if not (topology_agrees and telemetry_agrees):
        failed.append("cross_modal_consistency")
        details.append(
            f"topology_agrees={topology_agrees}, telemetry_agrees={telemetry_agrees} for "
            f"'{synthesis.root_cause_service}'."
        )


def _check_temporal_ordering(evidence: list[Evidence], failed: list[str], details: list[str]) -> None:
    now_ns = time.time_ns()
    stale_or_future = [
        e["id"]
        for e in evidence
        if e["source"] == "telemetry"
        and e["timestamp"] is not None
        and (e["timestamp"] > now_ns or e["timestamp"] < now_ns - MAX_EVIDENCE_AGE_NS)
    ]
    if stale_or_future:
        failed.append("temporal_ordering")
        details.append(f"telemetry evidence outside the valid time window: {stale_or_future}.")
