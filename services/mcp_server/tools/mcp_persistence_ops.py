
import redis
import time
import os
import json
from datetime import datetime

# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
BACKUP_DIR = os.getenv("BACKUP_DIR", "./mcp_storage/snapshots")

def get_redis_client():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

def trigger_snapshot():
    """Triggers a background save (BGSAVE) on the Redis/Dragonfly instance."""
    r = get_redis_client()
    try:
        last_save = r.lastsave()
        print(f"Last save: {datetime.fromtimestamp(last_save)}")
        
        print("Triggering BGSAVE...")
        r.bgsave()
        
        # Wait for verify? (Optional, usually we just trigger)
        print("Snapshot triggered successfully.")
        return True
    except redis.exceptions.ResponseError as e:
        print(f"Error triggering snapshot: {e}")
        return False
    except Exception as e:
        print(f"Connection failed: {e}")
        return False

if __name__ == "__main__":
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    success = trigger_snapshot()
    if success:
        with open(os.path.join(BACKUP_DIR, "snapshot_log.json"), "a") as f:
            f.write(json.dumps({"timestamp": time.time(), "action": "bgsave", "status": "triggered"}) + "\n")
