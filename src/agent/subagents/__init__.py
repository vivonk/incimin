"""Deterministic-by-default specialist sub-agents (Navigator/Diagnoser/Verifier).

Each module exposes a plain function, not a graph node — the meta-agent's tools (src/agent/tools.py)
call these directly and wrap the result in a Command. See .planning/research/MULTI_AGENT_ARCHITECTURE.md
for the design this package implements (Strategy A: tools that wrap subgraphs/functions).
"""
