"""Core probes, registered at import time.

Importing this package is what populates the global registry, so anything building a team
roster must import it first. `src.agent.kernel.graph` does that on your behalf.

Topology is deliberately *not* a probe. BFS runs once in the kernel's `ground` node — it
establishes the candidate set that everything downstream is scoped to, so it cannot be
something selection might choose to skip. It still emits citable `topology` evidence, which is
what lets a claim satisfy `cross_source_consistency`.
"""
from src.agent.probes.core import changes, logs  # noqa: F401  (import registers)

__all__ = ["changes", "logs"]
