from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .db import insert_webhook_event, merge_deployment_event
import logging

app = FastAPI()

class WebhookPayload(BaseModel):
    repository_url: str
    commit_sha: str
    service_name: str

@app.post("/webhook")
async def receive_webhook(payload: WebhookPayload):
    try:
        await insert_webhook_event(
            payload.repository_url, 
            payload.commit_sha, 
            payload.service_name
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
