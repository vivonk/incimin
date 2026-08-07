from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .db import insert_webhook_event, merge_deployment_event, insert_pr_merge_event
import logging
import asyncio
import os
from .topology.manager import TopologyManager
from .topology.plugins.signoz import SigNozPluginConfig
from .topology.repository import TopologyRepository
from .topology.models import ServiceNode
from .mcp_server import mcp
from mcp.server.sse import SseServerTransport
from starlette.requests import Request

app = FastAPI()

from mcp.server.sse import SseServerTransport

sse = SseServerTransport("/mcp/messages")
_base_app = app

async def asgi_wrapper(scope, receive, send):
    if scope["type"] == "http" and scope["path"] == "/mcp/sse":
        async with sse.connect_sse(scope, receive, send) as streams:
            await mcp.run(streams[0], streams[1], mcp.create_initialization_options())
    elif scope["type"] == "http" and scope["path"] == "/mcp/messages" and scope["method"] == "POST":
        await sse.handle_post_message(scope, receive, send)
    else:
        await _base_app(scope, receive, send)

# Replace the FastAPI app with our ASGI wrapper
app = asgi_wrapper



@app.on_event("startup")
async def start_topology_sync():
    async def sync_loop():
        config = SigNozPluginConfig(
            SIGNOZ_API_URL=os.getenv("SIGNOZ_API_URL", "http://127.0.0.1:3301/api/v1/dependency_graph"),
            SIGNOZ_API_TOKEN=os.getenv("SIGNOZ_API_TOKEN", "bwjOOKoWyIokMAUAb2m1p8OTkyw9b20KTahWjlrRH4k=")
        )
        plugin_class = TopologyManager.get_plugin_class("signoz")
        plugin = plugin_class(config)
        repo = TopologyRepository()
        
        while True:
            try:
                async for entity in plugin.fetch_topology():
                    if isinstance(entity, ServiceNode):
                        await repo.upsert_node(entity)
                    else:
                        await repo.upsert_edge(entity)
                logging.info("Successfully synced SigNoz topology.")
            except Exception as e:
                logging.error(f"Error syncing topology: {e}")
            await asyncio.sleep(60) # sync every 60 seconds
            
    asyncio.create_task(sync_loop())

class WebhookPayload(BaseModel):
    repository_url: str
    commit_sha: str
    service_name: str
    event_time: str

@app.post("/webhook")
async def receive_webhook(payload: WebhookPayload):
    try:
        await insert_webhook_event(
            payload.repository_url, 
            payload.commit_sha, 
            payload.service_name,
            payload.event_time
        )
        await merge_deployment_event(
            payload.repository_url,
            payload.service_name
        )
        return {"status": "success"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        logging.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class PRMergePayload(BaseModel):
    repository_url: str
    pr_number: int
    commit_sha: str
    author: str
    service_name: str
    event_time: str

@app.post("/webhook/pr-merge")
async def receive_pr_merge_webhook(payload: PRMergePayload):
    try:
        await insert_pr_merge_event(
            payload.repository_url, 
            payload.pr_number,
            payload.commit_sha, 
            payload.author,
            payload.service_name,
            payload.event_time
        )
        return {"status": "success"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        logging.error(f"Error processing PR merge webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))
