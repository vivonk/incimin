import httpx
import argparse
import datetime
import asyncio

API_URL = "http://127.0.0.1:8000"

async def trigger_pr_merge(service_name: str, author: str = "bad-actor"):
    event_time = datetime.datetime.now(datetime.UTC).isoformat()
    payload = {
        "repository_url": f"https://github.com/otel-demo/{service_name}",
        "pr_number": 101,
        "commit_sha": "abc123badcommit",
        "author": author,
        "service_name": service_name,
        "event_time": event_time
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{API_URL}/webhook/pr-merge", json=payload)
        if r.status_code == 200:
            print(f"[+] Injected PR merge event for '{service_name}' at {event_time}")
        else:
            print(f"[-] Failed to inject PR merge: {r.text}")

async def trigger_deployment(service_name: str):
    event_time = datetime.datetime.now(datetime.UTC).isoformat()
    payload = {
        "repository_url": f"https://github.com/otel-demo/{service_name}",
        "commit_sha": "abc123badcommit",
        "service_name": service_name,
        "event_time": event_time
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{API_URL}/webhook", json=payload)
        if r.status_code == 200:
            print(f"[+] Injected Deployment event for '{service_name}' at {event_time}")
        else:
            print(f"[-] Failed to inject Deployment: {r.text}")

async def run_scenario(scenario: str):
    print(f"Executing Scenario: {scenario.upper()}...")
    
    if scenario == "payment_timeout":
        # Scenario 1: Bad PR merged to payment service causing timeout
        await trigger_pr_merge("payment", author="intern")
        await trigger_deployment("payment")
        print("\n=> Action: Tell the agent 'We are seeing a massive latency spike on the frontend service. Investigate why.'")
        
    elif scenario == "redis_leak":
        # Scenario 2: Cart service redis leak
        await trigger_pr_merge("cart", author="dev-team")
        await trigger_deployment("cart")
        print("\n=> Action: Tell the agent 'The checkout service is throwing errors when trying to place orders. Find the root cause.'")
        
    elif scenario == "quote_logic":
        # Scenario 3: Bad shipping quote logic
        await trigger_pr_merge("quote", author="finance")
        await trigger_deployment("quote")
        print("\n=> Action: Tell the agent 'The shipping service is complaining about negative shipping costs. Where did this come from?'")

    elif scenario == "kafka_backup":
        # Scenario 4: Fraud detection config change blocking Kafka
        await trigger_pr_merge("fraud-detection", author="sre-team")
        await trigger_deployment("fraud-detection")
        print("\n=> Action: Tell the agent 'We have a Kafka topic lag alert on the orders topic. Figure out who is slowing it down.'")

    elif scenario == "noisy_neighbor":
        # Scenario 6: Ad service DDOSing flagd
        await trigger_pr_merge("ad", author="marketing")
        await trigger_deployment("ad")
        print("\n=> Action: Tell the agent 'The shared flagd service is experiencing high CPU and latency. Which downstream caller caused this?'")

    else:
        print(f"Unknown scenario: {scenario}")
        print("Available scenarios: payment_timeout, redis_leak, quote_logic, kafka_backup, noisy_neighbor")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inject events into Incimin for Otel-Demo scenarios")
    parser.add_argument("scenario", type=str, help="Name of the scenario to simulate")
    args = parser.parse_args()
    
    asyncio.run(run_scenario(args.scenario))
