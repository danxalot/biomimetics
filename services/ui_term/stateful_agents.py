"""
ARCA Stateful Agent Nodes
Persistent agent instances with memory and state management.
Each agent maintains conversation history and can be addressed by name.
"""

import os
import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
import logging
import redis
import httpx

logger = logging.getLogger(__name__)

# Start Central Config Integration
import sys
sys.path.append("/app/shared")
try:
    from shared.model_config import DEFAULTS
except ImportError:
    # Fallback default values if shared config is missing
    DEFAULTS = {
        "CHAT_MODEL": "gemini-2.0-flash-lite",
        "SERENA_MODEL": "gemma-4-31b-it",
        "ARCHITECT_MODEL": "gemini-exp-1206",
        "PLANNER_MODEL": "gemma-4-31b-it",
        "ENGINEER_MODEL": "gemini-2.5-flash",
        "REVIEWER_MODEL": "gemma-4-31b-it",
        "LOCAL_OPS_MODEL": "gemma-4-26b-a4b-it",
        "VISION_MODEL": "gemma-4-26b-a4b-it",
        "ROBOTICS_MODEL": "gemini-robotics-er",
        "LEARN_MODEL": "gemma-4-31b-it"
    }

# Model configuration from environment (all via Google AI Studio API)
# Priority: 1. Environment Variable, 2. Central Config Default, 3. Hardcoded Fallback
CHAT_MODEL = os.environ.get("ARCA_CHAT_MODEL", DEFAULTS.get("CHAT_MODEL", "gemini-2.0-flash-lite"))
SERENA_MODEL = os.environ.get("ARCA_SERENA_MODEL", DEFAULTS.get("SERENA_MODEL", "gemma-3-27b-it"))
ARCHITECT_MODEL = os.environ.get("ARCA_ARCHITECT_MODEL", DEFAULTS.get("ARCHITECT_MODEL", "gemini-exp-1206"))
PLANNER_MODEL = os.environ.get("ARCA_PLANNER_MODEL", DEFAULTS.get("PLANNER_MODEL", "gemma-3-27b-it"))
ENGINEER_MODEL = os.environ.get("ARCA_ENGINEER_MODEL", DEFAULTS.get("ENGINEER_MODEL", "gemini-2.5-flash"))
REVIEWER_MODEL = os.environ.get("ARCA_REVIEWER_MODEL", DEFAULTS.get("REVIEWER_MODEL", "gemma-3-27b-it"))
LOCAL_OPS_MODEL = os.environ.get("ARCA_LOCAL_OPS_MODEL", DEFAULTS.get("LOCAL_OPS_MODEL", "gemma-3-12b-it"))
VISION_MODEL = os.environ.get("ARCA_VISION_MODEL", DEFAULTS.get("VISION_MODEL", "gemma-3-12b-it"))
ROBOTICS_MODEL = os.environ.get("ARCA_ROBOTICS_MODEL", DEFAULTS.get("ROBOTICS_MODEL", "gemini-robotics-er"))
LEARN_MODEL = os.environ.get("ARCA_LEARN_MODEL", DEFAULTS.get("LEARN_MODEL", "gemma-3-27b-it"))

# Service URLs
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
VLLM_URL = os.environ.get("VLLM_BASE_URL", "http://vllm-server:8000/v1")
MCP_URL = os.environ.get("MCP_SERVER_URL", "http://mcp_server:8086")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")


