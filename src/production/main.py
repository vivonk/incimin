from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .db import insert_webhook_event, merge_deployment_event, insert_pr_merge_event
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

class PRMergePayload(BaseModel):
    repository_url: str
    pr_number: int
    commit_sha: str
    author: str
    service_name: str

@app.post("/webhook/pr-merge")
async def receive_pr_merge_webhook(payload: PRMergePayload):
    try:
        await insert_pr_merge_event(
            payload.repository_url, 
            payload.pr_number,
            payload.commit_sha, 
            payload.author,
            payload.service_name
        )
        return {"status": "success"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        logging.error(f"Error processing PR merge webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))
