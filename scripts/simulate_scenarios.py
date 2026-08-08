import httpx
import argparse
import datetime
import asyncio
import random
import json
import os

API_URL = "http://127.0.0.1:8000"

async def trigger_pr_merge(service_name: str, author: str = "bad-actor"):
    event_time = datetime.datetime.now(datetime.UTC).isoformat()
    payload = {
        "repository_url": f"https://github.com/otel-demo/{service_name}",
        "pr_number": random.randint(1, 1000),
        "commit_sha": "abc123badcommit",
        "author": author,
        "service_name": service_name,
        "event_time": event_time
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
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
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{API_URL}/webhook", json=payload)
        if r.status_code == 200:
            print(f"[+] Injected Deployment event for '{service_name}' at {event_time}")
        else:
            print(f"[-] Failed to inject Deployment: {r.text}")

def set_feature_flag(flag_name: str, variant: str):
    flag_file = "docker/otel-demo/src/flagd/demo.flagd.json"
    try:
        with open(flag_file, 'r') as f:
            data = json.load(f)
        if flag_name in data['flags']:
            data['flags'][flag_name]['defaultVariant'] = variant
            with open(flag_file, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"[+] INJECTED REAL CHAOS: {flag_name} = {variant}")
        else:
            print(f"[-] Flag {flag_name} not found.")
    except Exception as e:
        print(f"[-] Failed to update feature flag: {e}")

async def run_scenario(scenario: str):
    print(f"Executing Scenario: {scenario.upper()}...")
    
    if scenario == "payment_timeout":
        # Scenario 1: Bad PR merged to payment service causing timeout
        await trigger_pr_merge("payment", author="intern")
        await trigger_deployment("payment")
        set_feature_flag("paymentFailure", "100%")
        print("\n=> Action: Tell the agent 'We are seeing a massive latency spike on the frontend service. Investigate why.'")
        
    elif scenario == "redis_leak":
        # Scenario 2: Cart service redis leak
        await trigger_pr_merge("cart", author="dev-team")
        await trigger_deployment("cart")
        set_feature_flag("cartFailure", "100%")
        print("\n=> Action: Tell the agent 'The checkout service is throwing errors when trying to place orders. Find the root cause.'")
        
    elif scenario == "quote_logic":
        # Scenario 3: Bad shipping quote logic
        await trigger_pr_merge("quote", author="finance")
        await trigger_deployment("quote")
        set_feature_flag("intlShippingSlowdown", "10sec")
        print("\n=> Action: Tell the agent 'The shipping service is complaining about negative shipping costs. Where did this come from?'")

    elif scenario == "kafka_backup":
        # Scenario 4: Fraud detection config change blocking Kafka
        await trigger_pr_merge("fraud-detection", author="sre-team")
        await trigger_deployment("fraud-detection")
        set_feature_flag("kafkaQueueProblems", "on")
        print("\n=> Action: Tell the agent 'We have a Kafka topic lag alert on the orders topic. Figure out who is slowing it down.'")

    elif scenario == "noisy_neighbor":
        # Scenario 6: Ad service DDOSing flagd
        await trigger_pr_merge("ad", author="marketing")
        await trigger_deployment("ad")
        set_feature_flag("adHighCpu", "on")
        print("\n=> Action: Tell the agent 'The shared flagd service is experiencing high CPU and latency. Which downstream caller caused this?'")

    elif scenario == "delayed_cache_crash":
        # Scenario: Ticking Time Bomb
        print("[*] Simulating PR merge & deployment to recommendation service...")
        await trigger_pr_merge("recommendation", author="dev-team")
        await trigger_deployment("recommendation")
        
        print("[*] Timeline Shift: Simulating 60 seconds of healthy traffic before the bug triggers...")
        for i in range(10, 0, -1):
            print(f"Waiting... {i*6}s remaining", end='\r')
            await asyncio.sleep(6)
        print("\n[*] Time bomb exploded! Injecting recommendationCacheFailure flag.")
        set_feature_flag("recommendationCacheFailure", "on")
        print("\n=> Action: Wait for SigNoz alert, then tell the agent 'The Recommendation Service error rate just spiked. Investigate.'")


    elif scenario == "reset":
        set_feature_flag("paymentFailure", "off")
        set_feature_flag("cartFailure", "off")
        set_feature_flag("intlShippingSlowdown", "off")
        set_feature_flag("kafkaQueueProblems", "off")
        set_feature_flag("adHighCpu", "off")
        set_feature_flag("recommendationCacheFailure", "off")
        print("[+] Reset all chaos feature flags to normal.")

    else:
        print(f"Unknown scenario: {scenario}")
        print("Available scenarios: payment_timeout, redis_leak, quote_logic, kafka_backup, noisy_neighbor, delayed_cache_crash")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inject events into Incimin for Otel-Demo scenarios")
    parser.add_argument("scenario", type=str, help="Name of the scenario to simulate")
    args = parser.parse_args()
    
    asyncio.run(run_scenario(args.scenario))
