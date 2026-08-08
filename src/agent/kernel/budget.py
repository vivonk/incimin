"""Round budgeting and stopping rules.

Evidence sufficiency is decided here, in code, and never by the model. "Don't Let Me Ask for
It" (arXiv 2608.03388) measured LLMs systematically under-asking during multi-turn abduction —
they stop gathering too early and commit. So the loop's continue/stop decision is arithmetic
over posteriors and a counter, not a judgement call handed to the coordinator.
"""
from typing import Literal

from src.agent.kernel.beliefs import leader, normalized_entropy
from src.agent.kernel.state import Budget, Hypothesis

B_MIN = 1
B_MAX = 5
DEFAULT_TAU = 0.90

StopReason = Literal["", "converged", "budget_exhausted", "all_refuted", "no_discriminating_probe"]


def size_budget(
    hypotheses: list[Hypothesis], *, b_min: int = B_MIN, b_max: int = B_MAX
) -> Budget:
    """`B = min(B_max, B_min + ambiguity)` — more rounds only when the field is genuinely open.

    A single dominant hypothesis converges in one round; three near-equal ones earn the full
    budget. This is what replaces v1's flat `remaining_steps=10` regardless of the incident.
    """
    ambiguity = normalized_entropy(hypotheses)
    span = max(0, b_max - b_min)
    return Budget(max_rounds=min(b_max, b_min + round(ambiguity * span)))


def stop_reason(
    hypotheses: list[Hypothesis],
    budget: Budget,
    *,
    tau: float = DEFAULT_TAU,
    has_discriminating_probe: bool = True,
) -> StopReason:
    """Four independent terminal conditions. Order matters: convergence wins over exhaustion,
    so a run that converges on its last permitted round is reported as converged, not starved.
    """
    open_ = [h for h in hypotheses if h.status != "refuted"]
    if not open_:
        return "all_refuted"

    top = leader(hypotheses)
    if top is not None and top.posterior >= tau:
        return "converged"

    if budget.exhausted:
        return "budget_exhausted"

    if not has_discriminating_probe:
        return "no_discriminating_probe"

    return ""


def converged_on_confidence(reason: StopReason) -> bool:
    """Only a τ-crossing earns `confidence="high"`.

    A run that ran out of rounds may still have a leader with respectable mass, but it never
    got the chance to be refuted. The verifier's `budget_honesty` gate depends on this.
    """
    return reason == "converged"
