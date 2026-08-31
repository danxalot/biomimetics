#!/usr/bin/env python3
"""
ARCA MCP Server - MacBook Integration Server
Implements Anthropic Skills Framework with Gordon AI Integration
Provides MCP protocol interface for external AI assistants and development tools
"""

import asyncio
import json
import logging
import os
import ssl
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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("arca-mcp-server")

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
API_KEYS = os.getenv('MCP_API_KEYS', '').split(',') if os.getenv('MCP_API_KEYS') else []
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

class ARCAMCPServer:
    """Main ARCA MCP Server implementing Skills Framework"""
    
    def __init__(self):
        # Use app-writable directory for data
        data_dir = Path("/app/data")
        self.skills_manager = SkillsManager(data_dir)
        self.gordon_ai = GordonAIManager()
        
        # Initialize MCP server
        self.mcp_server = Server("arca-reasoning-hub")
        self._setup_mcp_handlers()
    
    def _setup_mcp_handlers(self):
        """Setup MCP protocol handlers"""
        
        @self.mcp_server.list_tools()
        async def handle_list_tools() -> ListToolsResult:
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
                    name="save_development_checkpoint",
                    description="Save a development checkpoint for iterative development resumption",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "checkpoint_id": {"type": "string", "description": "Unique checkpoint identifier"},
                            "service_name": {"type": "string", "description": "Name of the service being developed"},
                            "checkpoint_data": {"type": "object", "description": "Development state data to persist"}
                        },
                        "required": ["checkpoint_id", "service_name", "checkpoint_data"]
                    }
                ),
                Tool(
                    name="verify_deployment_health",
                    description="Verify deployment health and return status",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "service_name": {"type": "string", "description": "Name of the service to verify"},
                            "deployment_id": {"type": "string", "description": "Deployment identifier"}
                        },
                        "required": ["service_name", "deployment_id"]
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
                    name="gitops_deployment_workflow",
                    description="Execute complete GitOps deployment workflow with checkpoints and rollback",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "service_name": {"type": "string", "description": "Name of service to deploy"},
                            "deployment_type": {"type": "string", "enum": ["development", "staging", "production"], "description": "Type of deployment"},
                            "checkpoint_id": {"type": "string", "description": "Checkpoint ID for rollback capability"},
                            "build_locally": {"type": "boolean", "description": "Build container locally to avoid CI credits", "default": true},
                            "verify_health": {"type": "boolean", "description": "Verify deployment health after deployment", "default": true},
                            "auto_rollback": {"type": "boolean", "description": "Automatically rollback on failure", "default": true}
                        },
                        "required": ["service_name"]
                    }
                ),
                Tool(
                    name="development_checkpoint_management",
                    description="Manage development checkpoints for iterative development",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["create", "load", "list", "delete", "cleanup"], "description": "Checkpoint action"},
                            "checkpoint_id": {"type": "string", "description": "Checkpoint ID"},
                            "service_name": {"type": "string", "description": "Service name for filtering"},
                            "checkpoint_data": {"type": "object", "description": "Data to save in checkpoint"},
                            "keep_count": {"type": "number", "description": "Number of checkpoints to keep during cleanup"}
                        },
                        "required": ["action"]
                    }
                ),
                Tool(
                    name="docker_registry_operation",
                    description="Execute Docker registry operations for GitOps deployment from GHCR",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": ["login", "logout", "push", "pull", "tag", "buildx_build", "inspect", "images"],
                                "description": "Docker registry operation to perform"
                            },
                            "image": {"type": "string", "description": "Docker image name with registry"},
                            "source": {"type": "string", "description": "Source image for tag operation"},
                            "target": {"type": "string", "description": "Target image for tag operation"},
                            "registry": {"type": "string", "description": "Registry URL", "default": "ghcr.io"},
                            "username": {"type": "string", "description": "Registry username"},
                            "password": {"type": "string", "description": "Registry password/token"},
                            "dockerfile": {"type": "string", "description": "Path to Dockerfile", "default": "Dockerfile"},
                            "context": {"type": "string", "description": "Build context path", "default": "."},
                            "cache_from": {"type": "string", "description": "Cache source for buildx"},
                            "cache_to": {"type": "string", "description": "Cache destination for buildx"},
                            "output_type": {"type": "string", "enum": ["registry", "tar", "oci"], "description": "Output type for buildx", "default": "registry"},
                            "output_dest": {"type": "string", "description": "Output destination file for tar/oci exports"},
                            "platforms": {"type": "array", "items": {"type": "string"}, "description": "Target platforms", "default": ["linux/arm64"]},
                            "repository": {"type": "string", "description": "Repository filter for images listing"}
                        },
                        "required": ["operation"]
                    }
                ),
                Tool(
                    name="submit_job_to_orchestrator",
                    description="Submit a job to the orchestrator agent for processing",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "job_type": {"type": "string", "description": "Type of job (create_agent, update_world_model, etc.)"},
                            "description": {"type": "string", "description": "Human-readable description of the job"},
                            "parameters": {"type": "object", "description": "Job-specific parameters"},
                            "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"], "description": "Job priority level"},
                            "callback_agent": {"type": "string", "description": "Agent to notify when job completes"}
                        },
                        "required": ["job_type", "description"]
                    }
                )
            ]
            return ListToolsResult(tools=tools)
        
        @self.mcp_server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> CallToolResult:
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
                
                elif name == "save_development_checkpoint":
                    checkpoint_id = arguments["checkpoint_id"]
                    service_name = arguments["service_name"]
                    checkpoint_data = arguments["checkpoint_data"]
                    result = await self._save_development_checkpoint(checkpoint_id, service_name, checkpoint_data)
                
                elif name == "verify_deployment_health":
                    service_name = arguments["service_name"]
                    deployment_id = arguments["deployment_id"]
                    result = await self._verify_deployment_health(service_name, deployment_id)
                
                elif name == "git_maintainer_operation":
                    operation = arguments["operation"]
                    result = await self._execute_git_operation(
                        operation=operation,
                        repo_path=arguments.get("repo_path", "/home/ubuntu/ARCA"),
                        **{k: v for k, v in arguments.items() if k not in ["operation", "repo_path"]}
                    )
                
                elif name == "gitops_deployment_workflow":
                    service_name = arguments["service_name"]
                    deployment_type = arguments.get("deployment_type", "development")
                    checkpoint_id = arguments.get("checkpoint_id")
                    build_locally = arguments.get("build_locally", True)
                    verify_health = arguments.get("verify_health", True)
                    auto_rollback = arguments.get("auto_rollback", True)
                    result = await self._execute_gitops_deployment_workflow(
                        service_name, deployment_type, checkpoint_id, build_locally, verify_health, auto_rollback
                    )
                
                elif name == "development_checkpoint_management":
                    action = arguments["action"]
                    result = await self._manage_development_checkpoints(
                        action=action,
                        **{k: v for k, v in arguments.items() if k != "action"}
                    )
                
                elif name == "screen_inter_agent_prompt":
                    prompt = arguments["prompt"]
                    source_agent = arguments["source_agent"]
                    target_agent = arguments["target_agent"]
                    context = arguments.get("context", {})
                    result = await self._screen_inter_agent_prompt(prompt, source_agent, target_agent, context)
                
                elif name == "submit_job_to_orchestrator":
                    job_type = arguments["job_type"]
                    description = arguments["description"]
                    parameters = arguments.get("parameters", {})
                    priority = arguments.get("priority", "medium")
                    callback_agent = arguments.get("callback_agent")
                    result = await self._submit_job_to_orchestrator(job_type, description, parameters, priority, callback_agent)
                
                elif name == "docker_registry_operation":
                    operation = arguments["operation"]
                    result = await self._execute_docker_registry_operation(
                        operation=operation,
                        **{k: v for k, v in arguments.items() if k != "operation"}
                    )
                
                else:
                    raise ValueError(f"Unknown tool: {name}")
                
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                
            except Exception as e:
                logger.error(f"Tool call error: {e}")
                return CallToolResult(
                    content=[TextContent(type="text", text=f"Error: {str(e)}")],
                    isError=True
                )
        
        @self.mcp_server.list_resources()
        async def handle_list_resources() -> ListResourcesResult:
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
        
        @self.mcp_server.read_resource()
        async def handle_read_resource(uri: str) -> ReadResourceResult:
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
    
    async def _save_development_checkpoint(self, checkpoint_id: str, service_name: str, checkpoint_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a development checkpoint for iterative development resumption"""
        try:
            from scripts.development_checkpoint_manager import DevelopmentCheckpointManager
            
            # Initialize checkpoint manager
            checkpoint_manager = DevelopmentCheckpointManager()
            await checkpoint_manager.initialize()
            
            # Create checkpoint
            created_id = await checkpoint_manager.create_checkpoint(
                service_name=service_name,
                checkpoint_data=checkpoint_data,
                checkpoint_type="development"
            )
            
            logger.info(f"Development checkpoint saved: {created_id}")
            return {
                "status": "success",
                "checkpoint_id": created_id,
                "service_name": service_name,
                "timestamp": checkpoint_data.get("timestamp", datetime.now().isoformat())
            }
            
        except Exception as e:
            logger.error(f"Failed to save development checkpoint: {e}")
            return {"error": f"Failed to save checkpoint: {str(e)}"}
    
    async def _verify_deployment_health(self, service_name: str, deployment_id: str) -> Dict[str, Any]:
        """Verify deployment health and return status"""
        try:
            import aiohttp
            import subprocess
            
            # Check if service container is running
            result = subprocess.run([
                'docker', 'ps', '--filter', f'name={service_name}', '--format', '{{.Names}}'
            ], capture_output=True, text=True)
            
            container_running = service_name in result.stdout
            
            # Check service health endpoint if available
            health_status = "unknown"
            if container_running:
                try:
                    # Try to get container port
                    port_result = subprocess.run([
                        'docker', 'port', service_name
                    ], capture_output=True, text=True)
                    
                    if port_result.returncode == 0:
                        # Extract port from output like "8080/tcp -> 0.0.0.0:8080"
                        port_line = port_result.stdout.strip().split('\n')[0]
                        if '->' in port_line:
                            host_port = port_line.split('->')[1].split(':')[1]
                            health_url = f"http://localhost:{host_port}/health"
                            
                            async with aiohttp.ClientSession() as session:
                                async with session.get(health_url, timeout=5) as response:
                                    if response.status == 200:
                                        health_data = await response.json()
                                        health_status = health_data.get("status", "healthy")
                                    else:
                                        health_status = f"http_{response.status}"
                except Exception as e:
                    logger.warning(f"Health check failed for {service_name}: {e}")
                    health_status = "unreachable"
            
            return {
                "service_name": service_name,
                "deployment_id": deployment_id,
                "container_running": container_running,
                "health_status": health_status,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to verify deployment health: {e}")
            return {
                "error": f"Health verification failed: {str(e)}",
                "service_name": service_name,
                "deployment_id": deployment_id
            }
    
    async def _execute_git_operation(self, operation: str, repo_path: str = "/home/ubuntu/ARCA", **kwargs) -> Dict[str, Any]:
        """Execute comprehensive git operations for GitOps workflow"""
        import subprocess
        import os
        
        try:
            # Ensure we're in the repo directory
            original_cwd = os.getcwd()
            os.chdir(repo_path)
            
            cmd = ["git"]
            
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
    
    async def _execute_docker_registry_operation(self, operation: str, **kwargs) -> Dict[str, Any]:
        """Execute Docker registry operations for GHCR integration"""
        import subprocess
        import os
        
        try:
            cmd = ["docker"]
            
            if operation == "login":
                registry = kwargs.get("registry", "ghcr.io")
                username = kwargs.get("username")
                password = kwargs.get("password")
                if not username or not password:
                    raise ValueError("Username and password required for login")
                cmd.extend(["login", registry, "-u", username, "--password-stdin"])
                # Use subprocess with input for password
                result = subprocess.run(cmd, input=password, capture_output=True, text=True)
                return {
                    "operation": "login",
                    "registry": registry,
                    "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip(),
                    "exit_code": result.returncode,
                    "success": result.returncode == 0
                }
            
            elif operation == "logout":
                registry = kwargs.get("registry", "ghcr.io")
                cmd.extend(["logout", registry])
            
            elif operation == "push":
                image = kwargs.get("image")
                if not image:
                    raise ValueError("Image name required for push")
                cmd.extend(["push", image])
            
            elif operation == "pull":
                image = kwargs.get("image")
                if not image:
                    raise ValueError("Image name required for pull")
                cmd.extend(["pull", image])
            
            elif operation == "tag":
                source = kwargs.get("source")
                target = kwargs.get("target")
                if not source or not target:
                    raise ValueError("Source and target required for tag")
                cmd.extend(["tag", source, target])
            
            elif operation == "buildx_build":
                # Advanced buildx build with caching and export
                dockerfile = kwargs.get("dockerfile", "Dockerfile")
                context = kwargs.get("context", ".")
                image = kwargs.get("image")
                cache_from = kwargs.get("cache_from")
                cache_to = kwargs.get("cache_to")
                output_type = kwargs.get("output_type", "registry")
                platforms = kwargs.get("platforms", ["linux/arm64"])
                
                cmd.extend(["buildx", "build", "--platform", ",".join(platforms)])
                
                if image:
                    cmd.extend(["-t", image])
                
                if cache_from:
                    cmd.extend(["--cache-from", cache_from])
                
                if cache_to:
                    cmd.extend(["--cache-to", cache_to])
                
                if output_type == "tar":
                    output_dest = kwargs.get("output_dest", "runtime.tar.gz")
                    cmd.extend(["--output", f"type=tar,dest={output_dest}"])
                elif output_type == "oci":
                    output_dest = kwargs.get("output_dest", "runtime.oci")
                    cmd.extend(["--output", f"type=oci,dest={output_dest}"])
                else:
                    cmd.append("--push")  # Default to push to registry
                
                cmd.extend(["-f", dockerfile, context])
            
            elif operation == "inspect":
                image = kwargs.get("image")
                if not image:
                    raise ValueError("Image name required for inspect")
                cmd.extend(["inspect", image])
                result = subprocess.run(cmd, capture_output=True, text=True)
                import json
                try:
                    image_info = json.loads(result.stdout)
                    return {
                        "operation": "inspect",
                        "image": image,
                        "info": image_info,
                        "exit_code": result.returncode,
                        "success": result.returncode == 0
                    }
                except json.JSONDecodeError:
                    return {
                        "operation": "inspect",
                        "image": image,
                        "raw_output": result.stdout.strip(),
                        "exit_code": result.returncode,
                        "success": result.returncode == 0
                    }
            
            elif operation == "images":
                # List images, optionally filter by repository
                repository = kwargs.get("repository")
                if repository:
                    cmd.extend(["images", repository])
                else:
                    cmd.extend(["images"])
            
            else:
                raise ValueError(f"Unsupported docker registry operation: {operation}")
            
            # Execute the command for non-special cases
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
            return {"error": f"Docker registry operation failed: {str(e)}", "operation": operation}
    
    async def _execute_gitops_deployment_workflow(self, service_name: str, deployment_type: str,
                                                checkpoint_id: str = None, build_locally: bool = True,
                                                verify_health: bool = True, auto_rollback: bool = True) -> Dict[str, Any]:
        """Execute complete GitOps deployment workflow with checkpoints and rollback"""
        try:
            workflow_steps = []
            
            # Step 1: Create deployment checkpoint if not provided
            if not checkpoint_id:
                checkpoint_id = f"{service_name}_{deployment_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                checkpoint_result = await self._save_development_checkpoint(
                    checkpoint_id, service_name, {
                        "deployment_type": deployment_type,
                        "timestamp": datetime.now().isoformat(),
                        "build_locally": build_locally
                    }
                )
                workflow_steps.append({"step": "checkpoint", "result": checkpoint_result})
            
            # Step 2: Build container locally (if requested)
            if build_locally:
                build_result = await self._execute_git_operation(
                    "run_shell", 
                    command=f"cd /home/ubuntu/ARCA && ./scripts/local-build.sh {service_name}",
                    repo_path="/home/ubuntu/ARCA"
                )
                workflow_steps.append({"step": "build", "result": build_result})
                
                if not build_result.get("success", False):
                    if auto_rollback:
                        rollback_result = await self._rollback_deployment(service_name, checkpoint_id)
                        workflow_steps.append({"step": "rollback", "result": rollback_result})
                    return {"error": "Build failed", "workflow_steps": workflow_steps}
            
            # Step 3: Deploy via GitOps workflow
            deploy_result = await self._execute_git_operation(
                "run_shell",
                command=f"cd /home/ubuntu/ARCA && ./scripts/trigger-deployment.sh {service_name} {deployment_type}",
                repo_path="/home/ubuntu/ARCA"
            )
            workflow_steps.append({"step": "deploy", "result": deploy_result})
            
            if not deploy_result.get("success", False):
                if auto_rollback:
                    rollback_result = await self._rollback_deployment(service_name, checkpoint_id)
                    workflow_steps.append({"step": "rollback", "result": rollback_result})
                return {"error": "Deployment failed", "workflow_steps": workflow_steps}
            
            # Step 4: Verify health (if requested)
            if verify_health:
                health_result = await self._verify_deployment_health(service_name, checkpoint_id)
                workflow_steps.append({"step": "health_check", "result": health_result})
                
                if not health_result.get("healthy", False):
                    if auto_rollback:
                        rollback_result = await self._rollback_deployment(service_name, checkpoint_id)
                        workflow_steps.append({"step": "rollback", "result": rollback_result})
                    return {"error": "Health check failed", "workflow_steps": workflow_steps}
            
            # Step 5: Commit deployment changes
            commit_result = await self._execute_git_operation(
                "commit",
                message=f"GitOps deployment: {service_name} {deployment_type}",
                files=["."]
            )
            workflow_steps.append({"step": "commit", "result": commit_result})
            
            return {
                "success": True,
                "service_name": service_name,
                "deployment_type": deployment_type,
                "checkpoint_id": checkpoint_id,
                "workflow_steps": workflow_steps
            }
            
        except Exception as e:
            return {"error": f"GitOps workflow failed: {str(e)}", "service_name": service_name}
    
    async def _manage_development_checkpoints(self, action: str, **kwargs) -> Dict[str, Any]:
        """Manage development checkpoints for iterative development"""
        try:
            from scripts.development_checkpoint_manager import DevelopmentCheckpointManager
            
            checkpoint_manager = DevelopmentCheckpointManager()
            await checkpoint_manager.initialize()
            
            if action == "create":
                checkpoint_id = kwargs.get("checkpoint_id", f"checkpoint_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                service_name = kwargs.get("service_name", "unknown")
                checkpoint_data = kwargs.get("checkpoint_data", {})
                
                result = await checkpoint_manager.create_checkpoint(
                    service_name=service_name,
                    checkpoint_data=checkpoint_data,
                    checkpoint_type="development"
                )
                return {"action": "create", "checkpoint_id": result}
            
            elif action == "load":
                checkpoint_id = kwargs.get("checkpoint_id")
                if not checkpoint_id:
                    return {"error": "checkpoint_id required for load action"}
                
                checkpoint = await checkpoint_manager.load_checkpoint(checkpoint_id)
                return {"action": "load", "checkpoint": checkpoint}
            
            elif action == "list":
                service_name = kwargs.get("service_name")
                checkpoints = await checkpoint_manager.list_checkpoints(service_name)
                return {"action": "list", "checkpoints": checkpoints}
            
            elif action == "delete":
                checkpoint_id = kwargs.get("checkpoint_id")
                if not checkpoint_id:
                    return {"error": "checkpoint_id required for delete action"}
                
                success = await checkpoint_manager.delete_checkpoint(checkpoint_id)
                return {"action": "delete", "success": success}
            
            elif action == "cleanup":
                service_name = kwargs.get("service_name")
                keep_count = kwargs.get("keep_count", 5)
                if not service_name:
                    return {"error": "service_name required for cleanup action"}
                
                deleted = await checkpoint_manager.cleanup_old_checkpoints(service_name, keep_count)
                return {"action": "cleanup", "deleted_count": deleted}
            
            else:
                return {"error": f"Unknown checkpoint action: {action}"}
                
        except Exception as e:
            return {"error": f"Checkpoint management failed: {str(e)}"}
    
    async def _screen_inter_agent_prompt(self, prompt: str, source_agent: str, target_agent: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Screen inter-agent prompts using Guardian service"""
        try:
            import aiohttp
            
            guardian_url = os.getenv("GUARDIAN_SERVICE_URL", "http://guardian:8001")
            
            screening_request = {
                "prompt": prompt,
                "source_agent": source_agent,
                "target_agent": target_agent,
                "context": context,
                "request_id": f"screen_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{guardian_url}/screen",
                    json=screening_request,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return {
                            "screening_result": result,
                            "status": "screened"
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "error": f"Guardian service error: {response.status} - {error_text}",
                            "approved": False,  # Conservative default
                            "risk_level": "critical",
                            "status": "screening_failed"
                        }
                        
        except Exception as e:
            logger.error(f"Guardian screening failed: {str(e)}")
            return {
                "error": f"Screening service unavailable: {str(e)}",
                "approved": False,  # Conservative default
                "risk_level": "critical",
                "status": "screening_failed"
            }
    
    async def _rollback_deployment(self, service_name: str, checkpoint_id: str) -> Dict[str, Any]:
        """Rollback deployment using checkpoint"""
        try:
            # Load checkpoint
            checkpoint_manager = DevelopmentCheckpointManager()
            await checkpoint_manager.initialize()
            checkpoint = await checkpoint_manager.load_checkpoint(checkpoint_id)
            
            if not checkpoint:
                return {"error": f"Checkpoint {checkpoint_id} not found"}
            
            # Execute rollback script
            rollback_result = await self._execute_git_operation(
                "run_shell",
                command=f"cd /home/ubuntu/ARCA && ./scripts/rollback-deployment.sh {service_name} {checkpoint_id}",
                repo_path="/home/ubuntu/ARCA"
            )
            
            return {
                "rollback_success": rollback_result.get("success", False),
                "service_name": service_name,
                "checkpoint_id": checkpoint_id,
                "rollback_details": rollback_result
            }
            
        except Exception as e:
            return {"error": f"Rollback failed: {str(e)}"}
    
    async def _submit_job_to_orchestrator(self, job_type: str, description: str, parameters: Dict[str, Any], 
                                        priority: str = "medium", callback_agent: str = None) -> Dict[str, Any]:
        """Submit a job to the orchestrator agent by writing to genesis folder"""
        try:
            import uuid
            import json
            from pathlib import Path
            
            # Generate unique job ID
            job_id = f"job_{uuid.uuid4().hex[:8]}"
            
            # Prepare job data
            job_data = {
                "job_id": job_id,
                "job_type": job_type,
                "description": description,
                "parameters": parameters,
                "priority": priority,
                "callback_agent": callback_agent,
                "submitted_at": datetime.now().isoformat(),
                "status": "queued"
            }
            
            # Write job to genesis folder
            genesis_dir = Path("/app/genesis")
            genesis_dir.mkdir(parents=True, exist_ok=True)
            
            job_file = genesis_dir / f"{job_id}.json"
            with open(job_file, 'w') as f:
                json.dump(job_data, f, indent=2)
            
            logger.info(f"Job submitted to genesis folder: {job_id}")
            return {
                "job_id": job_id,
                "status": "queued",
                "message": f"Job queued in genesis folder. Run orchestrator agent to process.",
                "file_path": str(job_file)
            }
            
        except Exception as e:
            logger.error(f"Job submission failed: {str(e)}")
            return {
                "error": f"Job submission service unavailable: {str(e)}",
                "status": "submission_failed"
            }
    
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

@app.post("/jobs/submit")
async def submit_job(job_data: Dict[str, Any]):
    """HTTP endpoint for job submission to orchestrator agent"""
    if not mcp_server_instance:
        raise HTTPException(status_code=503, detail="MCP Server not initialized")
    
    try:
        # Extract job parameters
        job_type = job_data.get("job_type")
        description = job_data.get("description")
        parameters = job_data.get("parameters", {})
        priority = job_data.get("priority", "medium")
        callback_agent = job_data.get("callback_agent")
        
        if not job_type or not description:
            raise HTTPException(status_code=400, detail="job_type and description are required")
        
        # Submit the job
        result = await mcp_server_instance._submit_job_to_orchestrator(
            job_type, description, parameters, priority, callback_agent
        )
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job submission endpoint error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

if __name__ == "__main__":
    # Create SSL context if TLS is enabled
    ssl_context = create_ssl_context() if TLS_ENABLED else None
    
    protocol = "https" if TLS_ENABLED else "http"
    logger.info(f"🚀 Starting ARCA MCP Server on {protocol}://0.0.0.0:{DATA_HUB_PORT}")
    
    if TLS_ENABLED and ssl_context:
        logger.info("🔒 TLS enabled with mutual authentication")
        logger.info("  - Minimum TLS version: 1.2")
        logger.info("  - Client certificates: REQUIRED")
        uvicorn.run(
            "macbook_mcp_integration_server:app",
            host="0.0.0.0", 
            port=DATA_HUB_PORT,
            log_level="info",
            ssl_context=ssl_context
        )
    else:
        logger.warning("⚠️  TLS disabled - running in insecure mode")
        uvicorn.run(
            "macbook_mcp_integration_server:app",
            host="0.0.0.0", 
            port=DATA_HUB_PORT,
            log_level="info"
        )