import asyncio
from mcp.server import Server
from mcp.types import RequestParams, ListToolsResult
import mcp.types as types

server = Server("test")

class EmptyParams(RequestParams):
    pass

async def list_tools(ctx, params: EmptyParams) -> ListToolsResult:
    return ListToolsResult(tools=[])

server.add_request_handler("tools/list", EmptyParams, list_tools)
print("SUCCESS")
