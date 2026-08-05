from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class SREAgentState(TypedDict):
    messages: Annotated[list, add_messages]
    remaining_steps: int
