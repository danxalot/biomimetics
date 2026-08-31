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
import requests
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import sys

# Path utilities for shell command sanitization
sys.path.insert(0, '/app/scripts')
sys.path.append(str(Path(__file__).parent / "tools"))
try:
    from path_utils import quote_path, sanitize_shell_command
    PATH_UTILS_AVAILABLE = True
except ImportError:
    PATH_UTILS_AVAILABLE = False
    quote_path = lambda p: p
    sanitize_shell_command = lambda cmd, **kw: cmd

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.wsgi import WSGIMiddleware
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

# Local tool imports - make gracefully optional if not available
# Configure logging first (before any imports)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("arca-mcp-server")

# Local tool imports with graceful degradation
QueueManager = None
LangSearchClient = None
mcp_robotics = None
mcp_compressor = None
mcp_reviewer = None
mcp_insight_synthesis = None
mcp_skill_forge = None
mcp_otel_autopsy = None
mcp_knowledge_crystallizer = None
mcp_human_feedback = None
mcp_git_ops = None
mcp_docker_ops = None
mcp_file_ops = None
mcp_security_ops = None
mcp_vision_encoder = None
mcp_neo4j_admin = None
mcp_blackboard_redis = None
mcp_guardian = None
mcp_reasoningbank = None
mcp_arca_intelligence = None
mcp_infra_discovery = None
mcp_code_crawler = None
mcp_graph_visualizer = None
mcp_skill_discovery = None
mcp_vector_layer = None
mcp_agent_dispatch = None
mcp_semantic_search = None
skill_frame_server = None

# Try to import tools, but don't fail if they're not available
try:
    from tools.queue_manager_tool import QueueManager
    logger.info("✅ QueueManager imported")
except Exception as e:
    logger.warning(f"⚠️  QueueManager unavailable: {e}")

try:
    from tools.mcp_service_proxy import service_proxy, PROXY_TOOLS
    logger.info("✅ PROXY_TOOLS imported")
except Exception as e:
    logger.warning(f"⚠️  PROXY_TOOLS unavailable: {e}")
    PROXY_TOOLS = []
    service_proxy = None

try:
    from tools.langsearch_tools import LangSearchClient
    logger.info("✅ LangSearchClient imported")
except Exception as e:
    logger.warning(f"⚠️  LangSearchClient unavailable: {e}")

# Try importing individual tool modules
tool_modules = [
    'mcp_director', 'mcp_universal_context', 'queue_manager_tool',
    'mcp_infra_discovery', 'mcp_graph_linker', 'mcp_workflow_scanner', 'mcp_reasoningbank',
    'mcp_arca_intelligence', 'mcp_code_crawler', 'mcp_graph_visualizer',
    'mcp_skill_discovery', 'mcp_vector_layer', 'mcp_agent_dispatch',
    'mcp_neo4j_admin', 'mcp_blackboard_redis', 'mcp_guardian',
    'mcp_robotics', 'mcp_compressor', 'mcp_reviewer', 'mcp_insight_synthesis',
    'mcp_skill_forge', 'mcp_otel_autopsy', 'mcp_knowledge_crystallizer',
    'mcp_human_feedback', 'mcp_git_ops', 'mcp_docker_ops', 'mcp_file_ops',
    'mcp_security_ops', 'mcp_vision_encoder', 'skill_frame_server',
    'mcp_semantic_search', 'mcp_secrets_bridge'
]


for tool_name in tool_modules:
    try:
        module = __import__(f'tools.{tool_name}', fromlist=[tool_name])
        globals()[tool_name] = module
        logger.info(f"✅ {tool_name} imported")
    except Exception as e:
        logger.warning(f"⚠️  {tool_name} unavailable: {e}")
        globals()[tool_name] = None

logger.info("✅ All tool modules loaded (with graceful degradation)")

try:
    from tools.concept_assimilation.workflow import run_granular_assimilation
    from tools.concept_assimilation.internal.attention_engine import GeometricAttentionEngine
    logger.info("✅ concept_assimilation + attention_engine imported")
except ImportError as e:
    run_granular_assimilation = None
    GeometricAttentionEngine = None
    logger.warning(f"⚠️ concept_assimilation not available: {e}")

# OCI Skill Bank Integration
try:
    from tools.oci_skill_bank import OCISkillBank, SkillEntry
    OCI_SKILL_BANK_AVAILABLE = True
    logger.info("✅ OCISkillBank imported")
except ImportError:
    OCI_SKILL_BANK_AVAILABLE = False
    logger.warning("⚠️  OCISkillBank not available")

# Enhanced Skills Manager (with markdown integration)
try:
    from enhanced_skills_manager import EnhancedSkillsManager, get_enhanced_skills_manager
    ENHANCED_SKILLS_AVAILABLE = True
    logger.info("✅ EnhancedSkillsManager imported")
except ImportError:
    EnhancedSkillsManager = None
    get_enhanced_skills_manager = None
    ENHANCED_SKILLS_AVAILABLE = False
    logger.warning("⚠️  EnhancedSkillsManager not available - using basic SkillsManager")

# Skill Tools Registry
try:
    import mcp_skill_tools
    SKILL_TOOLS_AVAILABLE = True
    logger.info("✅ mcp_skill_tools imported")
except ImportError:
    SKILL_TOOLS_AVAILABLE = False
    logger.warning("⚠️  mcp_skill_tools not available")

# Universal Skill Frame (USF)
try:
    from tools.mcp_universal_context import get_universal_context
    USF_AVAILABLE = True
    logger.info("✅ mcp_universal_context imported")
except ImportError:
    get_universal_context = None
    USF_AVAILABLE = False
    logger.warning("⚠️  mcp_universal_context not available")

# Serena Integration (optional)
try:
    from serena.agent import SerenaAgent
    SERENA_AVAILABLE = True
except ImportError:
    SerenaAgent = None
    SERENA_AVAILABLE = False
    logger.warning("Serena agent not available - running without semantic code tools")

# Conversation Memory Integration
try:
    from tools.conversation_accumulator import ConversationAccumulator
    CONVERSATION_MEMORY_AVAILABLE = True
    logger.info("✅ ConversationAccumulator imported")
except ImportError:
    ConversationAccumulator = None
    CONVERSATION_MEMORY_AVAILABLE = False
    logger.warning("⚠️  ConversationAccumulator not available")

# Shared OTEL Instrumentation
import sys
sys.path.append("/app/shared")
try:
    from secrets_provider import secrets
except ImportError:
    class MockSecrets:
        def get(self, name): return os.getenv(name.upper())
    secrets = MockSecrets()
try:
    from shared.otel_setup import instrument_service
except ImportError:
    # Fallback for local dev
    sys.path.append(str(Path(__file__).parent.parent)) 
    from shared.otel_setup import instrument_service

# Configuration - Auto-detect local vs OCI/Docker environment
_local_arca_root = Path(__file__).parent.parent.parent  # services/mcp_server -> services -> ARCA root
ARCA_ROOT = Path(os.getenv('ARCA_ROOT', str(_local_arca_root)))
MCP_DATA_DIR = Path(os.getenv('MCP_DATA_DIR', ARCA_ROOT / "data"))
DATA_HUB_PORT = int(os.getenv('MCP_SERVER_PORT', '8086'))
INSTANCE_ID = os.getenv('INSTANCE_ID', 'workhorse-mcp')

# Skills and reasoning bank directories
# Use /app/skills mount if available (Docker), fall back to local ARCA paths
_default_skills = '/app/skills' if Path('/app/skills').exists() else str(ARCA_ROOT / "skills")
_default_reasoning = '/app/shared_storage/reasoning_bank' if Path('/app/shared_storage').exists() else str(ARCA_ROOT / "shared_storage" / "reasoning_bank")
SKILLS_DIR = Path(os.getenv('MCP_SKILLS_DIR', _default_skills))
REASONING_DIR = Path(os.getenv('MCP_REASONING_DIR', _default_reasoning))

