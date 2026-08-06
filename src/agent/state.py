import operator
from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class Evidence(TypedDict):
    """A single fact produced by a sub-agent. The unit every downstream check operates on."""

    id: str
    source: Literal["topology", "telemetry", "knowledge"]
    service: str
    summary: str
    raw: dict
    timestamp: int | None  # nanosecond epoch; telemetry only, None for topology/knowledge


class Synthesis(BaseModel):
    """Structured output the meta-agent (Coordinator) must produce before the Verifier can check it.

    Deliberately not free text: the Verifier's evidence-grounding check (subagents/verifier.py)
    depends on evidence_refs being concrete, checkable IDs rather than unconstrained prose.
    """

    root_cause_service: str
    evidence_refs: list[str] = Field(default_factory=list)
    remediation_runbook_id: str | None = None
    confidence: Literal["high", "low"] = "low"


class VerificationResult(TypedDict):
    passed: bool
    failed_checks: list[str]
    detail: str


class SREAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    remaining_steps: int
    evidence: Annotated[list[Evidence], operator.add]
    candidate_services: list[str]
    synthesis: Synthesis | None
    verification_result: VerificationResult | None
