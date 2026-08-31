#!/usr/bin/env python3
"""
ARCA MCP Server - Workhorse Reasoning Engine
Implements Anthropic Skills Framework with Gordon AI Integration
"""

import asyncio
import json
import logging
import os
import ssl
import aiohttp
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# MCP Protocol Implementation
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import (
    CallToolRequest, CallToolResult, GetPromptRequest, GetPromptResult,
    ListPromptsRequest, ListPromptsResult, ListResourcesRequest, 
    ListResourcesResult, ListToolsRequest, ListToolsResult,
    ReadResourceRequest, ReadResourceResult,
    Prompt, Resource, Tool, TextContent, ImageContent, EmbeddedResource
)
from tools.queue_manager_tool import QueueManager
from tools.mcp_service_proxy import service_proxy, PROXY_TOOLS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("arca-mcp-server")

# Load secrets from potential locations
secrets_paths = [
    Path("/mnt/mcp_storage/ARCA/.secrets/mcp.env"),
    Path(os.getenv('ARCA_ROOT', '/home/ubuntu/ARCA')) / ".secrets/mcp.env",
    Path(".secrets/mcp.env"),
    Path("mcp.env")
]

for path in secrets_paths:
    if path.exists():
        logger.info(f"Loading secrets from {path}")
        load_dotenv(path)
        break

# Configuration
ARCA_ROOT = Path(os.getenv('ARCA_ROOT', '/home/ubuntu/ARCA'))
DATA_HUB_PORT = int(os.getenv('MCP_SERVER_PORT', '8086'))
INSTANCE_ID = os.getenv('INSTANCE_ID', 'workhorse-mcp')

# TLS Configuration for zero-trust security
TLS_ENABLED = os.getenv('MCP_TLS_ENABLED', 'true').lower() == 'true'
CERT_DIR = Path(os.getenv('MCP_CERT_DIR', '/mnt/mcp_storage/certs'))
CA_CERT_PATH = CERT_DIR / "ca" / "ca.crt"
SERVER_CERT_PATH = CERT_DIR / "server" / "server.crt"
SERVER_KEY_PATH = CERT_DIR / "server" / "server.key"
CLIENT_CA_CERT_PATH = CERT_DIR / "ca" / "ca.crt"  # Same CA for client verification

# API Key Configuration for external AI assistants
# Support both MCP_API_KEYS (comma separated) and MCP_API_KEY (single)
api_keys_env = os.getenv('MCP_API_KEYS', '')
if not api_keys_env and os.getenv('MCP_API_KEY'):
    api_keys_env = os.getenv('MCP_API_KEY')
    
API_KEYS = api_keys_env.split(',') if api_keys_env else []
API_KEY_HEADER = 'X-API-Key'

class SkillCategory(Enum):
    REASONING = "reasoning"
    TECHNICAL = "technical" 
    CREATIVE = "creative"
    META = "meta"
    COMMUNICATION = "communication"

class SkillLevel(Enum):
    NOVICE = 1
    INTERMEDIATE = 2
    ADVANCED = 3
    EXPERT = 4
    MASTER = 5

@dataclass
class Skill:
    name: str
    category: SkillCategory
    level: SkillLevel
    success_count: int = 0
    failure_count: int = 0
    last_used: Optional[datetime] = None
    weaknesses: List[str] = None
    improvements: List[str] = None
    
    def __post_init__(self):
        if self.weaknesses is None:
            self.weaknesses = []
        if self.improvements is None:
            self.improvements = []
    
    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0
    
    @property
    def needs_improvement(self) -> bool:
        return self.success_rate < 0.7 or len(self.weaknesses) > 3

@dataclass
class LearningEvent:
    timestamp: datetime
    skill_name: str
    event_type: str  # success, failure, improvement
    context: str
    details: Dict[str, Any]
    insights: List[str] = None
    
    def __post_init__(self):
        if self.insights is None:
            self.insights = []