# Load required API keys via SecretsProvider
os.environ["GOOGLE_API_KEY"] = secrets.get("google_api_key") or ""
os.environ["OPENAI_API_KEY"] = secrets.get("openai_api_key") or ""
os.environ["ANTHROPIC_API_KEY"] = secrets.get("anthropic_api_key") or ""
os.environ["ARCA_MiniMax"] = secrets.get("minimax_api_key") or ""
os.environ["GENESIS_CHAIN_API_KEY"] = secrets.get("genesis_chain_api_key") or ""

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
            
        # Initialize OCI Skill Bank
        self.oci_bank = None
        if OCI_SKILL_BANK_AVAILABLE:
            try:
                # Use default wallet path or from env
                wallet_dir = os.getenv("TNS_ADMIN", "/app/secrets/wallet")
                self.oci_bank = OCISkillBank(wallet_dir=wallet_dir)
                logger.info("✅ SkillsManager connected to OCI Skill Bank")
            except Exception as e:
                logger.error(f"Failed to connect to OCI Skill Bank: {e}")

    def _get_embedding(self, text: str, headers: Optional[Dict[str, str]] = None) -> Optional[np.ndarray]:
        """Get embedding for text from embedding service"""
        # Standarized port 8005 and endpoint /v1/embeddings
        url = os.getenv("EMBEDDING_SERVICE_URL", "http://embedding_service:8005")
        if not url.endswith("/v1/embeddings"):
            url = f"{url.rstrip('/')}/v1/embeddings"
            
        final_headers = {"Content-Type": "application/json"}
        if headers:
            genesis = {k: v for k, v in headers.items() if k.lower().startswith("x-genesis-")}
            final_headers.update(genesis)
            
        try:
            payload = {"input": text, "model": "qwen3-embedding"}
            resp = requests.post(url, json=payload, headers=final_headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                vec = data.get("embedding") 
                if not vec and "data" in data: # OpenAI format
                     vec = data["data"][0]["embedding"]
                
                if vec:
                    return np.array(vec, dtype=np.float32)
            else:
                logger.error(f"Internal embedding failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.warning(f"Embedding failed for '{text[:20]}...': {e}")
        return None
    
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
            
            # Sync to OCI Skill Bank
            if self.oci_bank:
                count = 0
                for skill in self.skills.values():
                    # Generate vector if useful info exists
                    content = f"{skill.name} {skill.category.value} {skill.level.value} {' '.join(skill.weaknesses)}"
                    vector = self._get_embedding(content)
                    
                    if vector is not None:
                         # Pack into SkillEntry
                         entry = SkillEntry(
                             skill_id=skill.name,
                             concept_name=skill.name,
                             concept_type="skill",
                             state_vector=vector,
                             logic_payload={
                                 "category": skill.category.value,
                                 "level": skill.level.value, 
                                 "success_rate": skill.success_rate
                             },
                             energy_level=skill.success_rate
                         )
                         if self.oci_bank.add_skill(entry):
                             count += 1
                logger.info(f"Synced {count} skills to OCI Skill Bank")

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
    """Manages Gordon AI service integration (via docker-compose)"""
    
    def __init__(self):
        self.container_name = "gordon-ai"
        self.service_url = "http://gordon-ai:8091"  # Docker network DNS
        self.is_running = False
    
    async def check_gordon_ai_health(self) -> bool:
        """Check if Gordon AI service is running and healthy"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.service_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        self.is_running = True
                        logger.info("✅ Gordon AI service is healthy and running")
                        return True
                    else:
                        logger.warning(f"⚠️ Gordon AI returned status {response.status}")
                        return False
        except Exception as e:
            logger.warning(f"⚠️ Gordon AI health check failed: {e}")
            self.is_running = False
            return False
    
    async def start_gordon_ai(self) -> bool:
        """Verify Gordon AI is running (assumes it's started via docker-compose)"""
        logger.info("Verifying Gordon AI service via docker-compose...")
        return await self.check_gordon_ai_health()
    
    async def query_gordon_ai(self, prompt: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Query Gordon AI with a prompt"""
        if not self.is_running:
            health_ok = await self.check_gordon_ai_health()
            if not health_ok:
                return {'error': 'Gordon AI service is not available'}
        
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.service_url}/query",
                    json={'prompt': prompt, 'context': context or {}},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"Gordon AI query failed with status {response.status}")
                        return {'error': f'Gordon AI request failed: {response.status}'}
        except Exception as e:
            logger.error(f"Error querying Gordon AI: {e}")
            return {'error': str(e)}


class MemorySystemClient:
    """Client for the ARCA Memory System service (episodic, semantic, working memory)"""
    
    def __init__(self, base_url: str = None):
        self.base_url = base_url or os.environ.get("MEMORY_SYSTEM_URL", "http://arca-memory-system:8002")
        logger.info(f"MemorySystemClient initialized with URL: {self.base_url}")
    
    async def add_conversation_turn(self, session_id: str, user_id: str, user_message: str, 
                                   assistant_response: str, metadata: Dict[str, Any] = None):
        """Add a conversation turn to episodic memory"""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/conversation", json={
                "session_id": session_id,
                "user_id": user_id,
                "user_message": user_message,
                "assistant_response": assistant_response,
                "metadata": metadata or {}
            }) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Memory System Error ({response.status}): {error_text}")
                return await response.json()
    
    async def add_document(self, content: str, source: str, document_type: str = None):
        """Add a document to semantic memory"""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/document", json={
                "content": content,
                "source": source,
                "document_type": document_type
            }) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Memory System Error ({response.status}): {error_text}")
                return await response.json()
    
    async def get_context(self, session_id: str, query: str, user_id: str = "default"):
        """Get comprehensive context from memory"""
        import aiohttp
        payload = {
            "session_id": session_id,
            "query": query,
            "user_id": user_id
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/context", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Memory System Error ({response.status}): {error_text}")
                return await response.json()
    
    async def record_trajectory(self, agent_id: str, task_input: str, task_type: str,
                               actions_taken: List[str], context_used: Dict[str, Any],
                               outcome: str, execution_time: float):
        """Record agent trajectory for learning"""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/trajectory", json={
                "agent_id": agent_id,
                "task_input": task_input,
                "task_type": task_type,
                "actions_taken": actions_taken,
                "context_used": context_used,
                "outcome": outcome,
                "execution_time": execution_time
            }) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Memory System Error ({response.status}): {error_text}")
                return await response.json()
    
    async def get_learning_context(self, agent_id: str, task_context: str):
        """Get learning context for agent decision making"""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/learning", params={
                "agent_id": agent_id,
                "task_context": task_context
            }) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Memory System Error ({response.status}): {error_text}")
                return await response.json()
    
    async def get_strategies(self, task_type: str, limit: int = 5):
        """Get successful strategies for a task type"""
        import aiohttp
        params = {"task_type": task_type, "limit": limit}
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/strategies", params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Memory System Error ({response.status}): {error_text}")
                return await response.json()


class ARCAMCPServer:
    """Main ARCA MCP Server implementing Skills Framework"""
    
    def __init__(self):
        # Use Enhanced Skills Manager if available (supports 40+ skills from registry)
        # Use Enhanced Skills Manager if available (supports 40+ skills from registry)
        if ENHANCED_SKILLS_AVAILABLE and get_enhanced_skills_manager:
            # Use singleton getter to ensure mcp_skill_tools shares the same instance
            self.skills_manager = get_enhanced_skills_manager(
                data_dir=MCP_DATA_DIR,
                skills_dir=SKILLS_DIR
            )
            logger.info("✅ Using EnhancedSkillsManager with markdown integration")
        else:
            self.skills_manager = SkillsManager(MCP_DATA_DIR / "skills")
            logger.info("Using basic SkillsManager")
        self.gordon_ai = GordonAIManager()
        self.langsearch_client = LangSearchClient()
        
        # Initialize Memory System Client for episodic memory
        self.memory_system = MemorySystemClient()
        
        # Initialize Skills Bank directories (remote on OCI - don't create locally)
        # Skills Bank lives on OCI at ubuntu@100.70.0.13 - accessed via API, not filesystem
        self.skills_dir = SKILLS_DIR
        self.reasoning_dir = REASONING_DIR
        self.skills_available = False
        self.reasoning_available = False
        
        # Only create directories if they're local (not /app which is OCI mount point)
        try:
            if not str(self.skills_dir).startswith('/app'):
                self.skills_dir.mkdir(parents=True, exist_ok=True)
                self.skills_available = True
                logger.info(f"Skills Bank initialized at {self.skills_dir}")
            else:
                logger.info(f"Skills Bank on OCI: {self.skills_dir} (remote)")
        except OSError as e:
            logger.warning(f"⚠️  Skills Bank not available locally: {e}")
            
        try:
            if not str(self.reasoning_dir).startswith('/app'):
                self.reasoning_dir.mkdir(parents=True, exist_ok=True)
                self.reasoning_available = True
                logger.info(f"Reasoning Bank initialized at {self.reasoning_dir}")
            else:
                logger.info(f"Reasoning Bank on OCI: {self.reasoning_dir} (remote)")
        except OSError as e:
            logger.warning(f"⚠️  Reasoning Bank not available locally: {e}")

        # Initialize Skill Tools Registry (wrapper for skills_manager)
        if SKILL_TOOLS_AVAILABLE:
            try:
                self.skill_registry = mcp_skill_tools.get_skill_tools_registry()
                logger.info("✅ SkillToolsRegistry initialized")
            except Exception as e:
                logger.error(f"Failed to initialize SkillToolsRegistry: {e}")
                self.skill_registry = None
        else:
            self.skill_registry = None
        
        # Initialize new tools (with guards for missing modules)
        self.structural_analyst = mcp_robotics.StructuralAnalystTool() if mcp_robotics else None
        self.compressor = mcp_compressor.CompressorTool() if mcp_compressor else None
        self.reviewer = mcp_reviewer.ReviewerInterfaceTool() if mcp_reviewer else None
        self.insight_synthesis = mcp_insight_synthesis.InsightSynthesisTool() if mcp_insight_synthesis else None
        self.vision_encoder = mcp_vision_encoder.VisionEncoder() if mcp_vision_encoder else None
        
        # Initialize Neo4j and Blackboard tools (Critical for Genesis)
        self.neo4j_admin = mcp_neo4j_admin.Neo4jAdminTool() if mcp_neo4j_admin else None
        self.blackboard_redis = mcp_blackboard_redis.RedisBlackboardTool() if mcp_blackboard_redis else None
        
        # Initialize Guardian tool
        try:
            self.guardian = mcp_guardian.GuardianTool() if mcp_guardian else None
        except Exception as e:
            logger.warning(f"Guardian tool not initialized: {e}")
            self.guardian = None
        
        # Initialize new skills (with guards for missing modules)
        self.skill_forge = mcp_skill_forge.mcp if mcp_skill_forge else None
        self.otel_autopsy = mcp_otel_autopsy.mcp if mcp_otel_autopsy else None
        self.knowledge_crystallizer = mcp_knowledge_crystallizer.mcp if mcp_knowledge_crystallizer else None
        self.human_feedback = mcp_human_feedback.mcp if mcp_human_feedback else None
        
        # Initialize ReasoningBank
        self.mcp_reasoningbank = mcp_reasoningbank if mcp_reasoningbank else None
        if self.mcp_reasoningbank:
             logger.info("✅ ARCA MCP Server: ReasoningBank Initialized")
        
        # Initialize Director
        self.mcp_director = mcp_director if mcp_director else None
        
        # Initialize Maintainer Dispatcher
        self.mcp_agent_dispatch = mcp_agent_dispatch if mcp_agent_dispatch else None
        
        # Initialize internal Cognitive Scheduler (The "Hand" logic)
        try:
            from tools.geometry_kernel.model_engine import CognitiveScheduler
            self.scheduler = CognitiveScheduler()
            logger.info("✅ CognitiveScheduler initialized for MCP Hand")
        except Exception as e:
            logger.error(f"Failed to initialize CognitiveScheduler: {e}")
            self.scheduler = None

        # Initialize Redis for Blackboard (User requested retention)
        try:
            import redis
            redis_host = os.getenv("REDIS_HOST", "redis")
            redis_port = int(os.getenv("REDIS_PORT", 6379))
            self.redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
            logger.info(f"Connected to Redis Blackboard at {redis_host}:{redis_port}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None
        
        # Initialize Concept Assimilation Attention Engine
        if run_granular_assimilation and GeometricAttentionEngine and self.redis_client:
            # We let the engine create its own Neo4j driver for now or pass None
            self.attention_engine = GeometricAttentionEngine(self.redis_client, neo4j_driver=None)
            logger.info("✅ Geometric Attention Engine initialized")
        else:
            self.attention_engine = None

        # Initialize Serena agent for semantic code tools
        if SERENA_AVAILABLE:
            try:
                self.serena_agent = SerenaAgent(project=str(ARCA_ROOT))
                self.serena_tools = self.serena_agent.get_exposed_tool_instances()
                logger.info(f"Initialized Serena agent with {len(self.serena_tools)} tools")
            except Exception as e:
                logger.error(f"Failed to initialize Serena agent: {e}")
                self.serena_agent = None
                self.serena_tools = []
        else:
            self.serena_agent = None
            self.serena_tools = []

        if CONVERSATION_MEMORY_AVAILABLE:
            class HolographicMemoryService:
                def __init__(self, base_dir="/app/shared_storage/memory"):
                    self.base_dir = base_dir
                    self.sessions = {}
                    
                def get_session(self, session_id):
                    # Default session if none provided
                    if not session_id: 
                        session_id = "default"
                    
                    if session_id not in self.sessions:
                        # Load or Create
                        self.sessions[session_id] = ConversationAccumulator(session_id=session_id, base_dir=self.base_dir)
                        logger.info(f"Loaded Holographic Session: {session_id}")
                    return self.sessions[session_id]

            self.holographic_service = HolographicMemoryService()
            logger.info("✅ Holographic Conversation Memory Service initialized (Persistent)")
        else:
            self.holographic_service = None
        
        # Initialize MCP server
        self.mcp_server = Server("arca-reasoning-hub")
        self._setup_mcp_handlers()
    
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
    
    # --- Geometry Kernel Helper Methods (The Hand) ---
    # _split_logs and _split_narrative removed (Refactored to Delegate to Geometry Kernel API)

    def _update_state(self, state, new_data):
        try:
            # Clean up potential markdown
            if "```json" in new_data:
                new_data = new_data.split("```json")[1].split("```")[0]
            elif "```" in new_data:
                new_data = new_data.split("```")[1].split("```")[0]
            new_data = new_data.strip()
            
            data = json.loads(new_data)
            
            # Normalize list vs dict
            if isinstance(data, list):
                data = {"objects": data}
            
            # Update State
            state['trajectory_vector'] = data.get('vector', state['trajectory_vector'])
            state['current_context'] = data.get('summary', state['current_context'])
            
            objs = data.get('objects', [])
            if isinstance(objs, list):
                for obj in objs:
                    if isinstance(obj, dict):
                        obj_id = obj.get('id') or obj.get('name') or f"concept_{len(state['objects'])}"
                        state['objects'][obj_id] = obj

                        # --- SEMANTIC RECONSTRUCTION LAYER (The Mouth) ---
                        if self.redis_client:
                            try:
                                semantic_key = f"semantic:{obj_id}"
                                semantic_payload = {
                                    "summary": new_data.get("summary", "No summary provided"),
                                    "desc": obj.get("desc", ""),
                                    "source_file": state.get("current_context", "unknown"),
                                    "timestamp": str(datetime.now())
                                }
                                self.redis_client.hset(semantic_key, mapping=semantic_payload)
                                logger.info(f"⚓️ Semantic Anchoring: {obj_id} -> {semantic_key}")
                            except Exception as e:
                                logger.warning(f"Failed to store semantic sidecar for {obj_id}: {e}")
        except Exception as e:
            logger.warning(f"RLM State Update warning: {e}")

    # Skills Bank Helper Methods
    def _list_mcp_skills(self) -> dict:
        """List all skills in the Skills Bank."""
        skills = []
        for skill_file in self.skills_dir.glob("*.md"):
            skills.append(skill_file.stem)
        return {"skills": skills, "count": len(skills)}
    
    def _get_mcp_skill(self, skill_name: str) -> dict:
        """Get a skill by name."""
        skill_path = self.skills_dir / f"{skill_name}.md"
        if not skill_path.exists():
            return {"error": f"Skill not found: {skill_name}"}
        with open(skill_path, 'r') as f:
            content = f.read()
        return {"name": skill_name, "content": content}
    
    def _search_mcp_skills(self, query: str) -> dict:
        """Search skills by content."""
        query_lower = query.lower()
        matches = []
        for skill_file in self.skills_dir.glob("*.md"):
            try:
                with open(skill_file, 'r') as f:
                    content = f.read()
                if query_lower in content.lower() or query_lower in skill_file.stem.lower():
                    matches.append({
                        "name": skill_file.stem,
                        "relevance": "high" if query_lower in skill_file.stem.lower() else "medium"
                    })
            except Exception as e:
                logger.warning(f"Error searching skill file {skill_file}: {e}")
        return {"query": query, "matches": matches}
    
    def _search_reasoning_bank(self, query: str) -> dict:
        """Search reasoning traces."""
        query_lower = query.lower()
        matches = []
        for trace_file in self.reasoning_dir.glob("*.json"):
            try:
                with open(trace_file, 'r') as f:
                    trace = json.load(f)
                if query_lower in json.dumps(trace).lower():
                    matches.append(trace)
                    if len(matches) >= 10:
                        break
            except Exception as e:
                logger.warning(f"Error searching reasoning trace {trace_file}: {e}")
        return {"query": query, "traces": matches}
    
    def _store_reasoning(self, category: str, reasoning: Any) -> str:
        """Store a reasoning trace."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{category}_{timestamp}.json"
        filepath = self.reasoning_dir / filename
        
        # Handle string reasoning vs dictionary
        if isinstance(reasoning, str):
            trace = {
                "content": reasoning,
                "category": category,
                "stored_at": datetime.now().isoformat()
            }
        elif isinstance(reasoning, dict):
            trace = reasoning.copy()
            trace["stored_at"] = datetime.now().isoformat()
            trace["category"] = category
        else:
            trace = {
                "content": str(reasoning),
                "category": category,
                "stored_at": datetime.now().isoformat()
            }
            
        with open(filepath, 'w') as f:
            json.dump(trace, f, indent=2)
        return str(filepath)
    
    def _capture_skill(self, skill_name: str, category: str, description: str,
                       problem: str, solution_steps: list, verification: str,
                       mcp_tools_used: list = None, related_services: list = None) -> dict:
        """Capture a successful operation as a new skill."""
        skill_content = f"""# {skill_name}

**Version:** 1.0.0  
**Created:** {datetime.now().strftime("%Y-%m-%d")}  
**Category:** {category}

## Purpose

{description}

## Problem

{problem}

## Solution Steps

"""
        for i, step in enumerate(solution_steps, 1):
            skill_content += f"{i}. {step}\n"
        
        skill_content += f"""
## Verification

{verification}

## MCP Tools Required

"""
        if mcp_tools_used:
            for tool in mcp_tools_used:
                skill_content += f"- `{tool}`\n"
        else:
            skill_content += "- None specified\n"
        
        skill_content += f"""
## Related Services

"""
        if related_services:
            for service in related_services:
                skill_content += f"- {service}\n"
        else:
            skill_content += "- General\n"
        
        skill_content += """
## Auto-Captured

This skill was automatically captured from a successful operation.

---
*Generated by ARCA Skill Capture System*
"""
        
        filepath = self.skills_dir / f"{skill_name}.md"
        with open(filepath, 'w') as f:
            f.write(skill_content)
        
        logger.info(f"Captured new skill: {skill_name}")
        return {"captured": True, "path": str(filepath), "skill_name": skill_name}
    
    async def _list_tools(self) -> ListToolsResult:
        """List available MCP tools"""
        tools = [
            Tool(
                name="generate_image_embedding",
                description="Generate vector embedding for an image using SigLIP-2",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "image_input": {
                            "type": "string", 
                            "description": "Path to image file or base64 encoded image string"
                        }
                    },
                    "required": ["image_input"]
                }
            ),
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
                name="system_analysis",
                description="Queries the Observer Agent to review logs, system metrics, resource status, and geometric state. Returns a synthesized analysis of system health.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Specific health query or 'Perform comprehensive health check'"},
                        "depth": {"type": "string", "enum": ["summary", "detailed", "root_cause"], "description": "Level of inspection (default: summary)"}
                    },
                    "required": ["query"]
                }
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
                name="get_universal_frame",
                description="Get Universal 5-Hop Skill Frame for a given concept anchor",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "anchor_id": {"type": "string", "description": "Anchor concept ID (e.g. 'mcp_server')"},
                        "depth": {"type": "integer", "description": "Traversal depth (default: 5)"}
                    },
                    "required": ["anchor_id"]
                }
            ),
            Tool(
                name="read_file",
                description="Read content from a file (delegates to mcp_file_ops with Host Bridge support)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the file"}
                    },
                    "required": ["file_path"]
                }
            ),
            Tool(
                name="write_file",
                description="Write content to a file (delegates to mcp_file_ops with Host Bridge support)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the file"},
                        "content": {"type": "string", "description": "Content to write"}
                    },
                    "required": ["file_path", "content"]
                }
            ),
            Tool(
                name="create_file",
                description="Create a new file (fails if file already exists - use for creating new documents/skills only)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path for the new file (relative to shared_storage)"},
                        "content": {"type": "string", "description": "Content to write to the new file"},
                        "category": {"type": "string", "description": "Optional category for organizing (e.g., 'skills', 'reasoning', 'docs')", "default": "docs"}
                    },
                    "required": ["file_path", "content"]
                }
            ),
            Tool(
                name="list_files",
                description="List files in a directory. Supports optional pattern filtering.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "directory": {"type": "string", "description": "Directory path to list (default: /app/shared_storage)"},
                        "pattern": {"type": "string", "description": "Optional glob pattern to filter files (e.g., '*.md', 'serena*')"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="arca_system_query",
                description="Unified access point for ARCA's multi-layered system representation. Retrieves topology, state, and skills.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query_type": {
                            "type": "string",
                            "enum": ["topology", "state", "skills", "full"],
                            "description": "Information layer to query",
                            "default": "full"
                        },
                        "context": {"type": "string", "description": "Optional task context"}
                    }
                }
            ),
            Tool(
                name="get_skill_frame",
                description="Assemble contextual skill frame for agent consumption. Essential for system-aware operations.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "primary_skill": {"type": "string", "description": "First-layer skill title (e.g., 'DOCKER_OPS_SOP')"},
                        "task_content": {"type": "string", "description": "Optional task description for geometric matching"},
                        "include_layers": {"type": "array", "items": {"type": "string"}, "description": "Layers to include ['service', 'workflow', 'related']"}
                    },
                    "required": ["primary_skill"]
                }
            ),
            Tool(
                name="refresh_skill_index",
                description="Refresh the skill index from disk. Call after modifying mcp_skills/*.md files.",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="run_graph_linking",
                description="Trigger the Graph Linker to update semantic relationships between Infrastructure and Code.",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="scan_workflows",
                description="Scan and index markdown workflows from shared_storage into the knowledge graph.",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="get_skill_graph",
                description="Get overview of skill graph relationships and topological layers.",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="arca_feasibility_check",
                description="Evaluates the technical feasibility of a task against the current world state.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_description": {"type": "string", "description": "Description of task to evaluate"}
                    },
                    "required": ["task_description"]
                }
            ),
            Tool(
                name="list_directory",
                description="List contents of a directory (alias for list_files)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "dir_path": {"type": "string", "description": "Directory path to list"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="create_folder",
                description="Create a new folder in /shared_storage/ARCA/. Use for organizing ARCA's workspace.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "folder_path": {"type": "string", "description": "Path relative to /shared_storage/ARCA/ (e.g., 'reports/2025' creates /shared_storage/ARCA/reports/2025)"}
                    },
                    "required": ["folder_path"]
                }
            ),
            Tool(
                name="edit_file",
                description="Edit/update content in an existing file in /shared_storage/ARCA/",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path relative to /shared_storage/ARCA/"},
                        "content": {"type": "string", "description": "New content to write (replaces existing)"},
                        "append": {"type": "boolean", "description": "If true, append instead of replace"}
                    },
                    "required": ["file_path", "content"]
                }
            ),
            Tool(
                name="delete_file",
                description="Delete a file or empty folder in /shared_storage/ARCA/. Use with caution.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Path relative to /shared_storage/ARCA/ to delete"}
                    },
                    "required": ["path"]
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
                        "build_locally": {"type": "boolean", "description": "Build container locally to avoid CI credits", "default": True},
                        "verify_health": {"type": "boolean", "description": "Verify deployment health after deployment", "default": True},
                        "auto_rollback": {"type": "boolean", "description": "Automatically rollback on failure", "default": True}
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
                name="docker_container_file_read",
                description="Read a file from inside a running Docker container. Useful for inspecting config files, logs, or code inside containers.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "container_name": {"type": "string", "description": "Name or ID of the container"},
                        "file_path": {"type": "string", "description": "Path to the file inside the container (e.g., /app/main.py)"}
                    },
                    "required": ["container_name", "file_path"]
                }
            ),
            Tool(
                name="dispatch_agent",
                description="Unified Dispatcher: Route tasks to ARCA Maintainer Agents (Docker, Git, Security).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agent_type": {"type": "string", "enum": ["docker", "git", "security", "code_maintainer"], "description": "Target agent type"},
                        "operation": {"type": "string", "description": "High-level operation (e.g. 'execute', 'audit')"},
                        "params": {"type": "object", "description": "Parameters for the agent"},
                        "intent_hv": {"type": "array", "items": {"type": "number"}, "description": "Optional HDC intent vector for geometric validation"}
                    },
                    "required": ["agent_type", "operation"]
                }
            ),
            Tool(
                name="mcp_system_analysis",
                description="Observer Agent: Perform comprehensive system analysis, log review, and state synthesis.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Specific area of concern (e.g. 'Why is inference stalling?')"},
                        "depth": {"type": "string", "enum": ["summary", "detailed", "root_cause"], "description": "Depth of analysis", "default": "summary"}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="docker_execution_primitive",
                description="PRIMITIVE: Low-level Docker execution. FOR AGENT USE ONLY via dispatch_agent.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "operation": {"type": "string", "enum": ["exec_raw", "build"]},
                        "cmd": {"type": "array", "items": {"type": "string"}},
                        "target": {"type": "string"}
                     },
                     "required": ["operation"]
                }
            ),
            Tool(
                name="screen_inter_agent_prompt",
                description="Screen prompts for inter-agent communications using Guardian model",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "The prompt text to screen"},
                        "source_agent": {"type": "string", "description": "The agent sending the prompt"},
                        "target_agent": {"type": "string", "description": "The agent receiving the prompt"},
                        "context": {"type": "object", "description": "Additional context for screening"}
                    },
                    "required": ["prompt", "source_agent", "target_agent"]
                }
            ),
            Tool(
                name="web_search",
                description="Perform web search using LangSearch API",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search keywords or question"},
                        "count": {"type": "integer", "description": "Number of results to return (max 10)", "default": 10},
                        "freshness": {"type": "string", "description": "Time filter - oneDay, oneWeek, oneMonth, oneYear, noLimit", "default": "noLimit"},
                        "summary": {"type": "boolean", "description": "Whether to include detailed content summaries", "default": True}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="semantic_rerank",
                description="Perform semantic reranking of documents using LangSearch API",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query for relevance comparison"},
                        "documents": {"type": "array", "items": {"type": "string"}, "description": "List of document texts to rerank"},
                        "top_n": {"type": "integer", "description": "Optional limit on number of results to return"}
                    },
                    "required": ["query", "documents"]
                }
            ),
            # --- SERENA CODE INSPECTION TOOLS (Read-Only) ---
            Tool(
                name="serena_analyze_code",
                description="Analyze code for semantic meaning, quality, and potential issues (Read-Only)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Code to analyze"},
                        "context": {"type": "string", "description": "Context for analysis (optional)"}
                    },
                    "required": ["code"]
                }
            ),
            Tool(
                name="serena_refactor_suggestion",
                description="Suggest refactoring for a specific goal (Read-Only analysis, does not modify)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Code to analyze for refactoring"},
                        "goal": {"type": "string", "description": "Refactoring goal (e.g., 'improve readability', 'extract method')"}
                    },
                    "required": ["code", "goal"]
                }
            ),
            Tool(
                name="review_code",
                description="The 'Discernment Protocol' and Code Quality Gate",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code_str": {"type": "string", "description": "Code to review"},
                        "criteria_list": {"type": "array", "items": {"type": "string"}, "description": "List of criteria for review"}
                    },
                    "required": ["code_str", "criteria_list"]
                }
            ),
            Tool(
                name="request_human_feedback",
                description="Request input from the human operator when encountering uncertainty or requiring strategic clarification",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "The question to ask the human operator"}
                    },
                    "required": ["question"]
                }
            ),
            Tool(
                name="analyze_failure_insight",
                description="Learning Agent: Analyze failures and synthesize insights using LearnLM Flash 2.0",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "Content or context of the failure"},
                        "source_agent": {"type": "string", "description": "Agent that caused the failure"},
                        "failure_reason": {"type": "string", "description": "Reason for failure"},
                        "context_id": {"type": "string", "description": "Optional context ID for log correlation"}
                    },
                    "required": ["content", "source_agent", "failure_reason"]
                }
            ),
            # Neo4j Admin Tools (Critical for Genesis)
            Tool(
                name="neo4j_verify_connectivity",
                description="Verify connectivity to Neo4j database",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="neo4j_run_cypher",
                description="Execute a Cypher query against Neo4j database",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Cypher query to execute"}
                    },
                    "required": ["query"]
                }
            ),
            # Redis Blackboard Tools (Critical for Genesis)
            Tool(
                name="blackboard_read",
                description="Read a value from the Redis Blackboard (Hot State)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Key to read (e.g., 'arca:state:global')"}
                    },
                    "required": ["key"]
                }
            ),
            Tool(
                name="blackboard_write",
                description="Write a value to the Redis Blackboard (Hot State)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Key to write"},
                        "value": {"type": "object", "description": "Value to write (will be JSON serialized)"},
                        "expiration": {"type": "integer", "description": "Optional expiration in seconds"}
                    },
                    "required": ["key", "value"]
                }
            ),
            Tool(
                name="blackboard_acquire_lock",
                description="Acquire an atomic lock on a resource to prevent agent collision",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "resource": {"type": "string", "description": "Resource to lock (e.g., 'docker:container_1')"},
                        "timeout": {"type": "integer", "description": "Lock timeout in seconds", "default": 60}
                    },
                    "required": ["resource"]
                }
            ),
            Tool(
                name="blackboard_publish",
                description="Publish an event to a Redis channel for pub/sub messaging",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "channel": {"type": "string", "description": "Channel name (e.g., 'PLAN_UPDATED')"},
                        "message": {"type": "object", "description": "Message to publish"}
                    },
                    "required": ["channel", "message"]
                }
            ),
            # Skills Bank Tools (for Ops agents and Serena)
            Tool(
                name="skills_list",
                description="List all available repair/operation skills in the Skills Bank",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="skills_get",
                description="Get the full content of a specific skill document",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string", "description": "Name of the skill (e.g., 'ARCA_MEMORY_SYSTEM_REPAIR')"}
                    },
                    "required": ["skill_name"]
                }
            ),
            Tool(
                name="list_files",
                description="List files in a directory with optional pattern matching (Recursive)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "directory": {"type": "string", "description": "Directory to list (default: /app/shared_storage)", "default": "/app/shared_storage"},
                        "pattern": {"type": "string", "description": "Glob pattern (e.g., '*.md', '*JEPA*')", "default": ""},
                        "recursive": {"type": "boolean", "description": "Recursive search", "default": True}
                    },
                    "required": []
                }
            ),
            Tool(
                name="forge_new_skill",
                description="Create a new MCP tool python file (skill).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "The name of the file to create (e.g., mcp_docker_cleanup.py)"},
                        "code_content": {"type": "string", "description": "The complete Python code for the tool"},
                        "dependencies": {"type": "array", "items": {"type": "string"}, "description": "List of Python packages required"}
                    },
                    "required": ["filename", "code_content"]
                }
            ),
            Tool(
                name="store_memory",
                description="Store a text memory with semantic embedding",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "Text content to store"},
                        "metadata": {"type": "object", "description": "Optional metadata (JSON)"}
                    },
                    "required": ["content"]
                }
            ),
            Tool(
                name="search_memory",
                description="Search for memories semantically similar to query",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "integer", "description": "Max results (default 5)", "default": 5},
                        "threshold": {"type": "number", "description": "Similarity threshold (default 0.5)", "default": 0.5}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="discover_infrastructure",
                description="Discover and map infrastructure from docker-compose to Neo4j (Services, Ports, Volumes, Env Vars)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "compose_path": {"type": "string", "description": "Path to docker-compose.yml (default: /app/../docker-compose.local.yml)"},
                        "env_path": {"type": "string", "description": "Optional path to .env file"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="query_infrastructure",
                description="Run a Cypher query against the Infrastructure graph in Neo4j",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Cypher query to execute"}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="discover_logic",
                description="Discover and map MCP Tools/Skills from codebase to Neo4j Logic Graph (Functions, Tools, Skills)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tools_dir": {"type": "string", "description": "Path to tools directory (default: /app/tools)"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="query_logic",
                description="Run a Cypher query against the Logic graph in Neo4j (Tools, Functions, Skills)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Cypher query to execute"}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="generate_mermaid",
                description="Generate Mermaid diagram for graph visualization (Infrastructure or Logic layer)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "focus": {"type": "string", "description": "Entity to focus on (e.g., 'mcp_server', 'UserInteractionAgent')"},
                        "graph_type": {"type": "string", "description": "Graph type: 'infrastructure', 'logic', or 'full' (default: 'infrastructure')", "default": "infrastructure"}
                    },
                    "required": ["focus"]
                }
            ),
            Tool(
                name="discover_agents",
                description="Discover and map LangGraph Agent workflows to Neo4j (Agents, WorkflowNodes, Edges)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agents_dir": {"type": "string", "description": "Path to agent_service directory (default: /app/../agent_service)"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="crawl_codebase",
                description="Crawl codebase to build dependency graph in Neo4j (Phase 3: Modules, Imports, Classes)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "start_dir": {"type": "string", "description": "Root directory to crawl (default: /app)"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="dispatch_agent",
                description="Unified Dispatcher: Route tasks to the ARCA Maintainer Agents Service (The Brain).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agent_type": {"type": "string", "description": "Agent type: 'docker', 'git', 'security', 'code_maintainer'"},
                        "operation": {"type": "string", "description": "High-level operation (e.g. 'execute', 'audit', 'refactor_code')"},
                        "params": {"type": "object", "description": "Parameters for the agent"},
                        "intent_hv": {"type": "array", "items": {"type": "number"}, "description": "Optional HDC vector for intent"}
                    },
                    "required": ["agent_type", "operation"]
                }
            ),
            Tool(
                name="embed_graph",
                description="Add vector embeddings (standard + HSE) to all Neo4j nodes (Phase 4)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "node_types": {"type": "array", "items": {"type": "string"}, "description": "Node types to embed (default: all)"}
                    },
                    "required": []
                }
            ),
            Tool(
                name="semantic_graph_search",
                description="Semantic search across Neo4j graph using vector embeddings",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural language query"},
                        "node_types": {"type": "array", "items": {"type": "string"}, "description": "Node types to search"},
                        "limit": {"type": "integer", "description": "Max results (default: 5)", "default": 5},
                        "use_hse": {"type": "boolean", "description": "Use HSE vectors instead of standard (default: false)", "default": False}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="assimilate_concepts",
                description="Ingest documents via the Concept Assimilation Engine. Can accept either a single file_path OR a documents array.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to a single document file to assimilate (simpler interface)"
                        },
                        "documents": {
                            "type": "array", 
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "text": {"type": "string"}
                                }
                            },
                            "description": "List of documents to assimilate. Each has 'name' and 'text'."
                        },
                        "current_state_atoms": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Optional list of existing atoms from previous state.",
                            "default": []
                        }
                    }
                }
            ),
            Tool(
                name="geometry_context_update",
                description="Update the Geometric Attention Context Bubble. Apply Heat to active structure, Decay others.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "user_input": {"type": "string", "description": "The latest user message to analyze for focus."},
                        "focus_structure_id": {"type": "string", "description": "Explicit ID of structure to boost (if known)."}
                    },
                    "required": ["user_input"]
                }
            ),
            Tool(
                name="skills_search",
                description="Search the Skills Bank for relevant repair procedures",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search term (e.g., 'oracle', 'docker restart')"}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="reasoning_search",
                description="Search the Reasoning Bank for past diagnostic traces and repair attempts",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search term for past diagnostics"}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="reasoning_store",
                description="Store a reasoning trace for future reference (used by Ops agents after repairs)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "description": "Category (e.g., 'repair_oracle', 'deploy_docker')"},
                        "reasoning": {"type": "object", "description": "Reasoning trace data"}
                    },
                    "required": ["category", "reasoning"]
                }
            ),
            Tool(
                name="skill_capture",
                description="Capture a successful operation as a new skill (auto-documentation)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "skill_name": {"type": "string", "description": "Name for the new skill"},
                        "category": {"type": "string", "description": "Category (docker, git, security, dev, memory)"},
                        "description": {"type": "string", "description": "Brief description"},
                        "problem": {"type": "string", "description": "Problem this skill solves"},
                        "solution_steps": {"type": "array", "items": {"type": "string"}, "description": "Solution steps"},
                        "verification": {"type": "string", "description": "How to verify the fix"},
                        "mcp_tools_used": {"type": "array", "items": {"type": "string"}, "description": "MCP tools used"},
                        "related_services": {"type": "array", "items": {"type": "string"}, "description": "Related services"}
                    },
                    "required": ["skill_name", "category", "description", "problem", "solution_steps", "verification"]
                }
            ),
            Tool(
                name="publish_health_alert",
                description="Publish a health alert to trigger Serena's self-healing system",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "service": {"type": "string", "description": "Service name"},
                        "status": {"type": "string", "enum": ["healthy", "unhealthy", "error", "critical"], "description": "Health status"},
                        "details": {"type": "object", "description": "Additional details about the issue"}
                    },
                    "required": ["service", "status"]
                }
            ),
            # Episodic Memory System Tools
            Tool(
                name="add_conversation_turn",
                description="Add a conversation turn to episodic memory for session continuity",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Unique session identifier"},
                        "user_id": {"type": "string", "description": "User identifier"},
                        "user_message": {"type": "string", "description": "The user's message"},
                        "assistant_response": {"type": "string", "description": "The assistant's response"},
                        "metadata": {"type": "object", "description": "Optional metadata about the conversation"}
                    },
                    "required": ["session_id", "user_id", "user_message", "assistant_response"]
                }
            ),
            Tool(
                name="add_document",
                description="Add a document to semantic memory for retrieval",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "Document content"},
                        "source": {"type": "string", "description": "Source of the document"},
                        "document_type": {"type": "string", "description": "Type of document (skill, reasoning, code, etc.)"}
                    },
                    "required": ["content", "source"]
                }
            ),
            Tool(
                name="get_context",
                description="Get comprehensive context from memory for a query (combines working, episodic, and semantic memory)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "description": "Current session identifier"},
                        "query": {"type": "string", "description": "Query to get context for"},
                        "user_id": {"type": "string", "description": "Optional user identifier for personalized context"}
                    },
                    "required": ["session_id", "query"]
                }
            ),
            Tool(
                name="record_trajectory",
                description="Record agent trajectory for learning and improvement",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string", "description": "Agent identifier"},
                        "task_input": {"type": "string", "description": "Original task input"},
                        "task_type": {"type": "string", "description": "Type of task performed"},
                        "actions_taken": {"type": "array", "items": {"type": "string"}, "description": "List of actions taken"},
                        "context_used": {"type": "object", "description": "Context that was used"},
                        "outcome": {"type": "string", "description": "Outcome of the task"},
                        "execution_time": {"type": "number", "description": "Execution time in seconds"}
                    },
                    "required": ["agent_id", "task_input", "task_type", "actions_taken", "context_used", "outcome", "execution_time"]
                }
            ),
            Tool(
                name="get_learning_context",
                description="Get learning context for an agent based on past trajectories",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string", "description": "Agent identifier"},
                        "task_context": {"type": "string", "description": "Current task context to find relevant learnings"}
                    },
                    "required": ["agent_id", "task_context"]
                }
            ),
            Tool(
                name="get_strategies",
                description="Get successful strategies for a given task type from memory",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_type": {"type": "string", "description": "Type of task to get strategies for"},
                        "limit": {"type": "number", "description": "Maximum number of strategies to return"}
                    },
                    "required": ["task_type"]
                }
            )
        ]
        
        # Add Holographic Memory Tools
        if CONVERSATION_MEMORY_AVAILABLE:
            holographic_tools = [
                Tool(
                    name="recall_memory",
                    description="Recall past conversation turns using geometric similarity (Persistent)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Query text"},
                            "top_k": {"type": "integer", "description": "Number of results", "default": 3},
                            "session_id": {"type": "string", "description": "Session ID (optional, defaults to 'default')"}
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="get_memory_state",
                    description="Get the current state metadata of the Holographic Accumulator",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string", "description": "Session ID (optional, defaults to 'default')"}
                        }
                    }
                ),
                Tool(
                    name="visualize_memory",
                    description="[Holographic] Generates a 3D plot of the conversation trajectory and momentum.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string", "description": "Session ID to visualize."},
                            "output_path": {"type": "string", "description": "Optional custom path for image output."}
                        }
                    }
                ),
                Tool(
                    name="get_conversation_intuition",
                    description="[Bicameral] Uses the Corpus Callosum to 'feel' the conversation's geometric state (Volatility/Resonance).",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string", "description": "Session ID (optional)"}
                        }
                    }
                ),
                Tool(
                    name="predict_future_state",
                    description="[Neural] Uses the JEPA Predictor to forecast the next conversation state and its emotional resonance.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "session_id": {"type": "string", "description": "Session ID (optional)"},
                            "horizon": {"type": "integer", "description": "Number of steps to predict (default 1)", "default": 1}
                        }
                    }
                ),
                Tool(
                    name="verify_deployment",
                    description="[GitOps] Validates the current system state against Core Axioms using Holographic Hash.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "repo_path": {"type": "string", "description": "Path to repo (default '.')", "default": "."}
                        }
                    }
                ),
            ]
            tools.extend(holographic_tools)

        # Add Bicameral V2 Tools (Reflex Programming & Language of Thought)
        bicameral_tools = [
            Tool(
                name="set_reflex_constraint",
                description="[Bicameral V2] Map natural language to HDC constraint vector for HSE kernel monitoring. Creates a 'reflex' that triggers when system state matches the constraint.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Natural language constraint (e.g., 'Watch for database latency exceeding 500ms')"},
                        "threshold": {"type": "number", "description": "Activation threshold 0.0-1.0 (default 0.3)", "default": 0.3},
                        "priority": {"type": "integer", "description": "Importance 1-10 (default 5)", "default": 5},
                        "action": {"type": "string", "description": "Response: alert|block|log|callback (default: alert)", "default": "alert"}
                    },
                    "required": ["text"]
                }
            ),
            Tool(
                name="list_reflex_constraints",
                description="[Bicameral V2] List all active reflex constraints.",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            Tool(
                name="remove_reflex_constraint",
                description="[Bicameral V2] Remove a reflex constraint by ID.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "constraint_id": {"type": "string", "description": "Constraint ID to remove"}
                    },
                    "required": ["constraint_id"]
                }
            ),
            Tool(
                name="send_thought_vector",
                description="[LoT] Send a thought vector for secure agent-to-agent communication via HDC. Enables instant semantic resonance detection.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "thought_text": {"type": "string", "description": "The thought/message to encode and send"},
                        "target_agent": {"type": "string", "description": "Target agent ID ('*' for broadcast)", "default": "*"},
                        "urgency": {"type": "number", "description": "Urgency level 0.0-1.0", "default": 0.5},
                        "correlation_id": {"type": "string", "description": "Optional correlation ID for tracking"}
                    },
                    "required": ["thought_text"]
                }
            ),
            Tool(
                name="register_thought_interest",
                description="[LoT] Register an interest pattern for receiving relevant thoughts.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "interest_name": {"type": "string", "description": "Name for this interest"},
                        "interest_text": {"type": "string", "description": "Text describing what to listen for"}
                    },
                    "required": ["interest_name", "interest_text"]
                }
            ),
            Tool(
                name="genesis_hyper_encode_intent",
                description="[Genesis Hyper-Spatial] Encode architect intent into hypervector for holographic verification.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "intent_text": {"type": "string", "description": "The design intent to encode"},
                        "job_id": {"type": "string", "description": "Genesis job ID"}
                    },
                    "required": ["intent_text", "job_id"]
                }
            ),
            Tool(
                name="genesis_hyper_verify",
                description="[Genesis Hyper-Spatial] Verify job completion against original intent using holographic comparison.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string", "description": "Genesis job ID to verify"},
                        "outcome_text": {"type": "string", "description": "Description of the actual outcome"}
                    },
                    "required": ["job_id", "outcome_text"]
                }
            ),
        ]
        tools.extend(bicameral_tools)

        # Add TickFrame Pipeline Tools
        tickframe_tools = [
            Tool(
                name="tickframe_ingest",
                description="[TickFrame Pipeline] Ingest a telemetry tick and compute unified state (HDC + Quaternion + Energy).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tick_id": {"type": "string", "description": "Unique tick identifier (e.g., 'tick_001')"},
                        "observation_text": {"type": "string", "description": "Raw observation text to encode"},
                        "timestamp": {"type": "number", "description": "Unix timestamp (optional, defaults to now)"}
                    },
                    "required": ["tick_id", "observation_text"]
                }
            ),
            Tool(
                name="tickframe_preflight",
                description="[TickFrame Pipeline] Run preflight validation on the latest tick before handoff.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tick_id": {"type": "string", "description": "Tick ID to validate"},
                        "energy_threshold": {"type": "number", "description": "Max allowed E_total (default 2.0)"},
                        "rotation_threshold": {"type": "number", "description": "Max quaternion angular distance (default π/4)"}
                    },
                    "required": ["tick_id"]
                }
            ),
            Tool(
                name="tickframe_get_latest",
                description="[TickFrame Pipeline] Retrieve the most recent TickFrame state.",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            Tool(
                name="tickframe_add_attractor",
                description="[TickFrame Pipeline] Add a basin attractor for Hopfield energy calculation.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Attractor name (e.g., 'healthy_state')"},
                        "text": {"type": "string", "description": "Text description to encode as attractor"}
                    },
                    "required": ["name", "text"]
                }
            ),
        ]
        tools.extend(tickframe_tools)

        # Add Koopman Operator Tools
        koopman_tools = [
            Tool(
                name="koopman_fit",
                description="[Koopman Operator] Fit the Koopman operator from recent TickFrame history using EDMD.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "lift_type": {"type": "string", "description": "Lifting function: rbf|polynomial|random_fourier (default rbf)"},
                        "n_components": {"type": "integer", "description": "Number of lifted features (default 50)"},
                        "max_frames": {"type": "integer", "description": "Max historical frames to use (default 100)"}
                    }
                }
            ),
            Tool(
                name="koopman_predict",
                description="[Koopman Operator] Predict future HDC state using the fitted Koopman operator.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "steps": {"type": "integer", "description": "Number of steps to predict (default 1)"},
                        "current_state": {"type": "array", "description": "Current HDC state vector (optional, uses latest tick)"}
                    }
                }
            ),
            Tool(
                name="koopman_residual",
                description="[Koopman Operator] Compute residual energy between predicted and actual states.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "predicted": {"type": "array", "description": "Predicted HDC state vector"},
                        "actual": {"type": "array", "description": "Actual HDC state vector"}
                    },
                    "required": ["predicted", "actual"]
                }
            ),
            Tool(
                name="koopman_eigenmodes",
                description="[Koopman Operator] Analyze dominant eigenmodes for stability assessment.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "top_k": {"type": "integer", "description": "Number of top eigenmodes to return (default 5)"}
                    }
                }
            ),
        ]
        tools.extend(koopman_tools)

        # Add Conformal Prediction Tools
        conformal_tools = [
            Tool(
                name="conformal_calibrate",
                description="[Conformal Prediction] Calibrate the conformal predictor from historical residuals.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "target_coverage": {"type": "number", "description": "Target coverage probability (default 0.95)"}
                    }
                }
            ),
            Tool(
                name="conformal_gate",
                description="[Conformal Prediction] Gate a predicted state - PASS if within calibrated bounds, FAIL otherwise.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "predicted": {"type": "array", "description": "Predicted HDC state vector"},
                        "actual": {"type": "array", "description": "Actual HDC state vector"}
                    },
                    "required": ["predicted", "actual"]
                }
            ),
            Tool(
                name="conformal_stats",
                description="[Conformal Prediction] Get calibration statistics and current threshold.",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
        ]
        tools.extend(conformal_tools)

        # HDC Memory System Tools (SDM, InfiniMemory, LongMemory, Accumulator)
        memory_system_tools = [
            Tool(
                name="sdm_write",
                description="[SDM] Write data to Sparse Distributed Memory at given HDC address. Auto-stores as attractor.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "address": {"type": "array", "items": {"type": "number"}, "description": "HDC address vector"},
                        "data": {"type": "array", "items": {"type": "number"}, "description": "HDC data vector to store"},
                        "as_attractor": {"type": "boolean", "description": "Store as self-referential attractor (default: true)"}
                    },
                    "required": ["address", "data"]
                }
            ),
            Tool(
                name="sdm_read",
                description="[SDM] Read from Sparse Distributed Memory. Returns nearest stored pattern.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "address": {"type": "array", "items": {"type": "number"}, "description": "HDC address to query"}
                    },
                    "required": ["address"]
                }
            ),
            Tool(
                name="sdm_cleanup",
                description="[SDM] Auto-associative cleanup of noisy/partial pattern. Iterates to find stable attractor.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "array", "items": {"type": "number"}, "description": "Noisy/partial pattern"},
                        "iterations": {"type": "integer", "description": "Cleanup iterations (default: 3)"}
                    },
                    "required": ["pattern"]
                }
            ),
            Tool(
                name="sdm_stats",
                description="[SDM] Get Sparse Distributed Memory statistics.",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="infini_update",
                description="[InfiniMemory] Add content to infinite compressive memory with temporal encoding.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content_hv": {"type": "array", "items": {"type": "number"}, "description": "Content hypervector to accumulate"},
                        "importance": {"type": "number", "description": "Importance weight (default: 1.0)"}
                    },
                    "required": ["content_hv"]
                }
            ),
            Tool(
                name="infini_query",
                description="[InfiniMemory] Query infinite memory for relevance to a given vector.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query_hv": {"type": "array", "items": {"type": "number"}, "description": "Query hypervector"}
                    },
                    "required": ["query_hv"]
                }
            ),
            Tool(
                name="infini_retrieve_position",
                description="[InfiniMemory] Retrieve content at specific temporal position from infinite memory.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "position": {"type": "integer", "description": "Temporal position to retrieve"}
                    },
                    "required": ["position"]
                }
            ),
            Tool(
                name="infini_stats",
                description="[InfiniMemory] Get infinite memory statistics.",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="longmem_store",
                description="[LongMemory] Store episodic memory with HDC key for retrieval.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "key_hv": {"type": "array", "items": {"type": "number"}, "description": "HDC key vector"},
                        "value": {"type": "object", "description": "Arbitrary data to store (JSON serializable)"}
                    },
                    "required": ["key_hv", "value"]
                }
            ),
            Tool(
                name="longmem_retrieve",
                description="[LongMemory] Retrieve top-k memories most similar to query.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query_hv": {"type": "array", "items": {"type": "number"}, "description": "Query hypervector"},
                        "top_k": {"type": "integer", "description": "Number of results (default: 5)"},
                        "recency_weight": {"type": "number", "description": "Weight for recency (default: 0.1)"}
                    },
                    "required": ["query_hv"]
                }
            ),
            Tool(
                name="longmem_stats",
                description="[LongMemory] Get long-term memory statistics.",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="accumulator_add",
                description="[Accumulator] Add content to holographic accumulator channel.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "channel": {"type": "string", "enum": ["content", "context", "actions", "feedback", "metadata"], "description": "Channel to accumulate into"},
                        "content_hv": {"type": "array", "items": {"type": "number"}, "description": "Content hypervector"},
                        "importance": {"type": "number", "description": "Importance weight (default: 1.0)"}
                    },
                    "required": ["channel", "content_hv"]
                }
            ),
            Tool(
                name="accumulator_query",
                description="[Accumulator] Query relevance across all accumulator channels.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query_hv": {"type": "array", "items": {"type": "number"}, "description": "Query hypervector"}
                    },
                    "required": ["query_hv"]
                }
            ),
            Tool(
                name="accumulator_consolidate",
                description="[Accumulator] Consolidate all channels into single hard vector for storage.",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="accumulator_stats",
                description="[Accumulator] Get holographic accumulator statistics.",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="hopfield_store",
                description="[Hopfield] Store HDC patterns as attractors in energy landscape.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "patterns": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}, "description": "List of patterns to store"}
                    },
                    "required": ["patterns"]
                }
            ),
            Tool(
                name="hopfield_retrieve",
                description="[Hopfield] Retrieve nearest attractor via Modern Hopfield update (attention).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "array", "items": {"type": "number"}, "description": "Query pattern"},
                        "iterations": {"type": "integer", "description": "Retrieval iterations (default: 1)"}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="hopfield_energy",
                description="[Hopfield] Compute energy of a query state (low = near attractor).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "array", "items": {"type": "number"}, "description": "Query pattern"}
                    },
                    "required": ["query"]
                }
            ),
        ]
        tools.extend(memory_system_tools)

        # Memory Maintainer Tools (High-Level Agent Integration)
        maintainer_tools = [
            Tool(
                name="memory_sync_event",
                description="[MemoryMaintainer] Sync an event across all memory systems (InfiniMemory, LongMemory, Accumulator, optionally Hopfield). Use after significant events like conversation turns, task completions, or anomalies.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "event_type": {"type": "string", "description": "Event type: conversation_turn, conversation_end, task_start, task_complete, user_feedback, context_shift, anomaly_detected, repair_action"},
                        "content_hv": {"type": "array", "items": {"type": "number"}, "description": "HDC-encoded content vector"},
                        "importance": {"type": "number", "description": "Importance weight (default: 1.0, use 1.5+ for Hopfield storage)"},
                        "metadata": {"type": "object", "description": "Additional event metadata (session_id, summary, etc.)"}
                    },
                    "required": ["event_type", "content_hv"]
                }
            ),
            Tool(
                name="memory_retrieve",
                description="[MemoryMaintainer] Intelligent multi-system memory retrieval. Uses cascaded strategy: Hopfield (fast) → LongMemory (episodic) → InfiniMemory (relevance) → SDM (reconstruction).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query_hv": {"type": "array", "items": {"type": "number"}, "description": "HDC-encoded query vector"},
                        "strategy": {"type": "string", "enum": ["cascaded", "parallel", "fastest", "episodic", "compressive"], "description": "Retrieval strategy (default: cascaded)"},
                        "top_k": {"type": "integer", "description": "Number of results from LongMemory (default: 5)"},
                        "recency_weight": {"type": "number", "description": "Weight for recency in LongMemory (default: 0.2)"}
                    },
                    "required": ["query_hv"]
                }
            ),
            Tool(
                name="memory_consolidate",
                description="[MemoryMaintainer] Run memory consolidation (dreaming cycle). Consolidates Accumulator channels, stores as Hopfield attractor. Call during system idle time.",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="memory_health",
                description="[MemoryMaintainer] Get health status of all memory systems (SDM, InfiniMemory, LongMemory, Accumulator).",
                inputSchema={"type": "object", "properties": {}}
            ),
        ]
        tools.extend(maintainer_tools)

        # Add Genesis Chain Management Tools (Quota Protected)
        genesis_tools = [
            Tool(
                name="genesis_submit",
                description="⚠️ Submit Genesis Chain job with mandatory user authorization (QUOTA PROTECTED)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "genesis_prompt": {"type": "string", "description": "The architectural prompt for Genesis processing (min 50 chars)"},
                        "user_authorized": {"type": "boolean", "description": "REQUIRED - Must be True with explicit user consent for quota usage"},
                        "session_id": {"type": "string", "description": "Optional tracking ID for the Genesis job"},
                        "priority": {"type": "string", "description": "Job priority: normal|high|urgent"}
                    },
                    "required": ["genesis_prompt", "user_authorized"]
                }
            ),
            Tool(
                name="genesis_monitor",
                description="Monitor Genesis job progress and outputs in real-time",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string", "description": "Specific job ID to monitor (None for all recent)"},
                        "max_age_hours": {"type": "integer", "description": "How far back to look for jobs (default 24)"}
                    }
                }
            ),
            Tool(
                name="genesis_output",
                description="Retrieve Genesis job outputs and completion results",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string", "description": "Job identifier to retrieve outputs for"},
                        "output_type": {"type": "string", "description": "Output type: jobs|responses|complete|all"}
                    },
                    "required": ["job_id"]
                }
            ),
            Tool(
                name="genesis_quota",
                description="Check Genesis Chain quota usage and limits",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="genesis_diagnose",
                description="Diagnose Genesis job failures and provide recovery steps",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "job_id": {"type": "string", "description": "Job ID to diagnose"}
                    },
                    "required": ["job_id"]
                }
            ),
            Tool(
                name="genesis_restart",
                description="Restart Genesis Chain components safely",
                inputSchema={"type": "object", "properties": {}}
            )
        ]
        
        tools.extend(genesis_tools)
        
        # Add Geometry Kernel Tools
        geometry_tools = [
            Tool(
                name="telemetry_compress",
                description="Compress telemetry data into 3D latent coordinates via VAE Transformer",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "component_id": {"type": "string"},
                        "time_window": {"type": "string", "description": "e.g. 5m, 1h"}
                    },
                    "required": ["component_id"]
                }
            ),
            Tool(
                name="geometry_interpret",
                description="Interpret system state and events into geometric force vectors",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "snapshot": {"type": "object"},
                        "events": {"type": "array"},
                        "mode": {"type": "string", "enum": ["wake", "dream"]}
                    },
                    "required": ["snapshot", "events"]
                }
            ),
            Tool(
                name="geometry_audit",
                description="Audit proposed geometric state transitions for stability",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "state_before": {"type": "object"},
                        "state_after": {"type": "object"},
                        "forces": {"type": "array"}
                    },
                    "required": ["state_before", "state_after", "forces"]
                }
            ),
            Tool(
                name="perform_cognitive_tick",
                description="serialize specific cognitive cycle: Sensation -> VAE -> Grounding -> Interpretation",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "component_id": {"type": "string"},
                        "image_base64": {"type": "string", "description": "Optional visual snapshot"},
                        "log_sample": {"type": "string", "description": "Optional log text"}
                    },
                    "required": ["component_id"]
                }
            ),
            Tool(
                name="geometry_analyze",
                description="Analyze current geometric subject. Returns raw structural data (nodes, forces, trajectory) for agent inspection.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "focus": {"type": "string", "description": "Optional focus area query"}
                    }
                }
            ),
            Tool(
                name="inspect_geometric_region",
                description="Semantic Raycast: Retrieve text content (summary/desc) for specific geometry nodes.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "node_ids": {
                            "type": "array", 
                            "items": {"type": "string"},
                            "description": "List of Node IDs to inspect"
                        }
                    },
                    "required": ["node_ids"]
                }
            )
        ]
        
        # Add Native Geometry Kernel Tools (Physics Engine)
        kernel_physics_tools = [
            Tool(
                name="geometry_state",
                description="Get current state of the Geometry Kernel Physics Engine",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="geometry_simulate",
                description="Simulate forces on the Geometry Kernel (Dry Run)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "forces": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "target_id": {"type": "string"},
                                    "vector": {"type": "array", "items": {"type": "number"}},
                                    "magnitude": {"type": "number"},
                                    "source": {"type": "string"}
                                }
                            }
                        }
                    },
                    "required": ["forces"]
                }
            ),
            Tool(
                name="geometry_apply",
                description="Apply forces to the Geometry Kernel (State Mutation)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "forces": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "target_id": {"type": "string"},
                                    "vector": {"type": "array", "items": {"type": "number"}},
                                    "magnitude": {"type": "number"},
                                    "source": {"type": "string"}
                                }
                            }
                        },
                        "reason": {"type": "string"}
                    },
                    "required": ["forces", "reason"]
                }
            ),
            Tool(
                name="geometry_ingest",
                description="Ingest a file into the Geometry Kernel using Recursive RLM (The Hand)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Absolute path to the file to ingest"},
                        "objective": {"type": "string", "description": "Goal/Focus of the ingestion"},
                        "content_type": {"type": "string", "description": "Optional: 'AUTO', 'LOGS', 'NARRATIVE'", "default": "AUTO"}
                    },
                    "required": ["file_path", "objective"]
                }
            ),
            Tool(
                name="geometry_fetch_history",
                description="Fetch the history of ingested geometric models (Solar Systems) for multi-document synthesis.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Number of past items to retrieve (default 10)", "default": 10}
                    },
                    "required": []
                }
            ),
            Tool(
                name="vision_analyze",
                description="Analyze an image or document page using Qwen3-VL for text, handwriting, and visual understanding.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "image_path": {"type": "string", "description": "Absolute path to the image file"},
                        "prompt": {"type": "string", "description": "Analysis prompt (e.g., 'Extract text and handwriting')", "default": "Describe this image in detail, extracting all text and handwriting notes."}
                    },
                    "required": ["image_path"]
                }
            )
        ]
        tools.extend(geometry_tools)
        tools.extend(kernel_physics_tools)

        # Director Protocol Tools
        director_tools = [
            Tool(
                name="read_system_intuition",
                description="The Translator: Converts raw system state (vectors) into a conceptual brief. Use this to understand 'Entropy' and 'Stress' before acting.",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="process_input_attention",
                description="The HDC Filter: Re-ranks user input against local project vectors to filter noise.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Raw user input text"}
                    },
                    "required": ["text"]
                }
            ),
            Tool(
                name="promote_to_skill",
                description="Formalizes successful ad-hoc logic into a permanent Skill Frame (Python file).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_name": {"type": "string", "description": "Unique name for the skill (snake_case)"},
                        "python_code": {"type": "string", "description": "The python code to save"}
                    },
                    "required": ["task_name", "python_code"]
                }
            ),
            Tool(
                name="read_mission_state",
                description="Fetches current LangGraph mission state and active phase.",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="consult_reasoning_bank",
                description="Queries the Reasoning Bank for Patterns and Anti-Patterns.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query for patterns"}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="list_tools",
                description="List all available MCP tools on this server (for agent discovery)",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="list_resources",
                description="List all available MCP resources on this server (for agent discovery)",
                inputSchema={"type": "object", "properties": {}}
            ),
            Tool(
                name="get_arca_secret",
                description="Authoritative retrieval of a secret using SecretsProvider",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "key_name": {"type": "string", "description": "Name of the secret to retrieve"}
                    },
                    "required": ["key_name"]
                }
            )
        ]
        tools.extend(director_tools)
        
        # Add Enhanced Skill Tools (Dynamic from Registry)
        if self.skill_registry:
            try:
                skill_tools_list = self.skill_registry.get_tools_list()
                for tool_def in skill_tools_list:
                    tools.append(Tool(
                        name=tool_def['name'],
                        description=tool_def['description'],
                        inputSchema=tool_def['inputSchema']
                    ))
            except Exception as e:
                logger.error(f"Error adding skill tools: {e}")
        
        # Add Compress Tools
        tools.append(Tool(
            name="compress_file",
            description="Compress a specific file using the Compressor Agent (Gemini 2.5 Flash)",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to the file"},
                    "focus_point": {"type": "string", "description": "What to focus on during compression"}
                },
                "required": ["file_path", "focus_point"]
            }
        ))
        
        tools.append(Tool(
            name="compress_codebase",
            description="Perform a smart tree-based repository compression focused on a specific logic area.",
            inputSchema={
                "type": "object",
                "properties": {
                    "focus_area": {"type": "string", "description": "Conceptual focus (e.g., 'Deployment', 'Graph Logic')"},
                    "repo_path": {"type": "string", "description": "Path to the repository root (default: /workspace)", "default": "/workspace"}
                },
                "required": ["focus_area"]
            }
        ))
        
        # Add Universal Context Tool (USF)
        if USF_AVAILABLE:
            tools.append(Tool(
                name="get_universal_context",
                description="Retrieve specialized context frame around a subject (Service, Code, Workflow) from the Holographic Context Graph.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "subject": {"type": "string", "description": "Subject to query (e.g. 'neural_system', 'llama_cpp')"},
                        "radius": {"type": "integer", "description": "Graph traversal depth (default 4)"}
                    },
                    "required": ["subject"]
                }
            ))

        # Add Serena tools if available
        if self.serena_tools:
            tools.extend(self.serena_tools)
        
        # Add Path Sanitization Tool
        if PATH_UTILS_AVAILABLE:
            tools.append(Tool(
                name="sanitize_shell_command",
                description="Quote paths containing spaces in shell commands to prevent parsing errors. Essential for paths like '/Users/danexall/Documents/VS Code Projects/...'",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command with unquoted paths"},
                        "base_paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional: Known project base paths to protect (default: ARCA paths)"
                        }
                    },
                    "required": ["command"]
                }
            ))
            
            tools.append(Tool(
                name="quote_path",
                description="Quote a single path if it contains spaces or special shell characters.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File or directory path"}
                    },
                    "required": ["path"]
                }
            ))
            
        # Add proxy tools for mesh routing (e.g. gateway_request, service_request)
        for pt in PROXY_TOOLS:
            tools.append(Tool(**pt))
            
        return ListToolsResult(tools=tools)
    
    async def _call_tool(self, name: str, arguments: dict, headers: Optional[Dict[str, str]] = None) -> CallToolResult:
        """Call an MCP tool"""
        try:
            result = None
            
            # Director Protocol Tools
            if name == "read_system_intuition":
                if hasattr(self, 'mcp_director'):
                    director = self.mcp_director.get_director_tools()
                    result = await director.read_system_intuition()
                else:
                    raise Exception("Director tools not initialized")
            
            elif name == "process_input_attention":
                if hasattr(self, 'mcp_director'):
                    director = self.mcp_director.get_director_tools()
                    result = await director.process_input_attention(arguments.get("text"))
                else:
                    raise Exception("Director tools not initialized")
                    
            elif name == "promote_to_skill":
                if hasattr(self, 'mcp_director'):
                    director = self.mcp_director.get_director_tools()
                    result = await director.promote_to_skill(arguments.get("task_name"), arguments.get("python_code"))
                else:
                    raise Exception("Director tools not initialized")
            
            elif name == "read_mission_state":
                if hasattr(self, 'mcp_director'):
                    director = self.mcp_director.get_director_tools()
                    result = await director.read_mission_state()
                else:
                    raise Exception("Director tools not initialized")
            
            elif name == "consult_reasoning_bank":
                if hasattr(self, 'mcp_reasoningbank'):
                    result = self.mcp_reasoningbank.reasoning_search(arguments.get("query"))
                else:
                    raise Exception("ReasoningBank tool not initialized")

            elif name == "list_tools":
                result_obj = await self._list_tools()
                # Serialize the Tool objects to dicts for JSON output
                tools_data = []
                for t in result_obj.tools:
                    tools_data.append({
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.inputSchema
                    })
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(tools_data, indent=2))])

            elif name == "list_resources":
                result_obj = await self._list_resources()
                # Serialize the Resource objects to dicts for JSON output
                resources_data = []
                for r in result_obj.resources:
                    resources_data.append({
                        "uri": str(r.uri),
                        "name": r.name,
                        "description": r.description or "",
                        "mimeType": r.mimeType or "text/plain"
                    })
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(resources_data, indent=2))])

            elif name == "get_arca_secret":
                key_name = arguments.get("key_name")
                if hasattr(self, 'mcp_secrets_bridge') and self.mcp_secrets_bridge:
                    try:
                        result = self.mcp_secrets_bridge.get_arca_secret(key_name)
                        return CallToolResult(content=[TextContent(type="text", text=str(result))])
                    except Exception as e:
                        return CallToolResult(content=[TextContent(type="text", text=f"Error in secrets_bridge: {e}")], isError=True)
                else:
                    from shared.secrets_provider import SecretsProvider
                    provider = SecretsProvider()
                    val = provider.get(key_name)
                    if val:
                        return CallToolResult(content=[TextContent(type="text", text=str(val))])
                    else:
                        return CallToolResult(content=[TextContent(type="text", text=f"Error: Secret '{key_name}' not found.")], isError=True)

            elif name == "dispatch_agent":
                if hasattr(self, 'mcp_agent_dispatch') and self.mcp_agent_dispatch:
                    agent_type = arguments["agent_type"]
                    operation = arguments["operation"]
                    params = arguments.get("params")
                    intent_hv = arguments.get("intent_hv")
                    instruct = arguments.get("instruct")
                    result = self.mcp_agent_dispatch.dispatch_agent(
                        agent_type=agent_type, 
                        operation=operation, 
                        params=params, 
                        intent_hv=intent_hv,
                        instruct=instruct,
                        headers=headers
                    )
                    return CallToolResult(content=[TextContent(type="text", text=result)])
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: mcp_agent_dispatch tool not initialized")], isError=True)

            # Existing Tools
            # Check Dynamic Skill Registry first
            elif self.skill_registry and name in self.skill_registry.tools:
                result_json = self.skill_registry.call_tool(name, arguments)
                return CallToolResult(content=[TextContent(type="text", text=result_json)])

            elif name == "mcp_system_analysis" or name == "system_analysis":
                query = arguments.get("query", "Perform comprehensive health check")
                depth = arguments.get("depth", "summary")
                if getattr(self, 'mcp_system_analysis', None) is None:
                    try:
                        import tools.mcp_system_analysis as mcp_system_analysis
                        self.mcp_system_analysis = mcp_system_analysis
                    except Exception as e:
                        return CallToolResult(content=[TextContent(type="text", text=f"Error importing mcp_system_analysis: {e}")], isError=True)
                
                analysis_tool = self.mcp_system_analysis.SystemAnalysisTool()
                result = await analysis_tool.analyze(query, depth, headers=headers)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result) if isinstance(result, dict) else str(result))])


            elif name == "generate_image_embedding":
                image_input = arguments["image_input"]
                if getattr(self, 'vision_encoder', None) is None:
                    from tools.mcp_vision_encoder import VisionEncoder
                    self.vision_encoder = VisionEncoder()
                
                embedding = await self.vision_encoder.encode_image(image_input)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(embedding))])

            elif name == "vision_analyze":
                image_path = arguments["image_path"]
                prompt = arguments.get("prompt", "Describe this image in detail, extracting all text and handwriting notes.")
                
                if getattr(self, 'vision_encoder', None) is None:
                    from tools.mcp_vision_encoder import VisionEncoder
                    self.vision_encoder = VisionEncoder()
                
                analysis = await self.vision_encoder.analyze_image(image_path, prompt)
                return CallToolResult(content=[TextContent(type="text", text=analysis)])

                result = await self.saig_topology_tool.generate_topology(image_input)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result))])

            elif name == "compress_file":
                if not self.compressor:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Compressor tool not available")], isError=True)
                
                file_path = arguments["file_path"]
                focus_point = arguments["focus_point"]
                result = await self.compressor.compress_file(file_path, focus_point)
                return CallToolResult(content=[TextContent(type="text", text=result)])

            elif name == "sanitize_shell_command":
                if not PATH_UTILS_AVAILABLE:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Path utils not available")], isError=True)
                
                command = arguments["command"]
                base_paths = arguments.get("base_paths", ["/Users/danexall/Documents/VS Code Projects"])
                sanitized = sanitize_shell_command(command, base_paths)
                return CallToolResult(content=[TextContent(type="text", text=sanitized)])
            
            elif name == "quote_path":
                if not PATH_UTILS_AVAILABLE:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Path utils not available")], isError=True)
                
                path = arguments["path"]
                quoted = quote_path(path)
                return CallToolResult(content=[TextContent(type="text", text=quoted)])

            elif name == "compress_codebase":
                if not self.compressor:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Compressor tool not available")], isError=True)
                
                focus_area = arguments["focus_area"]
                repo_path = arguments.get("repo_path", "/workspace")
                result = await self.compressor.compress_codebase(focus_area, repo_path)
                return CallToolResult(content=[TextContent(type="text", text=result)])

            elif name == "telemetry_compress":
                if not self.telemetry_vae:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Telemetry VAE tool not available")], isError=True)
                
                component_id = arguments["component_id"]
                time_window = arguments.get("time_window", "5m")
                result = await self.telemetry_vae.compress_telemetry(component_id, time_window)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result))])

            elif name == "geometry_interpret":
                if not self.semantic_interpreter:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Geometry Interpreter tool not available")], isError=True)
                
                snapshot = arguments["snapshot"]
                events = arguments["events"]
                mode = arguments.get("mode", "wake")
                result = self.semantic_interpreter.interpret(snapshot, events, mode)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, default=str))])

            elif name == "geometry_audit":
                if not self.feasibility_auditor:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Geometry Auditor tool not available")], isError=True)
                
                state_before = arguments["state_before"]
                state_after = arguments["state_after"]
                forces = arguments["forces"]
                result = self.feasibility_auditor.audit(state_before, state_after, forces)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, default=str))])


            elif name == "inspect_geometric_region":
                if not self.redis_client:
                     return CallToolResult(content=[TextContent(type="text", text="Error: Redis Blackboard not available")], isError=True)
                
                node_ids = arguments["node_ids"]
                results = []
                
                try:
                    for nid in node_ids:
                        key = f"semantic:{nid}"
                        if self.redis_client.exists(key):
                            meta = self.redis_client.hgetall(key)
                            summary = meta.get("summary", "No summary")
                            desc = meta.get("desc", "No desc")
                            src = meta.get("source_file", "unknown")
                            results.append(f"🔍 NODE [{nid}]:\n   Desc: {desc}\n   Summary: {summary}\n   Source: {src}\n")
                        else:
                            results.append(f"❌ NODE [{nid}]: No semantic data found")
                    
                    return CallToolResult(content=[TextContent(type="text", text="\n".join(results))])
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Raycast Failed: {e}")], isError=True)

            elif name == "perform_cognitive_tick":
                if not self.geometry_orchestrator:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Geometry Orchestrator not available")], isError=True)
                
                component_id = arguments["component_id"]
                image_base64 = arguments.get("image_base64")
                log_sample = arguments.get("log_sample")
                
                result = await self.geometry_orchestrator.execute_tick(component_id, image_base64, log_sample)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, default=str))])

            elif name == "geometry_analyze":
                if not self.redis_client:
                     return CallToolResult(content=[TextContent(type="text", text="Error: Redis Blackboard not available")], isError=True)
                
                # Retrieve from Redis Blackboard
                try:
                    state_json = self.redis_client.get("arca:blackboard:working_model")
                    if not state_json:
                        # Fallback to history
                        history = self.redis_client.lrange("arca:blackboard:geometry_history", 0, 0)
                        if history:
                            state_json = json.loads(history[0]).get("solar_system")
                            if isinstance(state_json, dict):
                                state_json = json.dumps(state_json)
                    
                    if state_json:
                        return CallToolResult(content=[TextContent(type="text", text=state_json)])
                    else:
                        return CallToolResult(content=[TextContent(type="text", text="Blackboard is empty. No geometry loaded.")])
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Error reading Redis: {e}")], isError=True)

            # Native Geometry Kernel Tools
            elif name == "geometry_state":
                if not self.redis_client:
                     return CallToolResult(content=[TextContent(type="text", text="Error: Redis Blackboard not available")], isError=True)
                
                # Retrieve from Redis Blackboard as requested by user ("illuminate the redis space")
                try:
                    state_json = self.redis_client.get("arca:blackboard:working_model")
                    if not state_json:
                        # Fallback to history
                        history = self.redis_client.lrange("arca:blackboard:geometry_history", 0, 0)
                        if history:
                            state_json = json.loads(history[0]).get("solar_system")
                            if isinstance(state_json, dict):
                                state_json = json.dumps(state_json)
                    
                    if state_json:
                        return CallToolResult(content=[TextContent(type="text", text=state_json)])
                    else:
                        return CallToolResult(content=[TextContent(type="text", text="Blackboard is empty. No geometry loaded.")])
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Error reading Redis: {e}")], isError=True)

            elif name == "geometry_simulate":
                if not self.geometry_kernel:
                     return CallToolResult(content=[TextContent(type="text", text="Error: Geometry Kernel Tool not initialized")], isError=True)
                forces = arguments["forces"]
                result = self.geometry_kernel.simulate_forces(forces)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2, default=str))])

            elif name == "geometry_apply":
                if not self.geometry_kernel:
                     return CallToolResult(content=[TextContent(type="text", text="Error: Geometry Kernel Tool not initialized")], isError=True)
                forces = arguments["forces"]
                reason = arguments["reason"]
                result = self.geometry_kernel.apply_forces(forces, reason)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2, default=str))])

            elif name == "geometry_ingest":
                logger.info(f"DEBUG: geometry_ingest invoked (PROXY MODE) with arguments: {arguments}")
                # PROXY MODE: Delegate strictly to the verified Geometry Kernel API
                # This ensures we use the 'Golden Path' verified in the troubleshooting session.
                
                KERNEL_API_URL = os.environ.get(
                    "GEOMETRY_KERNEL_URL", "http://geometry_kernel:8087"
                ).rstrip("/") + "/geometry/ingest_recursive"
                
                try:
                    # Forward arguments exactly as received
                    # The Kernel API expects: file_path, objective, content_type
                    
                    # Ensure file_path is absolute (Agent might provide relative)
                    # We assume path is within /app/shared_storage or similar valid mount
                    
                    logger.info(f"🚀 Proxying Request to Kernel: {KERNEL_API_URL}")
                    
                    # Use a short timeout for connection, but long for read (ingestion is slow)
                    # Note: DeepSeek 1.5B takes ~6-8s per chunk. 50 chunks = ~400s. 
                    # Set timeout generous to avoid Agent timeouts.
                    resp = requests.post(KERNEL_API_URL, json=arguments, timeout=600)
                    
                    if resp.status_code == 200:
                        logger.info("✅ Kernel API returned success")
                        # Return raw JSON text from Kernel
                        return CallToolResult(content=[TextContent(type="text", text=resp.text)])
                    else:
                         error_msg = f"Kernel API Failed: {resp.status_code} - {resp.text}"
                         logger.error(error_msg)
                         return CallToolResult(content=[TextContent(type="text", text=json.dumps({
                             "error": error_msg,
                             "status": "failed"
                         }))], isError=True)

                except Exception as e:
                    logger.error(f"geometry_ingest proxy failed: {e}")
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps({
                        "error": str(e),
                        "status": "failed",
                        "message": "Failed to contact Geometry Kernel Service."
                    }))], isError=True)

            elif name == "geometry_fetch_history":
                if not self.redis_client:
                     return CallToolResult(content=[TextContent(type="text", text="Error: Redis Blackboard not available")], isError=True)
                
                limit = arguments.get("limit", 10)
                try:
                    # Fetch history list (LIFO)
                    history_raw = self.redis_client.lrange("arca:blackboard:geometry_history", 0, limit - 1)
                    history = []
                    for item in history_raw:
                        try:
                            history.append(json.loads(item))
                        except:
                            pass 
                    
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(history, indent=2, default=str))])
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Error reading history: {e}")], isError=True)

            elif name == "analyze_skill_performance":
                skill_name = arguments["skill_name"]
                time_period = arguments.get("time_period", "all")
                result = await self._analyze_skill_performance(skill_name, time_period)
                
            elif name == "get_skill_recommendations":
                context = arguments["context"]
                result = self.skills_manager.get_skill_recommendations(context)

            elif name == "read_file":
                file_path = arguments["file_path"]
                if mcp_file_ops:
                    result_str = mcp_file_ops.read_file(file_path)
                    result = {"content": result_str}
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: mcp_file_ops not available")], isError=True)

            elif name == "write_file":
                file_path = arguments["file_path"]
                content = arguments["content"]
                if mcp_file_ops:
                    result_str = mcp_file_ops.write_file(file_path, content)
                    result = {"status": "success", "result": result_str}
                else:
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps({"error": "mcp_file_ops not available", "status": "failed"}))], isError=True)
            
            elif name == "list_files" or name == "list_directory":
                # Handle both list_files and list_directory (same functionality)
                try:
                    directory = arguments.get("directory") or arguments.get("dir_path") or arguments.get("path") or "/app/shared_storage"
                    pattern = arguments.get("pattern", "")
                    recursive = arguments.get("recursive", True) # Default to recursive for better UX
                    
                    # Sanitation: Ensure arguments are strings, not lists (common LLM hallucination)
                    if isinstance(directory, list):
                        directory = directory[0] if directory else "/app/shared_storage"
                    if isinstance(pattern, list):
                        pattern = pattern[0] if pattern else ""

                    
                    # Security: Enforce path must be within authorized roots if strict
                    # But for now, we trust /app/shared_storage
                    
                    found_files = []
                    
                    # Local execution for /app/shared_storage (Volume Mount)
                    import fnmatch
                    import os
                    
                    if os.path.exists(directory):
                        if pattern and recursive:
                            # Recursive search for pattern
                            for root, dirs, files in os.walk(directory):
                                for filename in files:
                                    if fnmatch.fnmatch(filename, pattern):
                                        # Return path relative to searched directory for readability
                                        rel_dir = os.path.relpath(root, directory)
                                        if rel_dir == ".":
                                            found_files.append(filename)
                                        else:
                                            found_files.append(os.path.join(rel_dir, filename))
                                            
                                # Limit recursion depth/count if needed? 
                                # For now assume shared_storage isn't massive or 50 cap applies
                                if len(found_files) > 50:
                                    break
                        else:
                            # Shallow list (standard behavior) or no pattern
                            try:
                                entries = os.listdir(directory)
                                if pattern:
                                    found_files = [f for f in entries if fnmatch.fnmatch(f, pattern)]
                                else:
                                    found_files = entries
                            except Exception as e:
                                return CallToolResult(content=[TextContent(type="text", text=json.dumps({"error": f"Error listing directory: {e}", "status": "failed"}))], isError=True)
                                
                        # Return result
                        result = {"directory": directory, "files": found_files, "count": len(found_files)}
                        
                    else:
                        # Directory doesn't exist locally
                        return CallToolResult(content=[TextContent(type="text", text=json.dumps({"error": f"Directory not found: {directory}", "status": "failed"}))], isError=True)
                        
                except Exception as e:
                    logger.error(f"list_files failed: {e}")
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps({"error": str(e), "status": "failed"}))], isError=True)

            elif name == "create_folder":
                # Create folder in /shared_storage/ARCA/
                try:
                    folder_path = arguments["folder_path"]
                    base_path = Path("/app/shared_storage/ARCA")
                    full_path = (base_path / folder_path).resolve()
                    
                    # Security check: must be within /shared_storage/ARCA/
                    if not str(full_path).startswith(str(base_path)):
                        return CallToolResult(content=[TextContent(type="text", text=json.dumps({
                            "error": "Access denied: Can only create folders in /shared_storage/ARCA/",
                            "status": "failed"
                        }))], isError=True)
                    
                    full_path.mkdir(parents=True, exist_ok=True)
                    result = {"status": "success", "path": str(full_path), "message": f"Folder created: {folder_path}"}
                except Exception as e:
                    logger.error(f"create_folder failed: {e}")
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps({"error": str(e), "status": "failed"}))], isError=True)

            elif name == "edit_file":
                # Edit/update file in /shared_storage/ARCA/
                try:
                    file_path = arguments["file_path"]
                    content = arguments["content"]
                    append = arguments.get("append", False)
                    
                    base_path = Path("/app/shared_storage/ARCA")
                    full_path = (base_path / file_path).resolve()
                    
                    # Security check: must be within /shared_storage/ARCA/
                    if not str(full_path).startswith(str(base_path)):
                        return CallToolResult(content=[TextContent(type="text", text=json.dumps({
                            "error": "Access denied: Can only edit files in /shared_storage/ARCA/",
                            "status": "failed"
                        }))], isError=True)
                    
                    # Ensure parent directory exists
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    mode = "a" if append else "w"
                    with open(full_path, mode) as f:
                        f.write(content)
                    
                    result = {"status": "success", "path": str(full_path), "mode": "append" if append else "replace"}
                except Exception as e:
                    logger.error(f"edit_file failed: {e}")
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps({"error": str(e), "status": "failed"}))], isError=True)

            elif name == "delete_file":
                # Delete file or empty folder in /shared_storage/ARCA/
                try:
                    path = arguments["path"]
                    base_path = Path("/app/shared_storage/ARCA")
                    full_path = (base_path / path).resolve()
                    
                    # Security check: must be within /shared_storage/ARCA/
                    if not str(full_path).startswith(str(base_path)):
                        return CallToolResult(content=[TextContent(type="text", text=json.dumps({
                            "error": "Access denied: Can only delete files in /shared_storage/ARCA/",
                            "status": "failed"
                        }))], isError=True)
                    
                    if not full_path.exists():
                        return CallToolResult(content=[TextContent(type="text", text=json.dumps({
                            "error": f"Path not found: {path}",
                            "status": "failed"
                        }))], isError=True)
                    
                    if full_path.is_file():
                        full_path.unlink()
                        result = {"status": "success", "deleted": str(full_path), "type": "file"}
                    elif full_path.is_dir():
                        # Only delete empty directories for safety
                        if any(full_path.iterdir()):
                            return CallToolResult(content=[TextContent(type="text", text=json.dumps({
                                "error": "Directory not empty. Delete files first.",
                                "status": "failed"
                            }))], isError=True)
                        full_path.rmdir()
                        result = {"status": "success", "deleted": str(full_path), "type": "directory"}
                    else:
                        return CallToolResult(content=[TextContent(type="text", text=json.dumps({
                            "error": f"Unknown path type: {path}",
                            "status": "failed"
                        }))], isError=True)
                except Exception as e:
                    logger.error(f"delete_file failed: {e}")
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps({"error": str(e), "status": "failed"}))], isError=True)

            elif name == "create_file":
                # Create-only tool - fails if file exists (prevents accidental overwrites)
                file_path = arguments["file_path"]
                content = arguments["content"]
                category = arguments.get("category", "docs")
                
                # Determine base directory based on category
                if category == "skills":
                    base_dir = SKILLS_DIR
                elif category == "reasoning":
                    base_dir = REASONING_DIR
                else:
                    base_dir = ARCA_ROOT / "shared_storage" / "docs"
                
                full_path = (base_dir / file_path).resolve()
                
                # Security check: ensure path is within allowed directories
                if not (str(full_path).startswith(str(SKILLS_DIR)) or 
                        str(full_path).startswith(str(REASONING_DIR)) or
                        str(full_path).startswith(str(ARCA_ROOT / "shared_storage"))):
                    raise ValueError("Access denied: Can only create files in allowed directories")
                
                if mcp_file_ops:
                    # Check existence using read_file (Host Bridge aware)
                    # read_file returns content or error string
                    read_result = mcp_file_ops.read_file(str(full_path))
                    if not read_result.startswith("Error:"):
                         return CallToolResult(
                             content=[TextContent(type="text", text=f"Error: File already exists: {full_path}. Use a different name or path.")],
                             isError=True
                         )
                    
                    # File likely doesn't exist (result started with Error), proceed to write
                    write_result = mcp_file_ops.write_file(str(full_path), content)
                    result = {
                        "status": "created",
                        "path": str(full_path),
                        "category": category,
                        "message": f"Successfully created new file: {full_path.name}. Result: {write_result}"
                    }
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: mcp_file_ops not available")], isError=True)
                
            elif name == "record_learning_event":
                skill_name = arguments["skill_name"]
                success = arguments["success"]
                context = arguments["context"]
                details = arguments.get("details", {})
                self.skills_manager.record_skill_usage(skill_name, success, context, details)
                return CallToolResult(content=[TextContent(type="text", text="Learning event recorded")])

            elif name == "robotics_analysis":
                content = arguments["content"]
                mode = arguments.get("mode", "structure")
                context = arguments.get("context")
                result = await self.structural_analyst.analyze(content, mode, context)
                return CallToolResult(content=[TextContent(type="text", text=result)])
            
            elif name == "robotics_dry_run":
                script = arguments["script"]
                script_type = arguments.get("script_type", "bash")
                result = await self.structural_analyst.dry_run_check(script, script_type)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
            
            elif name == "robotics_symbiosis_check":
                policy = arguments["policy"]
                result = await self.structural_analyst.symbiosis_check(policy)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
            
            elif name == "robotics_blackboard_health":
                blackboard_json = arguments["blackboard_json"]
                result = await self.structural_analyst.blackboard_health_check(blackboard_json)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
            
            elif name == "robotics_usage_stats":
                result = self.structural_analyst.get_usage_stats()
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
            
            # Neo4j Admin Tools
            elif name == "neo4j_verify_connectivity":
                result = self.neo4j_admin.verify_connectivity()
                return CallToolResult(content=[TextContent(type="text", text=result)])
            
            elif name == "neo4j_run_cypher":
                query = arguments["query"]
                result = self.neo4j_admin.run_cypher(query)
                return CallToolResult(content=[TextContent(type="text", text=result)])
            
            # Redis Blackboard Tools
            elif name == "blackboard_read":
                key = arguments["key"]
                result = self.blackboard_redis.read_key(key)
                return CallToolResult(content=[TextContent(type="text", text=result)])
            
            elif name == "blackboard_write":
                key = arguments["key"]
                value = arguments["value"]
                expiration = arguments.get("expiration")
                result = self.blackboard_redis.write_key(key, value, expiration)
                return CallToolResult(content=[TextContent(type="text", text=result)])
            
            elif name == "blackboard_acquire_lock":
                resource = arguments["resource"]
                timeout = arguments.get("timeout", 60)
                result = self.blackboard_redis.acquire_lock(resource, timeout)
                return CallToolResult(content=[TextContent(type="text", text=result)])
            
            elif name == "blackboard_publish":
                channel = arguments["channel"]
                message = arguments["message"]
                result = self.blackboard_redis.publish(channel, message)
                return CallToolResult(content=[TextContent(type="text", text=result)])
            
            # Skills Bank Tools
            elif name == "skills_list":
                skills = self._list_mcp_skills()
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(skills, indent=2))])
            
            elif name == "skills_get":
                skill_name = arguments["skill_name"]
                skill = self._get_mcp_skill(skill_name)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(skill, indent=2))])
            
            elif name == "skills_search":
                query = arguments["query"]
                matches = self._search_mcp_skills(query)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(matches, indent=2))])
            
            # ============================================================
            # Contextual Skill Frame Tools (Phase 2 Terrain Map)
            # ============================================================
            elif name == "get_skill_frame":
                if skill_frame_server is not None:
                    primary_skill = arguments["primary_skill"]
                    task_content = arguments.get("task_content", "")
                    include_layers = arguments.get("include_layers", ["service", "workflow", "related"])
                    result = await skill_frame_server.get_skill_frame(primary_skill, task_content, include_layers, headers=headers)
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                else:
                    return CallToolResult(content=[TextContent(type="text", text='{"error": "skill_frame_server not available"}')])
            
            elif name == "refresh_skill_index":
                if skill_frame_server is not None:
                    result = await skill_frame_server.refresh_skill_index(headers=headers)
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                else:
                    return CallToolResult(content=[TextContent(type="text", text='{"error": "skill_frame_server not available"}')])
            
            elif name == "get_skill_graph":
                if skill_frame_server is not None:
                    result = await skill_frame_server.get_skill_graph(headers=headers)
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                else:
                    return CallToolResult(content=[TextContent(type="text", text='{"error": "skill_frame_server not available"}')])
                    
            elif name == "get_universal_frame":
                anchor_id = arguments.get("anchor_id")
                depth = arguments.get("depth", 5)
                
                # Check directly for the module function availability first
                try:
                    import tools.skill_frame_server as sfs_module
                    result = await sfs_module.get_universal_frame(anchor_id, depth, headers=headers)
                except (ImportError, AttributeError):
                     if skill_frame_server is not None:
                        # Fallback to the instance method if module function isn't reachable
                        # Assuming we added get_universal_frame to the tool interface wrapper in the server file too
                        # if not, we use the server instance directly
                        s_instance = skill_frame_server.get_server()
                        result = s_instance.query_universal_frame(anchor_id, depth, headers=headers)
                     else:
                        return CallToolResult(content=[TextContent(type="text", text='{"error": "skill_frame_server not available"}')])
            # ============================================================

            
            elif name == "reasoning_search":
                query = arguments["query"]
                traces = self._search_reasoning_bank(query)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(traces, indent=2))])
            
            elif name == "reasoning_store":
                category = arguments["category"]
                reasoning = arguments["reasoning"]
                path = self._store_reasoning(category, reasoning)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps({"stored": path}))])
            
            elif name == "skill_capture":
                result = self._capture_skill(
                    skill_name=arguments["skill_name"],
                    category=arguments["category"],
                    description=arguments["description"],
                    problem=arguments["problem"],
                    solution_steps=arguments["solution_steps"],
                    verification=arguments["verification"],
                    mcp_tools_used=arguments.get("mcp_tools_used", []),
                    related_services=arguments.get("related_services", [])
                )
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
            
            elif name == "publish_health_alert":
                service = arguments["service"]
                status = arguments["status"]
                details = arguments.get("details", {})
                self.blackboard_redis.publish("arca:health:alerts", json.dumps({
                    "service": service,
                    "status": status,
                    "details": details,
                    "timestamp": datetime.now().isoformat()
                }))
                return CallToolResult(content=[TextContent(type="text", text=json.dumps({"published": True, "service": service, "status": status}))])

            # Holographic Memory Tools
            elif name == "recall_memory":
                try:
                    session_id = arguments.get("session_id", "default")
                    query = arguments["query"]
                    # Map to the new Memory System Context API
                    res = await self.memory_system.get_context(session_id, query)
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(res, indent=2))])
                except Exception as e:
                    logger.error(f"Error in recall_memory (Memory System): {e}")
                    # Fallback to local holographic memory if available
                    if self.holographic_service:
                        session_id = arguments.get("session_id", "default")
                        memory = self.holographic_service.get_session(session_id)
                        top_k = arguments.get("top_k", 3)
                        res = memory.recall(query, top_k)
                        return CallToolResult(content=[TextContent(type="text", text=json.dumps(res, indent=2))])
                    return CallToolResult(content=[TextContent(type="text", text=f"Error: {e}")], isError=True)

            elif name == "get_memory_state":
                if self.holographic_service:
                    session_id = arguments.get("session_id", "default")
                    memory = self.holographic_service.get_session(session_id)
                    res = memory.get_state_summary()
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(res, indent=2))])
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Holographic Memory not available")], isError=True)

            elif name == "visualize_memory":
                if self.holographic_service:
                    try:
                        from .tools.attractor_visualizer import AttractorVisualizer
                        session_id = arguments.get("session_id", "default")
                        memory = self.holographic_service.get_session(session_id)
                        
                        visualizer = AttractorVisualizer(input_dim=memory.hdc.D)
                        
                        output_path = arguments.get("output_path")
                        if not output_path:
                            # Default path
                            output_path = str(memory.base_dir / f"{session_id}_viz.png")
                            
                        path = visualizer.save_plot_to_file(memory.history, output_path)
                        
                        if path:
                            return CallToolResult(content=[TextContent(type="text", text=f"Visualization saved to: {path}")])
                        else:
                            return CallToolResult(content=[TextContent(type="text", text="Failed to generate visualization (empty history?)")], isError=True)
                    except Exception as e:
                        return CallToolResult(content=[TextContent(type="text", text=f"Error generating visualization: {e}")], isError=True)
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Holographic Memory system not initialized")], isError=True)

            elif name == "get_conversation_intuition":
                 if self.holographic_service:
                    try:
                        from .tools.corpus_callosum import CorpusCallosum
                        session_id = arguments.get("session_id", "default")
                        
                        # Get accumulator
                        memory = self.holographic_service.get_session(session_id)
                        
                        # Instantiate Corpus Callosum
                        bridge = CorpusCallosum(memory)
                        
                        intuition = bridge.get_intuition()
                        return CallToolResult(content=[TextContent(type="text", text=json.dumps(intuition, indent=2))])
                    
                    except Exception as e:
                        return CallToolResult(content=[TextContent(type="text", text=f"Intuition Error: {e}")], isError=True)
                 else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Holographic Memory system not initialized")], isError=True)

            elif name == "predict_future_state":
                if self.holographic_service:
                    try:
                        from services.neural_system.neural_predictor import HDCNeuralPredictor
                        from .tools.corpus_callosum import CorpusCallosum
                        
                        session_id = arguments.get("session_id", "default")
                        memory = self.holographic_service.get_session(session_id)
                        
                        # 1. Get Current State
                        current_hv = memory.global_vector
                        
                        # 2. Predict Next State (Mock/JEPA)
                        predictor = HDCNeuralPredictor(hdc_dim=memory.hdc.D)
                        predicted_hv = predictor.predict_next(current_hv)
                        
                        # 3. Interpret Prediction via Corpus Callosum
                        # We use the Callosum to "feel" the predicted future
                        # Hack: Temporarily swap the accumulator vector in a lightweight copy
                        class MockAcc:
                            def __init__(self, vec, hdc, enc):
                                self.global_vector = vec
                                self.history = [] # No history for future
                                self.hdc = hdc
                                self.encoder = enc
                                
                        mock_acc = MockAcc(predicted_hv, memory.hdc, memory.encoder)
                        future_sensor = CorpusCallosum(mock_acc)
                        
                        intuition = future_sensor.get_intuition()
                        
                        result = {
                            "prediction_horizon": 1,
                            "future_intuition": intuition
                        }
                        
                        return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                        
                    except Exception as e:
                        return CallToolResult(content=[TextContent(type="text", text=f"Prediction Error: {e}")], isError=True)
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Holographic Memory system not initialized")], isError=True)

            elif name == "verify_deployment":
                try:
                    from services.neural_system.system_hash import SystemHash
                    
                    repo_path = arguments.get("repo_path", ".")
                    hasher = SystemHash(repo_path)
                    
                    # Compute Verification
                    v_sys = hasher.compute_system_vector()
                    is_aligned = hasher.verify_alignment(v_sys)
                    
                    score = hasher.hdc.similarity(v_sys, hasher.axiom_vector)
                    
                    result = {
                        "alignment_score": float(score),
                        "aligned": is_aligned,
                        "status": "APPROVED" if is_aligned else "REJECTED",
                        "axiom_check": "PASS" if is_aligned else "FAIL"
                    }
                    
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"GitOps Error: {e}")], isError=True)

            # Bicameral V2 Tools (Reflex Programming)
            elif name == "set_reflex_constraint":
                try:
                    from services.neural_system.bicameral_reflex import get_reflex_engine
                    
                    engine = get_reflex_engine()
                    constraint = engine.set_reflex_constraint(
                        text=arguments["text"],
                        threshold=arguments.get("threshold", 0.3),
                        priority=arguments.get("priority", 5),
                        action=arguments.get("action", "alert")
                    )
                    
                    result = {
                        "status": "created",
                        "constraint": constraint.to_dict()
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Reflex Error: {e}")], isError=True)

            elif name == "list_reflex_constraints":
                try:
                    from services.neural_system.bicameral_reflex import get_reflex_engine
                    
                    engine = get_reflex_engine()
                    constraints = engine.list_constraints()
                    
                    result = {
                        "count": len(constraints),
                        "constraints": constraints
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Reflex Error: {e}")], isError=True)

            elif name == "remove_reflex_constraint":
                try:
                    from services.neural_system.bicameral_reflex import get_reflex_engine
                    
                    engine = get_reflex_engine()
                    removed = engine.remove_constraint(arguments["constraint_id"])
                    
                    result = {
                        "status": "removed" if removed else "not_found",
                        "constraint_id": arguments["constraint_id"]
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Reflex Error: {e}")], isError=True)

            # Language of Thought (LoT) Tools
            elif name == "send_thought_vector":
                try:
                    from services.neural_system.bicameral_reflex import LanguageOfThought
                    
                    # Use MCP server as the sending agent
                    lot = LanguageOfThought(agent_id="mcp_server")
                    thought = lot.send_thought_vector(
                        thought_text=arguments["thought_text"],
                        target_agent=arguments.get("target_agent", "*"),
                        urgency=arguments.get("urgency", 0.5),
                        correlation_id=arguments.get("correlation_id")
                    )
                    
                    result = {
                        "status": "sent",
                        "thought": thought.to_serializable()
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"LoT Error: {e}")], isError=True)

            elif name == "register_thought_interest":
                try:
                    from services.neural_system.bicameral_reflex import LanguageOfThought
                    
                    lot = LanguageOfThought(agent_id="mcp_server")
                    lot.register_interest(
                        interest_name=arguments["interest_name"],
                        interest_text=arguments["interest_text"]
                    )
                    
                    result = {
                        "status": "registered",
                        "interest_name": arguments["interest_name"]
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"LoT Error: {e}")], isError=True)

            # Genesis Hyper-Spatial Tools
            elif name == "genesis_hyper_encode_intent":
                try:
                    from services.neural_system.bicameral_reflex import get_genesis_hyper
                    
                    hyper = get_genesis_hyper()
                    v_intent = hyper.encode_intent(
                        intent_text=arguments["intent_text"],
                        job_id=arguments["job_id"]
                    )
                    
                    result = {
                        "status": "encoded",
                        "job_id": arguments["job_id"],
                        "vector_norm": float(np.linalg.norm(v_intent))
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Genesis Hyper Error: {e}")], isError=True)

            elif name == "genesis_hyper_verify":
                try:
                    from services.neural_system.bicameral_reflex import get_genesis_hyper
                    
                    hyper = get_genesis_hyper()
                    verification = hyper.verify_job_completion(
                        job_id=arguments["job_id"],
                        outcome_text=arguments["outcome_text"]
                    )
                    
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(verification, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Genesis Hyper Error: {e}")], isError=True)

            # TickFrame Pipeline Tools
            elif name == "tickframe_ingest":
                try:
                    from services.neural_system.tickframe_pipeline import get_pipeline
                    import time
                    
                    pipeline = get_pipeline()
                    ts = arguments.get("timestamp", time.time())
                    frame = pipeline.ingest(
                        tick_id=arguments["tick_id"],
                        observation_text=arguments["observation_text"],
                        timestamp=ts
                    )
                    
                    result = {
                        "status": "ingested",
                        "tick_id": frame.tick_id,
                        "timestamp": frame.timestamp,
                        "energy": {
                            "E_rot": frame.energy.E_rot,
                            "E_hopfield": frame.energy.E_hopfield,
                            "E_jepa": frame.energy.E_jepa,
                            "E_curvature": frame.energy.E_curvature,
                            "E_total": frame.energy.E_total
                        },
                        "quaternion": frame.quaternion.tolist(),
                        "omega_norm": float(np.linalg.norm(frame.omega))
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"TickFrame Error: {e}")], isError=True)

            elif name == "tickframe_preflight":
                try:
                    from services.neural_system.tickframe_pipeline import get_pipeline
                    
                    pipeline = get_pipeline()
                    passed, violations = pipeline.preflight_check(
                        tick_id=arguments["tick_id"],
                        energy_threshold=arguments.get("energy_threshold", 2.0),
                        rotation_threshold=arguments.get("rotation_threshold", np.pi / 4)
                    )
                    
                    result = {
                        "status": "PASS" if passed else "FAIL",
                        "tick_id": arguments["tick_id"],
                        "violations": violations
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"TickFrame Error: {e}")], isError=True)

            elif name == "tickframe_get_latest":
                try:
                    from services.neural_system.tickframe_pipeline import get_pipeline
                    
                    pipeline = get_pipeline()
                    if not pipeline.history:
                        return CallToolResult(content=[TextContent(type="text", text='{"status": "no_frames", "message": "No TickFrames ingested yet"}')])
                    
                    frame = pipeline.history[-1]
                    result = {
                        "tick_id": frame.tick_id,
                        "timestamp": frame.timestamp,
                        "energy": {
                            "E_rot": frame.energy.E_rot,
                            "E_hopfield": frame.energy.E_hopfield,
                            "E_jepa": frame.energy.E_jepa,
                            "E_curvature": frame.energy.E_curvature,
                            "E_total": frame.energy.E_total
                        },
                        "quaternion": frame.quaternion.tolist(),
                        "omega_norm": float(np.linalg.norm(frame.omega)),
                        "hdc_state_norm": float(np.linalg.norm(frame.hdc_state))
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"TickFrame Error: {e}")], isError=True)

            elif name == "tickframe_add_attractor":
                try:
                    from services.neural_system.tickframe_pipeline import get_pipeline
                    
                    pipeline = get_pipeline()
                    pipeline.add_attractor(
                        name=arguments["name"],
                        text=arguments["text"]
                    )
                    
                    result = {
                        "status": "added",
                        "attractor_name": arguments["name"],
                        "total_attractors": len(pipeline.basin_attractors)
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"TickFrame Error: {e}")], isError=True)

            # Koopman Operator Tools
            elif name == "koopman_fit":
                try:
                    from services.neural_system.koopman_operator import get_koopman, get_pipeline
                    
                    koopman = get_koopman(
                        lift_type=arguments.get("lift_type", "rbf"),
                        n_components=arguments.get("n_components", 50)
                    )
                    pipeline = get_pipeline()
                    
                    max_frames = arguments.get("max_frames", 100)
                    states = [f.hdc_state for f in pipeline.history[-max_frames:]]
                    
                    if len(states) < 3:
                        return CallToolResult(content=[TextContent(type="text", text='{"status": "insufficient_data", "message": "Need at least 3 frames to fit Koopman operator"}')])
                    
                    koopman.fit(states)
                    
                    result = {
                        "status": "fitted",
                        "n_samples": len(states),
                        "lift_type": koopman.lift_type,
                        "lifted_dim": koopman.n_components,
                        "is_fitted": koopman.is_fitted
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Koopman Error: {e}")], isError=True)

            elif name == "koopman_predict":
                try:
                    from services.neural_system.koopman_operator import get_koopman, get_pipeline
                    
                    koopman = get_koopman()
                    
                    if not koopman.is_fitted:
                        return CallToolResult(content=[TextContent(type="text", text='{"status": "not_fitted", "message": "Koopman operator not fitted yet. Call koopman_fit first."}')])
                    
                    if "current_state" in arguments:
                        state = np.array(arguments["current_state"])
                    else:
                        pipeline = get_pipeline()
                        if not pipeline.history:
                            return CallToolResult(content=[TextContent(type="text", text='{"status": "no_state", "message": "No current state available"}')])
                        state = pipeline.history[-1].hdc_state
                    
                    horizon = arguments.get("steps", 1)  # MCP uses "steps", internal uses "horizon"
                    predicted = koopman.predict(state, horizon=horizon)
                    
                    result = {
                        "status": "predicted",
                        "steps": horizon,
                        "predicted_norm": float(np.linalg.norm(predicted)),
                        "predicted_sample": predicted[:10].tolist()  # First 10 dims for inspection
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Koopman Error: {e}")], isError=True)

            elif name == "koopman_residual":
                try:
                    from services.neural_system.koopman_operator import get_koopman
                    
                    koopman = get_koopman()
                    predicted = np.array(arguments["predicted"])
                    actual = np.array(arguments["actual"])
                    
                    residual = koopman.residual_energy(predicted, actual)
                    
                    result = {
                        "residual_energy": residual,
                        "l2_distance": float(np.linalg.norm(predicted - actual)),
                        "cosine_similarity": float(np.dot(predicted, actual) / (np.linalg.norm(predicted) * np.linalg.norm(actual) + 1e-10))
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Koopman Error: {e}")], isError=True)

            elif name == "koopman_eigenmodes":
                try:
                    from services.neural_system.koopman_operator import get_koopman
                    
                    koopman = get_koopman()
                    
                    if not koopman.is_fitted:
                        return CallToolResult(content=[TextContent(type="text", text='{"status": "not_fitted", "message": "Koopman operator not fitted yet"}')])
                    
                    top_k = arguments.get("top_k", 5)
                    modes = koopman.get_eigenmodes(top_k=top_k)
                    
                    result = {
                        "status": "analyzed",
                        "modes": [
                            {
                                "eigenvalue_magnitude": m.eigenvalue_magnitude,
                                "eigenvalue_phase": m.eigenvalue_phase,
                                "growth_rate": m.growth_rate,
                                "frequency": m.frequency,
                                "stability": m.stability
                            }
                            for m in modes
                        ]
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Koopman Error: {e}")], isError=True)

            # Conformal Prediction Tools
            elif name == "conformal_calibrate":
                try:
                    from services.neural_system.koopman_operator import get_conformal_predictor
                    
                    target_coverage = arguments.get("target_coverage", 0.95)
                    conformal = get_conformal_predictor(target_coverage=target_coverage)
                    
                    result = {
                        "status": "calibrated",
                        "target_coverage": conformal.target_coverage,
                        "current_threshold": conformal.threshold,
                        "n_residuals": len(conformal.residuals)
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Conformal Error: {e}")], isError=True)

            elif name == "conformal_gate":
                try:
                    from services.neural_system.koopman_operator import get_conformal_predictor
                    
                    conformal = get_conformal_predictor()
                    predicted = np.array(arguments["predicted"])
                    actual = np.array(arguments["actual"])
                    
                    passed, residual = conformal.gate_decision(predicted, actual)
                    
                    result = {
                        "decision": "PASS" if passed else "FAIL",
                        "residual": residual,
                        "threshold": conformal.threshold,
                        "margin": conformal.threshold - residual if passed else residual - conformal.threshold
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Conformal Error: {e}")], isError=True)

            elif name == "conformal_stats":
                try:
                    from services.neural_system.koopman_operator import get_conformal_predictor
                    
                    conformal = get_conformal_predictor()
                    
                    result = {
                        "target_coverage": conformal.target_coverage,
                        "current_threshold": conformal.threshold,
                        "n_calibration_residuals": len(conformal.residuals),
                        "residual_stats": {
                            "mean": float(np.mean(conformal.residuals)) if conformal.residuals else None,
                            "std": float(np.std(conformal.residuals)) if conformal.residuals else None,
                            "max": float(np.max(conformal.residuals)) if conformal.residuals else None
                        } if conformal.residuals else None
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Conformal Error: {e}")], isError=True)

            # =====================================================
            # HDC Memory System Tools (SDM, Infini, Long, Accumulator, Hopfield)
            # =====================================================
            
            elif name == "sdm_write":
                try:
                    from services.neural_system.sdm_memory import SDMMemory
                    
                    # Lazy singleton
                    if not hasattr(self, '_sdm_memory'):
                        self._sdm_memory = SDMMemory()
                    
                    address = np.array(arguments["address"], dtype=np.float32)
                    data = np.array(arguments["data"], dtype=np.float32)
                    as_attractor = arguments.get("as_attractor", True)
                    
                    if as_attractor:
                        result = self._sdm_memory.store_attractor(data)
                    else:
                        result = self._sdm_memory.write(address, data)
                    
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"SDM Error: {e}")], isError=True)

            elif name == "sdm_read":
                try:
                    from services.neural_system.sdm_memory import SDMMemory
                    
                    if not hasattr(self, '_sdm_memory'):
                        self._sdm_memory = SDMMemory()
                    
                    address = np.array(arguments["address"], dtype=np.float32)
                    data, confidence = self._sdm_memory.read(address, return_confidence=True)
                    
                    result = {
                        "data_sample": data[:20].tolist(),  # First 20 dims
                        "confidence": confidence,
                        "data_norm": float(np.linalg.norm(data))
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"SDM Error: {e}")], isError=True)

            elif name == "sdm_cleanup":
                try:
                    from services.neural_system.sdm_memory import SDMMemory
                    
                    if not hasattr(self, '_sdm_memory'):
                        self._sdm_memory = SDMMemory()
                    
                    pattern = np.array(arguments["pattern"], dtype=np.float32)
                    iterations = arguments.get("iterations", 3)
                    
                    cleaned = self._sdm_memory.cleanup(pattern, iterations=iterations)
                    
                    result = {
                        "cleaned_sample": cleaned[:20].tolist(),
                        "cleaned_norm": float(np.linalg.norm(cleaned)),
                        "iterations": iterations
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"SDM Error: {e}")], isError=True)

            elif name == "sdm_stats":
                try:
                    from services.neural_system.sdm_memory import SDMMemory
                    
                    if not hasattr(self, '_sdm_memory'):
                        self._sdm_memory = SDMMemory()
                    
                    stats = self._sdm_memory.get_stats()
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(stats, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"SDM Error: {e}")], isError=True)

            elif name == "infini_update":
                try:
                    from services.neural_system.hdc_infini_memory import HDCInfiniMemory
                    
                    if not hasattr(self, '_infini_memory'):
                        self._infini_memory = HDCInfiniMemory()
                    
                    content_hv = np.array(arguments["content_hv"], dtype=np.float32)
                    importance = arguments.get("importance", 1.0)
                    
                    result = self._infini_memory.update(content_hv, importance=importance)
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"InfiniMemory Error: {e}")], isError=True)

            elif name == "infini_query":
                try:
                    from services.neural_system.hdc_infini_memory import HDCInfiniMemory
                    
                    if not hasattr(self, '_infini_memory'):
                        self._infini_memory = HDCInfiniMemory()
                    
                    query_hv = np.array(arguments["query_hv"], dtype=np.float32)
                    similarity = self._infini_memory.query(query_hv)
                    
                    result = {
                        "similarity": similarity,
                        "memory_initialized": self._infini_memory.memory_initialized,
                        "position": self._infini_memory.position
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"InfiniMemory Error: {e}")], isError=True)

            elif name == "infini_retrieve_position":
                try:
                    from services.neural_system.hdc_infini_memory import HDCInfiniMemory
                    
                    if not hasattr(self, '_infini_memory'):
                        self._infini_memory = HDCInfiniMemory()
                    
                    position = arguments["position"]
                    retrieved = self._infini_memory.retrieve_at_position(position)
                    
                    result = {
                        "position": position,
                        "retrieved_sample": retrieved[:20].tolist(),
                        "retrieved_norm": float(np.linalg.norm(retrieved))
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"InfiniMemory Error: {e}")], isError=True)

            elif name == "infini_stats":
                try:
                    from services.neural_system.hdc_infini_memory import HDCInfiniMemory
                    
                    if not hasattr(self, '_infini_memory'):
                        self._infini_memory = HDCInfiniMemory()
                    
                    stats = self._infini_memory.get_stats()
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(stats, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"InfiniMemory Error: {e}")], isError=True)

            elif name == "longmem_store":
                try:
                    from services.neural_system.hdc_infini_memory import HDCLongMemory
                    
                    if not hasattr(self, '_long_memory'):
                        self._long_memory = HDCLongMemory()
                    
                    key_hv = np.array(arguments["key_hv"], dtype=np.float32)
                    value = arguments["value"]
                    
                    idx = self._long_memory.store(key_hv, value)
                    
                    result = {
                        "stored_index": idx,
                        "num_memories": self._long_memory.num_memories
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"LongMemory Error: {e}")], isError=True)

            elif name == "longmem_retrieve":
                try:
                    from services.neural_system.hdc_infini_memory import HDCLongMemory
                    
                    if not hasattr(self, '_long_memory'):
                        self._long_memory = HDCLongMemory()
                    
                    query_hv = np.array(arguments["query_hv"], dtype=np.float32)
                    top_k = arguments.get("top_k", 5)
                    recency_weight = arguments.get("recency_weight", 0.1)
                    
                    results = self._long_memory.retrieve(query_hv, top_k=top_k, recency_weight=recency_weight)
                    
                    result = {
                        "matches": [
                            {"value": v, "score": s} for v, s in results
                        ],
                        "num_results": len(results)
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2, default=str))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"LongMemory Error: {e}")], isError=True)

            elif name == "longmem_stats":
                try:
                    from services.neural_system.hdc_infini_memory import HDCLongMemory
                    
                    if not hasattr(self, '_long_memory'):
                        self._long_memory = HDCLongMemory()
                    
                    stats = self._long_memory.get_stats()
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(stats, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"LongMemory Error: {e}")], isError=True)

            elif name == "accumulator_add":
                try:
                    from services.neural_system.hdc_infini_memory import HolographicAccumulator
                    
                    if not hasattr(self, '_accumulator'):
                        self._accumulator = HolographicAccumulator()
                    
                    channel = arguments["channel"]
                    content_hv = np.array(arguments["content_hv"], dtype=np.float32)
                    importance = arguments.get("importance", 1.0)
                    
                    result = self._accumulator.accumulate(channel, content_hv, importance=importance)
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Accumulator Error: {e}")], isError=True)

            elif name == "accumulator_query":
                try:
                    from services.neural_system.hdc_infini_memory import HolographicAccumulator
                    
                    if not hasattr(self, '_accumulator'):
                        self._accumulator = HolographicAccumulator()
                    
                    query_hv = np.array(arguments["query_hv"], dtype=np.float32)
                    relevances = self._accumulator.query_all_channels(query_hv)
                    
                    result = {
                        "channel_relevances": relevances,
                        "max_channel": max(relevances, key=relevances.get) if relevances else None
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Accumulator Error: {e}")], isError=True)

            elif name == "accumulator_consolidate":
                try:
                    from services.neural_system.hdc_infini_memory import HolographicAccumulator
                    
                    if not hasattr(self, '_accumulator'):
                        self._accumulator = HolographicAccumulator()
                    
                    consolidated = self._accumulator.consolidate()
                    
                    result = {
                        "consolidated_sample": consolidated[:20].tolist(),
                        "consolidated_norm": float(np.linalg.norm(consolidated))
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Accumulator Error: {e}")], isError=True)

            elif name == "accumulator_stats":
                try:
                    from services.neural_system.hdc_infini_memory import HolographicAccumulator
                    
                    if not hasattr(self, '_accumulator'):
                        self._accumulator = HolographicAccumulator()
                    
                    stats = self._accumulator.get_stats()
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(stats, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Accumulator Error: {e}")], isError=True)

            elif name == "hopfield_store":
                try:
                    from services.neural_system.hopfield_memory import HDCHopfieldMemory
                    import torch
                    
                    if not hasattr(self, '_hopfield_memory'):
                        self._hopfield_memory = HDCHopfieldMemory()
                    
                    patterns = [np.array(p, dtype=np.float32) for p in arguments["patterns"]]
                    patterns_tensor = torch.tensor(np.array(patterns))
                    
                    self._hopfield_memory.store_patterns(patterns_tensor)
                    
                    result = {
                        "stored_patterns": len(patterns),
                        "pattern_dim": patterns[0].shape[0] if patterns else 0
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Hopfield Error: {e}")], isError=True)

            elif name == "hopfield_retrieve":
                try:
                    from services.neural_system.hopfield_memory import HDCHopfieldMemory
                    import torch
                    
                    if not hasattr(self, '_hopfield_memory'):
                        self._hopfield_memory = HDCHopfieldMemory()
                    
                    query = torch.tensor(arguments["query"], dtype=torch.float32)
                    iterations = arguments.get("iterations", 1)
                    
                    retrieved = self._hopfield_memory.retrieve(query, num_iterations=iterations)
                    
                    result = {
                        "retrieved_sample": retrieved.numpy()[:20].tolist(),
                        "retrieved_norm": float(torch.norm(retrieved).item())
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Hopfield Error: {e}")], isError=True)

            elif name == "hopfield_energy":
                try:
                    from services.neural_system.hopfield_memory import HDCHopfieldMemory
                    import torch
                    
                    if not hasattr(self, '_hopfield_memory'):
                        self._hopfield_memory = HDCHopfieldMemory()
                    
                    query = torch.tensor(arguments["query"], dtype=torch.float32)
                    energy = self._hopfield_memory.compute_energy(query)
                    
                    result = {
                        "energy": float(energy.item()),
                        "interpretation": "low energy = near attractor" if energy < 0.5 else "high energy = unstable region"
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Hopfield Error: {e}")], isError=True)

            # Memory Maintainer High-Level Tools (Agent Integration)
            elif name == "memory_sync_event":
                try:
                    from services.neural_system.memory_maintainer import MemoryMaintainer, MemoryEvent, AccumulatorChannel
                    
                    if not hasattr(self, '_memory_maintainer'):
                        self._memory_maintainer = MemoryMaintainer(mcp_call_tool=self._call_tool)
                    
                    # Build event
                    event = MemoryEvent(
                        event_type=arguments["event_type"],
                        content_hv=np.array(arguments["content_hv"], dtype=np.float32),
                        importance=arguments.get("importance", 1.0),
                        metadata=arguments.get("metadata", {})
                    )
                    
                    # Sync across systems
                    result = await self._memory_maintainer.sync_event(event)
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"MemoryMaintainer Error: {e}")], isError=True)

            elif name == "memory_retrieve":
                try:
                    from services.neural_system.memory_maintainer import MemoryMaintainer, RetrievalStrategy
                    
                    if not hasattr(self, '_memory_maintainer'):
                        self._memory_maintainer = MemoryMaintainer(mcp_call_tool=self._call_tool)
                    
                    # Parse strategy
                    strategy_map = {
                        "cascaded": RetrievalStrategy.CASCADED,
                        "parallel": RetrievalStrategy.PARALLEL,
                        "fastest": RetrievalStrategy.FASTEST,
                        "episodic": RetrievalStrategy.EPISODIC,
                        "compressive": RetrievalStrategy.COMPRESSIVE
                    }
                    strategy = strategy_map.get(arguments.get("strategy", "cascaded"), RetrievalStrategy.CASCADED)
                    
                    # Retrieve
                    query_hv = np.array(arguments["query_hv"], dtype=np.float32)
                    result = await self._memory_maintainer.retrieve(
                        query_hv=query_hv,
                        strategy=strategy,
                        top_k=arguments.get("top_k", 5),
                        recency_weight=arguments.get("recency_weight", 0.2)
                    )
                    
                    # Convert to dict for JSON
                    result_dict = {
                        "sources": result.sources,
                        "infini_relevance": result.infini_relevance,
                        "hopfield_energy": result.hopfield_energy,
                        "total_matches": result.total_matches,
                        "strategy_used": result.strategy_used,
                        "latency_ms": result.latency_ms
                    }
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result_dict, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"MemoryMaintainer Error: {e}")], isError=True)

            elif name == "memory_consolidate":
                try:
                    from services.neural_system.memory_maintainer import MemoryMaintainer
                    
                    if not hasattr(self, '_memory_maintainer'):
                        self._memory_maintainer = MemoryMaintainer(mcp_call_tool=self._call_tool)
                    
                    result = await self._memory_maintainer.run_consolidation()
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"MemoryMaintainer Error: {e}")], isError=True)

            elif name == "memory_health":
                try:
                    from services.neural_system.memory_maintainer import MemoryMaintainer
                    
                    if not hasattr(self, '_memory_maintainer'):
                        self._memory_maintainer = MemoryMaintainer(mcp_call_tool=self._call_tool)
                    
                    result = await self._memory_maintainer.health_check()
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
                    
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"MemoryMaintainer Error: {e}")], isError=True)
            
            # Episodic Memory System Tools
            elif name == "add_conversation_turn":
                # 1. Call standard memory (Episodic)
                result = await self.memory_system.add_conversation_turn(
                    session_id=arguments["session_id"],
                    user_id=arguments["user_id"],
                    user_message=arguments["user_message"],
                    assistant_response=arguments["assistant_response"],
                    metadata=arguments.get("metadata")
                )
                
                # 2. AUTO-ENCODE into Holographic Memory (Persistence & Logic)
                if self.holographic_service:
                    session_id = arguments["session_id"]
                    memory = self.holographic_service.get_session(session_id)
                    # Encode User
                    memory.add_turn("User", arguments["user_message"])
                    # Encode Assistant
                    memory.add_turn("Assistant", arguments["assistant_response"])
                    logger.info(f"Auto-encoded turn for session {session_id} into Holographic Memory")
                
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result))])
            
            elif name == "add_document":
                result = await self.memory_system.add_document(
                    content=arguments["content"],
                    source=arguments["source"],
                    document_type=arguments.get("document_type")
                )
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result))])
            
            elif name == "get_context":
                result = await self.memory_system.get_context(
                    session_id=arguments["session_id"],
                    query=arguments["query"],
                    user_id=arguments.get("user_id")
                )
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, default=str))])
            
            elif name == "record_trajectory":
                result = await self.memory_system.record_trajectory(
                    agent_id=arguments["agent_id"],
                    task_input=arguments["task_input"],
                    task_type=arguments["task_type"],
                    actions_taken=arguments["actions_taken"],
                    context_used=arguments["context_used"],
                    outcome=arguments["outcome"],
                    execution_time=arguments["execution_time"]
                )
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, default=str))])
            
            elif name == "get_learning_context":
                result = await self.memory_system.get_learning_context(
                    agent_id=arguments["agent_id"],
                    task_context=arguments["task_context"]
                )
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, default=str))])
            
            elif name == "get_strategies":
                result = await self.memory_system.get_strategies(
                    task_type=arguments["task_type"],
                    limit=arguments.get("limit", 5)
                )
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, default=str))])
                
            elif name == "compress_text":
                raw_text = arguments["raw_text"]
                focus_point = arguments["focus_point"]
                result = await self.compressor.compress_text(raw_text, focus_point)
                return CallToolResult(content=[TextContent(type="text", text=result)])

            elif name == "compress_codebase":
                repo_path = arguments["repo_path"]
                focus_area = arguments["focus_area"]
                result = await self.compressor.compress_codebase(repo_path, focus_area)
                return CallToolResult(content=[TextContent(type="text", text=result)])

            # --- SERENA CODE INSPECTION TOOLS ---
            elif name == "serena_analyze_code":
                try:
                    code = arguments["code"]
                    context = arguments.get("context", "")
                    # Use SerenaAgent for code analysis
                    if hasattr(self, 'serena_agent') and self.serena_agent:
                        result_str = await self.serena_agent.execute_tool("serena_analyze_code", {"code": code, "context": context}, headers=headers)
                        result = {"analysis": result_str, "status": "success"}
                    else:
                        # Fallback: return message that Serena is not available
                        result = {"analysis": "Serena Agent integration not available", "status": "unavailable"}
                    
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result))])
                except Exception as e:
                    return CallToolResult(content=[TextContent(type="text", text=f"Error in serena_analyze_code: {str(e)}")], isError=True)

            elif name == "discover_infrastructure":
                if mcp_infra_discovery and hasattr(mcp_infra_discovery, 'infra_discovery'):
                    compose_path = arguments.get("compose_path", "/app/../docker-compose.local.yml")
                    env_path = arguments.get("env_path")
                    try:
                        summary = mcp_infra_discovery.infra_discovery.discover_from_compose(compose_path, env_path)
                        return CallToolResult(content=[TextContent(type="text", text=json.dumps(summary, indent=2))])
                    except Exception as e:
                        return CallToolResult(content=[TextContent(type="text", text=f"Infrastructure discovery failed: {e}")], isError=True)
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Infrastructure Discovery tool not initialized")], isError=True)

            elif name == "query_infrastructure":
                if mcp_infra_discovery and hasattr(mcp_infra_discovery, 'infra_discovery'):
                    query = arguments["query"]
                    try:
                        results = mcp_infra_discovery.infra_discovery.query_infrastructure(query)
                        return CallToolResult(content=[TextContent(type="text", text=json.dumps(results, indent=2))])
                    except Exception as e:
                        return CallToolResult(content=[TextContent(type="text", text=f"Infrastructure query failed: {e}")], isError=True)
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Infrastructure Discovery tool not initialized")], isError=True)

            elif name == "discover_logic":
                if mcp_skill_discovery and hasattr(mcp_skill_discovery, 'logic_discovery'):
                    tools_dir = arguments.get("tools_dir", "/app/tools")
                    try:
                        summary = mcp_skill_discovery.logic_discovery.discover_tools(tools_dir)
                        return CallToolResult(content=[TextContent(type="text", text=json.dumps(summary, indent=2))])
                    except Exception as e:
                        return CallToolResult(content=[TextContent(type="text", text=f"Logic discovery failed: {e}")], isError=True)
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Logic Discovery tool not initialized")], isError=True)

            elif name == "query_logic":
                if mcp_skill_discovery and hasattr(mcp_skill_discovery, 'logic_discovery'):
                    query = arguments["query"]
                    try:
                        results = mcp_skill_discovery.logic_discovery.query_logic_graph(query)
                        return CallToolResult(content=[TextContent(type="text", text=json.dumps(results, indent=2))])
                    except Exception as e:
                        return CallToolResult(content=[TextContent(type="text", text=f"Logic query failed: {e}")], isError=True)
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Logic Discovery tool not initialized")], isError=True)

            elif name == "discover_agents":
                if mcp_skill_discovery and hasattr(mcp_skill_discovery, 'logic_discovery'):
                    agents_dir = arguments.get("agents_dir", "/app/../agent_service")
                    try:
                        summary = mcp_skill_discovery.logic_discovery.discover_agents(agents_dir)
                        return CallToolResult(content=[TextContent(type="text", text=json.dumps(summary, indent=2))])
                    except Exception as e:
                        return CallToolResult(content=[TextContent(type="text", text=f"Agent discovery failed: {e}")], isError=True)
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Logic Discovery tool not initialized")], isError=True)

            elif name == "generate_mermaid":
                if mcp_graph_visualizer and hasattr(mcp_graph_visualizer, 'graph_visualizer'):
                    focus = arguments["focus"]
                    graph_type = arguments.get("graph_type", "infrastructure")
                    try:
                        mermaid_text = mcp_graph_visualizer.graph_visualizer.generate_mermaid(focus, graph_type)
                        return CallToolResult(content=[TextContent(type="text", text=mermaid_text)])
                    except Exception as e:
                        return CallToolResult(content=[TextContent(type="text", text=f"Mermaid generation failed: {e}")], isError=True)
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Graph Visualizer not initialized")], isError=True)

            elif name == "crawl_codebase":
                if mcp_code_crawler and hasattr(mcp_code_crawler, 'code_crawler'):
                    start_dir = arguments.get("start_dir", "/app")
                    try:
                        summary = mcp_code_crawler.code_crawler.crawl_codebase(start_dir)
                        return CallToolResult(content=[TextContent(type="text", text=json.dumps(summary, indent=2))])
                    except Exception as e:
                        return CallToolResult(content=[TextContent(type="text", text=f"Code crawl failed: {e}")], isError=True)
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Code Crawler not initialized")], isError=True)

            elif name == "embed_graph":
                if mcp_vector_layer and hasattr(mcp_vector_layer, 'vector_layer'):
                    node_types = arguments.get("node_types")
                    try:
                        summary = mcp_vector_layer.vector_layer.embed_graph_nodes(node_types)
                        return CallToolResult(content=[TextContent(type="text", text=json.dumps(summary, indent=2))])
                    except Exception as e:
                        return CallToolResult(content=[TextContent(type="text", text=f"Graph embedding failed: {e}")], isError=True)
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Vector Layer not initialized")], isError=True)

            elif name == "semantic_graph_search":
                if mcp_vector_layer and hasattr(mcp_vector_layer, 'vector_layer'):
                    query = arguments["query"]
                    node_types = arguments.get("node_types")
                    limit = arguments.get("limit", 5)
                    use_hse = arguments.get("use_hse", False)
                    try:
                        results = mcp_vector_layer.vector_layer.semantic_search(query, node_types, limit, use_hse)
                        return CallToolResult(content=[TextContent(type="text", text=json.dumps(results, indent=2))])
                    except Exception as e:
                        return CallToolResult(content=[TextContent(type="text", text=f"Semantic search failed: {e}")], isError=True)
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Vector Layer not initialized")], isError=True)

            elif name == "forge_new_skill":
                logger.info(f"DEBUG_DISPATCH: Received forge_new_skill request. args={arguments}")
                if mcp_skill_forge:
                    filename = arguments["filename"]
                    code_content = arguments.get("code_content") or arguments.get("content")
                    dependencies = arguments.get("dependencies", [])
                    logger.info(f"DEBUG_DISPATCH: Calling module with filename={filename}")
                    result = mcp_skill_forge.forge_new_skill(filename, code_content, dependencies)
                    logger.info(f"DEBUG_DISPATCH: Result={result}")
                    return CallToolResult(content=[TextContent(type="text", text=result)])
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: mcp_skill_forge module not available")], isError=True)

            elif name == "store_memory":
                if mcp_semantic_search and hasattr(mcp_semantic_search, 'semantic_search_tool'):
                    content = arguments["content"]
                    metadata = arguments.get("metadata", {})
                    res_id = mcp_semantic_search.semantic_search_tool.store_memory(content, metadata, headers=headers)
                    return CallToolResult(content=[TextContent(type="text", text=f"Stored memory ID: {res_id}")])
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Semantic Search tool not initialized")], isError=True)

            elif name == "search_memory":
                if mcp_semantic_search and hasattr(mcp_semantic_search, 'semantic_search_tool'):
                    query = arguments["query"]
                    limit = arguments.get("limit", 5)
                    threshold = arguments.get("threshold", 0.5)
                    results = mcp_semantic_search.semantic_search_tool.search_memories(query, limit, threshold, headers=headers)
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(results, indent=2))])
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Semantic Search tool not initialized")], isError=True)

            elif name == "arca_system_query":
                if mcp_arca_intelligence and hasattr(mcp_arca_intelligence, 'arca_system_query'):
                    query_type = arguments.get("query_type", "full")
                    context = arguments.get("context")
                    result = mcp_arca_intelligence.arca_system_query(query_type, context)
                    return CallToolResult(content=[TextContent(type="text", text=result)])
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: ARCA Intelligence tool not initialized")], isError=True)

            elif name == "arca_feasibility_check":
                if mcp_arca_intelligence and hasattr(mcp_arca_intelligence, 'arca_feasibility_check'):
                    task_description = arguments["task_description"]
                    result = mcp_arca_intelligence.arca_feasibility_check(task_description)
                    return CallToolResult(content=[TextContent(type="text", text=result)])
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: ARCA Intelligence tool not initialized")], isError=True)

            elif name == "run_graph_linking":
                if mcp_graph_linker and hasattr(mcp_graph_linker, 'run_graph_linking'):
                    try:
                        result = mcp_graph_linker.run_graph_linking()
                        return CallToolResult(content=[TextContent(type="text", text=result)])
                    except Exception as e:
                        return CallToolResult(content=[TextContent(type="text", text=f"Graph linking failed: {e}")], isError=True)
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Graph Linker tool not initialized")], isError=True)

            elif name == "scan_workflows":
                if mcp_workflow_scanner and hasattr(mcp_workflow_scanner, 'scan_workflows'):
                    try:
                        result = mcp_workflow_scanner.scan_workflows()
                        return CallToolResult(content=[TextContent(type="text", text=result)])
                    except Exception as e:
                        return CallToolResult(content=[TextContent(type="text", text=f"Workflow scan failed: {e}")], isError=True)
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Workflow Scanner tool not initialized")], isError=True)

            elif name == "assimilate_concepts":
                if run_granular_assimilation:
                    # Handle both file_path (simple) and documents (advanced) interfaces
                    file_path = arguments.get("file_path")
                    documents = arguments.get("documents", [])
                    current_atoms = arguments.get("current_state_atoms", [])
                    
                    # If file_path provided, load and convert to documents format
                    if file_path and not documents:
                        try:
                            # Find the file
                            import os
                            from pathlib import Path
                            
                            # Clean the filename - strip common action verbs
                            clean_path = file_path
                            for action_verb in ["Ingest ", "Load ", "Read ", "Analyze ", "Process "]:
                                if clean_path.startswith(action_verb):
                                    clean_path = clean_path[len(action_verb):]
                            
                            # Search common locations
                            search_paths = [
                                f"/home/arca/source/documentation/{clean_path}",
                                f"/shared_storage/{clean_path}",
                                f"/app/shared_storage/{clean_path}",
                                f"/app/{clean_path}",
                                clean_path  # Try as absolute path
                            ]
                            
                            file_content = None
                            actual_path = None
                            for path in search_paths:
                                if os.path.exists(path):
                                    with open(path, 'r', encoding='utf-8') as f:
                                        file_content = f.read()
                                    actual_path = path
                                    break
                            
                            if not file_content:
                                return CallToolResult(content=[TextContent(type="text", text=f"File not found: {file_path}")], isError=True)
                            
                            # Convert to documents format
                            documents = [{
                                "name": os.path.basename(actual_path),
                                "text": file_content
                            }]
                            logger.info(f"Loaded file {actual_path} for assimilation")
                        except Exception as e:
                            logger.error(f"Failed to load file {file_path}: {e}")
                            return CallToolResult(content=[TextContent(type="text", text=f"File load error: {str(e)}")], isError=True)
                    
                    if not documents:
                        return CallToolResult(content=[TextContent(type="text", text="Error: No documents provided")], isError=True)
                    
                    try:
                        # Need to get Redis URL from env or default
                        redis_url = os.environ.get("REDIS_URL", "redis://redis:6379")
                        logger.info(f"Starting Concept Assimilation for {len(documents)} documents")
                        
                        # PROTECTIVE MEASURE: Limit documents to prevent timeouts
                        if len(documents) > 10:
                            logger.warning(f"Too many documents ({len(documents)}) for single assimilation pass. Taking top 10.")
                            # Sort by size (smallest first to maximize concept count?) or just take first 10
                            # Let's take first 10 for deterministic behavior
                            documents = documents[:10]
                        
                        result_doc = run_granular_assimilation(documents, current_atoms, redis_url)
                        
                        # Ensure result is a string
                        if not isinstance(result_doc, str):
                            result_doc = str(result_doc)
                            
                        return CallToolResult(content=[TextContent(type="text", text=result_doc)])
                    except Exception as e:
                        import traceback
                        error_trace = traceback.format_exc()
                        logger.error(f"Assimilation Failed: {e}\nFull traceback:\n{error_trace}")
                        return CallToolResult(content=[TextContent(type="text", text=f"Assimilation Error: {str(e)}\n\nTraceback:\n{error_trace}")], isError=True)
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Concept Assimilation module not loaded")], isError=True)

            elif name == "geometry_context_update":
                if self.attention_engine:
                    user_input = arguments.get("user_input")
                    focus_id = arguments.get("focus_structure_id")
                    result = self.attention_engine.update_context_bubbles(user_input, focus_id)
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result))])
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: Attention Engine not initialized")], isError=True)

            elif name == "serena_refactor_suggestion":
                try:
                    code = arguments["code"]
                    goal = arguments["goal"]
                    if hasattr(self, 'serena_agent') and self.serena_agent:
                        result_str = await self.serena_agent.execute_tool("serena_refactor_suggestion", {"code": code, "goal": goal}, headers=headers)
                        result = {"suggestion": result_str, "status": "success"}
                    else:
                        result = {"error": "Serena agent not initialized. Please check configuration.", "status": "failed"}
                except Exception as e:
                    logger.error(f"serena_refactor_suggestion failed: {e}")
                    return CallToolResult(content=[TextContent(type="text", text=json.dumps({"error": str(e), "status": "failed"}))], isError=True)
                
            elif name == "review_code":
                code_str = arguments["code_str"]
                criteria_list = arguments["criteria_list"]
                result = await self.reviewer.review_code(code_str, criteria_list)
                return CallToolResult(content=[TextContent(type="text", text=result)])

            elif name == "request_human_feedback":
                question = arguments["question"]
                # Since mcp_human_feedback uses FastMCP decorator, we can call the function directly if we had access to it,
                # but here we are using the mcp object. FastMCP object doesn't expose the function directly in a simple way 
                # without running the server.
                # However, looking at how other tools are implemented (e.g. compressor), they seem to be classes.
                # mcp_human_feedback is a FastMCP instance.
                # I should probably have implemented it as a class or just imported the function.
                # Let's check mcp_human_feedback.py again.
                # It defines `request_human_feedback` decorated with @mcp.tool().
                # I can import the function directly from the module if I want to call it here.
                # But I imported `mcp_human_feedback` module.
                # So I can call `mcp_human_feedback.request_human_feedback(question)`.
                result = mcp_human_feedback.request_human_feedback(question)
                return CallToolResult(content=[TextContent(type="text", text=result)])

            # Check if it's a Serena tool
            elif name == "get_universal_context":
                if USF_AVAILABLE:
                    result_str = get_universal_context(arguments["subject"], arguments.get("radius", 4))
                    return CallToolResult(content=[TextContent(type="text", text=result_str)])
                else:
                    raise Exception("Universal Context tool not available")

            elif self.serena_agent and any(t.name == name for t in self.serena_tools):
                result = await self.serena_agent.execute_tool(name, arguments, headers=headers)
                return CallToolResult(content=[TextContent(type="text", text=str(result))])
                result = {"status": "recorded", "skill": skill_name}
                
            elif name == "query_gordon_ai":
                prompt = arguments.get("prompt") or arguments.get("message")
                if not prompt:
                    raise ValueError("Both 'prompt' and 'message' arguments are missing.")
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
                repo_path = arguments.get("repo_path")
                # Resolve path if not provided
                if not repo_path:
                    repo_path = os.getenv("ARCA_ROOT", "/home/ubuntu/ARCA")
                    
                # Check if we have the thinking agent tool available
                if hasattr(mcp_git_ops, 'git_maintainer_operation'):
                    logger.info(f"Delegating git operation '{operation}' to Thinking Agent (mcp_git_ops)")
                    # The @mcp.tool decorator might wrap the function, or we call it directly.
                    # FastMCP tools are usually callable.
                    message = arguments.get("message")
                    result = mcp_git_ops.git_maintainer_operation(operation, repo_path=repo_path, message=message, headers=headers)
                    
                    # Ensure result is JSON compatible string or dict for CallToolResult
                    if isinstance(result, str):
                        # The tool returns a string log. Wrap it for the user.
                        # If it's pure text, we just return it.
                        pass
                    
                    return CallToolResult(content=[TextContent(type="text", text=str(result))])
                else:
                    # Fallback to old dispatch if module missing (unlikely)
                    result = await self._execute_git_operation(
                        operation=operation,
                        repo_path=repo_path,
                        **{k: v for k, v in arguments.items() if k not in ["operation", "repo_path"]}
                    )
            
            elif name == "docker_container_file_read":
                container_name = arguments["container_name"]
                file_path = arguments["file_path"]
                result = await self._read_file_from_container(container_name, file_path)
            
            elif name == "dispatch_agent":
                 try:
                     import tools.mcp_agent_dispatch as agent_dispatch
                     result = agent_dispatch.dispatch_agent(headers=headers, **arguments)
                     return CallToolResult(content=[TextContent(type="text", text=str(result))])
                 except Exception as e:
                     return CallToolResult(content=[TextContent(type="text", text=f"Dispatch Error: {e}")])

            elif name == "docker_execution_primitive":
                # Direct primitive handling
                if mcp_docker_ops is not None:
                     result = mcp_docker_ops.docker_execution_primitive(**arguments)
                     return CallToolResult(content=[TextContent(type="text", text=str(result))])
                else: 
                     return CallToolResult(content=[TextContent(type="text", text="Error: mcp_docker_ops not loaded")])

            elif name == "file_maintainer_operation":
                operation = arguments["operation"]
                if hasattr(mcp_file_ops, 'file_maintainer_operation'):
                    logger.info(f"Delegating file operation '{operation}' to Thinking Agent")
                    # Add mandatory firewall headers for internal dispatches, merging with incoming
                    internal_headers = {
                        "X-Genesis-Chain": "true",
                        "X-Genesis-Agent": "mcp_server",
                        "X-Genesis-Source": "internal_tool_delegation"
                    }
                    if headers:
                        # Merged headers: incoming headers take precedence for specific context, 
                        # but internal ones ensure minimum security requirements.
                        internal_headers.update({k: v for k, v in headers.items() if k.lower().startswith("x-genesis-")})
                        
                    result = mcp_file_ops.file_maintainer_operation(headers=internal_headers, **arguments)
                    return CallToolResult(content=[TextContent(type="text", text=str(result))])
                else:
                    return CallToolResult(content=[TextContent(type="text", text="Error: File Ops Agent not loaded.")], isError=True)

            elif name == "security_scan":
                operation = arguments["operation"]
                if hasattr(mcp_security_ops, 'security_scan'):
                    logger.info(f"Delegating security scan '{operation}' to Thinking Agent")
                    result = mcp_security_ops.security_scan(headers=headers, **arguments)
                    return CallToolResult(content=[TextContent(type="text", text=str(result))])
                else:
                     # Fallback to old or error
                     return CallToolResult(content=[TextContent(type="text", text="Error: Security Agent not loaded.")], isError=True)
            
            elif name == "web_search":
                query = arguments["query"]
                count = arguments.get("count", 10)
                freshness = arguments.get("freshness", "noLimit")
                summary = arguments.get("summary", True)
                result = self.langsearch_client.web_search(query, count, freshness, summary)
                
            elif name == "semantic_rerank":
                query = arguments["query"]
                documents = arguments["documents"]
                top_n = arguments.get("top_n")
                result = self.langsearch_client.semantic_rerank(query, documents, top_n)

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
            
            elif name == "analyze_failure_insight":
                content = arguments["content"]
                source_agent = arguments["source_agent"]
                failure_reason = arguments["failure_reason"]
                context_id = arguments.get("context_id")
                result = await self.insight_synthesis.analyze_failure(content, source_agent, failure_reason, context_id)

            # Genesis Chain Management Tools (Quota Protected)
            elif name == "genesis_submit":
                genesis_prompt = arguments["genesis_prompt"]
                user_authorized = arguments.get("user_authorized", False)
                session_id = arguments.get("session_id")
                priority = arguments.get("priority", "normal")
                
                try:
                    from tools.mcp_genesis_chain import genesis_submit
                    result = genesis_submit(genesis_prompt, user_authorized, session_id, priority)
                except ImportError:
                    result = {"error": "Genesis Chain tools not available", "status": "error"}
                except Exception as e:
                    result = {"error": str(e), "status": "error"}
            
            elif name == "genesis_monitor":
                job_id = arguments.get("job_id")
                max_age_hours = arguments.get("max_age_hours", 24)
                
                try:
                    from tools.mcp_genesis_chain import genesis_monitor
                    result = genesis_monitor(job_id, max_age_hours)
                except ImportError:
                    result = {"error": "Genesis Chain tools not available", "status": "error"}
                except Exception as e:
                    result = {"error": str(e), "status": "error"}
            
            elif name == "genesis_output":
                job_id = arguments["job_id"]
                output_type = arguments.get("output_type", "all")
                
                try:
                    from tools.mcp_genesis_chain import genesis_output
                    result = genesis_output(job_id, output_type)
                except ImportError:
                    result = {"error": "Genesis Chain tools not available", "status": "error"}
                except Exception as e:
                    result = {"error": str(e), "status": "error"}
            
            elif name == "genesis_quota":
                try:
                    from tools.mcp_genesis_chain import genesis_quota
                    result = genesis_quota()
                except ImportError:
                    result = {"error": "Genesis Chain tools not available", "status": "error"}
                except Exception as e:
                    result = {"error": str(e), "status": "error"}
            
            elif name == "genesis_diagnose":
                job_id = arguments["job_id"]
                
                try:
                    from tools.mcp_genesis_chain import genesis_diagnose
                    result = genesis_diagnose(job_id)
                except ImportError:
                    result = {"error": "Genesis Chain tools not available", "status": "error"}
                except Exception as e:
                    result = {"error": str(e), "status": "error"}
            
            elif name == "genesis_restart":
                try:
                    from tools.mcp_genesis_chain import genesis_restart
                    result = genesis_restart()
                except ImportError:
                    result = {"error": "Genesis Chain tools not available", "status": "error"}
                except Exception as e:
                    result = {"error": str(e), "status": "error"}

            # Proxy Tools (Mesh Routing)
            elif name == "service_request" and service_proxy:
                result = await service_proxy.service_request(**arguments)
            elif name == "gateway_request" and service_proxy:
                result = await service_proxy.gateway_request(**arguments)
            elif name == "redis_command" and service_proxy:
                result = await service_proxy.redis_command(**arguments)
            elif name == "embedding_request" and service_proxy:
                result = await service_proxy.embedding_request(**arguments)

            else:
                raise ValueError(f"Unknown tool: {name}")
            
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2))])
            
        except Exception as e:
            import traceback
            logger.error(f"Tool call error: {e}\n{traceback.format_exc()}")
            return CallToolResult(
                content=[TextContent(type="text", text=f"Error: {str(e)}\nTraceback: {traceback.format_exc()}")],
                isError=True
            )

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
                contents=[{
                    "uri": f"file:///{uri.replace('://', '/')}",
                    "mimeType": "application/json",
                    "text": content
                }]
            )
            
        except Exception as e:
            logger.error(f"Resource read error: {e}")
            return ReadResourceResult(
                contents=[{
                    "uri": uri,
                    "mimeType": "text/plain",
                    "text": f"Error: {str(e)}"
                }]
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
    
    async def _execute_git_operation(self, operation: str, repo_path: str = None, **kwargs) -> Dict[str, Any]:
        """Execute git operations via docker_helper service which has host filesystem access.
        
        Git operations are routed through docker_helper because:
        1. MCP server runs in a container without host filesystem access
        2. docker_helper runs with host access and can execute git commands
        3. This maintains security by keeping git credentials on the host
        """
        import httpx
        
        # Resolve repo path: prefer Argument -> Env Var -> Default
        if not repo_path:
            # Important: Default to ARCA_ROOT from env if available (set in docker-compose)
            repo_path = os.getenv("ARCA_ROOT", os.getcwd())
            
        # docker_helper service URL (Port 9091 based on docker-compose)
        docker_helper_url = os.getenv("DOCKER_HELPER_URL", "http://docker_helper:9091")
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Build request payload
                payload = {
                    "operation": operation,
                    "repo_path": repo_path
                }
                
                # Add operation-specific params
                if operation == "add":
                    payload["files"] = kwargs.get("files", ["."])
                elif operation == "commit":
                    payload["message"] = kwargs.get("message", "Auto-commit via ARCA MCP")
                elif operation in ["push", "pull"]:
                    payload["remote"] = kwargs.get("remote", "origin")
                    payload["branch"] = kwargs.get("branch", "main")
                    if kwargs.get("force"):
                        payload["force"] = True
                elif operation == "branch":
                    if kwargs.get("branch"):
                        payload["branch"] = kwargs["branch"]
                elif operation == "checkout":
                    payload["branch"] = kwargs.get("branch", "main")
                elif operation == "diff":
                    if kwargs.get("files"):
                        payload["files"] = kwargs["files"]
                
                response = await client.post(f"{docker_helper_url}/git", json=payload)
                
                if response.status_code == 200:
                    result = response.json()
                    return {
                        "operation": operation,
                        "output": result.get("output", ""),
                        "exit_code": result.get("exit_code", 0),
                        "success": result.get("success", True),
                        "error": result.get("error")
                    }
                else:
                    return {
                        "error": f"docker_helper returned {response.status_code}: {response.text}",
                        "operation": operation,
                        "success": False
                    }
                    
        except httpx.ConnectError:
            return {
                "error": "Cannot connect to docker_helper service. Is it running?",
                "operation": operation,
                "success": False
            }
        except Exception as e:
            return {
                "error": f"Git operation failed: {str(e)}", 
                "operation": operation,
                "success": False
            }
    
    async def _execute_docker_operation(self, operation: str, **kwargs) -> Dict[str, Any]:
        """Execute comprehensive Docker operations for container management.
        
        For read operations (ps, logs, inspect, images, system_df), this uses the
        docker_helper service which has direct Docker socket access.
        For write operations, it falls back to subprocess if Docker CLI is available.
        """
        import subprocess
        import os
        import httpx
        
        # docker_helper service URL (accessible via Docker network)
        docker_helper_url = os.getenv("DOCKER_HELPER_URL", "http://docker_helper:8082")
        
        try:
            # Read operations - use docker_helper service
            if operation == "ps":
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(f"{docker_helper_url}/containers", params={"all": "true"})
                    if response.status_code == 200:
                        containers = response.json()
                        # Format output similar to docker ps
                        lines = []
                        for c in containers:
                            name = c.get("Names", ["/unknown"])[0].lstrip("/")
                            image = c.get("Image", "unknown")
                            status = c.get("Status", "unknown")
                            state = c.get("State", "unknown")
                            lines.append(f"{name}: {image} ({state}) - {status}")
                        return {
                            "operation": operation,
                            "stdout": "\n".join(lines) if lines else "No containers found",
                            "containers": containers,
                            "success": True
                        }
                    else:
                        return {"error": f"docker_helper returned {response.status_code}", "operation": operation}
            
            elif operation == "logs":
                service_name = kwargs.get("service_name", "")
                tail = kwargs.get("tail", "50")
                if not service_name:
                    return {"error": "service_name required for logs operation", "operation": operation}
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(f"{docker_helper_url}/containers/{service_name}/logs", params={"tail": tail})
                    if response.status_code == 200:
                        return {
                            "operation": operation,
                            "stdout": response.text,
                            "success": True
                        }
                    else:
                        return {"error": f"docker_helper returned {response.status_code}: {response.text}", "operation": operation}
            
            elif operation == "inspect":
                service_name = kwargs.get("service_name", "")
                if not service_name:
                    return {"error": "service_name required for inspect operation", "operation": operation}
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(f"{docker_helper_url}/containers/{service_name}/stats")
                    if response.status_code == 200:
                        return {
                            "operation": operation,
                            "stdout": json.dumps(response.json(), indent=2),
                            "stats": response.json(),
                            "success": True
                        }
                    else:
                        return {"error": f"docker_helper returned {response.status_code}", "operation": operation}
            
            elif operation == "images":
                # images operation not yet in docker_helper, return helpful message
                return {
                    "operation": operation,
                    "stdout": "images operation requires docker_helper extension",
                    "success": False,
                    "error": "Operation not available via docker_helper"
                }
            
            elif operation == "system_df":
                # system_df not yet in docker_helper
                return {
                    "operation": operation,
                    "stdout": "system_df operation requires docker_helper extension",
                    "success": False,
                    "error": "Operation not available via docker_helper"
                }
            
            # Write operations that docker_helper supports
            elif operation in ["restart", "stop", "start"]:
                service_name = kwargs.get("service_name", "")
                if not service_name:
                    return {"error": f"service_name required for {operation} operation", "operation": operation}
                
                async with httpx.AsyncClient(timeout=60.0) as client:
                    payload = {
                        "operation": operation,
                        "container": service_name
                    }
                    response = await client.post(f"{docker_helper_url}/docker", json=payload)
                    if response.status_code == 200:
                        result = response.json()
                        return {
                            "operation": operation,
                            "stdout": result.get("output", f"Container {operation} initiated"),
                            "success": result.get("success", True)
                        }
                    else:
                        return {
                            "error": f"docker_helper returned {response.status_code}: {response.text}",
                            "operation": operation,
                            "success": False
                        }
            
            # Operations that still need direct docker CLI (build, push, etc.)
            cmd = ["docker"]
            
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
            
            elif operation == "remove":
                service_name = kwargs.get("service_name", "")
                # Stop first if running, then remove
                subprocess.run(["docker", "stop", service_name], capture_output=True)
                cmd.extend(["rm", service_name])
            
            elif operation == "exec":
                service_name = kwargs.get("service_name", "")
                command = kwargs.get("command", "/bin/bash")
                cmd.extend(["exec", "-it", service_name, command])
            
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
                remote_cmd = f"docker run -d --name {service_name} {image_name}:{tag}"
                ssh_cmd = ["ssh", "-i", "/home/ubuntu/.ssh/arca_key", f"ubuntu@{remote_host}", remote_cmd]
                
                result = subprocess.run(ssh_cmd, capture_output=True, text=True)
                return {
                    "operation": operation,
                    "command": " ".join(ssh_cmd),
                    "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip(),
                    "exit_code": result.returncode,
                    "success": result.returncode == 0
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
    
    async def _read_file_from_container(self, container_name: str, file_path: str) -> Dict[str, Any]:
        """Read a file from inside a running Docker container via docker_helper"""
        import httpx
        import os
        
        docker_helper_url = os.getenv("DOCKER_HELPER_URL", "http://docker_helper:8082")
        
        try:
            # Use docker_helper to read the file (we'll need to add this endpoint)
            # For now, try using docker exec via the docker socket
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Create exec instance
                create_url = f"{docker_helper_url}/exec/{container_name}"
                response = await client.post(
                    create_url,
                    json={"command": f"cat {file_path}"}
                )
                
                if response.status_code == 200:
                    return {
                        "container": container_name,
                        "file_path": file_path,
                        "content": response.text,
                        "success": True
                    }
                elif response.status_code == 404:
                    # Endpoint doesn't exist yet, return helpful message
                    return {
                        "container": container_name,
                        "file_path": file_path,
                        "error": "docker_helper /exec endpoint not available yet. File reading from containers requires docker_helper update.",
                        "success": False
                    }
                else:
                    return {
                        "error": f"docker_helper returned {response.status_code}: {response.text}",
                        "success": False
                    }
                    
        except Exception as e:
            return {"error": f"Failed to read file from container: {str(e)}", "success": False}
    
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
            
            # Step 2: Build container locally with buildx (if requested)
            if build_locally:
                # Build multi-platform image with buildx
                build_result = await self._execute_docker_operation(
                    "buildx_build",
                    service_name=service_name,
                    tag="latest",
                    platforms=["linux/amd64", "linux/arm64"],
                    build_context=f"services/{service_name}"
                )
                workflow_steps.append({"step": "build", "result": build_result})
                
                if not build_result.get("success", False):
                    if auto_rollback:
                        rollback_result = await self._rollback_deployment(service_name, checkpoint_id)
                        workflow_steps.append({"step": "rollback", "result": rollback_result})
                    return {"error": "Build failed", "workflow_steps": workflow_steps}
            
            # Step 3: Deploy to remote workhorse instance
            deploy_result = await self._execute_docker_operation(
                "deploy_to_remote",
                service_name=service_name,
                remote_host="100.124.13.62",  # workhorse IP
                image_name=service_name,
                tag="latest"
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
            
            guardian_url = os.getenv("GUARDIAN_SERVICE_URL", "http://guardian:8007")
            
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
            # checkpoint_manager = DevelopmentCheckpointManager()
            # await checkpoint_manager.initialize()
            # checkpoint = await checkpoint_manager.load_checkpoint(checkpoint_id)
            
            # if not checkpoint:
            #     return {"error": f"Checkpoint {checkpoint_id} not found"}
            
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

    async def process_json_rpc(self, request: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Process JSON-RPC request"""
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")
        
        try:
            result = None
            if method in ["list_tools", "tools/list"]:
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
                # Handle tool calls
                tool_name = method
                tool_args = params
                
                if method == "tools/call":
                    tool_name = params.get("name")
                    tool_args = params.get("arguments", {})
                
                # Check if tool exists
                tools_result = await self._list_tools()
                known_tools = [t.name for t in tools_result.tools]
                
                if tool_name in known_tools:
                    call_result = await self._call_tool(tool_name, tool_args, headers=headers)
                    if call_result.isError:
                        raise Exception(call_result.content[0].text)
                        
                    content = call_result.content[0].text
                    try:
                        result = json.loads(content)
                    except:
                        result = content
                else:
                     if method not in ["initialize", "notifications/initialized"]:
                        # raise ValueError(f"Unknown method or tool: {method}")
                        pass # Ignore unknown methods for now to avoid noise
                     
                     if method == "initialize":
                         result = {
                             "protocolVersion": "2024-11-05",
                             "capabilities": {
                                 "tools": {"listChanged": True},
                                 "resources": {"listChanged": True, "subscribe": True}
                             },
                             "serverInfo": {"name": "arca-mcp-server", "version": "1.0.0"}
                         }

            return {"jsonrpc": "2.0", "result": result, "id": req_id}
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"JSON-RPC Error: {e}\nTraceback:\n{error_trace}")
            return {
                "jsonrpc": "2.0", 
                "error": {"code": -32603, "message": str(e)}, 
                "id": req_id
            }

# FastAPI app for HTTP interface
app = FastAPI(title="ARCA MCP Server", version="1.0.0")

# Instrument with OpenTelemetry
try:
    sys.path.append("/app/shared")
    from shared.otel_setup import instrument_service
    instrument_service(app, "mcp_server")
except ImportError:
    pass

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

# Mount Geometry Kernel API
# Must be done after middleware but before startup
try:
    from tools.geometry_kernel.api import app as geometry_app
    app.mount("/geometry", WSGIMiddleware(geometry_app))
    logger.info("✅ Geometry Kernel API mounted at /geometry")
except Exception as e:
    logger.error(f"❌ Failed to mount Geometry Kernel API: {e}")

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

@app.get("/tools/status")
async def tools_status():
    """Get status of all loaded tools"""
    if not mcp_server_instance:
        raise HTTPException(status_code=503, detail="MCP Server not initialized")
    
    tools_info = {
        "structural_analyst": mcp_server_instance.structural_analyst is not None,
        "compressor": mcp_server_instance.compressor is not None,
        "reviewer": mcp_server_instance.reviewer is not None,
        "insight_synthesis": mcp_server_instance.insight_synthesis is not None,
        "vision_encoder": mcp_server_instance.vision_encoder is not None,
        "neo4j_admin": mcp_server_instance.neo4j_admin is not None,
        "blackboard_redis": mcp_server_instance.blackboard_redis is not None,
        "guardian": mcp_server_instance.guardian is not None,
        "langsearch": mcp_server_instance.langsearch_client is not None,
        "robotics": getattr(mcp_server_instance, 'mcp_robotics', None) is not None,
        "skill_forge": getattr(mcp_server_instance, 'mcp_skill_forge', None) is not None,
        "otel_autopsy": getattr(mcp_server_instance, 'mcp_otel_autopsy', None) is not None,
        "knowledge_crystallizer": getattr(mcp_server_instance, 'mcp_knowledge_crystallizer', None) is not None,
        "human_feedback": getattr(mcp_server_instance, 'mcp_human_feedback', None) is not None,
        "git_ops": getattr(mcp_server_instance, 'mcp_git_ops', None) is not None,
        "docker_ops": getattr(mcp_server_instance, 'mcp_docker_ops', None) is not None,
        "file_ops": getattr(mcp_server_instance, 'mcp_file_ops', None) is not None,
        "secrets_ops": getattr(mcp_server_instance, 'mcp_secrets_ops', None) is not None,
        "genesis_chain": getattr(mcp_server_instance, 'mcp_genesis_chain', None) is not None,
        "deepthink": getattr(mcp_server_instance, 'mcp_deepthink', None) is not None,
        "hitl_model_selection": getattr(mcp_server_instance, 'mcp_hitl_model_selection', None) is not None,
        "director": getattr(mcp_server_instance, 'mcp_director', None) is not None,
    }
    
    # Check hot-loadable tools directory
    hot_tools_path = Path("/app/tools_hot")
    hot_tools = []
    if hot_tools_path.exists():
        hot_tools = [f.stem for f in hot_tools_path.glob("mcp_*.py")]
    
    return {
        "timestamp": datetime.now().isoformat(),
        "tools_loaded": tools_info,
        "all_loaded": all(tools_info.values()),
        "hot_tools_available": hot_tools,
        "vision_model_path": os.getenv("VISION_MODEL_PATH", "not set"),
    }

@app.post("/tools/reload")
async def reload_tools():
    """Hot-reload tools from the mounted tools directory"""
    global mcp_server_instance
    
    if not mcp_server_instance:
        raise HTTPException(status_code=503, detail="MCP Server not initialized")
    
    try:
        import importlib
        reloaded = []
        errors = []
        
        # Reload individual tool modules
        tool_modules = [
            mcp_robotics, mcp_compressor, mcp_reviewer, mcp_insight_synthesis,
            mcp_skill_forge, mcp_otel_autopsy, mcp_knowledge_crystallizer, 
            mcp_human_feedback, mcp_neo4j_admin, mcp_blackboard_redis, 
            mcp_guardian, mcp_vision_encoder
        ]
        
        for module in tool_modules:
            try:
                importlib.reload(module)
                reloaded.append(module.__name__)
            except Exception as e:
                errors.append({"module": module.__name__, "error": str(e)})
        
        # Re-instantiate tools
        mcp_server_instance.structural_analyst = mcp_robotics.StructuralAnalystTool()
        mcp_server_instance.compressor = mcp_compressor.CompressorTool()
        mcp_server_instance.reviewer = mcp_reviewer.ReviewerInterfaceTool()
        mcp_server_instance.insight_synthesis = mcp_insight_synthesis.InsightSynthesisTool()
        mcp_server_instance.vision_encoder = mcp_vision_encoder.VisionEncoder()
        mcp_server_instance.neo4j_admin = mcp_neo4j_admin.Neo4jAdminTool()
        mcp_server_instance.blackboard_redis = mcp_blackboard_redis.RedisBlackboardTool()
        
        try:
            mcp_server_instance.guardian = mcp_guardian.GuardianTool()
        except Exception as e:
            errors.append({"module": "guardian", "error": str(e)})
        
        return {
            "status": "success",
            "reloaded": reloaded,
            "errors": errors,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Tool reload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/mcp")
async def handle_mcp_request(request: Request):
    """Handle MCP JSON-RPC requests over HTTP"""
    if not mcp_server_instance:
        raise HTTPException(status_code=503, detail="MCP Server not initialized")
    
    try:
        data = await request.json()
        headers = {k: v for k, v in request.headers.items() if k.lower().startswith("x-genesis-")}
        logger.info(f"Captured headers for MCP request: {headers}")
        return await mcp_server_instance.process_json_rpc(data, headers=dict(request.headers))
    except Exception as e:
        logger.error(f"MCP Request Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
        ssl_context.load_cert_chain(certfile=SERVER_CERT_PATH, keyfile=SERVER_KEY_PATH)
        
        # Load CA certificate for client verification
        ssl_context.load_verify_locations(cafile=CA_CERT_PATH)
        
        # Require client certificate
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        
        return ssl_context
    except Exception as e:
        logger.error(f"Failed to create SSL context: {e}")
        raise

if __name__ == "__main__":
    # Create SSL context if TLS is enabled
    ssl_context = create_ssl_context() if TLS_ENABLED else None
    
    protocol = "https" if TLS_ENABLED else "http"
    logger.info(f"🚀 Starting ARCA MCP Server on {protocol}://0.0.0.0:{DATA_HUB_PORT}")
    
    if TLS_ENABLED and ssl_context:
        logger.info("🔒 TLS enabled with mutual authentication")
        logger.info("  - Minimum TLS version: 1.2")
        logger.info("  - Client certificates: REQUIRED")
    else:
        logger.warning("⚠️  TLS disabled - running in insecure mode")
    
    if TLS_ENABLED and ssl_context:
        uvicorn.run(
            "mcp_server:app",
            host="0.0.0.0", 
            port=DATA_HUB_PORT,
            log_level="info",
            ssl_keyfile=str(SERVER_KEY_PATH),
            ssl_certfile=str(SERVER_CERT_PATH),
            ssl_ca_certs=str(CA_CERT_PATH)
        )
    else:
        uvicorn.run(
            "mcp_server:app",
            host="0.0.0.0", 
            port=DATA_HUB_PORT,
            log_level="info"
        )