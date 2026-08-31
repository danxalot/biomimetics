import json
import logging
from typing import Any, Dict, Optional
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from redis_blackboard import RedisBlackboard

logger = logging.getLogger(__name__)

# Initialize Blackboard Connection
# We use a lazy initialization or handle connection errors in the tools
try:
    blackboard = RedisBlackboard()
except Exception as e:
    logger.error(f"Failed to initialize RedisBlackboard: {e}")
    blackboard = None

class WriteBlackboardInput(BaseModel):
    key: str = Field(description="The key to write to (e.g., 'arca:state:session_123:plan')")
    value: str = Field(description="The value to write (JSON string or plain text)")
    expiration: Optional[int] = Field(default=None, description="Expiration time in seconds")

@tool("write_blackboard", args_schema=WriteBlackboardInput)
def write_blackboard(key: str, value: str, expiration: Optional[int] = None) -> str:
    """
    Write a value to the Redis Blackboard.
    Use this to store state, plans, or shared data visible to all agents.
    """
    if not blackboard:
        return "Error: Blackboard not connected."
    
    try:
        # Try to parse as JSON if it looks like it
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            parsed_value = value
            
        success = blackboard.set_state(key, parsed_value, ex=expiration)
        return "Success" if success else "Failed to write to Blackboard"
    except Exception as e:
        return f"Error writing to Blackboard: {str(e)}"

class ReadBlackboardInput(BaseModel):
    key: str = Field(description="The key to read from")

@tool("read_blackboard", args_schema=ReadBlackboardInput)
def read_blackboard(key: str) -> str:
    """
    Read a value from the Redis Blackboard.
    """
    if not blackboard:
        return "Error: Blackboard not connected."
    
    try:
        value = blackboard.get_state(key)
        if value is None:
            return "Key not found."
        return json.dumps(value) if isinstance(value, (dict, list)) else str(value)
    except Exception as e:
        return f"Error reading from Blackboard: {str(e)}"

class AcquireLockInput(BaseModel):
    resource: str = Field(description="The name of the resource to lock (e.g., 'docker:container_1')")
    timeout: int = Field(default=60, description="Lock duration in seconds")

@tool("acquire_lock", args_schema=AcquireLockInput)
def acquire_lock(resource: str, timeout: int = 60) -> str:
    """
    Acquire an atomic lock on a resource.
    Use this before modifying shared resources like Docker containers.
    """
    if not blackboard:
        return "Error: Blackboard not connected."
    
    try:
        success = blackboard.acquire_lock(resource, lock_timeout=timeout)
        return "Lock acquired" if success else "Failed to acquire lock (resource busy)"
    except Exception as e:
        return f"Error acquiring lock: {str(e)}"

class ReleaseLockInput(BaseModel):
    resource: str = Field(description="The name of the resource to unlock")

@tool("release_lock", args_schema=ReleaseLockInput)
def release_lock(resource: str) -> str:
    """
    Release a previously acquired lock.
    """
    if not blackboard:
        return "Error: Blackboard not connected."
    
    try:
        success = blackboard.release_lock(resource)
        return "Lock released" if success else "Failed to release lock (maybe it expired or wasn't held)"
    except Exception as e:
        return f"Error releasing lock: {str(e)}"

class PublishPulseInput(BaseModel):
    channel: str = Field(description="The channel to publish to (e.g., 'PLAN_UPDATED')")
    message: str = Field(description="The message to broadcast")

@tool("publish_pulse", args_schema=PublishPulseInput)
def publish_pulse(channel: str, message: str) -> str:
    """
    Publish a 'Pulse' event to the system.
    Use this to notify other agents of major updates.
    """
    if not blackboard:
        return "Error: Blackboard not connected."
    
    try:
        count = blackboard.publish_event(channel, message)
        return f"Message published to {count} subscribers"
    except Exception as e:
        return f"Error publishing pulse: {str(e)}"