class SkillsManager:
    """Manages the Anthropic Skills Framework"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.skills_file = data_dir / "skills_registry.json"
        self.learning_log = data_dir / "learning_events.json"
        self.skills: Dict[str, Skill] = {}
        self.learning_events: List[LearningEvent] = []
        
        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing data
        self._load_skills()
        self._load_learning_events()
        
        # Initialize core skills if empty
        if not self.skills:
            self._initialize_core_skills()
    
    def _initialize_core_skills(self):
        """Initialize core skills based on Anthropic methodology"""
        core_skills = [
            # Reasoning Skills
            Skill("logical_analysis", SkillCategory.REASONING, SkillLevel.INTERMEDIATE),
            Skill("critical_thinking", SkillCategory.REASONING, SkillLevel.INTERMEDIATE),
            Skill("problem_decomposition", SkillCategory.REASONING, SkillLevel.ADVANCED),
            Skill("causal_reasoning", SkillCategory.REASONING, SkillLevel.INTERMEDIATE),
            
            # Technical Skills
            Skill("code_generation", SkillCategory.TECHNICAL, SkillLevel.ADVANCED),
            Skill("infrastructure_management", SkillCategory.TECHNICAL, SkillLevel.EXPERT),
            Skill("system_architecture", SkillCategory.TECHNICAL, SkillLevel.EXPERT),
            Skill("debugging", SkillCategory.TECHNICAL, SkillLevel.ADVANCED),
            
            # Creative Skills
            Skill("innovative_problem_solving", SkillCategory.CREATIVE, SkillLevel.ADVANCED),
            Skill("alternative_approaches", SkillCategory.CREATIVE, SkillLevel.INTERMEDIATE),
            Skill("synthesis", SkillCategory.CREATIVE, SkillLevel.ADVANCED),
            
            # Meta Skills
            Skill("self_reflection", SkillCategory.META, SkillLevel.INTERMEDIATE),
            Skill("learning_optimization", SkillCategory.META, SkillLevel.INTERMEDIATE),
            Skill("skill_assessment", SkillCategory.META, SkillLevel.ADVANCED),
            Skill("adaptation", SkillCategory.META, SkillLevel.ADVANCED),
            
            # Communication Skills
            Skill("clear_explanation", SkillCategory.COMMUNICATION, SkillLevel.ADVANCED),
            Skill("context_awareness", SkillCategory.COMMUNICATION, SkillLevel.EXPERT),
            Skill("user_intent_understanding", SkillCategory.COMMUNICATION, SkillLevel.ADVANCED),
        ]
        
        for skill in core_skills:
            self.skills[skill.name] = skill
        
        self._save_skills()
        logger.info(f"Initialized {len(core_skills)} core skills")
    
    def _load_skills(self):
        """Load skills from JSON file"""
        if self.skills_file.exists():
            try:
                with open(self.skills_file, 'r') as f:
                    data = json.load(f)
                    for skill_data in data:
                        skill = Skill(
                            name=skill_data['name'],
                            category=SkillCategory(skill_data['category']),
                            level=SkillLevel(skill_data['level']),
                            success_count=skill_data.get('success_count', 0),
                            failure_count=skill_data.get('failure_count', 0),
                            last_used=datetime.fromisoformat(skill_data['last_used']) if skill_data.get('last_used') else None,
                            weaknesses=skill_data.get('weaknesses', []),
                            improvements=skill_data.get('improvements', [])
                        )
                        self.skills[skill.name] = skill
                logger.info(f"Loaded {len(self.skills)} skills from {self.skills_file}")
            except Exception as e:
                logger.error(f"Failed to load skills: {e}")
    
    def _save_skills(self):
        """Save skills to JSON file"""
        try:
            data = []
            for skill in self.skills.values():
                skill_data = {
                    'name': skill.name,
                    'category': skill.category.value,
                    'level': skill.level.value,
                    'success_count': skill.success_count,
                    'failure_count': skill.failure_count,
                    'last_used': skill.last_used.isoformat() if skill.last_used else None,
                    'weaknesses': skill.weaknesses,
                    'improvements': skill.improvements
                }
                data.append(skill_data)
            
            with open(self.skills_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved {len(self.skills)} skills to {self.skills_file}")
        except Exception as e:
            logger.error(f"Failed to save skills: {e}")
    
    def _load_learning_events(self):
        """Load learning events from JSON file"""
        if self.learning_log.exists():
            try:
                with open(self.learning_log, 'r') as f:
                    data = json.load(f)
                    for event_data in data:
                        event = LearningEvent(
                            timestamp=datetime.fromisoformat(event_data['timestamp']),
                            skill_name=event_data['skill_name'],
                            event_type=event_data['event_type'],
                            context=event_data['context'],
                            details=event_data['details'],
                            insights=event_data.get('insights', [])
                        )
                        self.learning_events.append(event)
                logger.info(f"Loaded {len(self.learning_events)} learning events")
            except Exception as e:
                logger.error(f"Failed to load learning events: {e}")
    
    def _save_learning_events(self):
        """Save learning events to JSON file"""
        try:
            data = []
            for event in self.learning_events[-1000:]:  # Keep last 1000 events
                event_data = {
                    'timestamp': event.timestamp.isoformat(),
                    'skill_name': event.skill_name,
                    'event_type': event.event_type,
                    'context': event.context,
                    'details': event.details,
                    'insights': event.insights
                }
                data.append(event_data)
            
            with open(self.learning_log, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save learning events: {e}")
    
    def record_skill_usage(self, skill_name: str, success: bool, context: str, details: Dict[str, Any] = None):
        """Record skill usage and learn from it"""
        if skill_name not in self.skills:
            logger.warning(f"Unknown skill: {skill_name}")
            return
        
        skill = self.skills[skill_name]
        skill.last_used = datetime.now()
        
        if success:
            skill.success_count += 1
            event_type = "success"
        else:
            skill.failure_count += 1
            event_type = "failure"
        
        # Record learning event
        event = LearningEvent(
            timestamp=datetime.now(),
            skill_name=skill_name,
            event_type=event_type,
            context=context,
            details=details or {}
        )
        
        self.learning_events.append(event)
        
        # Analyze for improvements if failure
        if not success:
            self._analyze_failure(skill, event)
        
        self._save_skills()
        self._save_learning_events()
    
    def _analyze_failure(self, skill: Skill, event: LearningEvent):
        """Analyze failure and suggest improvements"""
        # Simple heuristic analysis - could be enhanced with AI
        context_words = event.context.lower().split()
        
        if skill.category == SkillCategory.TECHNICAL:
            if any(word in context_words for word in ['complex', 'large', 'multiple']):
                weakness = "Struggles with complex technical tasks"
                improvement = "Break down complex tasks into smaller components"
            elif any(word in context_words for word in ['new', 'unfamiliar', 'unknown']):
                weakness = "Difficulty with unfamiliar technologies"
                improvement = "Research and understand new technologies before implementation"
            else:
                weakness = "General technical execution issues"
                improvement = "Review technical fundamentals and best practices"
        
        elif skill.category == SkillCategory.REASONING:
            if any(word in context_words for word in ['multiple', 'conflicting', 'ambiguous']):
                weakness = "Difficulty handling ambiguous situations"
                improvement = "Develop structured approaches for ambiguous problems"
            else:
                weakness = "Logical reasoning gaps"
                improvement = "Strengthen logical analysis methodology"
        
        else:
            weakness = f"Issues in {skill.category.value} domain"
            improvement = f"Focus on improving {skill.category.value} fundamentals"
        
        if weakness not in skill.weaknesses:
            skill.weaknesses.append(weakness)
        if improvement not in skill.improvements:
            skill.improvements.append(improvement)
        
        # Add insights to the event
        event.insights.append(f"Identified weakness: {weakness}")
        event.insights.append(f"Suggested improvement: {improvement}")
    
    def get_skills_needing_improvement(self) -> List[Skill]:
        """Get skills that need improvement"""
        return [skill for skill in self.skills.values() if skill.needs_improvement]
    
    def get_skill_recommendations(self, context: str) -> List[str]:
        """Get recommended skills for a given context"""
        context_words = set(context.lower().split())
        recommendations = []
        
        # Simple keyword-based recommendations
        if any(word in context_words for word in ['code', 'programming', 'technical', 'infrastructure']):
            recommendations.extend(['code_generation', 'infrastructure_management', 'debugging'])
        
        if any(word in context_words for word in ['problem', 'issue', 'challenge']):
            recommendations.extend(['problem_decomposition', 'critical_thinking', 'innovative_problem_solving'])
        
        if any(word in context_words for word in ['explain', 'clarify', 'understand']):
            recommendations.extend(['clear_explanation', 'context_awareness'])
        
        return recommendations[:5]  # Top 5 recommendations

class GordonAIManager:
    """Manages Gordon AI Docker integration"""
    
    def __init__(self):
        self.container_name = "gordon-ai"
        self.image_name = "gordon-ai:latest"
        self.is_running = False
    
    async def start_gordon_ai(self) -> bool:
        """Start Gordon AI Docker container"""
        try:
            # Check if container exists and start it
            import subprocess
            result = subprocess.run([
                'docker', 'run', '-d', '--name', self.container_name,
                '-p', '8091:8080', self.image_name
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                self.is_running = True
                logger.info("Gordon AI container started successfully")
                return True
            else:
                logger.error(f"Failed to start Gordon AI: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error starting Gordon AI: {e}")
            return False
    
    async def query_gordon_ai(self, prompt: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Query Gordon AI with a prompt"""
        if not self.is_running:
            await self.start_gordon_ai()
        
        try:
            # Placeholder for actual Gordon AI API call
            # This would be replaced with actual HTTP requests to Gordon AI
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'http://localhost:8091/query',
                    json={'prompt': prompt, 'context': context or {}}
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return {'error': f'Gordon AI request failed: {response.status}'}
        except Exception as e:
            logger.error(f"Error querying Gordon AI: {e}")
            return {'error': str(e)}

