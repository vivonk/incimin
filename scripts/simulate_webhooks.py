import requests
import sys

def simulate():
    url = "http://127.0.0.1:8000/webhook"
    payload = {
        "repository_url": "https://github.com/incimin/demo",
        "commit_sha": "abc123def456",
        "service_name": "checkoutservice"
    }
    
    print(f"Sending payload to {url}...")
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("Success:", response.json())
    except Exception as e:
        print("Failed to send webhook:", e)
        sys.exit(1)

if __name__ == "__main__":
    simulate()
