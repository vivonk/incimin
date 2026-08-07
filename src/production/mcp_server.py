import json
import asyncio
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from neo4j import AsyncGraphDatabase
import clickhouse_connect

async def handle_list_tools(context, params) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[
        types.Tool(
            name="get_service_topology",
            description="Get the upstream and downstream dependencies for a service",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_name": {"type": "string"},
                    "max_depth": {"type": "integer", "default": 3, "description": "How many hops to traverse (default: 3). Use 1 for immediate dependencies, or higher for blast-radius analysis."}
                },
                "required": ["service_name"]
            }
        ),
        types.Tool(
            name="get_system_events",
            description="Get system events (deployments, PR merges) for a service within a time window",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_name": {"type": "string"},
                    "start_time": {"type": "string", "description": "ISO8601 string, e.g. '2023-01-01 00:00:00'"},
                    "end_time": {"type": "string", "description": "ISO8601 string"}
                },
                "required": ["service_name", "start_time", "end_time"]
            }
        )
    ])

def _query_ch(query: str) -> list:
    client = clickhouse_connect.get_client(host='127.0.0.1', port=8123)
    return client.query(query).result_rows

async def handle_call_tool(context, params) -> types.CallToolResult:
    name = params.name
    arguments = params.arguments or {}
        
    if name == "get_service_topology":
        service_name = arguments["service_name"]
        max_depth = arguments.get("max_depth", 3)
        
        query = f"""
        MATCH path = (s:Service {{name: $service_name}})-[*1..{max_depth}]-(other:Service)
        UNWIND relationships(path) AS rel
        RETURN DISTINCT startNode(rel).name AS source, type(rel) AS rel_type, endNode(rel).name AS target
        """
        driver = AsyncGraphDatabase.driver("bolt://127.0.0.1:7687", auth=("", ""))
        results = []
        async with driver.session() as session:
            result = await session.run(query, service_name=service_name)
            async for record in result:
                results.append(record.data())
        await driver.close()
        
        return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(results, indent=2))])
        
    elif name == "get_system_events":
        service_name = arguments["service_name"]
        start_time = arguments["start_time"]
        end_time = arguments["end_time"]
        
        query = f"""
        SELECT timestamp, repository_url, commit_sha, source 
        FROM system_changes 
        WHERE service_name = '{service_name}' 
        AND timestamp >= '{start_time}' 
        AND timestamp <= '{end_time}'
        ORDER BY timestamp DESC
        """
        try:
            rows = await asyncio.to_thread(_query_ch, query)
            events = [
                {
                    "timestamp": str(row[0]),
                    "repository_url": row[1],
                    "commit_sha": row[2],
                    "source": row[3]
                }
                for row in rows
            ]
            return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(events, indent=2))])
        except Exception as e:
            return types.CallToolResult(content=[types.TextContent(type="text", text=f"Error querying events: {e}")])
            
    raise ValueError(f"Unknown tool: {name}")

mcp = Server(
    "incimin-sre",
    on_list_tools=handle_list_tools,
    on_call_tool=handle_call_tool
)

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(read_stream, write_stream, mcp.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
