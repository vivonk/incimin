import requests
import time
from fastapi.testclient import TestClient
from src.production.main import app

client = TestClient(app)

print("Starting test")
response = client.post("/webhook", json={
    "repository_url": "repo",
    "commit_sha": "sha",
    "service_name": "srv"
})
print("Response:", response.status_code)
print(response.json())
