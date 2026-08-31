"""
UnifiedMemorySystem Client
Acts as a proxy client to the centralized Memory System Service.
Replaces direct database access with HTTP calls to the memory_manager.
"""

import os
import logging
import httpx
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class UnifiedMemorySystem:
    """
    Client for the centralized ARCA Memory System Service.
    Routes all memory operations to the memory_system container via HTTP.
    """

    def __init__(self, base_url: str = None):
        self.base_url = base_url or os.environ.get("MEMORY_SYSTEM_URL", "http://memory_system:8001")
        self.client = httpx.AsyncClient(timeout=30.0)
        logger.info(f"UnifiedMemorySystem Client initialized with URL: {self.base_url}")

    async def initialize(self):
        """Verify connection to Memory System Service"""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                logger.info(f"Connected to Memory System Service: {status}")
                return True
            else:
                logger.warning(f"Memory System Service health check failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Failed to connect to Memory System Service: {e}")
            return False

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

    async def add_conversation_turn(self, session_id: str, user_id: str,
                                  user_message: str, assistant_response: str,
                                  metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Add a conversation turn to memory via API"""
        try:
            payload = {
                "session_id": session_id,
                "user_id": user_id,
                "user_message": user_message,
                "assistant_response": assistant_response,
                "metadata": metadata
            }
            response = await self.client.post(f"{self.base_url}/conversation", json=payload)
            response.raise_for_status()
            result = response.json()
            return result.get("result", {})
        except Exception as e:
            logger.error(f"Error adding conversation turn via API: {e}")
            # Return a safe fallback to prevent crashes
            return {"working_memory": None, "episodic_memory": None, "structural_memory": None, "error": str(e)}

    async def get_comprehensive_context(self, session_id: str, query: str,
                                      user_id: str = "default") -> Dict[str, Any]:
        """Get comprehensive context from all memory layers via API"""
        try:
            payload = {
                "session_id": session_id,
                "query": query,
                "user_id": user_id
            }
            response = await self.client.post(f"{self.base_url}/context", json=payload)
            response.raise_for_status()
            result = response.json()
            return result.get("context", {})
        except Exception as e:
            logger.error(f"Error getting context via API: {e}")
            return {}

    async def add_document(self, content: str, source: str, document_type: str = "document") -> List[str]:
        """Add a document to memory via API"""
        try:
            payload = {
                "content": content,
                "source": source,
                "document_type": document_type
            }
            response = await self.client.post(f"{self.base_url}/document", json=payload)
            response.raise_for_status()
            result = response.json()
            return result.get("result", [])
        except Exception as e:
            logger.error(f"Error adding document via API: {e}")
            return []

    async def record_agent_trajectory(self, trajectory: Any) -> Dict[str, Any]:
        """Record agent trajectory for learning via API"""
        try:
            # Convert ReasoningTrajectory object to dict if needed
            if hasattr(trajectory, 'to_dict'):
                traj_data = trajectory.to_dict()
            else:
                # Manual conversion if it's a Pydantic model or dataclass
                traj_data = {
                    "agent_id": getattr(trajectory, "agent_id", "unknown"),
                    "task_input": getattr(trajectory, "initial_state", {}).get("task_input", ""),
                    "task_type": getattr(trajectory, "initial_state", {}).get("task_type", "general"),
                    "actions_taken": getattr(trajectory, "actions_taken", []),
                    "context_used": getattr(trajectory, "context_used", {}),
                    "outcome": getattr(trajectory, "outcome", ""),
                    "execution_time": getattr(trajectory, "execution_time", 0.0),
                    "timestamp": getattr(trajectory, "timestamp", datetime.now().isoformat())
                }
                # Handle datetime serialization if needed
                if isinstance(traj_data["timestamp"], datetime):
                    traj_data["timestamp"] = traj_data["timestamp"].isoformat()

            response = await self.client.post(f"{self.base_url}/trajectory", json=traj_data)
            response.raise_for_status()
            result = response.json()
            return result.get("result", {})
        except Exception as e:
            logger.error(f"Error recording trajectory via API: {e}")
            return {"error": str(e)}

    async def get_agent_learning_context(self, agent_id: str, task_context: str) -> Dict[str, Any]:
        """Get learning context via API"""
        try:
            payload = {
                "agent_id": agent_id,
                "task_context": task_context
            }
            response = await self.client.post(f"{self.base_url}/learning", json=payload)
            response.raise_for_status()
            result = response.json()
            return result.get("learning_context", {})
        except Exception as e:
            logger.error(f"Error getting learning context via API: {e}")
            return {}