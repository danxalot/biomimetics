# Gemini Reasoning Integration for ARCA User Interaction Terminal
# Uses Google AI Studio with configurable models for real-time interaction
# Model names are configurable via environment variables

import asyncio
import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
import httpx
import logging

logger = logging.getLogger(__name__)

# Model configuration (all via Google AI Studio API)
CHAT_MODEL = os.environ.get("ARCA_CHAT_MODEL", "gemini-2.0-flash-lite")
SERENA_MODEL = os.environ.get("ARCA_SERENA_MODEL", "gemma-3-27b-it")
ARCHITECT_MODEL = os.environ.get("ARCA_ARCHITECT_MODEL", "gemini-2.5-pro-preview-06-05")
PLANNER_MODEL = os.environ.get("ARCA_PLANNER_MODEL", "gemini-2.0-flash-lite")
ENGINEER_MODEL = os.environ.get("ARCA_ENGINEER_MODEL", "gemini-2.0-flash")
REVIEWER_MODEL = os.environ.get("ARCA_REVIEWER_MODEL", "gemma-3-27b-it")
LOCAL_OPS_MODEL = os.environ.get("ARCA_LOCAL_OPS_MODEL", "gemma-3-12b-it")
ROBOTICS_MODEL = os.environ.get("ARCA_ROBOTICS_MODEL", "gemini-robotics-er")
LEARN_MODEL = os.environ.get("ARCA_LEARN_MODEL", "gemma-3-27b-it")  # Learning model (was LearnLM)


class MCPToolClient:
    """Client for calling MCP server tools"""
    def __init__(self, mcp_url: str = "http://mcp_server:8086"):
        self.mcp_url = mcp_url
        self.available = False
    
    async def check_availability(self) -> bool:
        """Check if MCP server is available"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.mcp_url}/health")
                self.available = response.status_code == 200
                return self.available
        except:
            self.available = False
            return False
    
    async def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call an MCP tool using JSON-RPC format"""
        if not self.available:
            await self.check_availability()
        
        if not self.available:
            return {"error": "MCP server not available"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.mcp_url}/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": tool_name,
                            "arguments": params
                        },
                        "id": 1
                    }
                )
                result = response.json()
                return result.get("result", result)
        except Exception as e:
            return {"error": str(e)}
    
    async def read_file(self, path: str) -> str:
        """Read a file via MCP"""
        result = await self.call_tool("file_read", {"path": path})
        if "error" in result:
            return f"Error reading file: {result['error']}"
        return result.get("content", str(result))
    
    async def list_directory(self, path: str) -> List[str]:
        """List directory contents via MCP"""
        result = await self.call_tool("file_list", {"path": path})
        if "error" in result:
            return []
        return result.get("files", [])
    
    async def run_shell(self, command: str) -> str:
        """Run shell command via MCP"""
        result = await self.call_tool("run_shell", {"command": command})
        if "error" in result:
            return f"Error: {result['error']}"
        return result.get("output", str(result))
    
    async def blackboard_read(self, key: str) -> Any:
        """Read from Redis blackboard"""
        result = await self.call_tool("blackboard_read", {"key": key})
        return result
    
    async def blackboard_write(self, key: str, value: Any) -> Dict:
        """Write to Redis blackboard"""
        return await self.call_tool("blackboard_write", {"key": key, "value": value})


class GeminiAIStudioClient:
    """Client for Google AI Studio API (Gemini models)"""
    
    def __init__(self, api_key: str, model: str = None):
        self.api_key = api_key
        self.model = model or CHAT_MODEL
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        
    async def generate(self, prompt: str, system_prompt: str = None, max_tokens: int = 4096) -> Dict[str, Any]:
        """Generate response from Gemini"""
        try:
            url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
            
            contents = []
            if system_prompt:
                contents.append({
                    "role": "user",
                    "parts": [{"text": f"System instructions: {system_prompt}"}]
                })
                contents.append({
                    "role": "model", 
                    "parts": [{"text": "Understood. I will follow these instructions."}]
                })
            
            contents.append({
                "role": "user",
                "parts": [{"text": prompt}]
            })
            
            payload = {
                "contents": contents,
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": 0.7
                }
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                result = response.json()
                
                # Extract text from Gemini response
                candidates = result.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        return {
                            "text": parts[0].get("text", ""),
                            "finish_reason": candidates[0].get("finishReason", "STOP"),
                            "usage": result.get("usageMetadata", {})
                        }
                
                return {"text": "", "error": "No response generated"}
                
        except httpx.HTTPStatusError as e:
            logger.error(f"Gemini API error: {e.response.status_code} - {e.response.text}")
            return {"text": "", "error": f"API error: {e.response.status_code}"}
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            return {"text": "", "error": str(e)}


