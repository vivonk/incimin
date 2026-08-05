import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agent.graph import app

def main():
    start_time = time.time()
    
    query = "Checkout latency is spiking. Investigate and give me a recommendation."
    initial_state = {
        "messages": [("user", query)],
        "remaining_steps": 10
    }
    
    print(f"Sending query to agent: '{query}'")
    
    try:
        result = app.invoke(initial_state)
    except Exception as e:
        print(f"FAIL: Agent invocation failed with exception: {e}")
        sys.exit(1)
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"Agent execution completed in {duration:.2f} seconds.")
    
    if duration >= 60:
        print(f"FAIL: Execution time exceeded 60 seconds (took {duration:.2f}s).")
        sys.exit(1)
        
    messages = result.get("messages", [])
    if not messages:
        print("FAIL: No messages returned from agent.")
        sys.exit(1)
        
    final_message = messages[-1].content.lower()
    print(f"Final Agent Response:\n{messages[-1].content}")
    
    # Assertions
    if "paymentservice" not in final_message:
        print("FAIL: Expected 'paymentservice' in the final response.")
        sys.exit(1)
        
    if "recommend" not in final_message and "step" not in final_message and "restart" not in final_message:
        print("FAIL: Expected recommendation or steps in the final response.")
        sys.exit(1)
        
    print("SUCCESS: Golden path verified.")
    sys.exit(0)

if __name__ == "__main__":
    main()
