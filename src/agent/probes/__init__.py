"""Probes: the unit of extension.

A probe is a deterministic-by-default evidence source with a declared manifest. Core probes
ship here; teams contribute their own through `registry.register`. Probes replaced v1's
sub-agents because a sub-agent's contract was "an LLM tool docstring", which the coordinator
had to be prompted into calling in the right order. A manifest is data the kernel can select
on without asking a model anything.
"""
from src.agent.probes.base import (
    Probe,
    ProbeConfig,
    ProbeManifest,
    ProbeRequest,
    ProbeResult,
    TimeWindow,
)
from src.agent.probes.registry import ProbeRegistry, register, registry_for_team

__all__ = [
    "Probe",
    "ProbeConfig",
    "ProbeManifest",
    "ProbeRequest",
    "ProbeResult",
    "ProbeRegistry",
    "TimeWindow",
    "register",
    "registry_for_team",
]
