"""Deterministic belief update.

**The LLM never emits a number.** It returns one of five ordinal verdicts per
(hypothesis, evidence) pair; this module maps those to fixed likelihood ratios and does the
arithmetic in code.

Two reasons, both load-bearing:

  - *Replayability.* The belief trajectory can be recomputed exactly from the verdict log, so
    an incident review can ask "why did it converge on this?" and get an arithmetic answer.
  - *Calibration.* A model asked directly for a probability will happily emit 0.85 for two
    unrelated pieces of evidence in the same batch. Asked to pick from five ordered labels, it
    is doing the comparative judgement it is actually good at.

The ratios below are a starting point, not a result. Only the Phase 17 eval harness can
calibrate them; until then treat them as a documented guess.
"""
import math
from typing import Literal

from pydantic import BaseModel, Field

from src.agent.kernel.state import Hypothesis

Verdict = Literal["strongly_supports", "supports", "neutral", "weakens", "refutes"]

LIKELIHOOD_RATIO: dict[Verdict, float] = {
    "strongly_supports": 4.0,
    "supports": 2.0,
    "neutral": 1.0,
    "weakens": 0.5,
    "refutes": 0.1,
}

# Below this, a hypothesis is not worth carrying into another round of probing.
PRUNE_FLOOR = 1e-4


class EvidenceVerdict(BaseModel):
    hypothesis_id: str
    evidence_id: str
    verdict: Verdict
    rationale: str = ""


class VerdictBatch(BaseModel):
    """Structured output schema for the judging LLM call."""

    verdicts: list[EvidenceVerdict] = Field(default_factory=list)


class BeliefUpdate(BaseModel):
    hypotheses: list[Hypothesis]
    rejected_verdicts: list[str] = Field(default_factory=list)


def seed_posteriors(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    """Normalize priors to sum to 1 and copy them into posteriors."""
    out = [h.model_copy(deep=True) for h in hypotheses]
    total = sum(max(h.prior, 0.0) for h in out)
    if total <= 0:
        uniform = 1.0 / len(out) if out else 0.0
        for h in out:
            h.prior = uniform
            h.posterior = uniform
        return out
    for h in out:
        h.prior = max(h.prior, 0.0) / total
        h.posterior = h.prior
    return out


def apply_verdicts(hypotheses: list[Hypothesis], verdicts: list[EvidenceVerdict]) -> BeliefUpdate:
    """Fold a round of verdicts into posteriors. Pure — no I/O, no clock, no model."""
    by_id = {h.id: h.model_copy(deep=True) for h in hypotheses}
    rejected: list[str] = []

    for v in verdicts:
        h = by_id.get(v.hypothesis_id)
        if h is None:
            rejected.append(f"unknown hypothesis {v.hypothesis_id!r}")
            continue
        # A refuted hypothesis stays refuted. Without this, a later "supports" verdict could
        # resurrect a claim that contradictory evidence already eliminated — the contradiction
        # check the design calls for, in its narrowest defensible form.
        if h.status == "refuted":
            rejected.append(f"{v.evidence_id} -> {v.hypothesis_id} (already refuted)")
            continue
        if v.evidence_id in h.supporting_refs or v.evidence_id in h.refuting_refs:
            rejected.append(f"duplicate verdict {v.evidence_id} -> {v.hypothesis_id}")
            continue

        h.posterior *= LIKELIHOOD_RATIO[v.verdict]

        if v.verdict == "refutes":
            h.status = "refuted"
            h.posterior = 0.0
            h.refuting_refs.append(v.evidence_id)
        elif v.verdict == "weakens":
            h.refuting_refs.append(v.evidence_id)
        elif v.verdict in ("supports", "strongly_supports"):
            h.supporting_refs.append(v.evidence_id)

    updated = list(by_id.values())
    _prune(updated)
    _renormalize(updated)
    return BeliefUpdate(hypotheses=updated, rejected_verdicts=rejected)


def _prune(hypotheses: list[Hypothesis]) -> None:
    for h in hypotheses:
        if h.status == "open" and h.posterior < PRUNE_FLOOR:
            h.status = "refuted"
            h.posterior = 0.0


def _renormalize(hypotheses: list[Hypothesis]) -> None:
    """Redistribute mass across surviving hypotheses so posteriors sum to 1."""
    open_ = [h for h in hypotheses if h.status != "refuted"]
    total = sum(h.posterior for h in open_)
    if not open_:
        return
    if total <= 0:
        # Everything collapsed numerically but nothing was explicitly refuted. Fall back to
        # uniform rather than emitting NaNs — the budget will stop the loop soon enough.
        uniform = 1.0 / len(open_)
        for h in open_:
            h.posterior = uniform
        return
    for h in open_:
        h.posterior /= total


def leader(hypotheses: list[Hypothesis]) -> Hypothesis | None:
    """Highest-posterior open hypothesis. Ties break on id for replayability."""
    open_ = [h for h in hypotheses if h.status != "refuted"]
    if not open_:
        return None
    return max(open_, key=lambda h: (h.posterior, h.id))


def top_two(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    open_ = [h for h in hypotheses if h.status != "refuted"]
    return sorted(open_, key=lambda h: (-h.posterior, h.id))[:2]


def normalized_entropy(hypotheses: list[Hypothesis]) -> float:
    """Ambiguity in [0, 1]: 0 when one hypothesis holds all mass, 1 when mass is uniform.

    Drives the adaptive round budget — a clear alert gets one round, a genuinely ambiguous one
    earns more.
    """
    open_ = [h for h in hypotheses if h.status != "refuted"]
    probs = [h.posterior for h in open_ if h.posterior > 0]
    if len(probs) <= 1:
        return 0.0
    entropy = -sum(p * math.log(p) for p in probs)
    return min(1.0, entropy / math.log(len(probs)))
