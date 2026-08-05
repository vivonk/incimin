#!/usr/bin/env python3
import argparse
import subprocess
import sys

def get_container_status(container_name="paymentservice"):
    try:
        # Check if container is running
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip().lower() == "true"
    except subprocess.CalledProcessError:
        # Container doesn't exist or Docker is not running
        print(f"Error: Could not inspect container '{container_name}'. Is it created?")
        sys.exit(1)

def stop_container(container_name="paymentservice"):
    if not get_container_status(container_name):
        print(f"Container '{container_name}' is already stopped. Operation is idempotent.")
        return
    print(f"Stopping container '{container_name}'...")
    subprocess.run(["docker", "stop", container_name], check=True)
    print("Chaos injected: payment service is down.")

def recover_container(container_name="paymentservice"):
    if get_container_status(container_name):
        print(f"Container '{container_name}' is already running. Operation is idempotent.")
        return
    print(f"Starting container '{container_name}'...")
    subprocess.run(["docker", "start", container_name], check=True)
    print("Recovery completed: payment service is up.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chaos Injection for OTel Astronomy Shop demo.")
    parser.add_argument("--mode", choices=["stop", "recover"], required=True,
                        help="Mode of operation: stop (inject chaos) or recover (restore normal operation).")
    
    args = parser.parse_args()
    
    if args.mode == "stop":
        stop_container()
    elif args.mode == "recover":
        recover_container()
