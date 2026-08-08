import os
import asyncio
from contextlib import asynccontextmanager
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

@asynccontextmanager
async def signoz_mcp_session():
    # Construct absolute path to the binary
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    binary_path = os.path.join(base_dir, "signoz-mcp-server_darwin_arm64", "bin", "signoz-mcp-server")
    
    server_params = StdioServerParameters(
        command=binary_path,
        args=[],
        env={
            **os.environ,
            "SIGNOZ_URL": os.getenv("SIGNOZ_URL", "http://127.0.0.1:3301"),
            "SIGNOZ_API_KEY": os.getenv("SIGNOZ_API_TOKEN", "")
        }
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session
