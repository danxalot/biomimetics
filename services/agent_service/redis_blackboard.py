import redis
import json
import logging
import time
import os
from typing import Any, Dict, Optional, List, Union

logger = logging.getLogger(__name__)

class RedisBlackboard:
    """
    The Blackboard (Redis): The "Ether." It holds the Active Will and Current State.
    
    Implements:
    1. Connection: Standard redis-py via internal Docker network.
    2. Data Structure: Auto-serialization of JSON objects.
    3. Atomic Locks: Mutex using SETNX for Robotics Interface.
    4. The "Pulse": Pub/Sub for system-wide notifications.
    """
    
    def __init__(self, host: str = None, port: int = 6379, db: int = 0):
        # Use environment variable, then fallback to parameter, then default
        redis_host = host or os.getenv("REDIS_HOST", "redis")
        self.client = redis.Redis(host=redis_host, port=port, db=db, decode_responses=True)
        self.pubsub = self.client.pubsub()
        logger.info(f"Connected to Redis Blackboard at {redis_host}:{port}")

    def _serialize(self, value: Any) -> str:
        """Auto-serialize data to JSON string."""
        try:
            return json.dumps(value)
        except (TypeError, ValueError) as e:
            logger.error(f"Serialization error: {e}")
            return str(value)

    def _deserialize(self, value: Optional[str]) -> Any:
        """Auto-deserialize JSON string to data."""
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    def set_state(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """
        Write a value to the Blackboard.
        
        Args:
            key: The key to write to (e.g., 'arca:state:session_123:plan')
            value: The data to write (will be JSON serialized)
            ex: Expiration time in seconds (optional)
        """
        serialized_value = self._serialize(value)
        return self.client.set(key, serialized_value, ex=ex)

    def get_state(self, key: str) -> Any:
        """
        Read a value from the Blackboard.
        
        Args:
            key: The key to read from.
        """
        value = self.client.get(key)
        return self._deserialize(value)

    def delete_state(self, key: str) -> int:
        """Delete a key from the Blackboard."""
        return self.client.delete(key)

    def acquire_lock(self, lock_name: str, acquire_timeout: int = 10, lock_timeout: int = 60) -> bool:
        """
        Atomic Lock (Mutex) using SETNX.
        Allows the Robotics Model to "Lock" a part of the system.
        
        Args:
            lock_name: The name of the resource to lock (e.g., 'lock:docker:container_1')
            acquire_timeout: How long to wait to acquire the lock (seconds)
            lock_timeout: How long the lock is valid for (seconds)
        """
        identifier = str(time.time())
        end = time.time() + acquire_timeout
        lock_key = f"lock:{lock_name}"

        while time.time() < end:
            if self.client.setnx(lock_key, identifier):
                self.client.expire(lock_key, lock_timeout)
                return True
            elif not self.client.ttl(lock_key):
                self.client.expire(lock_key, lock_timeout)
            time.sleep(0.1)
        return False

    def release_lock(self, lock_name: str) -> bool:
        """Release a lock."""
        lock_key = f"lock:{lock_name}"
        return self.client.delete(lock_key) == 1

    def publish_event(self, channel: str, message: Any) -> int:
        """
        The "Pulse": Publish an event to a channel.
        Allows the Planner to "shout" to the Local Agents.
        
        Args:
            channel: The channel name (e.g., 'PLAN_UPDATED')
            message: The message payload (will be JSON serialized)
        """
        serialized_message = self._serialize(message)
        return self.client.publish(channel, serialized_message)

    def subscribe_to_events(self, channels: List[str]):
        """Subscribe to one or more channels."""
        self.pubsub.subscribe(*channels)
        
    def listen_for_events(self):
        """Generator that yields messages from subscribed channels."""
        for message in self.pubsub.listen():
            if message['type'] == 'message':
                yield {
                    'channel': message['channel'],
                    'data': self._deserialize(message['data'])
                }

    # --- Specific Blackboard Methods for ARCA ---

    def update_global_state(self, session_id: str, state_update: Dict[str, Any]):
        """Update specific fields in the Global State for a session."""
        for field, value in state_update.items():
            key = f"arca:state:{session_id}:{field}"
            self.set_state(key, value)
        
        # Pulse the update
        self.publish_event(f"session:{session_id}:update", {"fields": list(state_update.keys())})

    def get_full_global_state(self, session_id: str, schema_keys: List[str]) -> Dict[str, Any]:
        """Retrieve the full Global State for a session based on schema keys."""
        state = {}
        for key in schema_keys:
            redis_key = f"arca:state:{session_id}:{key}"
            value = self.get_state(redis_key)
            if value is not None:
                state[key] = value
        return state
