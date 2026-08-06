from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from src.agent.state import SREAgentState
from src.agent.tools import graph_bfs_tool, clickhouse_log_tool, qdrant_runbook_tool
from src.agent.llm import build_llm
from langchain_core.messages import AIMessage

llm = build_llm()
tools = [graph_bfs_tool, clickhouse_log_tool, qdrant_runbook_tool]
llm_with_tools = llm.bind_tools(tools)

system_prompt = """You are an SRE AI assistant. Your goal is to identify the root cause of an incident and retrieve recommended next steps from the runbook for the human to execute.
You NEVER output or suggest remediation actions yourself, you ONLY retrieve them."""

def agent_node(state: SREAgentState):
    messages = [{"role": "system", "content": system_prompt}] + state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response], "remaining_steps": state["remaining_steps"] - 1}

def graceful_exit_node(state: SREAgentState):
    msg = AIMessage(content="insufficient data to determine root cause")
    return {"messages": [msg], "remaining_steps": state["remaining_steps"] - 1}

def route_condition(state: SREAgentState):
    if state["remaining_steps"] <= 2:
        return "graceful_exit"
    messages = state.get("messages", [])
    if messages:
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
    return END

workflow = StateGraph(SREAgentState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", ToolNode(tools))
workflow.add_node("graceful_exit", graceful_exit_node)

workflow.set_entry_point("agent")
workflow.add_conditional_edges("agent", route_condition, {
    "tools": "tools",
    "graceful_exit": "graceful_exit",
    END: END
})
workflow.add_edge("tools", "agent")
workflow.add_edge("graceful_exit", END)

app = workflow.compile()
