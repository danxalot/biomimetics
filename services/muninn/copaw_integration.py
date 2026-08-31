# MuninnDB Integration for Copaw
# 
# This module integrates MuninnDB with Copaw to log all conversation turns
# to GCP-based MuninnDB. NO local dependencies - all data stays in GCP.

import os
import json
import uuid
import aiohttp
from datetime import datetime
from typing import List, Dict, Any, Optional


class CopawMuninnBridge:
    """
    Bridge between Copaw and MuninnDB (GCP-only)
    
    All data is sent to GCP MuninnDB instance.
    NO local storage - everything stays in GCP free tier.
    """
    
    def __init__(
        self,
        muninn_gcp_url: str,  # e.g., "http://34.123.45.67:8097"
        session_id: str = None,
    ):
        """
        Initialize bridge to GCP MuninnDB
        
        Args:
            muninn_gcp_url: Full URL to GCP MuninnDB instance
            session_id: Unique session identifier
        """
        self.muninn_gcp_url = muninn_gcp_url.rstrip('/')
        self.session_id = session_id or str(uuid.uuid4())
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def log_conversation_turn(
        self,
        role: str,  # "user" or "assistant"
        content: str,
        tools_used: List[str] = None,
        files_accessed: List[str] = None,
        metadata: Dict[str, Any] = None,
    ):
        """
        Log a conversation turn to MuninnDB (GCP)
        
        Args:
            role: "user" or "assistant"
            content: The message content
            tools_used: List of tools used
            files_accessed: List of files accessed
            metadata: Additional metadata
        """
        
        engram = {
            "type": "conversation_turn",
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": self.session_id,
            "role": role,
            "content": {
                "text": content,
                "tools_used": tools_used or [],
                "files_accessed": files_accessed or [],
            },
            "metadata": metadata or {},
        }
        
        await self._send_engram(engram)
    
    async def log_pubsub_event(
        self,
        event_type: str,
        source: str,
        data: Dict[str, Any],
        attributes: Dict[str, str] = None,
    ):
        """
        Log a Pub/Sub event to MuninnDB (GCP)
        """
        
        engram = {
            "type": f"pubsub.{event_type}",
            "timestamp": datetime.utcnow().isoformat(),
            "source": source,
            "content": data,
            "metadata": {
                "attributes": attributes or {},
            },
        }
        
        await self._send_engram(engram)
    
    async def retrieve_relevant_memories(
        self,
        query: str = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve relevant memories from MuninnDB (GCP)
        """
        
        session = await self._get_session()
        
        params = {"limit": limit}
        if query:
            params["q"] = query
        
        try:
            async with session.get(
                f"{self.muninn_gcp_url}/engrams",
                params=params,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    return []
                
                data = await resp.json()
                return data
        except Exception as e:
            print(f"Failed to retrieve memories: {e}")
            return []
    
    async def _send_engram(self, engram: Dict[str, Any]):
        """Send engram to MuninnDB (GCP)"""
        
        session = await self._get_session()
        
        try:
            async with session.post(
                f"{self.muninn_gcp_url}/engrams",
                json=engram,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    print(f"Failed to send engram: {resp.status}")
        except Exception as e:
            # Don't fail conversation if MuninnDB is unavailable
            print(f"MuninnDB logging error: {e}")
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# Copaw hook function
async def copaw_message_hook(
    message: Dict[str, Any],
    bridge: CopawMuninnBridge,
):
    """
    Hook to log all Copaw messages to MuninnDB (GCP)
    """
    
    role = message.get("role", "unknown")
    content = message.get("content", "")
    
    # Extract metadata
    tools_used = []
    files_accessed = []
    
    metadata = message.get("metadata", {})
    if metadata:
        tools_used = metadata.get("tools_used", [])
        files_accessed = metadata.get("files_accessed", [])
    
    # Log to MuninnDB
    await bridge.log_conversation_turn(
        role=role,
        content=content,
        tools_used=tools_used,
        files_accessed=files_accessed,
        metadata={
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": bridge.session_id,
        },
    )
