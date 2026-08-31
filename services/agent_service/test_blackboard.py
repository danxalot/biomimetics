import sys
import os
import time
import logging

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from redis_blackboard import RedisBlackboard

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_blackboard():
    print("Testing Redis Blackboard...")
    
    # Connect
    try:
        bb = RedisBlackboard(host="localhost", port=6379) # Assuming running inside container or port forwarded
    except Exception as e:
        print(f"Connection failed: {e}")
        # Try with the docker service name if running in network
        try:
            bb = RedisBlackboard(host="arca-langgraph-redis", port=6379)
        except Exception as e:
            print(f"Connection failed again: {e}")
            return

    # Test Write
    print("Testing Write...")
    bb.set_state("test:key", {"foo": "bar"})
    
    # Test Read
    print("Testing Read...")
    val = bb.get_state("test:key")
    print(f"Read value: {val}")
    assert val == {"foo": "bar"}
    
    # Test Lock
    print("Testing Lock...")
    if bb.acquire_lock("test_resource", timeout=5):
        print("Lock acquired.")
        if not bb.acquire_lock("test_resource", timeout=1):
            print("Lock correctly denied.")
        bb.release_lock("test_resource")
        print("Lock released.")
    else:
        print("Failed to acquire lock.")

    # Test Pub/Sub
    print("Testing Pub/Sub...")
    p = bb.client.pubsub()
    p.subscribe("test_channel")
    bb.publish_event("test_channel", "hello world")
    time.sleep(0.1)
    msg = p.get_message() # Subscribe message
    msg = p.get_message() # Actual message
    print(f"Received: {msg}")
    
    print("Blackboard Test Complete.")

if __name__ == "__main__":
    test_blackboard()
