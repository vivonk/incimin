import asyncio
import sys
from typing import Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REMEDIATION_SERVER_CMD = ["uv", "run", "python", "src/remediation_mcp.py"]

async def execute_remediation_action(tool_name: str, arguments: dict) -> Any:
    """Spins up the Remediation MCP server over stdio and executes the requested tool."""
    server_params = StdioServerParameters(
        command=REMEDIATION_SERVER_CMD[0],
        args=REMEDIATION_SERVER_CMD[1:],
        env=None
    )
    
    print(f"\n[System] Connecting to Remediation MCP Server to execute '{tool_name}'...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Execute the tool
            print(f"[System] Executing tool {tool_name} with {arguments}...")
            result = await session.call_tool(tool_name, arguments)
            return result

if __name__ == "__main__":
    # Test script
    asyncio.run(execute_remediation_action("toggle_feature_flag", {"flag_name": "recommendationCacheFailure", "variant": "off"}))
