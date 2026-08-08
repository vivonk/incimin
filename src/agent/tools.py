"""Meta-agent tools — Strategy A from MULTI_AGENT_ARCHITECTURE.md §5: each tool wraps a
deterministic-by-default sub-agent function and hands its structured output back to the graph
via Command, instead of returning a single formatted string like v1.5's flat tools did.
"""
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from src.agent.subagents.telemetry import run_telemetry_subagent
from src.agent.subagents.topology import run_topology_subagent


@tool
def topology_tool(
    source: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Navigator sub-agent: BFS-traverses the Memgraph service graph from `source` and returns a
    ranked list of candidate root-cause services. Call this first."""
    result = run_topology_subagent(source)
    return Command(
        update={
            "evidence": result.evidence,
            "candidate_services": result.candidate_services,
            "messages": [ToolMessage(content=result.summary, tool_call_id=tool_call_id)],
        }
    )


@tool
def telemetry_tool(
    tool_call_id: Annotated[str, InjectedToolCallId],
    candidate_services: Annotated[list[str], InjectedState("candidate_services")] = None,
    window_mins: int = 30,
) -> Command:
    """Diagnoser sub-agent: queries ClickHouse/SigNoz for error evidence on the topology
    sub-agent's candidate services. Call this after topology_tool."""
    # InjectedState("candidate_services") only injects when the key is already present in
    # graph state (i.e. after topology_tool has run) — default to [] otherwise rather than
    # raising, since run_telemetry_subagent already handles an empty candidate list.
    result = run_telemetry_subagent(candidate_services or [], window_mins=window_mins)
    return Command(
        update={
            "evidence": result.evidence,
            "messages": [ToolMessage(content=result.summary, tool_call_id=tool_call_id)],
        }
    )