@dataclass
class AgentMemory:
    """Memory store for an agent"""
    conversation_history: List[Dict] = field(default_factory=list)
    working_memory: Dict[str, Any] = field(default_factory=dict)
    last_active: datetime = field(default_factory=datetime.now)
    session_count: int = 0
    
    def add_message(self, role: str, content: str, metadata: Dict = None):
        """Add a message to conversation history"""
        self.conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        })
        self.last_active = datetime.now()
        # Keep last 50 messages
        if len(self.conversation_history) > 50:
            self.conversation_history = self.conversation_history[-50:]
    
    def get_context(self, max_messages: int = 10) -> str:
        """Get recent conversation context as string"""
        recent = self.conversation_history[-max_messages:]
        lines = []
        for msg in recent:
            lines.append(f"{msg['role'].upper()}: {msg['content']}")
        return "\n".join(lines)
    
    def to_dict(self) -> Dict:
        """Serialize memory to dict"""
        return {
            "conversation_history": self.conversation_history,
            "working_memory": self.working_memory,
            "last_active": self.last_active.isoformat(),
            "session_count": self.session_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "AgentMemory":
        """Deserialize memory from dict"""
        memory = cls()
        memory.conversation_history = data.get("conversation_history", [])
        memory.working_memory = data.get("working_memory", {})
        memory.last_active = datetime.fromisoformat(data.get("last_active", datetime.now().isoformat()))
        memory.session_count = data.get("session_count", 0)
        return memory


class StatefulAgentNode:
    """Base class for stateful agent nodes"""
    
    def __init__(
        self,
        name: str,
        model: str,
        provider: str = "google",  # 'google', 'local', 'openai'
        system_prompt: str = "",
        tools: List[str] = None,
        persist_memory: bool = True
    ):
        self.name = name
        self.model = model
        self.provider = provider
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.persist_memory = persist_memory
        self.memory = AgentMemory()
        self._redis = None
        
        logger.info(f"Initialized agent '{name}' with model '{model}' ({provider})")
    
    @property
    def redis(self):
        """Lazy Redis connection"""
        if self._redis is None:
            try:
                self._redis = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
        return self._redis
    
    def _memory_key(self) -> str:
        """Redis key for agent memory"""
        return f"agent:{self.name}:memory"
    
    def load_memory(self):
        """Load memory from Redis"""
        if not self.persist_memory or not self.redis:
            return
        try:
            data = self.redis.get(self._memory_key())
            if data:
                self.memory = AgentMemory.from_dict(json.loads(data))
                logger.info(f"Loaded memory for '{self.name}' ({len(self.memory.conversation_history)} messages)")
        except Exception as e:
            logger.warning(f"Failed to load memory for '{self.name}': {e}")
    
    def save_memory(self):
        """Save memory to Redis"""
        if not self.persist_memory or not self.redis:
            return
        try:
            self.redis.set(self._memory_key(), json.dumps(self.memory.to_dict()))
        except Exception as e:
            logger.warning(f"Failed to save memory for '{self.name}': {e}")
    
    async def _call_google(self, prompt: str) -> str:
        """Call Google AI Studio API"""
        if not GOOGLE_API_KEY:
            return "Error: GOOGLE_API_KEY not configured"
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                params={"key": GOOGLE_API_KEY},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.7,
                        "maxOutputTokens": 4096
                    }
                }
            )
            
            if response.status_code != 200:
                return f"Error: {response.status_code} - {response.text}"
            
            data = response.json()
            return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    
    async def _call_local(self, prompt: str) -> str:
        """Call local vLLM server"""
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{VLLM_URL}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 2048,
                    "temperature": 0.7
                }
            )
            
            if response.status_code != 200:
                return f"Error: {response.status_code} - {response.text}"
            
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    
    async def process(self, message: str, user: str = "user") -> Dict[str, Any]:
        """Process a message and return response"""
        self.load_memory()
        self.memory.add_message("user", message, {"user": user})
        
        # Build prompt with context
        context = self.memory.get_context()
        full_prompt = f"""{self.system_prompt}

## Recent Conversation
{context}

## Current Message
USER: {message}

Please respond as {self.name}:"""
        
        # Call appropriate provider
        try:
            if self.provider == "google":
                response_text = await self._call_google(full_prompt)
            elif self.provider == "local":
                response_text = await self._call_local(message)
            else:
                response_text = f"Unknown provider: {self.provider}"
        except Exception as e:
            logger.error(f"Agent '{self.name}' error: {e}")
            response_text = f"Error: {str(e)}"
        
        self.memory.add_message("assistant", response_text)
        self.save_memory()
        
        return {
            "agent": self.name,
            "model": self.model,
            "response": response_text,
            "timestamp": datetime.now().isoformat()
        }
    
    def clear_memory(self):
        """Clear agent memory"""
        self.memory = AgentMemory()
        self.save_memory()
        logger.info(f"Cleared memory for '{self.name}'")


# Pre-configured agent nodes
class ChatAgent(StatefulAgentNode):
    """User-facing chat agent for general interaction"""
    
    def __init__(self):
        super().__init__(
            name="chat",
            model=CHAT_MODEL,
            provider="google",
            system_prompt="""You are ARCA's friendly chat interface. You help users interact with the ARCA system.
You can answer questions, provide status updates, and guide users to the right agents for specific tasks.
Be concise, helpful, and friendly.""",
            persist_memory=True
        )


class SerenaAgent(StatefulAgentNode):
    """Serena - Noetic Code Agent for development tasks (Gemma 3 27B)"""
    
    def __init__(self):
        super().__init__(
            name="serena",
            model=SERENA_MODEL,
            provider="google",
            system_prompt="""You are Serena, the Noetic Code Agent for ARCA.
You excel at software development, code analysis, architecture decisions, and technical problem-solving.
You have access to MCP tools for file operations, code search, and system management.
Be thorough, precise, and provide working code examples when relevant.""",
            tools=["mcp_tools", "code_search", "file_operations"],
            persist_memory=True
        )


class LocalOpsAgent(StatefulAgentNode):
    """Local operations agent (Gemma 3 12B) - NO conversation history"""
    
    def __init__(self):
        super().__init__(
            name="local_ops",
            model=LOCAL_OPS_MODEL,
            provider="google",  # All via Google AI Studio
            system_prompt="""You are the Local Operations Agent for ARCA.
You handle system administration, file management, and operational tasks.
Each request is independent - you do not maintain conversation history.
Prioritize security and efficiency.""",
            persist_memory=False  # NO conversation history
        )


