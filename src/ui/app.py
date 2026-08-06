import streamlit as st
import asyncio
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
import sys
import os

# Add src to python path so we can import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.agent.graph import app as agent_app

st.set_page_config(page_title="Incimin.io AI SRE Agent", page_icon="🤖")
st.title("AI SRE Agent")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.write(msg.content)
    elif isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            if msg.content:
                st.markdown(msg.content)
            if msg.tool_calls:
                for tool_call in msg.tool_calls:
                    with st.status(f"Tool Execution: {tool_call['name']}", state="complete"):
                        st.write(f"Arguments: {tool_call['args']}")
    elif isinstance(msg, ToolMessage):
        with st.status(f"Tool Result: {msg.name}", state="complete"):
            st.write(f"Result: {msg.content}")

def run_agent_sync(user_input, history):
    # Prepare state
    inputs = {"messages": history + [HumanMessage(content=user_input)], "remaining_steps": 10}
    
    # We use a wrapper to handle asyncio event loops to prevent collision with Streamlit's loop
    # stream_mode="updates" yields the state of the graph after each node
    def run_graph():
        updates = []
        for update in agent_app.stream(inputs, stream_mode="updates"):
            updates.append(update)
        return updates

    # Depending on python environment, we might not need asyncio.run if the graph is fully sync
    # but to satisfy the plan's requirement for a synchronous wrapper:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # LangGraph app.stream is a generator, so we can't await it. We just run it synchronously.
        # But if the plan requires an async wrapper, we'll wrap astream instead.
        async def run_async_graph():
            updates = []
            async for update in agent_app.astream(inputs, stream_mode="updates"):
                updates.append(update)
            return updates
        updates = loop.run_until_complete(run_async_graph())
    finally:
        loop.close()
    
    return updates

if prompt := st.chat_input("Ask the AI SRE Agent..."):
    st.session_state.messages.append(HumanMessage(content=prompt))
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        
        # In a real app we might render tool calls dynamically during the stream, 
        # but for simplicity we'll render them as they come in updates or after.
        updates = run_agent_sync(prompt, st.session_state.messages[:-1])
        
        final_message = None
        
        for update in updates:
            for node_name, state_update in update.items():
                if node_name == "agent":
                    messages = state_update.get("messages", [])
                    if messages:
                        last_msg = messages[-1]
                        if isinstance(last_msg, AIMessage):
                            # We only want to append it to history if it's not the exact same AIMessage object we just appended
                            if not st.session_state.messages or st.session_state.messages[-1] != last_msg:
                                st.session_state.messages.append(last_msg)
                                if last_msg.content:
                                    st.markdown(last_msg.content)
                                
                                if last_msg.tool_calls:
                                    for tool_call in last_msg.tool_calls:
                                        with st.status(f"Tool Execution: {tool_call['name']}", state="running") as status:
                                            st.write(f"Arguments: {tool_call['args']}")
                                            status.update(state="complete")
                elif node_name == "tools":
                    messages = state_update.get("messages", [])
                    if messages:
                        for tool_msg in messages:
                            if isinstance(tool_msg, ToolMessage):
                                # Only append if we haven't appended this exact ToolMessage yet
                                if not st.session_state.messages or st.session_state.messages[-1] != tool_msg:
                                    st.session_state.messages.append(tool_msg)
                                    with st.status(f"Tool Result: {tool_msg.name}", state="complete"):
                                        st.write(f"Result: {tool_msg.content}")
