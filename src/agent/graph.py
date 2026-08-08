"""Meta-agent (Coordinator) — Strategy A from MULTI_AGENT_ARCHITECTURE.md §5.

Shape: agent (LLM, the only mandatory-LLM node) <-> tools (topology/telemetry
sub-agents) loop, then synthesize (LLM, structured output) -> verifier (deterministic,
Layer 1 only per §6/§9) -> finalize (deterministic formatting) or graceful_exit.

This intentionally keeps the v1.5 agent<->tools loop shape almost unchanged (low migration
risk, per §5's recommendation) while adding the Verifier gate v1.5 never had.
"""
from typing import Literal

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.agent.llm import build_llm
from src.agent.state import SREAgentState, Synthesis
from src.agent.subagents.verifier import verify
from src.agent.tools import telemetry_tool, topology_tool

llm = build_llm()
tools = [topology_tool, telemetry_tool]
llm_with_tools = llm.bind_tools(tools)
synthesis_llm = build_llm().with_structured_output(Synthesis)

COORDINATOR_SYSTEM_PROMPT = """You are the Coordinator of an SRE AI system. You do not query any \
data source directly — you delegate to two specialist sub-agents via tools, then a separate \
step synthesizes their findings and a deterministic Verifier checks your synthesis before it is \
shown to a human.

Call sub-agents in this fixed order, ONE AT A TIME, waiting for each result before calling the \
next. Do not call more than one tool in the same turn:
1. topology_tool — find candidate root-cause services from the service graph.
2. telemetry_tool — check those candidates for error evidence.

Once you have called both (or a tool's result makes further calls pointless), stop calling \
tools. You NEVER output or suggest remediation actions yourself — you only gather evidence \
through these tools; a later step composes the final answer from what you gathered.
"""


def agent_node(state: SREAgentState):
    messages = [{"role": "system", "content": COORDINATOR_SYSTEM_PROMPT}] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response], "remaining_steps": state["remaining_steps"] - 1}


def route_after_agent(state: SREAgentState) -> Literal["tools", "synthesize", "graceful_exit"]:
    if state["remaining_steps"] <= 2:
        return "graceful_exit"
    messages = state.get("messages", [])
    if messages:
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
    return "synthesize"


def synthesize_node(state: SREAgentState):
    evidence = state.get("evidence", [])
    if not evidence:
        # Nothing to synthesize from — let the Verifier fail closed rather than asking the
        # LLM to invent a claim with zero grounding.
        return {"synthesis": None}

    evidence_listing = "\n".join(
        f"- {e['id']} [{e['source']}] service={e['service']}: {e['summary']}" for e in evidence
    )
    candidates = state.get("candidate_services", [])
    prompt = (
        f"Candidate services (from topology traversal): {candidates}\n"
        f"Accumulated evidence:\n{evidence_listing}\n\n"
        "Produce a Synthesis: the single most likely root_cause_service, the evidence_refs "
        "(evidence ids from the list above) that support it, and your confidence."
    )
    try:
        synthesis = synthesis_llm.invoke(prompt)
    except Exception:
        synthesis = None
    return {"synthesis": synthesis}


def verifier_node(state: SREAgentState):
    result = verify(state.get("evidence", []), state.get("candidate_services", []), state.get("synthesis"))
    return {"verification_result": result}


def route_after_verifier(state: SREAgentState) -> Literal["finalize", "graceful_exit"]:
    vr = state.get("verification_result")
    return "finalize" if vr and vr.get("passed") else "graceful_exit"


def finalize_node(state: SREAgentState):
    synthesis: Synthesis = state["synthesis"]
    evidence_by_id = {e["id"]: e for e in state.get("evidence", [])}

    lines = [f"Root cause: {synthesis.root_cause_service} (confidence: {synthesis.confidence})."]
    cited = [evidence_by_id[ref] for ref in synthesis.evidence_refs if ref in evidence_by_id]
    if cited:
        lines.append("\nSupporting evidence:")
        lines.extend(f"- {e['id']} [{e['source']}] {e['summary']}" for e in cited)
    lines.append("\nEscalate to a human SRE for remediation steps.")

    msg = AIMessage(content="\n".join(lines))
    return {"messages": [msg]}


def graceful_exit_node(state: SREAgentState):
    vr = state.get("verification_result")
    content = "insufficient data to determine root cause"
    if vr and not vr.get("passed"):
        content += f" ({vr.get('detail')})"
    msg = AIMessage(content=content)
    return {"messages": [msg], "remaining_steps": state.get("remaining_steps", 1) - 1}


workflow = StateGraph(SREAgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", ToolNode(tools))
workflow.add_node("synthesize", synthesize_node)
workflow.add_node("verifier", verifier_node)
workflow.add_node("finalize", finalize_node)
workflow.add_node("graceful_exit", graceful_exit_node)

workflow.set_entry_point("agent")
workflow.add_conditional_edges(
    "agent",
    route_after_agent,
    {"tools": "tools", "synthesize": "synthesize", "graceful_exit": "graceful_exit"},
)
workflow.add_edge("tools", "agent")
workflow.add_edge("synthesize", "verifier")
workflow.add_conditional_edges(
    "verifier",
    route_after_verifier,
    {"finalize": "finalize", "graceful_exit": "graceful_exit"},
)
workflow.add_edge("finalize", END)
workflow.add_edge("graceful_exit", END)

app = workflow.compile()
