import json
import asyncio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult
from neo4j import AsyncGraphDatabase
import clickhouse_connect

mcp = Server("incimin-sre")

@mcp.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_service_topology",
            description="Get the upstream and downstream dependencies for a service",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_name": {"type": "string"},
                    "max_depth": {"type": "integer", "default": 1}
                },
                "required": ["service_name"]
            }
        ),
        Tool(
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
    ]

def _query_ch(query: str) -> list:
    client = clickhouse_connect.get_client(host='127.0.0.1', port=8123)
    return client.query(query).result_rows

@mcp.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent | CallToolResult]:
    if arguments is None:
        arguments = {}
        
    if name == "get_service_topology":
        service_name = arguments["service_name"]
        max_depth = arguments.get("max_depth", 1)
        
        query = f"""
        MATCH (s:Service {{name: $service_name}})-[r*1..{max_depth}]-(other:Service)
        RETURN other.name as service, type(r[-1]) as rel_type, startNode(r[-1]).name as source_node, endNode(r[-1]).name as target_node
        """
        driver = AsyncGraphDatabase.driver("bolt://127.0.0.1:7687", auth=("", ""))
        results = []
        async with driver.session() as session:
            result = await session.run(query, service_name=service_name)
            async for record in result:
                results.append(record.data())
        await driver.close()
        
        return [TextContent(type="text", text=json.dumps(results, indent=2))]
        
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
            return [TextContent(type="text", text=json.dumps(events, indent=2))]
        except Exception as e:
            return [TextContent(type="text", text=f"Error querying events: {e}")]
            
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await mcp.run(read_stream, write_stream, mcp.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
