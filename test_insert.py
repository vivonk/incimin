import asyncio
from src.production.db import insert_webhook_event
asyncio.run(insert_webhook_event("repo", "sha", "srv"))
print("Done!")
