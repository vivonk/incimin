import requests
import datetime
import time

def simulate():
    url_deploy = "http://127.0.0.1:8000/webhook"
    url_pr = "http://127.0.0.1:8000/webhook/pr-merge"
    
    # 1. PR Merge Event (happened 10 minutes ago)
    pr_time = (datetime.datetime.now() - datetime.timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    pr_payload = {
        "repository_url": "https://github.com/incimin/demo",
        "pr_number": 42,
        "commit_sha": "abc123def456",
        "author": "dev-user",
        "service_name": "checkoutservice",
        "event_time": pr_time
    }
    
    print(f"Sending PR Merge event for {pr_time}...")
    try:
        response = requests.post(url_pr, json=pr_payload)
        response.raise_for_status()
        print("Success:", response.json())
    except Exception as e:
        print("Failed to send PR webhook:", e)

    time.sleep(1)

    # 2. Deployment Event (happened 5 minutes ago)
    deploy_time = (datetime.datetime.now() - datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    deploy_payload = {
        "repository_url": "https://github.com/incimin/demo",
        "commit_sha": "abc123def456",
        "service_name": "checkoutservice",
        "event_time": deploy_time
    }
    
    print(f"\nSending Deployment event for {deploy_time}...")
    try:
        response = requests.post(url_deploy, json=deploy_payload)
        response.raise_for_status()
        print("Success:", response.json())
    except Exception as e:
        print("Failed to send Deployment webhook:", e)

if __name__ == "__main__":
    simulate()