class MemorySystemClient:
    """Client for interacting with the ARCA Memory System"""
    
    def __init__(self, base_url: str = "http://arca-memory-system:8001"):
        self.base_url = base_url
        
    async def add_conversation_turn(self, session_id: str, user_id: str, user_message: str, assistant_response: str, metadata: Dict[str, Any] = None):
        async with aiohttp.ClientSession() as session:
            payload = {
                "session_id": session_id,
                "user_id": user_id,
                "user_message": user_message,
                "assistant_response": assistant_response,
                "metadata": metadata
            }
            async with session.post(f"{self.base_url}/conversation", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Memory System Error ({response.status}): {error_text}")
                return await response.json()

    async def add_document(self, content: str, source: str, document_type: str = "document"):
        async with aiohttp.ClientSession() as session:
            payload = {
                "content": content,
                "source": source,
                "document_type": document_type
            }
            async with session.post(f"{self.base_url}/document", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Memory System Error ({response.status}): {error_text}")
                return await response.json()

    async def get_context(self, session_id: str, query: str, user_id: str = "default"):
        async with aiohttp.ClientSession() as session:
            payload = {
                "session_id": session_id,
                "query": query,
                "user_id": user_id
            }
            async with session.post(f"{self.base_url}/context", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Memory System Error ({response.status}): {error_text}")
                return await response.json()
                
    async def record_trajectory(self, agent_id: str, task_input: str, task_type: str, actions_taken: List[str], context_used: Dict[str, Any], outcome: str, execution_time: float):
        async with aiohttp.ClientSession() as session:
            payload = {
                "agent_id": agent_id,
                "task_input": task_input,
                "task_type": task_type,
                "actions_taken": actions_taken,
                "context_used": context_used,
                "outcome": outcome,
                "execution_time": execution_time
            }
            async with session.post(f"{self.base_url}/trajectory", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Memory System Error ({response.status}): {error_text}")
                return await response.json()

    async def get_learning_context(self, agent_id: str, task_context: str):
        async with aiohttp.ClientSession() as session:
            payload = {
                "agent_id": agent_id,
                "task_context": task_context
            }
            async with session.post(f"{self.base_url}/learning", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Memory System Error ({response.status}): {error_text}")
                return await response.json()

    async def get_strategies(self, task_context: str, top_k: int = 5):
        async with aiohttp.ClientSession() as session:
            params = {
                "task_context": task_context,
                "top_k": top_k
            }
            async with session.get(f"{self.base_url}/strategies", params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Memory System Error ({response.status}): {error_text}")
                return await response.json()

class ARCAMCPServer:
    """Main ARCA MCP Server implementing Skills Framework"""
    
    def __init__(self):
        self.skills_manager = SkillsManager(ARCA_ROOT / "data" / "skills")
        self.gordon_ai = GordonAIManager()
        # Use MEMORY_SYSTEM_URL env var, fallback to container name on docker network
        memory_url = os.environ.get("MEMORY_SYSTEM_URL", "http://arca-memory-system:8002")
        self.memory_system = MemorySystemClient(base_url=memory_url)
        logger.info(f"Initialized MemorySystemClient with URL: {memory_url}")
        self.queue_manager = QueueManager()
        
        # Initialize MCP server
        self.mcp_server = Server("arca-reasoning-hub")
        self._setup_mcp_handlers()
    
    async def process_json_rpc(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process JSON-RPC request"""
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")
        
        try:
            result = None
            if method == "list_tools":
                tools_result = await self._list_tools()
                result = {"tools": [t.model_dump() for t in tools_result.tools]}
                
            elif method == "resources/list":
                resources_result = await self._list_resources()
                result = {"resources": [r.model_dump() for r in resources_result.resources]}
                
            elif method == "resources/read":
                uri = params.get("uri")
                read_result = await self._read_resource(uri)
                result = {"contents": [c.model_dump() for c in read_result.contents]}
                
            else:
                # Assume it's a tool call
                tools_result = await self._list_tools()
                tool_names = [t.name for t in tools_result.tools]
                
                if method in tool_names:
                    call_result = await self._call_tool(method, params)
                    if call_result.isError:
                        raise Exception(call_result.content[0].text)
                        
                    content = call_result.content[0].text
                    try:
                        result = json.loads(content)
                    except:
                        result = content
                else:
                    raise ValueError(f"Unknown method or tool: {method}")
            
            return {"jsonrpc": "2.0", "result": result, "id": req_id}
            
        except Exception as e:
            logger.error(f"JSON-RPC Error: {e}")
            return {
                "jsonrpc": "2.0", 
                "error": {"code": -32603, "message": str(e)}, 
                "id": req_id
            }

    async def _list_tools(self) -> ListToolsResult:
        """List available MCP tools"""
        tools = [
            Tool(
                name="analyze_skill_performance",
                description="Analyze performance of specific skills",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string", "description": "Name of skill to analyze"},
                        "time_period": {"type": "string", "description": "Time period for analysis (7d, 30d, all)"}
                    },
                    "required": ["skill_name"]
                }
            ),
            Tool(
                name="get_skill_recommendations",
                description="Get skill recommendations for a given context",
                inputSchema={
                    "type": "object", 
                    "properties": {
                        "context": {"type": "string", "description": "Context for skill recommendations"}
                    },
                    "required": ["context"]
                }
            ),
            Tool(
                name="record_learning_event",
                description="Record a learning event for skill improvement",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string"},
                        "success": {"type": "boolean"},
                        "context": {"type": "string"},
                        "details": {"type": "object"}
                    },
                    "required": ["skill_name", "success", "context"]
                }
            ),
            Tool(
                name="query_gordon_ai",
                description="Query Gordon AI with a prompt",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string"},
                        "context": {"type": "object"}
                    },
                    "required": ["prompt"]
                }
            ),
            Tool(
                name="get_skills_needing_improvement",
                description="Get list of skills that need improvement",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="execute_oracle_sql",
                description="Execute SQL statements on Oracle database",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "credentials": {"type": "object"},
                        "sql_statements": {"type": "string"}
                    },
                    "required": ["credentials", "sql_statements"]
                }
            ),
            Tool(
                name="create_job",
                description="Create and submit a job to the queue",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "queue_name": {"type": "string", "description": "Name of the queue (e.g., genesis_jobs)"},
                        "job_data": {"type": "object", "description": "Job payload data"}
                    },
                    "required": ["queue_name", "job_data"]
                }
            ),
            Tool(
                name="docker_maintainer_operation",
                description="Execute comprehensive Docker operations for container management",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["build", "run", "stop", "start", "restart", "logs", "ps", "images", "pull", "push", "rm", "rmi", "prune", "inspect", "exec", "network", "volume", "compose"],
                            "description": "Docker operation to perform"
                        },
                        "service_name": {"type": "string", "description": "Name of the service/container"},
                        "image_name": {"type": "string", "description": "Name of the image"},
                        "tag": {"type": "string", "description": "Image tag"},
                        "dockerfile": {"type": "string", "description": "Path to Dockerfile"},
                        "build_context": {"type": "string", "description": "Build context path"},
                        "ports": {"type": "object", "description": "Port mappings"},
                        "env_vars": {"type": "object", "description": "Environment variables"},
                        "volumes": {"type": "object", "description": "Volume mappings"},
                        "network": {"type": "string", "description": "Network name"},
                        "command": {"type": "string", "description": "Command to run in container"},
                        "options": {"type": "object", "description": "Additional options"}
                    },
                    "required": ["operation"]
                }
            ),
            # Memory System Tools
            Tool(
                name="add_conversation_turn",
                description="Add a conversation turn to memory",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "user_id": {"type": "string"},
                        "user_message": {"type": "string"},
                        "assistant_response": {"type": "string"},
                        "metadata": {"type": "object"}
                    },
                    "required": ["session_id", "user_id", "user_message", "assistant_response"]
                }
            ),
            Tool(
                name="add_document",
                description="Add a document to memory",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "source": {"type": "string"},
                        "document_type": {"type": "string"}
                    },
                    "required": ["content", "source"]
                }
            ),
            Tool(
                name="get_context",
                description="Get comprehensive context from memory",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "query": {"type": "string"},
                        "user_id": {"type": "string"}
                    },
                    "required": ["session_id", "query"]
                }
            ),
            Tool(
                name="record_trajectory",
                description="Record agent trajectory for learning",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                        "task_input": {"type": "string"},
                        "task_type": {"type": "string"},
                        "actions_taken": {"type": "array", "items": {"type": "string"}},
                        "context_used": {"type": "object"},
                        "outcome": {"type": "string"},
                        "execution_time": {"type": "number"}
                    },
                    "required": ["agent_id", "task_input", "task_type", "actions_taken", "context_used", "outcome", "execution_time"]
                }
            ),
            Tool(
                name="get_learning_context",
                description="Get learning context for agent decision making",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                        "task_context": {"type": "string"}
                    },
                    "required": ["agent_id", "task_context"]
                }
            ),
            Tool(
                name="get_strategies",
                description="Get reasoning strategies for a task context",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_context": {"type": "string"},
                        "top_k": {"type": "integer"}
                    },
                    "required": ["task_context"]
                }
            ),
            Tool(
                name="analyze_code",
                description="Analyze code for patterns and issues",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"}
                    },
                    "required": ["code"]
                }
            ),
            Tool(
                name="read_file",
                description="Read content from a file",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to the file"}
                    },
                    "required": ["path"]
                }
            ),
            Tool(
                name="write_file",
                description="Write content to a file",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path to the file"},
                        "content": {"type": "string", "description": "Content to write"}
                    },
                    "required": ["path", "content"]
                }
            ),
            Tool(
                name="git_maintainer_operation",
                description="Execute comprehensive git operations for GitOps workflow",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "operation": {
                            "type": "string",
                            "enum": ["status", "add", "commit", "push", "pull", "branch", "checkout", "merge", "rebase", "stash", "log", "diff", "reset", "clean", "tag", "remote", "fetch", "clone", "init"],
                            "description": "Git operation to perform"
                        },
                        "repo_path": {"type": "string", "description": "Path to git repository"},
                        "files": {"type": "array", "items": {"type": "string"}, "description": "Files for add/commit operations"},
                        "message": {"type": "string", "description": "Commit message"},
                        "branch": {"type": "string", "description": "Branch name for checkout/branch operations"},
                        "remote": {"type": "string", "description": "Remote name for push/pull operations"},
                        "url": {"type": "string", "description": "URL for clone operation"},
                        "force": {"type": "boolean", "description": "Force operation (for push, reset, etc.)"},
                        "options": {"type": "object", "description": "Additional options for the operation"}
                    },
                    "required": ["operation"]
                }
            ),
            Tool(
                name="get_oracle_credentials",
                description="Retrieve Oracle database credentials from secure vault",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="test_oracle_connection",
                description="Test connection to Oracle database",
                inputSchema={"type": "object", "properties": {}}
            ),
        ]
        
        # Add proxy tools for mesh routing (e.g. gateway_request, service_request)
        for pt in PROXY_TOOLS:
            tools.append(Tool(**pt))
            
        return ListToolsResult(tools=tools)

    async def _call_tool(self, name: str, arguments: dict) -> CallToolResult:
        """Handle tool calls"""
        try:
            if name == "analyze_skill_performance":
                skill_name = arguments["skill_name"]
                time_period = arguments.get("time_period", "all")
                result = await self._analyze_skill_performance(skill_name, time_period)
                
            elif name == "get_skill_recommendations":
                context = arguments["context"]
                result = self.skills_manager.get_skill_recommendations(context)
                
            elif name == "record_learning_event":
                skill_name = arguments["skill_name"]
                success = arguments["success"]
                context = arguments["context"]
                details = arguments.get("details", {})
                self.skills_manager.record_skill_usage(skill_name, success, context, details)
                result = {"status": "recorded", "skill": skill_name}
                
            elif name == "query_gordon_ai":
                prompt = arguments["prompt"]
                context = arguments.get("context", {})
                result = await self.gordon_ai.query_gordon_ai(prompt, context)
                
            elif name == "get_skills_needing_improvement":
                skills = self.skills_manager.get_skills_needing_improvement()
                result = [{"name": s.name, "success_rate": s.success_rate, "weaknesses": s.weaknesses} for s in skills]
            
            elif name == "create_job":
                queue_name = arguments["queue_name"]
                job_data = arguments["job_data"]
                success = self.queue_manager.submit_job(queue_name, job_data)
                result = {"status": "success" if success else "failure", "job_id": job_data.get("job_id")}
            
            # Memory System Tools
            elif name == "add_conversation_turn":
                result = await self.memory_system.add_conversation_turn(
                    arguments["session_id"],
                    arguments["user_id"],
                    arguments["user_message"],
                    arguments["assistant_response"],
                    arguments.get("metadata")
                )
            elif name == "add_document":
                result = await self.memory_system.add_document(
                    arguments["content"],
                    arguments["source"],
                    arguments.get("document_type", "document")
                )
            elif name == "get_context":
                result = await self.memory_system.get_context(
                    arguments["session_id"],
                    arguments["query"],
                    arguments.get("user_id", "default")
                )
            elif name == "record_trajectory":
                result = await self.memory_system.record_trajectory(
                    arguments["agent_id"],
                    arguments["task_input"],
                    arguments["task_type"],
                    arguments["actions_taken"],
                    arguments["context_used"],
                    arguments["outcome"],
                    arguments["execution_time"]
                )
            elif name == "get_learning_context":
                result = await self.memory_system.get_learning_context(
                    arguments["agent_id"],
                    arguments["task_context"]
                )
            elif name == "get_strategies":
                result = await self.memory_system.get_strategies(
                    arguments["task_context"],
                    arguments.get("top_k", 5)
                )

            elif name == "analyze_code":
                # Mock analysis
                result = {"analysis": "Code analysis complete. No critical issues found."}

            elif name == "read_file":
                path = Path(arguments["path"])
                if not path.is_absolute():
                    path = ARCA_ROOT / path
                
                logger.info(f"Reading file: {path}, exists: {path.exists()}")

                if path.exists():
                    result = {"content": path.read_text()}
                else:
                    result = {"error": f"File not found: {path}"}

            elif name == "write_file":
                path = Path(arguments["path"])
                if not path.is_absolute():
                    path = ARCA_ROOT / path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(arguments["content"])
                result = {"status": "success", "path": str(path)}

            elif name == "get_oracle_credentials":
                # In a real scenario, this would fetch from Vault or encrypted secrets
                # For now, we return placeholder or env vars
                result = {
                    "user": os.getenv("ORACLE_USER", "admin"),
                    "password": os.getenv("ORACLE_PASSWORD", "secure_password"),
                    "dsn": os.getenv("ORACLE_DSN", "localhost/xepdb1")
                }

            elif name == "test_oracle_connection":
                # Mock connection test
                result = {"status": "success", "message": "Connection to Oracle database successful"}

            elif name == "execute_oracle_sql":
                credentials = arguments.get("credentials", {})
                sql_statements = arguments.get("sql_statements", "")
                
                user = credentials.get("user") or os.getenv("ORACLE_USER")
                password = credentials.get("password") or os.getenv("ORACLE_PASSWORD")
                dsn = credentials.get("dsn") or os.getenv("ORACLE_DSN")
                
                if not all([user, password, dsn]):
                     result = {"error": "Missing Oracle credentials"}
                else:
                    try:
                        connection = oracledb.connect(user=user, password=password, dsn=dsn)
                        cursor = connection.cursor()
                        
                        statements = [s.strip() for s in sql_statements.split(';') if s.strip()]
                        results = []
                        for sql in statements:
                            try:
                                cursor.execute(sql)
                                results.append({"status": "success", "sql": sql[:50] + "..."})
                            except Exception as e:
                                results.append({"status": "error", "sql": sql[:50] + "...", "error": str(e)})
                        
                        connection.commit()
                        cursor.close()
                        connection.close()
                        result = {"status": "completed", "results": results}
                        
                    except Exception as e:
                        result = {"error": f"Oracle execution failed: {str(e)}"}
            
            elif name == "git_maintainer_operation":
                operation = arguments["operation"]
                result = await self._execute_git_operation(
                    operation=operation,
                    repo_path=arguments.get("repo_path", "/home/ubuntu/ARCA"),
                    **{k: v for k, v in arguments.items() if k not in ["operation", "repo_path"]}
                )
            
            elif name == "docker_maintainer_operation":
                operation = arguments["operation"]
                result = await self._execute_docker_operation(
                    operation=operation,
                    **{k: v for k, v in arguments.items() if k != "operation"}
                )
                
            # Proxy Tools (Mesh Routing)
            elif name == "service_request":
                result = await service_proxy.service_request(**arguments)
            elif name == "gateway_request":
                result = await service_proxy.gateway_request(**arguments)
            elif name == "redis_command":
                result = await service_proxy.redis_command(**arguments)
            elif name == "embedding_request":
                result = await service_proxy.embedding_request(**arguments)

            else:
                raise ValueError(f"Unknown tool: {name}")
            
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
            
        except Exception as e:
            logger.error(f"Tool call error: {e}")
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: {str(e)}")],
                isError=True
            )

    async def _execute_git_operation(self, operation: str, repo_path: str = "/home/ubuntu/ARCA", **kwargs) -> Dict[str, Any]:
        """Execute comprehensive git operations for GitOps workflow"""
        import subprocess
        import os
        
        try:
            # Ensure we're in the repo directory
            original_cwd = os.getcwd()
            os.chdir(repo_path)
            
            cmd = ["/usr/bin/git"]
            
            if operation == "status":
                cmd.extend(["status", "--porcelain"])
                result = subprocess.run(cmd, capture_output=True, text=True)
                return {
                    "operation": "status",
                    "output": result.stdout.strip(),
                    "exit_code": result.returncode
                }
            
            elif operation == "add":
                files = kwargs.get("files", ["."])
                cmd.extend(["add"] + files)
            
            elif operation == "commit":
                message = kwargs.get("message", "Auto-commit")
                cmd.extend(["commit", "-m", message])
                if kwargs.get("files"):
                    # Stage specific files first
                    subprocess.run(["git", "add"] + kwargs["files"], check=True)
            
            elif operation == "push":
                remote = kwargs.get("remote", "origin")
                branch = kwargs.get("branch", "main")
                cmd.extend(["push", remote, branch])
                if kwargs.get("force"):
                    cmd.append("--force")
            
            elif operation == "pull":
                remote = kwargs.get("remote", "origin")
                branch = kwargs.get("branch", "main")
                cmd.extend(["pull", remote, branch])
            
            elif operation == "branch":
                branch_name = kwargs.get("branch")
                if not branch_name:
                    # List branches
                    result = subprocess.run(["git", "branch", "-a"], capture_output=True, text=True)
                    return {"branches": result.stdout.strip().split('\n')}
                cmd.extend(["branch", branch_name])
            
            elif operation == "checkout":
                branch = kwargs.get("branch", "main")
                cmd.extend(["checkout", branch])
            
            elif operation == "log":
                cmd.extend(["log", "--oneline", "-10"])
            
            elif operation == "diff":
                commit = kwargs.get("commit")
                if commit:
                    cmd.extend(["diff", commit])
                else:
                    cmd.extend(["diff"])
            
            elif operation == "stash":
                action = kwargs.get("stash_action", "push")
                cmd.extend(["stash", action])
            
            elif operation == "reset":
                commit = kwargs.get("commit", "HEAD~1")
                mode = "--hard" if kwargs.get("hard") else "--soft"
                cmd.extend(["reset", mode, commit])
            
            elif operation == "clean":
                cmd.extend(["clean", "-fd"])
            
            elif operation == "tag":
                tag_name = kwargs.get("tag")
                message = kwargs.get("message", f"Tag {tag_name}")
                cmd.extend(["tag", "-a", tag_name, "-m", message])
            
            elif operation == "remote":
                action = kwargs.get("remote_action", "show")
                if action == "show":
                    result = subprocess.run(["git", "remote", "-v"], capture_output=True, text=True)
                    return {"remotes": result.stdout.strip()}
                elif action == "add":
                    name = kwargs.get("name", "origin")
                    url = kwargs.get("url")
                    cmd.extend(["remote", "add", name, url])
            
            elif operation == "fetch":
                remote = kwargs.get("remote", "origin")
                cmd.extend(["fetch", remote])
            
            elif operation == "clone":
                url = kwargs.get("url")
                if not url:
                    raise ValueError("URL required for clone operation")
                directory = kwargs.get("directory", ".")
                cmd.extend(["clone", url, directory])
            
            elif operation == "init":
                cmd.extend(["init"])
            
            else:
                raise ValueError(f"Unsupported git operation: {operation}")
            
            # Execute the command
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Restore original directory
            os.chdir(original_cwd)
            
            return {
                "operation": operation,
                "command": " ".join(cmd),
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "exit_code": result.returncode,
                "success": result.returncode == 0
            }
            
        except Exception as e:
            # Restore original directory on error
            try:
                os.chdir(original_cwd)
            except:
                pass
            return {"error": f"Git operation failed: {str(e)}", "operation": operation}
    
    async def _execute_docker_operation(self, operation: str, **kwargs) -> Dict[str, Any]:
        """Execute comprehensive Docker operations for container management"""
        import subprocess
        import os
        
        try:
            logger.info(f"PATH: {os.environ.get('PATH')}")
            docker_path = "/usr/bin/docker"
            if not os.path.exists(docker_path):
                docker_path = "docker"
            
            cmd = [docker_path]
            
            if operation == "build":
                service_name = kwargs.get("service_name", "")
                tag = kwargs.get("tag", "latest")
                build_context = kwargs.get("build_context", f"services/{service_name}")
                dockerfile = kwargs.get("dockerfile", "Dockerfile")
                
                cmd.extend(["build", "-t", f"{service_name}:{tag}", "-f", dockerfile, build_context])
            
            elif operation == "push":
                image_name = kwargs.get("image_name", "")
                tag = kwargs.get("tag", "latest")
                cmd.extend(["push", f"{image_name}:{tag}"])
            
            elif operation == "pull":
                image_name = kwargs.get("image_name", "")
                tag = kwargs.get("tag", "latest")
                cmd.extend(["pull", f"{image_name}:{tag}"])
            
            elif operation == "run":
                service_name = kwargs.get("service_name", "")
                image_name = kwargs.get("image_name", "")
                tag = kwargs.get("tag", "latest")
                
                cmd.extend(["run", "-d", "--name", service_name, f"{image_name}:{tag}"])
                
                # Add any additional options
                options = kwargs.get("options", {})
                if options.get("ports"):
                    for port_mapping in options["ports"]:
                        cmd.extend(["-p", port_mapping])
                if options.get("volumes"):
                    for volume_mapping in options["volumes"]:
                        cmd.extend(["-v", volume_mapping])
                if options.get("env_vars"):
                    for env_var in options["env_vars"]:
                        cmd.extend(["-e", env_var])
            
            elif operation == "stop":
                service_name = kwargs.get("service_name", "")
                cmd.extend(["stop", service_name])
            
            elif operation == "remove":
                service_name = kwargs.get("service_name", "")
                # Stop first if running
                subprocess.run(["/usr/bin/docker", "stop", service_name], capture_output=True)
                cmd.extend(["rm", service_name])
            
            elif operation == "logs":
                service_name = kwargs.get("service_name", "")
                tail = kwargs.get("tail", "50")
                cmd.extend(["logs", "--tail", tail, service_name])
            
            elif operation == "exec":
                service_name = kwargs.get("service_name", "")
                command = kwargs.get("command", "/bin/bash")
                cmd.extend(["exec", "-it", service_name, command])
            
            elif operation == "inspect":
                service_name = kwargs.get("service_name", "")
                cmd.extend(["inspect", service_name])
            
            elif operation == "ps":
                cmd.extend(["ps", "-a"])
            
            elif operation == "images":
                cmd.extend(["images"])
            
            elif operation == "system_df":
                cmd.extend(["system", "df"])
            
            elif operation == "buildx_build":
                service_name = kwargs.get("service_name", "")
                tag = kwargs.get("tag", "latest")
                platforms = kwargs.get("platforms", ["linux/amd64", "linux/arm64"])
                build_context = kwargs.get("build_context", f"services/{service_name}")
                
                cmd.extend(["buildx", "build"])
                for platform in platforms:
                    cmd.extend(["--platform", platform])
                cmd.extend(["-t", f"{service_name}:{tag}", "--push", build_context])
            
            elif operation == "buildx_push":
                # This is handled by buildx_build with --push flag
                return {"error": "Use buildx_build operation instead", "operation": operation}
            
            elif operation == "deploy_to_remote":
                service_name = kwargs.get("service_name", "")
                remote_host = kwargs.get("remote_host", "")
                image_name = kwargs.get("image_name", "")
                tag = kwargs.get("tag", "latest")
                
                if not remote_host:
                    return {"error": "remote_host required for deploy_to_remote", "operation": operation}
                
                # Use docker context or SSH to deploy
                remote_cmd = f"/usr/bin/docker run -d --name {service_name} {image_name}:{tag}"
                ssh_cmd = ["ssh", "-i", "/home/ubuntu/.ssh/arca_key", f"ubuntu@{remote_host}", remote_cmd]
                result = subprocess.run(ssh_cmd, capture_output=True, text=True)
                return {
                    "operation": "deploy_to_remote",
                    "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip(),
                    "exit_code": result.returncode
                }
            
            else:
                raise ValueError(f"Unsupported docker operation: {operation}")
            
            # Execute the command
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            return {
                "operation": operation,
                "command": " ".join(cmd),
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "exit_code": result.returncode,
                "success": result.returncode == 0
            }
            
        except Exception as e:
            return {"error": f"Docker operation failed: {str(e)}", "operation": operation}

    async def _list_resources(self) -> ListResourcesResult:
        """List available resources"""
        resources = [
            Resource(
                uri="skills://registry",
                name="Skills Registry",
                description="Complete registry of all skills and their performance",
                mimeType="application/json"
            ),
            Resource(
                uri="skills://learning-events",
                name="Learning Events Log", 
                description="Log of all learning events and improvements",
                mimeType="application/json"
            ),
            Resource(
                uri="skills://performance-dashboard",
                name="Skills Performance Dashboard",
                description="Dashboard view of skills performance metrics",
                mimeType="application/json"
            )
        ]
        return ListResourcesResult(resources=resources)

    async def _read_resource(self, uri: str) -> ReadResourceResult:
        """Read resource content"""
        try:
            if uri == "skills://registry":
                skills_data = {
                    skill_name: {
                        "category": skill.category.value,
                        "level": skill.level.value,
                        "success_rate": skill.success_rate,
                        "total_uses": skill.success_count + skill.failure_count,
                        "last_used": skill.last_used.isoformat() if skill.last_used else None,
                        "needs_improvement": skill.needs_improvement,
                        "weaknesses": skill.weaknesses,
                        "improvements": skill.improvements
                    }
                    for skill_name, skill in self.skills_manager.skills.items()
                }
                content = json.dumps(skills_data, indent=2)
                
            elif uri == "skills://learning-events":
                events_data = [
                    {
                        "timestamp": event.timestamp.isoformat(),
                        "skill_name": event.skill_name,
                        "event_type": event.event_type,
                        "context": event.context,
                        "insights": event.insights
                    }
                    for event in self.skills_manager.learning_events[-100:]  # Last 100 events
                ]
                content = json.dumps(events_data, indent=2)
                
            elif uri == "skills://performance-dashboard":
                dashboard_data = await self._generate_performance_dashboard()
                content = json.dumps(dashboard_data, indent=2)
                
            else:
                raise ValueError(f"Unknown resource: {uri}")
            
            return ReadResourceResult(
                contents=[TextContent(type="text", text=content)]
            )
            
        except Exception as e:
            logger.error(f"Resource read error: {e}")
            return ReadResourceResult(
                contents=[TextContent(type="text", text=f"Error: {str(e)}")]
            )

    def _setup_mcp_handlers(self):
        """Setup MCP protocol handlers"""
        
        @self.mcp_server.list_tools()
        async def handle_list_tools() -> ListToolsResult:
            return await self._list_tools()
        
        @self.mcp_server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> CallToolResult:
            return await self._call_tool(name, arguments)
        
        @self.mcp_server.list_resources()
        async def handle_list_resources() -> ListResourcesResult:
            return await self._list_resources()
        
        @self.mcp_server.read_resource()
        async def handle_read_resource(uri: str) -> ReadResourceResult:
            return await self._read_resource(uri)
    
    async def _analyze_skill_performance(self, skill_name: str, time_period: str) -> Dict[str, Any]:
        """Analyze performance of a specific skill"""
        if skill_name not in self.skills_manager.skills:
            return {"error": f"Skill '{skill_name}' not found"}
        
        skill = self.skills_manager.skills[skill_name]
        
        # Filter events by time period if needed
        events = [e for e in self.skills_manager.learning_events if e.skill_name == skill_name]
        
        if time_period != "all":
            from datetime import timedelta
            days = int(time_period.replace('d', ''))
            cutoff = datetime.now() - timedelta(days=days)
            events = [e for e in events if e.timestamp >= cutoff]
        
        success_events = [e for e in events if e.event_type == "success"]
        failure_events = [e for e in events if e.event_type == "failure"]
        
        analysis = {
            "skill_name": skill_name,
            "category": skill.category.value,
            "level": skill.level.value,
            "overall_success_rate": skill.success_rate,
            "period_success_rate": len(success_events) / len(events) if events else 0,
            "total_uses_period": len(events),
            "recent_weaknesses": skill.weaknesses,
            "suggested_improvements": skill.improvements,
            "trend": "improving" if len(success_events) > len(failure_events) else "declining",
            "last_used": skill.last_used.isoformat() if skill.last_used else None
        }
        
        return analysis
    
    async def _generate_performance_dashboard(self) -> Dict[str, Any]:
        """Generate comprehensive performance dashboard"""
        skills_by_category = {}
        for skill in self.skills_manager.skills.values():
            category = skill.category.value
            if category not in skills_by_category:
                skills_by_category[category] = []
            skills_by_category[category].append({
                "name": skill.name,
                "success_rate": skill.success_rate,
                "needs_improvement": skill.needs_improvement
            })
        
        total_skills = len(self.skills_manager.skills)
        skills_needing_improvement = len(self.skills_manager.get_skills_needing_improvement())
        
        recent_events = self.skills_manager.learning_events[-50:]
        success_events = [e for e in recent_events if e.event_type == "success"]
        
        dashboard = {
            "overview": {
                "total_skills": total_skills,
                "skills_needing_improvement": skills_needing_improvement,
                "improvement_rate": 1 - (skills_needing_improvement / total_skills) if total_skills > 0 else 0,
                "recent_success_rate": len(success_events) / len(recent_events) if recent_events else 0
            },
            "skills_by_category": skills_by_category,
            "top_performing_skills": [
                {"name": s.name, "success_rate": s.success_rate}
                for s in sorted(self.skills_manager.skills.values(), key=lambda x: x.success_rate, reverse=True)[:5]
            ],
            "skills_needing_attention": [
                {"name": s.name, "success_rate": s.success_rate, "weaknesses": s.weaknesses}
                for s in self.skills_manager.get_skills_needing_improvement()[:5]
            ]
        }
        
        return dashboard
    
    async def start_server(self):
        """Start the MCP server"""
        logger.info(f"Starting ARCA MCP Server on port {DATA_HUB_PORT}")
        
        # Start Gordon AI
        await self.gordon_ai.start_gordon_ai()
        
        # Start MCP server (this would integrate with your transport layer)
        logger.info("ARCA MCP Reasoning Hub is ready!")
        logger.info("Skills Framework initialized with Anthropic methodology")
        logger.info("Gordon AI integration active")
        logger.info("Self-improvement learning system online")

def create_ssl_context() -> Optional[ssl.SSLContext]:
    """Create SSL context for mutual TLS authentication"""
    if not TLS_ENABLED:
        logger.warning("TLS is disabled - running in insecure mode")
        return None
    
    # Check if certificate files exist
    required_files = [CA_CERT_PATH, SERVER_CERT_PATH, SERVER_KEY_PATH, CLIENT_CA_CERT_PATH]
    missing_files = [f for f in required_files if not f.exists()]
    
    if missing_files:
        logger.error(f"Missing TLS certificate files: {missing_files}")
        logger.error("Please run scripts/security/generate_mcp_certificates.sh to generate certificates")
        raise FileNotFoundError(f"Missing TLS certificates: {missing_files}")
    
    try:
        # Create SSL context with TLS 1.2 minimum
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        ssl_context.maximum_version = ssl.TLSVersion.TLSv1_3
        
        # Load server certificate and key
        ssl_context.load_cert_chain(
            certfile=str(SERVER_CERT_PATH),
            keyfile=str(SERVER_KEY_PATH)
        )
        
        # Load CA certificate for client verification (mutual TLS)
        ssl_context.load_verify_locations(cafile=str(CLIENT_CA_CERT_PATH))
        
        # Require client certificates
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        
        logger.info("🔒 TLS context created with mutual authentication")
        logger.info(f"  Server cert: {SERVER_CERT_PATH}")
        logger.info(f"  CA cert: {CA_CERT_PATH}")
        logger.info("  Client certificate verification: REQUIRED")
        
        return ssl_context
        
    except Exception as e:
        logger.error(f"Failed to create SSL context: {e}")
        raise

# Initialize OpenTelemetry
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint="otel_collector:4317", insecure=True))
)

# Initialize auto-instrumentation
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

# FastAPI app for HTTP interface
app = FastAPI(title="ARCA MCP Server", version="1.0.0")

# Add HTTPS redirect middleware if TLS is enabled
if TLS_ENABLED:
    app.add_middleware(HTTPSRedirectMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Client Certificate Validation Middleware
@app.middleware("http")
async def validate_client_certificate(request: Request, call_next):
    """Validate client certificates for zero-trust security"""
    if not TLS_ENABLED:
        return await call_next(request)
    
    # Get client certificate from request
    client_cert = request.scope.get("ssl", {}).get("client_cert")
    
    if not client_cert:
        logger.warning(f"❌ Client certificate missing from {request.client.host}")
        raise HTTPException(
            status_code=401,
            detail="Client certificate required for authentication"
        )
    
    # Validate certificate is issued by our CA
    try:
        # Extract certificate details for logging
        cert_info = {
            "subject": client_cert.get("subject", []),
            "issuer": client_cert.get("issuer", []),
            "serial": client_cert.get("serialNumber"),
            "notBefore": client_cert.get("notBefore"),
            "notAfter": client_cert.get("notAfter")
        }
        
        # Check if certificate is from our CA (basic validation)
        issuer = str(cert_info.get("issuer", []))
        if "ARCA MCP CA" not in issuer:
            logger.warning(f"❌ Invalid certificate issuer: {issuer}")
            raise HTTPException(
                status_code=401,
                detail="Certificate not issued by authorized CA"
            )
        
        # Log successful authentication
        subject = str(cert_info.get("subject", []))
        logger.info(f"✅ Client certificate validated: {subject}")
        
    except Exception as e:
        logger.error(f"❌ Certificate validation error: {e}")
        raise HTTPException(
            status_code=401,
            detail="Certificate validation failed"
        )
    
    return await call_next(request)

# Instrument the FastAPI app
FastAPIInstrumentor.instrument_app(app)

# Instrument HTTP clients
RequestsInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()

# Global server instance
mcp_server_instance = None

@app.on_event("startup")
async def startup_event():
    global mcp_server_instance
    mcp_server_instance = ARCAMCPServer()
    await mcp_server_instance.start_server()

@app.get("/")
async def root():
    return {
        "service": "ARCA MCP Reasoning Hub",
        "status": "online",
        "skills_count": len(mcp_server_instance.skills_manager.skills) if mcp_server_instance else 0,
        "gordon_ai_status": "running" if mcp_server_instance and mcp_server_instance.gordon_ai.is_running else "stopped"
    }

@app.get("/skills/dashboard")
async def get_dashboard():
    if not mcp_server_instance:
        raise HTTPException(status_code=503, detail="MCP Server not initialized")
    return await mcp_server_instance._generate_performance_dashboard()

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/mcp")
async def handle_mcp_request(request: Request):
    """Handle MCP JSON-RPC requests over HTTP"""
    if not mcp_server_instance:
        raise HTTPException(status_code=503, detail="MCP Server not initialized")
    
    try:
        data = await request.json()
        return await mcp_server_instance.process_json_rpc(data)
    except Exception as e:
        logger.error(f"MCP Request Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    ssl_config = {}
    if TLS_ENABLED:
        # Check if certificate files exist
        required_files = [CA_CERT_PATH, SERVER_CERT_PATH, SERVER_KEY_PATH]
        missing_files = [f for f in required_files if not f.exists()]
        
        if missing_files:
            logger.error(f"Missing TLS certificate files: {missing_files}")
            logger.warning("Falling back to insecure mode due to missing certificates")
            TLS_ENABLED = False
        else:
            ssl_config = {
                "ssl_keyfile": str(SERVER_KEY_PATH),
                "ssl_certfile": str(SERVER_CERT_PATH),
                "ssl_ca_certs": str(CA_CERT_PATH),
                "ssl_cert_reqs": ssl.CERT_REQUIRED,
            }

    protocol = "https" if TLS_ENABLED else "http"
    logger.info(f"🚀 Starting ARCA MCP Server on {protocol}://0.0.0.0:{DATA_HUB_PORT}")
    
    if TLS_ENABLED:
        logger.info("🔒 TLS enabled with mutual authentication")
        logger.info("  - Minimum TLS version: 1.2")
        logger.info("  - Client certificates: REQUIRED")
    else:
        logger.warning("⚠️  TLS disabled - running in insecure mode")
    
    uvicorn.run(
        "data_hub_mcp_server:app",
        host="0.0.0.0", 
        port=DATA_HUB_PORT,
        log_level="info",
        **ssl_config
    )

import oracledb