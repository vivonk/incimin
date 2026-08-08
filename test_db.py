from src.production.db import insert_webhook_event, merge_deployment_event
print("init")
print("insert")
insert_webhook_event("repo", "sha", "service")
print("merge")
merge_deployment_event("repo", "service")
print("done")
