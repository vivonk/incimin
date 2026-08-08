from fastapi import FastAPI
from mcp.server import Server

mcp = Server("test")
app = FastAPI()
mcp_app = mcp.streamable_http_app(streamable_http_path="/mcp/sse")
app.mount("/", mcp_app)
