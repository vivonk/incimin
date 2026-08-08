import asyncio
from mcp.server import Server
from mcp.types import CallToolRequestParams
import mcp.types as types
server = Server("test")

async def list_tools(ctx, params):
    return types.ListToolsResult(tools=[])

server.add_request_handler("tools/list", type(None), list_tools)
print("SUCCESS")
