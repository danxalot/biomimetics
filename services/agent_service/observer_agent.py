
import asyncio
import json
import logging
import os
import signal
from typing import Dict, Any

from mcp_client import MCPClient

import httpx

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("observer_agent")

CONVERSATIONAL_HDC_URL = os.getenv("CONVERSATIONAL_HDC_URL", "http://conversational_hdc:8096")
GEOMETRY_KERNEL_URL = os.getenv("GEOMETRY_KERNEL_URL", "http://geometry_kernel:8089")

class ObserverAgent:
    """
    The Learning Engine (Pythagoras & Oracle).
    Silent Listener that subscribes to 'arca:activity',
    vectorizes it via HDC, and creates Geometric Memories.
    """
    def __init__(self):
        self.mcp_client = MCPClient()
        self.redis = None
        self.running = True
        
        # Redis setup
        import redis.asyncio as redis
        redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
        self.redis = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        logger.info(f"Observer Agent initialized. Connected to Redis at {redis_url}")
        
    async def listen(self):
        """Subscribe to Redis channel and process messages."""
        async with self.redis.pubsub() as pubsub:
            await pubsub.subscribe("arca:activity")
            logger.info("Subscribed to 'arca:activity'")
            
            while self.running:
                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message:
                        await self.process_message(message["data"])
                except Exception as e:
                    logger.error(f"Error in listener loop: {e}")
                    await asyncio.sleep(1)

    async def get_hdc_vector(self, content: str) -> list:
        """Call The Oracle (HDC) to get a vector representation of the log."""
        try:
            # We use the /context endpoint or a new /encode endpoint. 
            # Re-using /conversation/message logic but purely for vector generation
            # Or better: /conversation/encode if it existed.
            # Fallback: Use message endpoint with a dummy session to get context + vector?
            # Actually, `api.py` in HDC service might not return vector directly in response.
            # Let's assume we can get it or compute a lightweight one.
            # CHECK: `conversational_hdc/api.py` was viewed. It returns `hdc_context` string.
            # It might not return the vector. 
            # Plan B: Use the `embedding_service` if HDC doesn't expose vector, 
            # OR just send text to GeometryKernel and let it handle embedding (if it could).
            # The plan said: "Encoder (The Oracle): conversational_hdc".
            # Let's try to pass the text to HDC to get the "Context" which is a semantic summary,
            # and perhaps rely on `embedding_service` for the coordinate vector.
            
            # For now, let's use the `embedding_service` for the Geometry Vector (Position),
            # and HDC for the "Resonance" (Mass/Energy/TextContext).
            
            return [] # Placeholder if we don't have direct vector access yet.
        except Exception:
            return []

    async def ingest_geometry(self, content: str, source: str, metadata: dict):
        """Feed Pythagoras (Geometry Kernel)."""
        try:
            # We need a vector for the geometry kernel.
            # Ideally we call embedding service here.
            # For efficiency in this loop, we might optimize.
            
            payload = {
                "title": f"System Event: {source}",
                "content_snippet": content[:500],
                "source": source,
                "mode": "store",
                # "vector": ... (Kernel will use default if empty, or we should embed)
            }
            
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(f"{GEOMETRY_KERNEL_URL}/geometry/ingest", json=payload)
                
        except Exception as e:
            logger.debug(f"Geometry Ingest failed: {e}")

    async def process_message(self, data_str: str):
        """Process incoming activity log."""
        try:
            event = json.loads(data_str)
            event_type = event.get('type')
            
            # Filter for meaningful events (don't loop on every debug print)
            if event_type in ["agent_thought", "tool_use", "system_alert", "error"]:
                logger.info(f"Observed event: {event_type}")
                
                details = event.get('details', {})
                timestamp = event.get('timestamp')
                content = f"[{event_type}] {json.dumps(details)}"
                
                # 1. Feed Geometry (Pythagoras)
                # This creates the "Shape" of the system state
                asyncio.create_task(self.ingest_geometry(content, source="observer", metadata=event))

                # 2. Persist to Memory (Legacy MCP)
                # Keep this for archival text retrieval
                memory_content = f"Timestamp: {timestamp}\nType: {event_type}\nDetails: {json.dumps(details)}"
                chunk = {
                    "content": memory_content,
                    "sequence": 0,
                    "page_number": 0,
                    "section_title": f"Event: {event_type}"
                }
                
                await self.mcp_client.call_tool("store_memory", {
                    "content_type": "text_chunks",
                    "content": {
                        "source_id": 0, 
                        "chunks": [chunk]
                    }
                })
            
        except Exception as e:
            logger.error(f"Failed to process message: {e}")

    async def run(self):
        await self.listen()

async def main():
    agent = ObserverAgent()
    
    # Handle shutdown
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    
    def signal_handler():
        agent.running = False
        stop_event.set()
        
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
        
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main())
