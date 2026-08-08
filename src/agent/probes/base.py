"""The probe contract.

Design constraints, in the order they mattered:

  - The kernel must be able to *select* a probe without invoking a model. Hence
    `discriminates` and `cost_tier` on the manifest: selection is a table join, not a prompt.
  - A probe must never abort an investigation. `run` returns a status; it does not raise.
  - A probe's cost must be visible before it runs, so the budget can be enforced up front.
"""
import hashlib
import json
import time
from typing import Any, ClassVar, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

from src.agent.kernel.state import Evidence

CostTier = Literal["cheap", "normal", "expensive"]

# Selection divides a probe's discrimination score by its cost weight, so a cheap probe wins
# ties against an expensive one that discriminates equally well. Cheap breadth first, expensive
# depth only on finalists.
COST_WEIGHT: dict[CostTier, float] = {"cheap": 1.0, "normal": 2.0, "expensive": 5.0}


class ProbeConfig(BaseSettings):
    """Per-probe settings, env-backed.

    Kept from `src/production/topology/plugin.py`'s `PluginConfig`: a subclass per probe means
    each probe declares its own connection/credential schema instead of reaching into a shared
    settings blob. That part of the old plugin design was right.
    """


class TimeWindow(BaseModel):
    start_ns: int
    end_ns: int

    @property
    def duration_ns(self) -> int:
        return self.end_ns - self.start_ns

    @classmethod
    def lookback(cls, minutes: int, *, end_ns: int | None = None) -> "TimeWindow":
        end = end_ns if end_ns is not None else time.time_ns()
        return cls(start_ns=end - int(minutes * 60 * 1e9), end_ns=end)


class ProbeManifest(BaseModel):
    """What the kernel knows about a probe without running it."""

    id: str  # "signoz.error_logs"
    source: str  # becomes Evidence.source
    description: str = ""
    owner: Literal["core", "team"] = "core"
    team: str | None = None
    discriminates: list[str] = Field(default_factory=list)
    cost_tier: CostTier = "normal"
    latency_budget_ms: int = 5_000
    max_evidence: int = 25
    # Hypothesis kinds this probe introduces beyond the kernel's base taxonomy. Declaring one
    # here is how a team teaches the kernel about a failure mode it did not ship with.
    declares_kinds: list[str] = Field(default_factory=list)


class ProbeRequest(BaseModel):
    probe_id: str
    hypothesis_ids: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    window: TimeWindow
    params: dict[str, Any] = Field(default_factory=dict)
    round_index: int = 0

    @property
    def dedup_key(self) -> str:
        """Identity of "this exact question, already asked".

        Window *duration* is part of the key but window *bounds* are not. Bounds move every
        round because `end_ns` is wall-clock now; including them would make every key unique
        and silently disable dedup. Duration is included because broadening the lookback is a
        genuinely different question and must be allowed to run.
        """
        payload = json.dumps(
            {
                "probe": self.probe_id,
                "services": sorted(self.services),
                "params": self.params,
                "window_minutes": round(self.window.duration_ns / 6e10),
            },
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
        return f"{self.probe_id}:{digest}"


class ProbeResult(BaseModel):
    evidence: list[Evidence] = Field(default_factory=list)
    status: Literal["ok", "empty", "error", "timeout", "skipped"] = "ok"
    summary: str = ""

    @classmethod
    def failed(cls, summary: str) -> "ProbeResult":
        return cls(status="error", summary=summary)

    @classmethod
    def nothing(cls, summary: str) -> "ProbeResult":
        return cls(status="empty", summary=summary)


@runtime_checkable
class Probe(Protocol):
    """Implementations must not raise out of `run` — return `ProbeResult.failed(...)` instead.

    One failed evidence source degrades an investigation; it does not end one.
    """

    manifest: ClassVar[ProbeManifest]

    async def run(self, req: ProbeRequest) -> ProbeResult: ...
