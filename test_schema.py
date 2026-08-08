import asyncio
from src.agent.signoz_mcp import signoz_mcp_session

async def main():
    async with signoz_mcp_session() as session:
        tools = await session.list_tools()
        for t in tools.tools:
            if t.name == "signoz_search_logs":
                print(t.inputSchema)

asyncio.run(main())
