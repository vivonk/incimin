from src.production.db import insert_webhook_event, merge_deployment_event
import time

print("init")
print("init done")

print("merge")
merge_deployment_event("repo", "service")
print("merge done")

print("insert")
insert_webhook_event("repo", "sha", "service")
print("insert done")
print("done")
