"""
OpenClaw Persistent WebSocket Client for ARCA LLM Gateway
Provides persistent connection to OpenClaw gateway with auto-reconnect.
"""
import os
import json
import asyncio
import logging
import uuid
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Configuration
OPENCLAW_GATEWAY_URL = os.getenv("OPENCLAW_GATEWAY_URL", "ws://100.116.196.80:18789")
OPENCLAW_TOKEN_FILE = os.getenv("OPENCLAW_TOKEN_FILE", "/app/.secrets/openclaw_token")


def _load_token() -> str:
    """Load OpenClaw token from file."""
    try:
        with open(OPENCLAW_TOKEN_FILE, 'r') as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.warning(f"Token file not found: {OPENCLAW_TOKEN_FILE}")
        return os.getenv("OPENCLAW_TOKEN", "")


@dataclass
class OpenClawMessage:
    """Represents an OpenClaw RPC message."""
    type: str
    id: str
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    event: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class OpenClawClient:
    """Persistent WebSocket client for OpenClaw gateway."""
    
    def __init__(self):
        self.ws = None
        self.connected = False
        self.token = _load_token()
        self.pending_requests: Dict[str, asyncio.Future] = {}
        self.event_handlers: Dict[str, Callable] = {}
        self._reconnect_task = None
        self._receive_task = None
        
    async def connect(self):
        """Establish connection to OpenClaw gateway."""
        try:
            import websockets
            self.ws = await websockets.connect(
                OPENCLAW_GATEWAY_URL,
                additional_headers={"Authorization": f"Bearer {self.token}"}
            )
            self.connected = True
            self._receive_task = asyncio.create_task(self._receive_loop())
            logger.info(f"Connected to OpenClaw gateway at {OPENCLAW_GATEWAY_URL}")
        except Exception as e:
            logger.error(f"Failed to connect to OpenClaw: {e}")
            self.connected = False
            # Schedule reconnect
            self._schedule_reconnect()
            
    def _schedule_reconnect(self, delay: float = 5.0):
        """Schedule a reconnection attempt."""
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._reconnect(delay))
            
    async def _reconnect(self, delay: float):
        """Attempt to reconnect after delay."""
        await asyncio.sleep(delay)
        await self.connect()
        
    async def _receive_loop(self):
        """Background task to receive messages."""
        try:
            async for message in self.ws:
                data = json.loads(message)
                msg = OpenClawMessage(**{k: v for k, v in data.items() if k in OpenClawMessage.__dataclass_fields__})
                
                if msg.type == "res" and msg.id in self.pending_requests:
                    # Complete pending request
                    future = self.pending_requests.pop(msg.id)
                    if msg.error:
                        future.set_exception(Exception(msg.error.get("message", "Unknown error")))
                    else:
                        future.set_result(msg.result)
                elif msg.type == "event" and msg.event in self.event_handlers:
                    # Handle event
                    await self.event_handlers[msg.event](msg.payload)
        except Exception as e:
            logger.error(f"WebSocket receive error: {e}")
            self.connected = False
            self._schedule_reconnect()
            
    async def request(self, method: str, params: Dict[str, Any], timeout: float = 60.0) -> Any:
        """Send RPC request and wait for response."""
        if not self.connected:
            await self.connect()
            
        req_id = str(uuid.uuid4())
        message = {
            "type": "req",
            "id": req_id,
            "method": method,
            "params": params
        }
        
        future = asyncio.get_event_loop().create_future()
        self.pending_requests[req_id] = future
        
        await self.ws.send(json.dumps(message))
        
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self.pending_requests.pop(req_id, None)
            raise
            
    async def chat_send(
        self,
        content: str,
        session_id: Optional[str] = None,
        genesis_headers: Optional[Dict[str, str]] = None
    ) -> str:
        """Send a chat message and collect streaming response."""
        session_id = session_id or str(uuid.uuid4())
        
        # Collect streaming text
        response_text = ""
        done_event = asyncio.Event()
        
        async def on_text_delta(payload):
            nonlocal response_text
            response_text += payload.get("text", "")
            
        async def on_run_complete(payload):
            done_event.set()
            
        # Register handlers
        self.event_handlers["agent.text.delta"] = on_text_delta
        self.event_handlers["agent.run.complete"] = on_run_complete
        
        try:
            await self.request("chat.send", {
                "content": content,
                "sessionId": session_id
            })
            
            # Wait for completion with timeout
            await asyncio.wait_for(done_event.wait(), timeout=300.0)
            return response_text
        finally:
            self.event_handlers.pop("agent.text.delta", None)
            self.event_handlers.pop("agent.run.complete", None)
            
    async def close(self):
        """Close the connection."""
        if self._receive_task:
            self._receive_task.cancel()
        if self.ws:
            await self.ws.close()
        self.connected = False


# Singleton instance
_client: Optional[OpenClawClient] = None


async def get_openclaw_client() -> OpenClawClient:
    """Get or create the singleton OpenClaw client."""
    global _client
    if _client is None:
        _client = OpenClawClient()
        await _client.connect()
    return _client


async def openclaw_chat_completion(
    messages: list,
    genesis_headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    OpenAI-compatible chat completion via OpenClaw.
    Used by llm_gateway to route requests.
    """
    client = await get_openclaw_client()
    
    # Extract last user message
    user_content = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_content = msg.get("content", "")
            break
    
    session_id = genesis_headers.get("X-Genesis-Session-ID") if genesis_headers else None
    response_text = await client.chat_send(user_content, session_id, genesis_headers)
    
    return {
        "id": f"openclaw-{uuid.uuid4()}",
        "object": "chat.completion",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": response_text
            },
            "finish_reason": "stop"
        }],
        "model": "openclaw-agent"
    }
