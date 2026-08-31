import os
import json
import redis
import logging
from typing import Any, Optional, Dict

logger = logging.getLogger(__name__)

class RedisBlackboardTool:
    """
    MCP Tool for Redis Blackboard interaction.
    Supports read/write, atomic locks, and pub/sub.
    """
    def __init__(self):
        self.host = os.getenv("REDIS_HOST", "redis")
        self.port = int(os.getenv("REDIS_PORT", 6379))
        self.db = int(os.getenv("REDIS_DB", 0))
        self.client = None

    def _get_client(self):
        if not self.client:
            self.client = redis.Redis(host=self.host, port=self.port, db=self.db, decode_responses=True)
        return self.client

    def read_key(self, key: str) -> str:
        """Read a value from the Redis Blackboard."""
        try:
            client = self._get_client()
            val = client.get(key)
            if val is None:
                return "Key not found"
            try:
                # Try to parse JSON to return a clean string representation if it's an object
                return json.dumps(json.loads(val))
            except:
                return val
        except Exception as e:
            return f"Error reading key: {e}"

    def write_key(self, key: str, value: Any, expiration: Optional[int] = None) -> str:
        """Write a value to the Redis Blackboard. Auto-serializes JSON."""
        try:
            client = self._get_client()
            if isinstance(value, (dict, list)):
                val_str = json.dumps(value)
            else:
                val_str = str(value)
            
            client.set(key, val_str, ex=expiration)
            return "Success"
        except Exception as e:
            return f"Error writing key: {e}"

    def acquire_lock(self, resource: str, timeout: int = 60) -> str:
        """Acquire a lock on a resource using Redis SETNX."""
        try:
            client = self._get_client()
            lock_key = f"lock:{resource}"
            if client.setnx(lock_key, "locked"):
                client.expire(lock_key, timeout)
                return "Lock acquired"
            return "Lock failed"
        except Exception as e:
            return f"Error acquiring lock: {e}"

    def publish(self, channel: str, message: Any) -> str:
        """Publish an event to a Redis channel (or RabbitMQ if configured)."""
        try:
            client = self._get_client()
            if isinstance(message, (dict, list)):
                msg_str = json.dumps(message)
            else:
                msg_str = str(message)
            count = client.publish(channel, msg_str)
            return f"Published to {count} subscribers"
        except Exception as e:
            return f"Error publishing: {e}"
