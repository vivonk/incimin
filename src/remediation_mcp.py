import json
import logging
import asyncio
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolRequestParams, PaginatedRequestParams, ListToolsResult, CallToolResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("remediation_mcp")

server = Server("incimin-remediation")
FLAG_FILE = "/Users/nsarswat/personal/incimin.io/docker/otel-demo/src/flagd/demo.flagd.json"

async def list_tools(ctx, params: PaginatedRequestParams) -> ListToolsResult:
    return ListToolsResult(
        tools=[
            types.Tool(
                name="toggle_feature_flag",
                description="Toggles a feature flag in the OpenTelemetry Demo environment to mitigate bugs.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "flag_name": {"type": "string", "description": "Name of the feature flag (e.g. 'recommendationCacheFailure')"},
                        "variant": {"type": "string", "description": "Variant to set (e.g. 'on', 'off')"}
                    },
                    "required": ["flag_name", "variant"]
                }
            ),
            types.Tool(
                name="post_incident_update",
                description="Simulates posting an incident update to the SRE Slack channel.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "The Markdown summary message to post"}
                    },
                    "required": ["message"]
                }
            ),
            types.Tool(
                name="revert_deployment",
                description="Simulates reverting a bad Kubernetes deployment.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service_name": {"type": "string", "description": "Name of the service to revert"}
                    },
                    "required": ["service_name"]
                }
            )
        ]
    )

async def call_tool(ctx, params: CallToolRequestParams) -> CallToolResult:
    name = params.name
    arguments = params.arguments or {}

    if name == "toggle_feature_flag":
        flag_name = arguments.get("flag_name")
        variant = arguments.get("variant")
        try:
            with open(FLAG_FILE, 'r') as f:
                data = json.load(f)
                
            if flag_name in data.get('flags', {}):
                data['flags'][flag_name]['defaultVariant'] = variant
                with open(FLAG_FILE, 'w') as f:
                    json.dump(data, f, indent=2)
                return CallToolResult(content=[types.TextContent(type="text", text=f"Successfully set feature flag '{flag_name}' to '{variant}'.")])
            else:
                return CallToolResult(content=[types.TextContent(type="text", text=f"Error: Feature flag '{flag_name}' not found.")])
        except Exception as e:
            return CallToolResult(isError=True, content=[types.TextContent(type="text", text=f"Error toggling feature flag: {str(e)}")])

    elif name == "post_incident_update":
        msg = arguments.get("message")
        return CallToolResult(content=[types.TextContent(type="text", text=f"Successfully posted update to Slack:\n{msg}")])

    elif name == "revert_deployment":
        svc = arguments.get("service_name")
        return CallToolResult(content=[types.TextContent(type="text", text=f"Successfully triggered reverting Kubernetes deployment for {svc}.")])
        
    return CallToolResult(isError=True, content=[types.TextContent(type="text", text=f"Unknown tool: {name}")])

server.add_request_handler("tools/list", PaginatedRequestParams, list_tools)
server.add_request_handler("tools/call", CallToolRequestParams, call_tool)

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