class GeminiReasoningWorkflow:
    """
    Reasoning workflow using configurable Gemini models for user interaction.
    Model names are set via ARCA_*_MODEL environment variables.
    """
    
    def __init__(self, conversation_history: List[Dict] = None, mcp_url: str = None):
        self.conversation_history = conversation_history or []
        self.proposals = {}
        self.api_key = self._load_api_key()
        self.model = CHAT_MODEL  # Configurable via ARCA_CHAT_MODEL env var
        
        # Initialize clients
        self.gemini = GeminiAIStudioClient(self.api_key, self.model) if self.api_key else None
        self.mcp_client = MCPToolClient(mcp_url or os.getenv("MCP_SERVER_URL", "http://mcp_server:8086"))
        self.use_mcp_tools = True

    def _load_api_key(self) -> str:
        """Load Google AI Studio API key from secrets"""
        secrets_paths = [
            "/app/secrets/google_ai_studio",
            "/mnt/mcp_storage/ARCA/.secrets/google_ai_studio",
            "/home/ubuntu/ARCA/.secrets/google_ai_studio",
            os.path.expanduser("~/.secrets/google_ai_studio")
        ]
        
        # Check environment first
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_AI_STUDIO_API")
        if api_key:
            return api_key
        
        # Try file paths
        for path in secrets_paths:
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        content = f.read().strip()
                        if "GOOGLE_AI_STUDIO_API=" in content:
                            return content.split("=", 1)[1].strip()
                        elif "=" in content:
                            return content.split("=", 1)[1].strip()
                        return content
                except Exception as e:
                    logger.warning(f"Failed to load API key from {path}: {e}")
        
        logger.warning("Google AI Studio API key not found")
        return ""

    async def chat(self, message: str, session_id: str = None) -> Dict[str, Any]:
        """
        Main chat endpoint - process user message and return response.
        This is the primary interaction method.
        """
        if not self.gemini:
            return {
                "response": "Error: Google AI Studio API key not configured. Please check secrets.",
                "error": True
            }
        
        # Build context from conversation history
        context = self._build_context()
        
        # Check for special commands
        if message.lower().startswith("/"):
            return await self._handle_command(message)
        
        # System prompt for interaction agent
        system_prompt = """You are ARCA's User Interaction Agent - a helpful, knowledgeable assistant for the ARCA system.

ARCA is an Agentic AI orchestration system with:
- Neo4j knowledge graph for ontology and relationships
- Redis blackboard for real-time state management
- Multi-agent architecture with tiered agents (Architect, Planner, Engineer, Reviewer, Ops)
- MCP (Model Context Protocol) tools for system interaction

Your role:
1. Answer questions about ARCA's architecture and capabilities
2. Help users understand and interact with the system
3. Explain agent workflows and reasoning
4. Provide status updates when asked
5. Execute simple queries via MCP tools when appropriate

Be concise, helpful, and technically accurate. If you don't know something, say so."""

        # Build the prompt with context
        prompt = f"""Previous conversation context:
{context}

User message: {message}

Respond helpfully and concisely."""

        # Generate response
        result = await self.gemini.generate(prompt, system_prompt)
        
        if result.get("error"):
            return {
                "response": f"Error generating response: {result['error']}",
                "error": True
            }
        
        response_text = result.get("text", "")
        
        # Update conversation history
        self.conversation_history.append({"role": "user", "content": message})
        self.conversation_history.append({"role": "assistant", "content": response_text})
        
        return {
            "response": response_text,
            "model": self.model,
            "usage": result.get("usage", {}),
            "session_id": session_id
        }

    def _build_context(self, max_messages: int = 10) -> str:
        """Build conversation context string"""
        recent = self.conversation_history[-max_messages:]
        context_parts = []
        for msg in recent:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:500]  # Truncate long messages
            context_parts.append(f"{role}: {content}")
        return "\n".join(context_parts) if context_parts else "No previous context."

    async def _handle_command(self, command: str) -> Dict[str, Any]:
        """Handle slash commands"""
        cmd = command.lower().strip()
        
        if cmd == "/status":
            return await self._get_system_status()
        elif cmd == "/agents":
            return await self._get_agent_status()
        elif cmd == "/blackboard":
            return await self._get_blackboard_state()
        elif cmd.startswith("/query "):
            cypher = command[7:].strip()
            return await self._run_neo4j_query(cypher)
        elif cmd == "/help":
            return {
                "response": """**Available Commands:**
- `/status` - Get system status
- `/agents` - List active agents
- `/blackboard` - Show Redis blackboard state
- `/query <cypher>` - Run Neo4j query
- `/help` - Show this help

Or just chat naturally!"""
            }
        else:
            return {"response": f"Unknown command: {cmd}. Use /help for available commands."}

    async def _get_system_status(self) -> Dict[str, Any]:
        """Get ARCA system status"""
        try:
            global_state = await self.mcp_client.blackboard_read("arca:state:global")
            genesis_status = await self.mcp_client.blackboard_read("genesis:status")
            
            return {
                "response": f"""**ARCA System Status**
- Genesis: {genesis_status or 'unknown'}
- Global State: {json.dumps(global_state, indent=2) if global_state else 'Not available'}
- MCP Server: {'Connected' if self.mcp_client.available else 'Disconnected'}
- Model: {self.model}"""
            }
        except Exception as e:
            return {"response": f"Error getting status: {e}"}

    async def _get_agent_status(self) -> Dict[str, Any]:
        """Get agent registry status"""
        agents = {
            "architect": {"model": ARCHITECT_MODEL, "tier": 3, "queue": "tier3.architect"},
            "planner": {"model": PLANNER_MODEL, "tier": 2, "queue": "tier2.planner"},
            "engineer": {"model": ENGINEER_MODEL, "tier": 1, "queue": "tier1.engineer"},
            "reviewer": {"model": REVIEWER_MODEL, "tier": 1, "queue": "tier1.action"},
            "ops_controller": {"model": CHAT_MODEL, "tier": 1, "queue": "tier1.action"},
            "interaction": {"model": CHAT_MODEL, "tier": 0, "queue": "user.interaction"}
        }
        
        lines = ["**Agent Registry:**"]
        for name, info in agents.items():
            lines.append(f"- **{name}**: {info['model']} (Tier {info['tier']})")
        
        return {"response": "\n".join(lines)}

    async def _get_blackboard_state(self) -> Dict[str, Any]:
        """Get current blackboard state"""
        try:
            keys = ["arca:state:global", "genesis:status", "genesis:ops:completed"]
            state = {}
            for key in keys:
                value = await self.mcp_client.blackboard_read(key)
                state[key] = value
            
            return {
                "response": f"**Redis Blackboard State:**\n```json\n{json.dumps(state, indent=2)}\n```"
            }
        except Exception as e:
            return {"response": f"Error reading blackboard: {e}"}

    async def _run_neo4j_query(self, cypher: str) -> Dict[str, Any]:
        """Run a Neo4j Cypher query"""
        try:
            result = await self.mcp_client.call_tool("neo4j_run_cypher", {"query": cypher})
            return {
                "response": f"**Query Result:**\n```\n{json.dumps(result, indent=2)}\n```"
            }
        except Exception as e:
            return {"response": f"Query error: {e}"}

    async def invoke_reasoning(self, context_depth: int = 10) -> Dict[str, Any]:
        """Analyze recent conversation and generate proposal (legacy compatibility)"""
        recent_context = self.conversation_history[-context_depth:]
        analysis = await self._analyze_context(recent_context)
        proposal = await self._create_proposal_from_analysis(analysis)
        
        return {
            "context_used": len(recent_context),
            "analysis": analysis,
            "proposal": proposal,
            "status": "awaiting_approval"
        }

    async def _analyze_context(self, context: List[Dict]) -> Dict[str, Any]:
        """Analyze conversation context"""
        if not self.gemini:
            return {"error": "API key not configured"}
        
        formatted_context = "\n".join([
            f"{msg.get('role', 'user')}: {msg.get('content', '')}"
            for msg in context
        ])
        
        prompt = f"""Analyze this conversation and provide:
1. Summary of discussion
2. Key requirements mentioned
3. Recommended technical approach
4. Step-by-step reasoning

Conversation:
{formatted_context}

Respond in JSON format with: summary, key_requirements, technical_approach, reasoning_chain"""

        result = await self.gemini.generate(prompt)
        text = result.get("text", "")
        
        # Try to parse JSON
        try:
            # Find JSON in response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
        
        return {
            "summary": text[:500],
            "key_requirements": [],
            "technical_approach": text,
            "reasoning_chain": []
        }

    async def _create_proposal_from_analysis(self, analysis: Dict) -> Dict[str, Any]:
        """Create a proposal from analysis"""
        proposal_id = f"proposal_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        proposal = {
            "id": proposal_id,
            "timestamp": datetime.utcnow().isoformat(),
            "summary": analysis.get("summary", ""),
            "implementation_plan": {"tasks": [], "job_submissions": []},
            "approval_status": "pending"
        }
        self.proposals[proposal_id] = proposal
        return proposal

    async def approve_proposal(self, proposal_id: str) -> Dict[str, Any]:
        """Approve a proposal"""
        if proposal_id not in self.proposals:
            return {"error": "Proposal not found"}
        
        proposal = self.proposals[proposal_id]
        proposal["approval_status"] = "approved"
        return {"status": "approved", "proposal": proposal}


# Backward compatibility function
async def handle_reasoning_trigger(message: str, conversation_history: List[Dict]) -> Dict[str, Any]:
    """Handle reasoning triggers (legacy compatibility)"""
    triggers = ["execute this", "create proposal", "implement this", "make this happen"]
    
    if any(trigger in message.lower() for trigger in triggers):
        workflow = GeminiReasoningWorkflow(conversation_history)
        result = await workflow.invoke_reasoning()
        return {"reasoning_triggered": True, "result": result}
    
    return {"reasoning_triggered": False}


# Export the main class for use in main.py
__all__ = ["GeminiReasoningWorkflow", "handle_reasoning_trigger", "MCPToolClient"]
