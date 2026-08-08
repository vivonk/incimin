"""Kernel state: evidence, hypotheses, budget.

Two deliberate departures from `src/agent/state.py` (v1):

1. `Evidence.source` is an open `str`, not a `Literal`. In v1 adding an evidence plane meant
   editing a core type, which made the "a new sub-agent touches nothing" claim false. Sources
   are now validated against `SOURCE_REGISTRY` when a probe registers, so the check moved from
   the type system to registration time without being lost.
2. The unit of reasoning is a `Hypothesis` with a posterior, not a single `Synthesis`. That is
   what lets the agent report what it ruled out, and what gives the loop something to converge.
"""
import operator
from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

# Hypothesis kinds the kernel ships with. Probes declare which of these they can discriminate
# between; playbooks declare which they seed. Teams may register additional kinds alongside a
# probe that discriminates them (see probes/registry.py) — the kernel does not treat this list
# as closed, only as the set it can reason about out of the box.
BASE_HYPOTHESIS_KINDS: tuple[str, ...] = (
    "deploy_regression",
    "resource_exhaustion",
    "dependency_failure",
    "config_change",
    "traffic_anomaly",
    "external_dependency",
    "data_issue",
)


class Evidence(TypedDict):
    """A single fact produced by a probe. The unit every downstream check operates on."""

    id: str
    source: str  # open; validated against SOURCE_REGISTRY at probe registration
    service: str
    summary: str
    raw: dict
    timestamp: int | None  # nanosecond epoch; None when the source is atemporal (e.g. topology)


class Hypothesis(BaseModel):
    """A candidate explanation, carrying its own belief mass.

    `posterior` is written only by `kernel.beliefs`, never by an LLM — see that module for why.
    """

    id: str
    kind: str
    statement: str
    subject_service: str
    origin: Literal["playbook", "topology", "history", "llm", "mcp"]
    prior: float = 0.0
    posterior: float = 0.0
    status: Literal["open", "refuted", "confirmed"] = "open"
    supporting_refs: list[str] = Field(default_factory=list)
    refuting_refs: list[str] = Field(default_factory=list)


class Budget(BaseModel):
    """Round budget for the loop. Sized once at seed time from hypothesis ambiguity.

    Replaces v1's flat `remaining_steps`, which was decremented only in the coordinator node and
    left probe-internal LLM calls entirely unbudgeted.
    """

    max_rounds: int = 1
    rounds_used: int = 0
    exit_reason: str = ""

    @property
    def exhausted(self) -> bool:
        return self.rounds_used >= self.max_rounds


class Synthesis(BaseModel):
    """The winning hypothesis, flattened.

    Exists purely so `src/api/runner.py` keeps populating `incidents.root_cause_service` /
    `confidence` / `evidence_refs` unchanged. The kernel reasons over `Hypothesis`; this is the
    projection the persistence layer already understands, and keeping it means the v1.7 API
    did not have to be rewritten alongside the agent.
    """

    root_cause_service: str
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: Literal["high", "low"] = "low"


class VerificationResult(TypedDict):
    passed: bool
    failed_checks: list[str]
    detail: str


class ProbeRun(TypedDict):
    """One probe execution, for the audit trail and for dedup."""

    probe_id: str
    dedup_key: str
    status: str
    summary: str
    evidence_count: int
    round_index: int


class IncidentState(TypedDict, total=False):
    """Graph state for the kernel loop.

    Reducer notes:
      - `evidence` and `probe_log` accumulate across parallel probe branches, so both need
        `operator.add`. Anything a fanned-out probe writes must have a reducer or LangGraph
        raises `InvalidUpdateError`.
      - `hypotheses` and `budget` are written only by `seed` and `update_beliefs`, both single
        nodes on the critical path. Plain last-write-wins is correct; do not fan out a writer
        of these without adding a merge reducer first.
    """

    messages: Annotated[list, add_messages]
    alert: dict
    team_id: str
    candidate_services: list[str]
    hypotheses: list[Hypothesis]
    evidence: Annotated[list[Evidence], operator.add]
    probe_log: Annotated[list[ProbeRun], operator.add]
    seen_probe_keys: Annotated[list[str], operator.add]
    budget: Budget
    round_index: int
    verification_result: VerificationResult
    synthesis: Synthesis | None

    # Human-in-the-loop. `remediation_proposal` is written by `propose_remediation`
    # and is what a human reads before deciding; `approval_decision` and
    # `escalation_decision` are what `interrupt()` returns once they have. All are
    # last-write-wins single-node writes — do not fan out a writer of these.
    remediation_proposal: dict | None
    approval_decision: dict | None
    execution_result: dict | None
    escalation_decision: dict | None