class VisionAgent(StatefulAgentNode):
    """Vision agent (Gemma 3 12B) - NO conversation history"""
    
    def __init__(self):
        super().__init__(
            name="vision",
            model=VISION_MODEL,
            provider="google",  # All via Google AI Studio
            system_prompt="""You are the Vision Agent for ARCA.
You process images and video for analysis tasks.
Each request is independent - you do not maintain conversation history.
You can describe images, detect objects, read text, and provide visual analysis.""",
            persist_memory=False  # NO conversation history
        )


class RoboticsAgent(StatefulAgentNode):
    """Robotics agent (Google Robotics 1.5 ER) - for physical task planning"""
    
    def __init__(self):
        super().__init__(
            name="robotics",
            model=ROBOTICS_MODEL,
            provider="google",
            system_prompt="""You are the Robotics Agent for ARCA.
You specialize in physical task planning, robot control, and embodied AI.
You can plan manipulation sequences, navigate environments, and coordinate robotic actions.""",
            persist_memory=True
        )


class LearnAgent(StatefulAgentNode):
    """Learning agent (Google LearnLM) - for educational and tutoring tasks"""
    
    def __init__(self):
        super().__init__(
            name="learn",
            model=LEARN_MODEL,
            provider="google",
            system_prompt="""You are the Learning Agent for ARCA powered by LearnLM.
You specialize in education, tutoring, and knowledge transfer.
You can explain concepts, create learning materials, and adapt to learner needs.""",
            persist_memory=True
        )


# Agent registry
_agent_registry: Dict[str, StatefulAgentNode] = {}


def get_agent(name: str) -> Optional[StatefulAgentNode]:
    """Get or create an agent by name"""
    if name not in _agent_registry:
        if name == "chat":
            _agent_registry[name] = ChatAgent()
        elif name == "serena":
            _agent_registry[name] = SerenaAgent()
        elif name == "local_ops":
            _agent_registry[name] = LocalOpsAgent()
        elif name == "vision":
            _agent_registry[name] = VisionAgent()
        elif name == "robotics":
            _agent_registry[name] = RoboticsAgent()
        elif name == "learn":
            _agent_registry[name] = LearnAgent()
        else:
            return None
    return _agent_registry[name]


def list_agents() -> List[Dict[str, str]]:
    """List all available agents"""
    agents = [
        {"name": "chat", "model": CHAT_MODEL, "description": "General chat interface", "has_memory": True},
        {"name": "serena", "model": SERENA_MODEL, "description": "Noetic code agent (Gemma 4 31B)", "has_memory": True},
        {"name": "local_ops", "model": LOCAL_OPS_MODEL, "description": "Local operations (Gemma 4 26B-A4B)", "has_memory": False},
        {"name": "vision", "model": VISION_MODEL, "description": "Vision analysis (Gemma 4 26B-A4B)", "has_memory": False},
        {"name": "robotics", "model": ROBOTICS_MODEL, "description": "Physical task planning (Robotics ER)", "has_memory": True},
        {"name": "learn", "model": LEARN_MODEL, "description": "Education/tutoring (LearnLM)", "has_memory": True},
    ]
    return agents


async def route_to_agent(message: str, agent_name: str = None, user: str = "user") -> Dict[str, Any]:
    """Route a message to the appropriate agent"""
    # Auto-detect agent from message if not specified
    if not agent_name:
        message_lower = message.lower()
        if any(kw in message_lower for kw in ["code", "develop", "fix", "implement", "debug", "serena"]):
            agent_name = "serena"
        elif any(kw in message_lower for kw in ["robot", "physical", "manipulate", "navigate", "arm", "gripper"]):
            agent_name = "robotics"
        elif any(kw in message_lower for kw in ["learn", "teach", "explain", "tutor", "education"]):
            agent_name = "learn"
        elif any(kw in message_lower for kw in ["image", "picture", "video", "see", "look", "camera"]):
            agent_name = "vision"
        elif any(kw in message_lower for kw in ["local", "secure", "private", "admin", "system"]):
            agent_name = "local_ops"
        else:
            agent_name = "chat"
    
    agent = get_agent(agent_name)
    if not agent:
        return {"error": f"Unknown agent: {agent_name}", "available": [a["name"] for a in list_agents()]}
    
    return await agent.process(message, user)


# CLI for testing
if __name__ == "__main__":
    import sys
    
    async def main():
        print("ARCA Stateful Agent Nodes")
        print("=" * 50)
        print("\nAvailable agents:")
        for agent in list_agents():
            print(f"  - {agent['name']}: {agent['model']} ({agent['description']})")
        
        if len(sys.argv) > 2:
            agent_name = sys.argv[1]
            message = " ".join(sys.argv[2:])
            print(f"\nRouting to {agent_name}: {message}")
            result = await route_to_agent(message, agent_name)
            print(f"\nResponse:\n{result.get('response', result)}")
    
    asyncio.run(main())
