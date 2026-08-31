import os
import re
import uuid
import json
import threading
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
import asyncio
import sys

import httpx
import redis
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketDisconnect
from pydantic import BaseModel
import logging
import hmac
import hashlib

# System monitoring imports
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import docker

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

# Import centralized model configuration
sys.path.insert(0, "/app")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.model_config import (
    chat_model,
    serena_model,
    architect_model,
    local_ops_model,
    local_vision_model,
)

sys.path.append("/app/shared")
try:
    from secrets_provider import secrets
except ImportError:

    class MockSecrets:
        def get(self, name):
            return os.getenv(name.upper())

    secrets = MockSecrets()

# Import Gemini reasoning integration
from gemini_reasoning_integration import GeminiReasoningWorkflow

# Import Curiosity Engine
from curiosity_engine import CuriosityEngine
from concept_monad import ConceptMonad

# Configure logging early (before imports that may log)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import Serena LangGraph (optional)
try:
    from serena_graph import SerenaGraph, parse_glm_tool_calls, format_tools_for_glm

    SERENA_GRAPH_AVAILABLE = True
except ImportError as e:
    SERENA_GRAPH_AVAILABLE = False
    logger.warning(f"Serena LangGraph not available: {e}")

# Import Attention Model for topic tracking
try:
    from attention_model import (
        get_attention_model,
        get_context as get_attention_context,
    )

    ATTENTION_MODEL_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Attention model not available: {e}")
    ATTENTION_MODEL_AVAILABLE = False

    def get_attention_context(session_id, top_n=10):
        return ""


# Environment variables
AGENT_SERVICE_URL = os.environ.get("AGENT_SERVICE_URL", "http://localhost:8088")
USER_AGENT_PORT = int(os.environ.get("USER_AGENT_PORT", 8084))
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://mcp_server:8086")
GOOGLE_API_KEY = secrets.get("google_api_key") or ""
GENESIS_CHAIN_API_KEY = secrets.get("genesis_chain_api_key") or ""

# Model configuration - using centralized model_config.py (single source of truth)
# ARCA Chat: Gemma 3 27B (tool calls via <tool_call> tags)
# Serena: GLM-4.7 (tool calls via <|tool_call|> tags) - reads from ARCA_SERENA_MODEL env
CHAT_MODEL = chat_model()  # gemma-3-27b-it (ARCA's conversational interface)
SERENA_MODEL = serena_model()  # glm-4.7 (Serena's code agent model via env)
ARCHITECT_MODEL = architect_model()  # gemini-3-flash (strategic planning)
LOCAL_OPS_MODEL = local_ops_model()  # qwen-3-vl-Instruct-2B (local operations)
VISION_MODEL = local_vision_model()  # nanovlm-230m-8k-f16 (visual processing)
LEARN_MODEL = os.environ.get("ARCA_LEARN_MODEL", "gemma-3-27b-it")  # Learning model

# Global state
conversation_history: Dict[str, List[Dict]] = {}  # session_id -> messages
genesis_threads: Dict[str, Dict] = {}  # thread_id -> thread_info
telemetry_cache: Dict[str, Any] = {"data": {}, "last_update": None}
curiosity_engine = CuriosityEngine(
    curiosity_threshold=0.3, high_curiosity_threshold=0.7
)

# Serena conversation memory - stores recent exchanges per session with embeddings
serena_memory: Dict[
    str, List[Dict]
] = {}  # session_id -> [{"role": "user/assistant", "content": str, "timestamp": str, "tool_results": list, "embedding": list}]
serena_memory_embeddings: Dict[
    str, List[Dict]
] = {}  # session_id -> [{"content": str, "embedding": list, "timestamp": str}]
serena_pending_cache: Dict[
    str, List[Dict]
] = {}  # session_id -> [{"content": str, "role": str, "timestamp": str}] - awaiting batch embed
serena_cache_tokens: Dict[
    str, int
] = {}  # session_id -> current token count in pending cache
SERENA_MEMORY_LIMIT = 10  # Keep last N exchanges in active memory
SERENA_MEMORY_TOKEN_LIMIT = 30000  # Max tokens for embedded memory cache
SERENA_BATCH_EMBED_THRESHOLD = 25000  # Trigger batch embed when cache nears this
SERENA_BATCH_EMBED_THRESHOLD = 25000  # Trigger batch embed when cache nears this
EMBEDDING_SERVICE_URL = os.environ.get(
    "EMBEDDING_SERVICE_URL", "http://embedding_service:8005"
)
CONVERSATIONAL_HDC_URL = os.environ.get(
    "CONVERSATIONAL_HDC_URL", "http://conversational_hdc:8096"
)
GEOMETRY_KERNEL_URL = os.environ.get(
    "GEOMETRY_KERNEL_URL", "http://geometry_kernel:8089"
)


# Redis configuration for persistent memory
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_DB = int(os.environ.get("REDIS_DB", 1))  # Use DB 1 for Serena memory
SERENA_REDIS_PREFIX = "serena:"

# Initialize Redis client
try:
    redis_client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True
    )
    redis_client.ping()
    REDIS_AVAILABLE = True
    logger.info(f"Redis connected at {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    redis_client = None
    REDIS_AVAILABLE = False
    logger.warning(f"Redis unavailable, using in-memory storage: {e}")

# Health alert subscription configuration
HEALTH_CHANNEL = "arca:health:alerts"
health_alerts_queue: List[Dict[str, Any]] = []  # Queue for received health alerts
health_alert_lock = threading.Lock()  # Thread-safe access to alerts queue
health_subscription_active = False  # Track if subscription thread is running

# Actions that are read-only and don't need approval
READ_ONLY_ACTIONS = {
    "list_containers",
    "container_logs",
    "container_file_read",
    "skills_list",
    "skills_search",
    "read_file",
    "neo4j_verify_connectivity",
    "check_status",
    "check_logs",
    "check_service_status",
    "investigate",
    "analyze",
}

# Pending actions awaiting user approval
pending_approvals: Dict[
    str, Dict
] = {}  # approval_id -> {"action": str, "session_id": str, "details": dict, "timestamp": str}


# --- Pydantic Models for API ---
class AgentRequest(BaseModel):
    objective: str
    session_id: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = "default"


class SerenaRequest(BaseModel):
    command: str
    session_id: Optional[str] = None


class ReasoningRequest(BaseModel):
    context_depth: Optional[int] = 10
    session_id: Optional[str] = None


# --- FastAPI App Setup ---
app = FastAPI(
    title="ARCA User Interaction Agent",
    description="Real-time user interface for the ARCA system with full MiniMax integration",
    version="3.2.2",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Serve static files (web interface)
static_dir = "static"
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
else:
    logger.warning(f"Static directory '{static_dir}' not found.")


@app.get("/monitor")
async def monitor_page():
    """Serve the system activity monitor page"""
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/")
async def root_page():
    """Serve the main chat interface"""
    return FileResponse(os.path.join(static_dir, "index.html"))


# --- System Telemetry Functions ---
def get_system_telemetry() -> Dict[str, Any]:
    """Collect real system metrics from the host environment"""
    telemetry = {
        "cpu": "N/A",
        "memory": "N/A",
        "swap": "N/A",
        "containers": "N/A",
        "llm_perf": "N/A",
        "neo4j": "Unknown",
        "redis": "Unknown",
    }

    if PSUTIL_AVAILABLE:
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()

            telemetry["cpu"] = f"{cpu_percent}%"
            telemetry["memory"] = f"{mem.percent}%"
        except Exception as e:
            logger.error(f"Error getting psutil metrics: {e}")

    if DOCKER_AVAILABLE:
        try:
            client = docker.from_env()
            containers = client.containers.list()
            telemetry["containers"] = f"{len(containers)}"

            # Check Critical Services
            telemetry["neo4j"] = (
                "Online"
                if any("neo4j" in c.name.lower() for c in containers)
                else "Offline"
            )
            telemetry["redis"] = (
                "Online"
                if any("redis" in c.name.lower() for c in containers)
                else "Offline"
            )
        except Exception as e:
            logger.warning(f"Docker metrics unavailable: {e}")

    # Check Native LLM Performance via Redis or direct health check
    if redis_client:
        try:
            # Check for generic performance stats
            perf = redis_client.get("arca:telemetry:llm:perf")
            if perf:
                telemetry["llm_perf"] = f"{perf} tok/s"

            # Check for current global state
            global_state = redis_client.get("arca:state:global")
            if global_state:
                state_data = json.loads(global_state)
                # Could extract more here
        except Exception:
            pass

    return telemetry

    return telemetry


def get_geometry_context_for_prompt() -> str:
    """
    Fetch geometry context from Redis and return a QUALITATIVE summary for ARCA's prompt.
    Returns 'no model loaded' message if Redis is empty, ensuring ARCA is honest.
    """
    if not redis_client:
        return "[Geometry Context: Redis unavailable. Cannot access geometric models.]"

    try:
        raw_data = redis_client.get("arca:blackboard:working_model")

        if not raw_data:
            return """[Geometry Context: No model loaded. 
If the user asks about geometry context or a document, tell them: "I don't have any document loaded yet. Would you like me to ingest one? Tell me the file path."]"""

        # Parse the model
        model = json.loads(raw_data)

        # Extract qualitative summary
        gravity_well = model.get("gravity_well", {})
        objective = gravity_well.get("concept", "Unknown Topic")
        objects = model.get("objects", [])

        if not objects:
            return f"""[Geometry Context: Document "{objective}" is loaded but no concepts were extracted. 
The ingestion may have failed. Suggest re-ingesting with a clearer objective.]"""

        # Build qualitative summary with Curiosity modulation
        concept_summaries = []
        max_gradient = 0.0
        active_inquiry = None

        for obj in objects[:5]:  # Top 5
            name = obj.get("id", "Unnamed")
            desc = obj.get("desc", "No description available")

            # 1. Hydrate ConceptMonad for Curiosity Check
            monad = ConceptMonad(concept_id=name)
            # Basic entropy from length/complexity proxy if not stored
            monad.uncertainty = min(0.9, len(desc) / 500)

            # 2. Check Curiosity
            gradient = curiosity_engine.compute_curiosity_gradient(monad)

            # 3. Check "Satisfaction" (Abatement) from Redis
            # Satisfaction key: "arca:curiosity:satisfied:{name}" -> exists if discussed
            is_satisfied = redis_client.exists(f"arca:curiosity:satisfied:{name}")

            if is_satisfied:
                gradient *= 0.1  # Collapse curiosity if satisfied

            if gradient > max_gradient:
                max_gradient = gradient
                if gradient > 0.7:
                    active_inquiry = f"INITIATIVE: Allow yourself to interrupt and ask: '{curiosity_engine.generate_inquiry(monad)}'"

            flag = ""
            if gradient > 0.7:
                flag = "[HIGH INTEREST]"
            elif is_satisfied:
                flag = "[SATISFIED]"

            concept_summaries.append(f"- {name} {flag}: {desc[:100]}...")

        concepts_text = "\\n".join(concept_summaries)

        # DYNAMIC INSTRUCTION
        instruction_block = ""
        if max_gradient > 0.6:
            instruction_block = f"""5. **High Curiosity State**: You are fascinated by these concepts.
{active_inquiry}
Use the `web_search` tool to investigate."""
        elif max_gradient < 0.2:
            instruction_block = "5. **Abated Curiosity**: You have processed this document. Only discuss it if the user asks."
        else:
            instruction_block = "5. **Standard Protocol**: Refer to these concepts if relevant to the user's message."

        return f"""[Geometry Context - INTERNAL USE ONLY]
Currently loaded: "{objective}"
Key concepts extracted:
{concepts_text}

CRITICAL BEHAVIOR RULES:
1. EXECUTE requests directly - do NOT narrate your process.
2. Discuss concepts as REAL IDEAS, not "objects in a model".
3. NEVER mention: vectors, trajectory, mass, JSON, model representation, topology layer, attention engine, system sensation.
4. If the user asks about the document, synthesize what these concepts MEAN.
{instruction_block}"""

    except Exception as e:
        return f"[Geometry Context: Error reading model - {e}]"


def extract_and_register_topics(session_id: str, message: str):
    """
    Extract key topics from user message and register them with attention model.

    Uses simple heuristics:
    - Capitalized words (proper nouns)
    - Multi-word patterns after "about", "regarding", "the"
    - Known domain terms
    """
    if not ATTENTION_MODEL_AVAILABLE:
        return

    try:
        from attention_model import mention

        # Simple topic extraction patterns
        words = message.split()

        # Find capitalized words (excluding sentence start)
        for i, word in enumerate(words):
            clean_word = word.strip('.,!?";:()[]')
            if len(clean_word) > 2 and clean_word[0].isupper() and i > 0:
                mention(session_id, clean_word, desc=f"Topic mentioned in conversation")

        # Find patterns like "about X", "the X", "my X"
        trigger_words = {"about", "regarding", "the", "my", "our", "this"}
        for i, word in enumerate(words[:-1]):
            if word.lower() in trigger_words:
                next_word = words[i + 1].strip('.,!?";:()[]')
                if len(next_word) > 2 and next_word[0].isalpha():
                    mention(
                        session_id,
                        next_word,
                        desc=f"Topic extracted from '{word} {next_word}'",
                    )

        # Domain-specific terms
        domain_terms = {
            "geometry",
            "document",
            "file",
            "kernel",
            "ingestion",
            "analysis",
            "report",
        }
        for term in domain_terms:
            if term in message.lower():
                mention(session_id, term.capitalize(), desc=f"Domain concept: {term}")

        # --- CONCEPT ASSIMILATION (User -> Geometry Kernel) ---
        # Inject extracted topics into the persistent Working Model so Curiosity Engine sees them.
        if redis_client:
            raw_data = redis_client.get("arca:blackboard:working_model")
            model = (
                json.loads(raw_data)
                if raw_data
                else {"objects": [], "gravity_well": {"concept": "Conversation"}}
            )

            existing_ids = {obj.get("id") for obj in model.get("objects", [])}
            new_objects = []

            # Extract from Attention Model logic or just re-use the words list logic
            # For simplicity, let's use the 'capitalized words' heuristic again or accessible list
            # Ideally we'd get the list from 'mention' calls, but 'mention' returns dict.
            # Let's just re-scan for assimilation:

            assimilated_count = 0
            for i, word in enumerate(words):
                clean_word = word.strip('.,!?";:()[]')
                if len(clean_word) > 3 and clean_word[0].isupper() and i > 0:
                    if clean_word not in existing_ids:
                        # Create new Concept Object
                        new_obj = {
                            "id": clean_word,
                            "desc": f"Concept introduced by User during conversation about {clean_word}.",
                            "source": "user_interaction",
                            "confidence": 0.8,
                        }
                        model["objects"].append(new_obj)
                        existing_ids.add(clean_word)
                        assimilated_count += 1

            if assimilated_count > 0:
                # Save back to Blackboard
                redis_client.set("arca:blackboard:working_model", json.dumps(model))
                logger.info(
                    f"Assimilated {assimilated_count} user concepts into Geometry Kernel."
                )

    except Exception as e:
        logger.debug(f"Topic extraction/assimilation failed: {e}")


async def update_telemetry_cache():
    """Update telemetry cache periodically and ingest Proprioception into Geometry Kernel"""
    global telemetry_cache
    while True:
        try:
            telemetry = get_system_telemetry()
            telemetry_cache["data"] = telemetry
            telemetry_cache["last_update"] = datetime.utcnow().isoformat()

            # --- PROPRIOCEPTION (System Body -> Geometry) ---
            # Ingest system state as a concept every 60s (approx)
            # We sample every 5s, so checking random or counter could work,
            # or just simple probability 1/12
            if datetime.utcnow().second < 5:  # Roughly once a minute window
                state_desc = f"System State: CPU {telemetry.get('cpu')}, RAM {telemetry.get('memory')}. Containers: {telemetry.get('containers')}."
                # Self-embedding calculation (can affect performace, keep light)
                # We'll skip embedding here and let Kernel/Default handle it or pass None
                asyncio.create_task(
                    ingest_into_geometry_kernel(
                        state_desc, source="proprioception", title="System Self-Model"
                    )
                )

        except Exception as e:
            logger.error(f"Error updating telemetry cache: {e}")
        await asyncio.sleep(5)  # Update every 5 seconds


# --- WebSocket Connection Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_alive: Dict[
            str, bool
        ] = {}  # Track if connection is still alive

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        self.connection_alive[session_id] = True
        logger.info(f"WebSocket connected: {session_id}")

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
        if session_id in self.connection_alive:
            del self.connection_alive[session_id]
        logger.info(f"WebSocket disconnected: {session_id}")

    def is_connected(self, session_id: str) -> bool:
        return session_id in self.active_connections and self.connection_alive.get(
            session_id, False
        )

    async def send_message(self, message: Dict[str, Any], session_id: str):
        if session_id in self.active_connections and self.connection_alive.get(
            session_id, False
        ):
            try:
                await self.active_connections[session_id].send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Failed to send WebSocket message to {session_id}: {e}")
                self.connection_alive[session_id] = False

    async def send_keepalive(self, session_id: str):
        """Send a ping/keepalive message to keep connection alive"""
        if session_id in self.active_connections and self.connection_alive.get(
            session_id, False
        ):
            try:
                await self.active_connections[session_id].send_text(
                    json.dumps(
                        {"type": "ping", "timestamp": datetime.utcnow().isoformat()}
                    )
                )
            except Exception as e:
                logger.error(f"Failed to send keepalive to {session_id}: {e}")
                self.connection_alive[session_id] = False


manager = ConnectionManager()


# --- Keepalive Helper ---
async def send_keepalives_during_processing(session_id: str, interval: float = 10.0):
    """Send keepalive pings during long-running operations to prevent WebSocket timeout"""
    while manager.is_connected(session_id):
        await asyncio.sleep(interval)
        if manager.is_connected(session_id):
            await manager.send_keepalive(session_id)
        else:
            break


# --- Helper Functions ---
def get_genesis_headers(
    payload: Optional[Dict[str, Any]] = None,
    incoming_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Generate mandatory X-Genesis headers for inter-service communication."""
    api_key = os.getenv("GENESIS_CHAIN_API_KEY")
    headers = {
        "X-Genesis-Chain": "ENABLED",
        "X-Genesis-Agent": "arca_chat",
        "X-Genesis-Reasoning-Depth": "strategic",  # Provide a default
        "Content-Type": "application/json",
    }

    # Generate Traceability IDs if not present
    task_id = str(uuid.uuid4())
    workflow_id = str(uuid.uuid4())

    headers["X-Genesis-Task-ID"] = task_id
    headers["X-Genesis-Workflow-ID"] = workflow_id
    headers["X-Genesis-Target-Agent"] = "agent_service"  # Default target

    # Propagate any existing x-genesis headers (overwriting defaults)
    if incoming_headers:
        for k, v in incoming_headers.items():
            if k.lower().startswith("x-genesis-"):
                headers[k] = v

    if api_key and payload:
        body_str = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            api_key.encode("utf-8"), body_str.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        headers["X-Genesis-Signature"] = signature

    return headers


async def call_agent_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Calls the backend agent service with fallback"""
    try:
        final_headers = get_genesis_headers(payload)
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{AGENT_SERVICE_URL}/invoke", json=payload, headers=final_headers
            )
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as e:
        logger.error(f"Agent service unavailable: {e}")
        # Return fallback response
        return {
            "response": "Agent service is currently unavailable. Using local processing.",
            "status": "fallback",
            "error": str(e),
        }
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Agent service error: {e.response.status_code} - {e.response.text}"
        )
        return {
            "response": f"Agent service error: {e.response.status_code}",
            "status": "error",
            "error": e.response.text,
        }


# --- Serena MCP Tool Definitions for Function Calling ---
# These are simplified tool names that map to actual MCP tools
# NOTE: reasoning_store/reasoning_search are ReasoningBank tools, not Serena tools
SERENA_TOOLS = [
    {
        "name": "list_containers",
        "description": "List all Docker containers running on the system with their status",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "container_logs",
        "description": "Get logs from a specific Docker container",
        "parameters": {
            "type": "object",
            "properties": {
                "container_name": {
                    "type": "string",
                    "description": "Name of the container to get logs from",
                }
            },
            "required": ["container_name"],
        },
    },
    {
        "name": "container_file_read",
        "description": "Read a file from inside a running Docker container. Use this to inspect config files, code, or logs inside containers.",
        "parameters": {
            "type": "object",
            "properties": {
                "container_name": {
                    "type": "string",
                    "description": "Name of the container",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to the file inside the container (e.g., /app/main.py)",
                },
            },
            "required": ["container_name", "file_path"],
        },
    },
    {
        "name": "skills_list",
        "description": "List all available skills in the ARCA skills bank",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "skills_search",
        "description": "Search for skills by keyword or capability",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for finding relevant skills",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_file",
        "description": "Read contents of a file from the system",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to read"}
            },
            "required": ["path"],
        },
    },
    {
        "name": "neo4j_verify_connectivity",
        "description": "Verify Neo4j graph database connectivity and status",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "publish_health_alert",
        "description": "Publish a health alert to system monitoring",
        "parameters": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Name of the service"},
                "status": {
                    "type": "string",
                    "description": "Health status: healthy, unhealthy, error, critical",
                },
                "details": {"type": "string", "description": "Details about the issue"},
            },
            "required": ["service", "status"],
        },
    },
    {
        "name": "serena_analyze_code",
        "description": "Analyze code for patterns, issues, and improvements",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to analyze"},
                "language": {"type": "string", "description": "Programming language"},
            },
            "required": ["code"],
        },
    },
    # Git operations - mapped to git_maintainer_operation MCP tool
    {
        "name": "git_status",
        "description": "Get git repository status showing modified, staged, and untracked files",
        "parameters": {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Path to git repository (default: /home/ubuntu/ARCA)",
                }
            },
            "required": [],
        },
    },
    {
        "name": "git_add",
        "description": "Stage files for commit. Use '.' to stage all changes.",
        "parameters": {
            "type": "object",
            "properties": {
                "files": {
                    "type": "string",
                    "description": "Files to stage (e.g., 'file.py' or '.' for all)",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Path to git repository (default: /home/ubuntu/ARCA)",
                },
            },
            "required": ["files"],
        },
    },
    {
        "name": "git_commit",
        "description": "Commit staged changes with a message",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Commit message describing the changes",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Path to git repository (default: /home/ubuntu/ARCA)",
                },
            },
            "required": ["message"],
        },
    },
    {
        "name": "git_push",
        "description": "Push committed changes to remote repository",
        "parameters": {
            "type": "object",
            "properties": {
                "remote": {
                    "type": "string",
                    "description": "Remote name (default: origin)",
                },
                "branch": {
                    "type": "string",
                    "description": "Branch name (default: main)",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Path to git repository (default: /home/ubuntu/ARCA)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "web_search",
        "description": "Perform a web search using LangSearch to find current information from the internet.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query or question"},
                "count": {
                    "type": "integer",
                    "description": "Number of results (default: 5, max 10)",
                },
                "freshness": {
                    "type": "string",
                    "description": "Time filter: 'oneDay', 'oneWeek', 'oneMonth', 'oneYear', 'noLimit' (default: noLimit)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_tasks",
        "description": "List active tasks from the Maintainer Agents service. Use this to check agent busyness.",
        "parameters": {
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "description": "Filter by status (e.g., 'running', 'pending', 'completed')",
                }
            },
            "required": [],
        },
    },
    {
        "name": "edit_task",
        "description": "Edit a task description or status in the system.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The ID of the task to edit",
                },
                "updates": {
                    "type": "string",
                    "description": "JSON string of fields to update (e.g., {'status': 'cancelled'})",
                },
            },
            "required": ["task_id", "updates"],
        },
    },
    {
        "name": "submit_task",
        "description": "Dispatch a new task to the Maintainer Agents or Serena.",
        "parameters": {
            "type": "object",
            "properties": {
                "agent_type": {
                    "type": "string",
                    "description": "Target agent (e.g., 'git', 'docker', 'serena')",
                },
                "operation": {
                    "type": "string",
                    "description": "Operation name (e.g., 'execute', 'analyze')",
                },
                "params": {
                    "type": "string",
                    "description": "JSON string of parameters for the operation",
                },
            },
            "required": ["agent_type", "operation", "params"],
        },
    },
    {
        "name": "observer_task",
        "description": "Task the Observer Agent to gather information or monitor state.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Information to gather or state to monitor",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "submit_draft_prompt",
        "description": "Submit a draft prompt found in the UI for refinement or execution.",
        "parameters": {
            "type": "object",
            "properties": {
                "draft_text": {
                    "type": "string",
                    "description": "The draft text to submit",
                },
                "action": {
                    "type": "string",
                    "description": "Action to take: 'refine', 'execute', 'append'",
                },
            },
            "required": ["draft_text", "action"],
        },
    },
    {
        "name": "semantic_rerank",
        "description": "Rerank a list of document chunks by semantic relevance to a query.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Relevance query"},
                "documents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of text chunks to rerank",
                },
                "top_n": {
                    "type": "integer",
                    "description": "Number of top results to return",
                },
            },
            "required": ["query", "documents"],
        },
    },
    {
        "name": "git_diff",
        "description": "Show changes in working directory or between commits",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Specific file or directory to diff",
                },
                "staged": {
                    "type": "boolean",
                    "description": "Show staged changes (--staged flag)",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Path to git repository (default: /home/ubuntu/ARCA)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "git_log",
        "description": "Show recent commit history",
        "parameters": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of commits to show (default: 10)",
                },
                "repo_path": {
                    "type": "string",
                    "description": "Path to git repository (default: /home/ubuntu/ARCA)",
                },
            },
            "required": [],
        },
    },
    # Docker write operations - for self-healing
    {
        "name": "docker_restart",
        "description": "Restart a Docker container. REQUIRES APPROVAL for production systems.",
        "parameters": {
            "type": "object",
            "properties": {
                "container_name": {
                    "type": "string",
                    "description": "Name of the container to restart",
                }
            },
            "required": ["container_name"],
        },
    },
    # NOTE: dispatch_ops_job removed - not implemented in MCP server
    # Serena should use direct git_* and docker_* tools instead
    # --- Geometry Kernel Tools (V2) ---
    # These enable geometric reasoning instead of raw text processing
    {
        "name": "geometry_ingest",
        "description": "Ingest a document into the Geometry Kernel as a 'Solar System' of concepts. Use for code, logs, or documentation. Returns geometric model.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to ingest",
                },
                "objective": {
                    "type": "string",
                    "description": "What to focus on (e.g., 'Find security issues', 'Understand auth flow')",
                },
                "content_type": {
                    "type": "string",
                    "description": "Type: LOGS, NARRATIVE, CODE, or AUTO (default: AUTO)",
                },
            },
            "required": ["file_path", "objective"],
        },
    },
    {
        "name": "geometry_analyze",
        "description": "Analyze the current geometric state for anomalies and propose corrections. Uses Security, Git, or Architect perspective.",
        "parameters": {
            "type": "object",
            "properties": {
                "objective": {
                    "type": "string",
                    "description": "What to analyze (e.g., 'Is auth module secure?', 'What changed since last commit?')",
                },
                "role": {
                    "type": "string",
                    "description": "Agent perspective: security, git, architect (default: architect)",
                },
            },
            "required": ["objective"],
        },
    },
    {
        "name": "geometry_apply_force",
        "description": "Apply a force proposal to the geometry. Used to correct anomalies or update system state.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_node": {
                    "type": "string",
                    "description": "ID of the concept node to affect",
                },
                "force_vector": {
                    "type": "array",
                    "description": "[x, y, z] force direction in semantic space",
                },
                "magnitude": {
                    "type": "number",
                    "description": "Force strength (0.0 to 1.0)",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Why this force is being applied",
                },
            },
            "required": ["target_node", "force_vector", "reasoning"],
        },
    },
    {
        "name": "geometry_state",
        "description": "Get current geometric state as a simplified view. Shows nodes, attractors, and anomalies.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "geometry_recursive_walk",
        "description": "Walk through a document recursively using RLM strategy. Better for large files than single-shot analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to walk",
                },
                "objective": {
                    "type": "string",
                    "description": "What to find or analyze",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum recursion depth (default: 3)",
                },
            },
            "required": ["file_path", "objective"],
        },
    },
    # --- ARCA → Serena Coordination Tools ---
    # These tools allow ARCA to build prompts for Serena and submit them
    {
        "name": "serena_draft_prompt",
        "description": "Start building a prompt for Serena. Use this to compose complex tasks collaboratively with the user before submitting.",
        "parameters": {
            "type": "object",
            "properties": {
                "initial_content": {
                    "type": "string",
                    "description": "Initial prompt content to draft",
                },
                "context_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File paths to include as context",
                },
            },
            "required": ["initial_content"],
        },
    },
    {
        "name": "serena_append_prompt",
        "description": "Append additional content to the current Serena prompt draft.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Content to append to the draft",
                },
                "context_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Additional file paths to include",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "serena_view_draft",
        "description": "View the current Serena prompt draft before submitting.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "serena_submit",
        "description": "Submit the current prompt draft to Serena for execution. Only call when user approves.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "serena_delegate",
        "description": "Delegate a task directly to Serena. For quick tasks that don't need collaborative prompting.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Task description for Serena",
                },
                "maintainer": {
                    "type": "string",
                    "enum": ["docker", "git", "auto"],
                    "description": "Which maintainer agent Serena should use (default: auto)",
                },
            },
            "required": ["task"],
        },
    },
]


# --- ARCA Tools (for Gemma 3 27B) ---
# These are tools ARCA uses for coordinating with Serena and system operations
ARCA_TOOLS = [
    {
        "name": "serena_draft_prompt",
        "description": "Start building a prompt for Serena. Use this to compose complex tasks collaboratively with the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "initial_content": {
                    "type": "string",
                    "description": "Initial prompt content",
                },
                "context_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File paths for context",
                },
            },
            "required": ["initial_content"],
        },
    },
    {
        "name": "serena_append_prompt",
        "description": "Add content to the Serena prompt draft.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "context_files": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["content"],
        },
    },
    {
        "name": "serena_view_draft",
        "description": "View current Serena prompt draft.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "serena_submit",
        "description": "Submit the prompt draft to Serena. Call only when user approves.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "serena_delegate",
        "description": "Delegate a quick task directly to Serena.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Task for Serena"},
                "maintainer": {
                    "type": "string",
                    "enum": ["docker", "git", "auto"],
                    "description": "Maintainer to use",
                },
            },
            "required": ["task"],
        },
    },
    # Include common tools ARCA can also use
    {
        "name": "read_file",
        "description": "Read contents of a file from the system",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file"}
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in a directory",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {"type": "string"},
                "pattern": {"type": "string"},
            },
            "required": [],
        },
    },
    {
        "name": "geometry_ingest",
        "description": "Ingest a document into the Geometry Kernel for analysis.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file"},
                "objective": {"type": "string", "description": "Analysis focus"},
            },
            "required": ["file_path", "objective"],
        },
    },
    {
        "name": "geometry_state",
        "description": "Get current geometric state of loaded documents.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "web_search",
        "description": "Search the web for information.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "count": {
                    "type": "integer",
                    "description": "Number of results (default 5)",
                },
            },
            "required": ["query"],
        },
    },
]


def build_arca_tools_prompt() -> str:
    """Build tools description for ARCA (Gemma 3 27B)"""
    tools_str = "You have access to the following tools:\n\n"
    for tool in ARCA_TOOLS:
        name = tool["name"]
        desc = tool.get("description", "No description")
        params = tool.get("parameters", {}).get("properties", {})
        required = tool.get("parameters", {}).get("required", [])

        params_desc = []
        for pname, pinfo in params.items():
            req_mark = "*" if pname in required else ""
            params_desc.append(
                f"  - {pname}{req_mark}: {pinfo.get('description', pinfo.get('type', 'any'))}"
            )

        params_str = "\n".join(params_desc) if params_desc else "  (no parameters)"
        tools_str += f"**{name}**: {desc}\nParameters:\n{params_str}\n\n"

    tools_str += """
To call a tool, use this exact format:
<tool_call>{"name": "tool_name", "arguments": {"param1": "value1"}}</tool_call>

You can call multiple tools by including multiple <tool_call> blocks.
Wait for tool results before continuing your response.
"""
    return tools_str


class SerenaMCPClient:
    """MCP client for Serena to execute tools"""

    def __init__(self, mcp_url: str = None):
        self.mcp_url = mcp_url or MCP_SERVER_URL

        # Map Serena's simplified tool names to actual MCP tool calls
        # docker_maintainer_operation uses: operation (ps/logs/etc), service_name
        # git_maintainer_operation uses: operation (status/add/commit/push/etc), repo_path, files, message, etc.
        self.tool_mapping = {
            # Docker read operations
            "list_containers": ("docker_maintainer_operation", {"operation": "ps"}),
            "container_logs": ("docker_maintainer_operation", {"operation": "logs"}),
            "container_file_read": ("docker_container_file_read", {}),
            # Docker write operations
            "docker_restart": ("docker_maintainer_operation", {"operation": "restart"}),
            # Git operations
            "git_status": ("git_maintainer_operation", {"operation": "status"}),
            "git_add": ("git_maintainer_operation", {"operation": "add"}),
            "git_commit": ("git_maintainer_operation", {"operation": "commit"}),
            "git_push": ("git_maintainer_operation", {"operation": "push"}),
            "git_diff": ("git_maintainer_operation", {"operation": "diff"}),
            "git_log": ("git_maintainer_operation", {"operation": "log"}),
            # General mappings
            "search_skills": ("skills_search", {}),
            "read_file": ("read_file", {}),  # Passthrough
        }

    async def _send_mcp_request(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Internal method to send raw JSON-RPC request to MCP server, bypassing tool mapping and interception."""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments or {}},
                    "id": str(uuid.uuid4()),
                }

                logger.info(f"MCP call (internal): {tool_name} with {arguments}")

                final_headers = get_genesis_headers(payload)
                response = await client.post(
                    f"{self.mcp_url}/mcp", json=payload, headers=final_headers
                )
                response.raise_for_status()
                result = response.json()

                if "error" in result:
                    return {"error": result["error"], "success": False}

                # Extract the actual result - MCP returns nested structure
                mcp_result = result.get("result", {})
                return {"result": mcp_result, "success": True}

        except Exception as e:
            logger.error(f"MCP tool call failed: {tool_name} - {e}")
            return {"error": str(e), "success": False}

    async def call_tool(
        self, tool_name: str, arguments: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Call an MCP tool with mapping and interception logic."""
        try:
            # --- Geometry Kernel Tools (V2) ---
            # Intercept "high-level" geometry tools to bridge them to specific MCP calls
            # We ONLY intercept the simplified tool names exposed to the agent
            if tool_name.startswith("geometry_") and tool_name not in [
                "geometry_ingest_content",
                "geometry_apply",
            ]:
                return await self._handle_geometry_tool(tool_name, arguments or {})

            # Special handling for container_file_read
            if tool_name == "container_file_read":
                return await self._read_container_file(
                    arguments.get("container_name", ""), arguments.get("file_path", "")
                )

            # Check if tool needs mapping
            if tool_name in self.tool_mapping:
                actual_tool, base_args = self.tool_mapping[tool_name]
                merged_args = {**base_args, **(arguments or {})}
                if "container_name" in merged_args:
                    merged_args["service_name"] = merged_args.pop("container_name")
                if (
                    actual_tool == "git_maintainer_operation"
                    and "repo_path" not in merged_args
                ):
                    merged_args["repo_path"] = "/home/ubuntu/ARCA"
                tool_name = actual_tool
                arguments = merged_args

            # Perform the actual request
            return await self._send_mcp_request(tool_name, arguments)

        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} - {e}")
            return {"error": str(e), "success": False}

    async def list_containers(self) -> Dict[str, Any]:
        """Get list of all Docker containers"""
        return await self.call_tool(
            "docker_maintainer_operation", {"operation": "status"}
        )

    async def get_container_logs(
        self, container: str, tail: int = 50
    ) -> Dict[str, Any]:
        """Get logs from a container"""
        return await self.call_tool(
            "docker_maintainer_operation",
            {"operation": "logs", "container": container, "tail": tail},
        )

    async def _read_container_file(
        self, container_name: str, file_path: str
    ) -> Dict[str, Any]:
        """Read a file from inside a Docker container via docker_helper"""
        docker_helper_url = os.getenv("DOCKER_HELPER_URL", "http://docker_helper:8082")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{docker_helper_url}/exec/{container_name}",
                    json={"command": f"cat {file_path}"},
                )

                if response.status_code == 200:
                    return {
                        "result": {
                            "container": container_name,
                            "file_path": file_path,
                            "content": response.text,
                            "success": True,
                        },
                        "success": True,
                    }
                else:
                    return {
                        "error": f"Failed to read file: {response.status_code} - {response.text}",
                        "success": False,
                    }
        except Exception as e:
            logger.error(f"Container file read failed: {e}")
            return {"error": str(e), "success": False}

    async def _handle_geometry_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle Geometry Kernel tools by bridging calls to the real Geometry Kernel (via MCP).
        Refactored to remove local mocks and use the centralized mcp_server.
        Uses _send_mcp_request to avoid recursion in call_tool.
        """
        try:
            # 1. Ingest: Read file locally, then push content to Kernel
            # 1. Ingest: Direct pass-through to MCP (which proxies to Kernel)
            if tool_name == "geometry_ingest":
                # Ensure we have a file path
                file_path = arguments.get("file_path") or arguments.get("document")
                if not file_path:
                    return {
                        "error": "No file_path or document provided",
                        "success": False,
                    }

                # Update arguments to standardized format
                # The user might have provided "document" but Kernel expects "file_path"
                mcp_args = {
                    "file_path": file_path,
                    "objective": arguments.get("objective", "Detailed Analysis"),
                    "content_type": arguments.get("content_type", "AUTO"),
                }

                # Call MCP tool: geometry_ingest (The Fixed Proxy)
                # No local file reading - let the Kernel/MCP handle access via volume mounts
                return await self._send_mcp_request("geometry_ingest", mcp_args)

            # 2. State: Direct proxy
            elif tool_name == "geometry_state":
                return await self._send_mcp_request("geometry_state", {})

            # 3. Apply Force: Map arguments to Kernel API format
            elif tool_name == "geometry_apply_force":
                target_node = arguments.get("target_node")
                force_vector = arguments.get("force_vector", [0, 0, 0])
                magnitude = arguments.get("magnitude", 0.1)
                reasoning = arguments.get("reasoning", "Agent applied force")

                # Construct force object (Kernel expects list of forces)
                force_payload = {
                    "target_id": target_node,
                    "vector": force_vector,
                    "magnitude": magnitude,
                    "source": "agent_interaction",
                    "rationale": reasoning,
                }

                return await self._send_mcp_request(
                    "geometry_apply", {"forces": [force_payload], "reason": reasoning}
                )

            # 4. Analyze: Fallback to State (Analysis happens in Agent's mind based on State)
            elif tool_name == "geometry_analyze":
                # The 'analysis' is the Agent's cognitive task.
                # We return the state so the Agent can 'see' what to analyze.
                return await self._send_mcp_request("geometry_state", {})

            # 5. Recursive Walk: Not yet fully implemented in MCP, fallback to simple ingest
            elif tool_name == "geometry_recursive_walk":
                return {
                    "error": "Recursive walk not supported in this version. Use geometry_ingest.",
                    "success": False,
                }

            else:
                return {
                    "error": f"Unknown geometry tool: {tool_name}",
                    "success": False,
                }

        except Exception as e:
            logger.error(f"Geometry bridge error: {e}")
            return {"error": str(e), "success": False}


# Global Serena MCP client
serena_mcp = SerenaMCPClient()


# --- Health Alert Subscription ---
def health_alert_listener():
    """Background thread to listen for health alerts via Redis pub/sub"""
    global health_subscription_active
    health_subscription_active = True

    if not REDIS_AVAILABLE or not redis_client:
        logger.warning("Health alert listener cannot start: Redis unavailable")
        health_subscription_active = False
        return

    try:
        # Create a separate Redis connection for pubsub
        pubsub_client = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True
        )
        pubsub = pubsub_client.pubsub()
        pubsub.subscribe(HEALTH_CHANNEL)
        logger.info(f"Health alert listener subscribed to {HEALTH_CHANNEL}")

        for message in pubsub.listen():
            if message["type"] == "message":
                try:
                    alert_data = json.loads(message["data"])
                    with health_alert_lock:
                        health_alerts_queue.append(
                            {
                                "timestamp": datetime.now().isoformat(),
                                "alert": alert_data,
                            }
                        )
                        # Keep only last 50 alerts
                        if len(health_alerts_queue) > 50:
                            health_alerts_queue.pop(0)

                    logger.info(
                        f"Health alert received: {alert_data.get('service', 'unknown')} - {alert_data.get('status', 'unknown')}"
                    )
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid health alert JSON: {e}")

            if not health_subscription_active:
                break

    except Exception as e:
        logger.error(f"Health alert listener error: {e}")
    finally:
        health_subscription_active = False
        logger.info("Health alert listener stopped")


async def get_pending_health_alerts() -> List[Dict[str, Any]]:
    """Get and clear pending health alerts for Serena to analyze"""
    with health_alert_lock:
        alerts = list(health_alerts_queue)
        health_alerts_queue.clear()
    return alerts


async def analyze_health_alert_with_serena(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Have Serena analyze a health alert and suggest fixes"""
    service = alert.get("alert", {}).get("service", "unknown")
    status = alert.get("alert", {}).get("status", "unknown")
    details = alert.get("alert", {}).get("details", "No details")

    message = f"""HEALTH ALERT RECEIVED - AUTOMATIC ANALYSIS REQUESTED

Service: {service}
Status: {status}
Details: {details}
Timestamp: {alert.get("timestamp", "unknown")}

Please:
1. Check the container status and logs for {service}
2. Diagnose the issue
3. Suggest or take appropriate action (restart if needed, or other remediation)

This is an automated health alert - take appropriate diagnostic action."""

    return await execute_serena_gemma(message, user="system_health_monitor")


def build_tools_prompt() -> str:
    """Build the tools description for prompt-based function calling"""
    tools_desc = []
    for tool in SERENA_TOOLS:
        params = tool.get("parameters", {}).get("properties", {})
        param_desc = ", ".join(
            [
                f"{k}: {v.get('description', 'no description')}"
                for k, v in params.items()
            ]
        )
        tools_desc.append(
            f"- {tool['name']}: {tool['description']}\n  Parameters: {param_desc if param_desc else 'none'}"
        )
    return "\n".join(tools_desc)


def parse_tool_calls(response_text: str) -> List[Dict[str, Any]]:
    """
    Parse tool calls from model responses.
    Supports multiple formats for both Gemma 3 and GLM-4.7:

    Gemma 3 27B format:
    - <tool_call>{"name": "...", "arguments": {...}}</tool_call>

    GLM-4.7 (devstral-2) format:
    - <|tool_call|>{"name": "...", "arguments": {...}}<|tool_call_end|>

    Also supports:
    - tool_code {"name": "...", "arguments": {...}}
    - Action: tool_name\nAction Input: {...}
    """
    tool_calls = []

    # Format 1: Gemma style <tool_call>JSON</tool_call>
    pattern = r"<tool_call>\s*(\{.*?\})\s*</tool_call>"
    matches = re.findall(pattern, response_text, re.DOTALL)

    for match in matches:
        try:
            call = json.loads(match)
            if "name" in call:
                tool_calls.append(
                    {
                        "name": call["name"],
                        "arguments": call.get("arguments", call.get("params", {})),
                    }
                )
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse tool call: {match}")
            continue

    # Format 2: GLM style <|tool_call|>JSON<|tool_call_end|>
    if not tool_calls:
        glm_pattern = r"<\|tool_call\|>\s*(\{.*?\})\s*<\|tool_call_end\|>"
        glm_matches = re.findall(glm_pattern, response_text, re.DOTALL)
        for match in glm_matches:
            try:
                call = json.loads(match)
                if "name" in call:
                    tool_calls.append(
                        {
                            "name": call["name"],
                            "arguments": call.get("arguments", call.get("params", {})),
                        }
                    )
            except json.JSONDecodeError:
                continue

    # Format 3: tool_code JSON style
    if not tool_calls:
        tc_pattern = r"tool_code\s*(\{.*?\})"
        tc_matches = re.findall(tc_pattern, response_text, re.DOTALL)
        for match in tc_matches:
            try:
                call = json.loads(match)
                if "name" in call:
                    tool_calls.append(
                        {
                            "name": call["name"],
                            "arguments": call.get("arguments", call.get("params", {})),
                        }
                    )
            except json.JSONDecodeError:
                continue

    # Format 4: ReAct style - Action: tool_name\nAction Input: {...}
    if not tool_calls:
        action_match = re.search(r"Action:\s*(\w+)", response_text)
        input_match = re.search(r"Action Input:\s*(\{.*?\})", response_text, re.DOTALL)
        if action_match and input_match:
            try:
                args = json.loads(input_match.group(1).strip())
                tool_calls.append(
                    {"name": action_match.group(1).strip(), "arguments": args}
                )
            except json.JSONDecodeError:
                pass

    return tool_calls


# --- REST API Endpoints ---


def get_serena_memory(session_id: str) -> str:
    """Format recent conversation history for Serena's context"""
    # Load from Redis if not in memory
    if session_id not in serena_memory:
        _load_from_redis(session_id)

    if session_id not in serena_memory or not serena_memory[session_id]:
        return ""

    history = serena_memory[session_id][-SERENA_MEMORY_LIMIT:]
    formatted = []
    for entry in history:
        role = entry.get("role", "unknown")
        content = entry.get("content", "")[:500]  # Limit per entry
        formatted.append(f"[{role}]: {content}")

    return "\n".join(formatted)


# --- Redis Persistence Functions ---


def _redis_key(session_id: str, suffix: str) -> str:
    """Generate Redis key for a session"""
    return f"{SERENA_REDIS_PREFIX}{session_id}:{suffix}"


def _save_to_redis(session_id: str):
    """Persist Serena memory state to Redis"""
    if not REDIS_AVAILABLE or not redis_client:
        return

    try:
        # Save memory (without memory_entry references which can't be serialized)
        if session_id in serena_memory:
            memory_data = []
            for entry in serena_memory[session_id]:
                memory_data.append(
                    {
                        "role": entry.get("role"),
                        "content": entry.get("content"),
                        "timestamp": entry.get("timestamp"),
                        "tool_results": entry.get("tool_results", []),
                        "embedding": entry.get("embedding"),
                    }
                )
            redis_client.set(_redis_key(session_id, "memory"), json.dumps(memory_data))

        # Save embeddings
        if session_id in serena_memory_embeddings:
            redis_client.set(
                _redis_key(session_id, "embeddings"),
                json.dumps(serena_memory_embeddings[session_id]),
            )

        # Save pending cache (without memory_entry references)
        if session_id in serena_pending_cache:
            cache_data = []
            for entry in serena_pending_cache[session_id]:
                cache_data.append(
                    {
                        "content": entry.get("content"),
                        "role": entry.get("role"),
                        "timestamp": entry.get("timestamp"),
                    }
                )
            redis_client.set(_redis_key(session_id, "pending"), json.dumps(cache_data))
            redis_client.set(
                _redis_key(session_id, "tokens"),
                str(serena_cache_tokens.get(session_id, 0)),
            )

        # Set expiry (7 days)
        for suffix in ["memory", "embeddings", "pending", "tokens"]:
            redis_client.expire(_redis_key(session_id, suffix), 604800)

    except Exception as e:
        logger.warning(f"Failed to save Serena memory to Redis: {e}")


def _load_from_redis(session_id: str):
    """Load Serena memory state from Redis if available"""
    if not REDIS_AVAILABLE or not redis_client:
        return False

    try:
        # Load memory
        memory_data = redis_client.get(_redis_key(session_id, "memory"))
        if memory_data:
            serena_memory[session_id] = json.loads(memory_data)

        # Load embeddings
        embeddings_data = redis_client.get(_redis_key(session_id, "embeddings"))
        if embeddings_data:
            serena_memory_embeddings[session_id] = json.loads(embeddings_data)

        # Load pending cache
        pending_data = redis_client.get(_redis_key(session_id, "pending"))
        if pending_data:
            serena_pending_cache[session_id] = json.loads(pending_data)

        tokens_data = redis_client.get(_redis_key(session_id, "tokens"))
        if tokens_data:
            serena_cache_tokens[session_id] = int(tokens_data)

        if memory_data or embeddings_data:
            logger.info(f"Loaded Serena memory from Redis for session {session_id}")
            return True

    except Exception as e:
        logger.warning(f"Failed to load Serena memory from Redis: {e}")

    return False


def add_to_serena_memory(
    session_id: str, role: str, content: str, tool_results: list = None
):
    """Add an entry to Serena's conversation memory - caches until token limit then batch embeds"""
    # Load from Redis if this is a new session in memory
    if session_id not in serena_memory:
        _load_from_redis(session_id)

    if session_id not in serena_memory:
        serena_memory[session_id] = []
    if session_id not in serena_memory_embeddings:
        serena_memory_embeddings[session_id] = []
    if session_id not in serena_pending_cache:
        serena_pending_cache[session_id] = []
        serena_cache_tokens[session_id] = 0

    timestamp = datetime.now().isoformat()
    truncated_content = content[:2000]  # Limit stored content

    # Add to active memory (for immediate context)
    entry = {
        "role": role,
        "content": truncated_content,
        "timestamp": timestamp,
        "tool_results": tool_results or [],
        "embedding": None,  # Will be filled when batch embedded
    }
    serena_memory[session_id].append(entry)

    # Trim active memory to limit
    if len(serena_memory[session_id]) > SERENA_MEMORY_LIMIT * 2:
        serena_memory[session_id] = serena_memory[session_id][-SERENA_MEMORY_LIMIT:]

    # Add to pending cache (for batch embedding)
    cache_entry = {
        "content": truncated_content,
        "role": role,
        "timestamp": timestamp,
        "memory_entry": entry,  # Reference to update embedding later
    }
    serena_pending_cache[session_id].append(cache_entry)

    # Estimate tokens (~4 chars per token)
    entry_tokens = len(truncated_content) // 4
    serena_cache_tokens[session_id] += entry_tokens

    logger.debug(
        f"Serena cache for {session_id}: {serena_cache_tokens[session_id]} tokens, {len(serena_pending_cache[session_id])} entries"
    )

    # Save to Redis after each addition
    _save_to_redis(session_id)

    # Trigger batch embed if cache is nearing threshold
    if serena_cache_tokens[session_id] >= SERENA_BATCH_EMBED_THRESHOLD:
        asyncio.create_task(_batch_embed_cache(session_id))


async def _batch_embed_cache(session_id: str):
    """Batch embed all pending cache entries to optimize API calls"""
    if session_id not in serena_pending_cache or not serena_pending_cache[session_id]:
        return

    pending = serena_pending_cache[session_id]
    logger.info(
        f"Batch embedding {len(pending)} entries for session {session_id} (~{serena_cache_tokens.get(session_id, 0)} tokens)"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Process in batches to avoid overwhelming the service
            batch_size = 10
            for i in range(0, len(pending), batch_size):
                batch = pending[i : i + batch_size]

                for cache_entry in batch:
                    try:
                        response = await client.post(
                            f"{EMBEDDING_SERVICE_URL}/embed",
                            json={"text": cache_entry["content"][:1000]},
                        )
                        if response.status_code == 200:
                            data = response.json()
                            embedding = data.get("embedding", [])

                            # Update the memory entry reference
                            if cache_entry.get("memory_entry"):
                                cache_entry["memory_entry"]["embedding"] = embedding

                            # Add to embeddings store for semantic search
                            serena_memory_embeddings[session_id].append(
                                {
                                    "content": cache_entry["content"][:500],
                                    "embedding": embedding,
                                    "timestamp": cache_entry["timestamp"],
                                    "role": cache_entry["role"],
                                }
                            )
                    except Exception as e:
                        logger.warning(f"Failed to embed entry: {e}")
                        continue

                # Small delay between batches
                await asyncio.sleep(0.1)

        # Clear the pending cache after embedding
        serena_pending_cache[session_id] = []
        serena_cache_tokens[session_id] = 0

        # Trim embeddings based on token limit
        _trim_embeddings_to_token_limit(session_id)

        # Save updated state to Redis
        _save_to_redis(session_id)

        logger.info(
            f"Batch embed complete for {session_id}, {len(serena_memory_embeddings.get(session_id, []))} total embeddings"
        )

    except Exception as e:
        logger.error(f"Batch embed failed for {session_id}: {e}")


def _trim_embeddings_to_token_limit(session_id: str):
    """Trim embeddings cache to stay under token limit"""
    if session_id not in serena_memory_embeddings:
        return

    total_chars = sum(
        len(e.get("content", "")) for e in serena_memory_embeddings[session_id]
    )
    approx_tokens = total_chars // 4

    # Remove oldest entries until under limit
    while (
        approx_tokens > SERENA_MEMORY_TOKEN_LIMIT
        and len(serena_memory_embeddings[session_id]) > 1
    ):
        removed = serena_memory_embeddings[session_id].pop(0)
        approx_tokens -= len(removed.get("content", "")) // 4


async def search_serena_memory(
    session_id: str, query: str, top_k: int = 5
) -> List[Dict]:
    """Search Serena's embedded memory for relevant past conversations"""
    # Flush pending cache before searching to include recent conversations
    if session_id in serena_pending_cache and serena_pending_cache[session_id]:
        await _batch_embed_cache(session_id)

    if (
        session_id not in serena_memory_embeddings
        or not serena_memory_embeddings[session_id]
    ):
        return []

    try:
        # Get query embedding
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{EMBEDDING_SERVICE_URL}/embed", json={"text": query}
            )
            if response.status_code != 200:
                return []

            query_embedding = response.json().get("embedding", [])
            if not query_embedding:
                return []

        # Calculate cosine similarity with stored embeddings
        import math

        def cosine_similarity(a, b):
            if not a or not b or len(a) != len(b):
                return 0.0
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(x * x for x in b))
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)

        # Score all memories
        scored = []
        for mem in serena_memory_embeddings[session_id]:
            if mem.get("embedding"):
                score = cosine_similarity(query_embedding, mem["embedding"])
                scored.append((score, mem))

        # Sort by score and return top_k
        scored.sort(key=lambda x: x[0], reverse=True)
        return [{"score": s, **m} for s, m in scored[:top_k]]

    except Exception as e:
        logger.warning(f"Memory search failed: {e}")
        return []


async def get_embedding(text: str) -> List[float]:
    """Get embedding for text from embedding service using OpenAI compatible endpoint"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{EMBEDDING_SERVICE_URL}/v1/embeddings",
                json={"input": text, "model": "qwen3-embedding"},
            )
            if response.status_code == 200:
                data = response.json()
                if "data" in data and len(data["data"]) > 0:
                    return data["data"][0].get("embedding", [])
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
    return []


async def call_conversational_hdc(
    session_id: str, user_id: str, content: str, embedding: List[float]
) -> Dict:
    """Call Conversational HDC service for context"""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(
                f"{CONVERSATIONAL_HDC_URL}/conversation/message",
                json={
                    "session_id": session_id,
                    "user_id": user_id,
                    "content": content,
                    "embedding": embedding,
                },
            )
            if response.status_code == 200:
                data = response.json()
                return data  # Expecting {"hdc_context": str, "resonance": dict}

            return {}

    except Exception as e:
        logger.warning(f"Conversational HDC call failed: {e}")
        return {}


async def ingest_into_geometry_kernel(
    text: str,
    source: str,
    embedding: List[float] = None,
    title: str = "User Interaction",
):
    """
    Async ingestion of content into the Geometry Kernel.
    treats thoughts/state as physical objects in the concept manifold.
    """
    try:
        # Fire and forget - don't block the chat
        if not embedding:
            # Try to get embedding if missing (optional, Kernel handles raw too?)
            # For speed, we might skip or let Kernel handle.
            pass

        payload = {
            "title": title,
            "content_snippet": text[:1000],  # Truncate for snippet
            "vector": embedding if embedding else [],
            "source": source,
            "mode": "store",
        }

        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(f"{GEOMETRY_KERNEL_URL}/geometry/ingest", json=payload)

    except Exception as e:
        # Log summary only to avoid spam
        logger.debug(f"Geometry Kernel Ingestion failed: {e}")


async def update_hdc_state(session_id: str, role: str, content: str, user_id: str):
    """Update HDC service with new message (Fire-and-Forget)"""
    try:
        # 1. Get embedding
        embedding = await get_embedding(content[:1000])  # Embed prefix for speed
        if not embedding:
            return

        # 2. Push to HDC
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{CONVERSATIONAL_HDC_URL}/conversation/message",
                json={
                    "user_id": user_id,
                    "session_id": session_id,
                    "role": role,
                    "content": content,
                    "embedding": embedding,
                },
            )
    except Exception as e:
        logger.warning(f"HDC State update failed: {e}")


async def execute_serena_gemma(
    message: str, user: str = "danexall", session_id: str = None
) -> Dict[str, Any]:
    """Execute Serena Code Agent via agent_service (which routes through llm_gateway)"""
    try:
        # Use persistent session_id based on user - survives container restarts
        # This ensures memory is recovered from Redis on restart
        if not session_id:
            session_id = f"serena_{user}_persistent"  # Persistent ID based on user

        # Store user message in memory (will load from Redis if not in memory)
        add_to_serena_memory(session_id, "user", message)

        # --- REGISTER TOPICS (lightweight, always do) ---
        extract_and_register_topics(session_id, message)

        # --- AGENT-AWARE CONTEXT INJECTION ---
        # Serena is a system/code agent - don't distract with geometry context
        # Only inject geometry context for conversational/research tasks, not system work
        # Check if this is a system operation (git, docker, file ops, etc.)
        system_keywords = [
            "git",
            "commit",
            "push",
            "pull",
            "docker",
            "restart",
            "deploy",
            "build",
            "run",
            "execute",
            "file",
            "folder",
            "directory",
        ]
        is_system_task = any(kw in message.lower() for kw in system_keywords)

        if is_system_task:
            # For system tasks, skip geometry context entirely - Serena stays focused
            enriched_message = f"User Message: {message}"
        else:
            # For research/conversational tasks, optionally add light context
            attention_context = get_attention_context(session_id, top_n=5)

            # --- HDC GEOMETRIC CONTEXT ---
            # Retrieve deep memory context from Vector/HDC space
            hdc_context = await get_hdc_context(session_id, message, user)

            enriched_message = f"User Message: {message}"
            context_parts = []

            if attention_context and "No topics tracked" not in attention_context:
                context_parts.append(attention_context)

            if hdc_context:
                context_parts.append(
                    f"\n[Extended Memory / Geometric Context]:\n{hdc_context}"
                )

            if context_parts:
                enriched_message = (
                    "\n\n".join(context_parts) + f"\n\nUser Message: {message}"
                )

        # Call agent_service instead of using direct genai
        # This routes through llm_gateway for unified model access
        payload = {
            "user_input": enriched_message,  # Now agent-aware context
            "session_id": session_id,
            "user_id": user,
            "model": SERENA_MODEL,  # Use Serena's model (glm:latest via Ollama)
        }

        try:
            final_headers = get_genesis_headers(payload)
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{AGENT_SERVICE_URL}/invoke", json=payload, headers=final_headers
                )

                if response.status_code == 200:
                    result = response.json()
                    assistant_response = result.get("response", "")
                    tool_results = result.get("tools_called", [])

                    # Execute Local UI Tools (Client-Side)
                    # These run in the frontend agent because they are UI/Management specific
                    local_tools = [
                        "list_tasks",
                        "edit_task",
                        "submit_task",
                        "observer_task",
                        "submit_draft_prompt",
                    ]

                    # Check parsed tools from response text if agent_service didn't return them
                    if not tool_results:
                        parsed_tools = parse_tool_calls(assistant_response)
                        if parsed_tools:
                            tool_results.extend(parsed_tools)
                            logger.info(
                                f"Parsed {len(parsed_tools)} local tool calls from response text"
                            )

                    for tool_call in tool_results:
                        if tool_call["name"] in local_tools:
                            logger.info(f"Executing Local UI Tool: {tool_call['name']}")
                            try:
                                ui_result = await execute_local_tool(
                                    tool_call["name"], tool_call["arguments"]
                                )
                                # Append UI result to response for the user to see
                                assistant_response += f"\n\n[UI Tool Result ({tool_call['name']})]:\n{json.dumps(ui_result, indent=2)}"
                            except Exception as e:
                                assistant_response += f"\n\n[UI Tool Error ({tool_call['name']})]: {str(e)}"

                    # Store response in memory
                    add_to_serena_memory(
                        session_id, "assistant", assistant_response, tool_results
                    )

                    # Async update of HDC state (Fire-and-forget)
                    asyncio.create_task(
                        update_hdc_state(session_id, "user", message, user)
                    )
                    asyncio.create_task(
                        update_hdc_state(
                            session_id, "assistant", assistant_response, user
                        )
                    )

                    return {
                        "response": assistant_response,
                        "model": SERENA_MODEL,
                        "status": "success",
                        "tools_called": tool_results,
                        "session_id": session_id,
                    }
                else:
                    error_msg = f"Agent service returned {response.status_code}"
                    logger.error(error_msg)
                    return {"response": f"Serena error: {error_msg}", "status": "error"}

        except Exception as e:
            logger.error(f"Failed to call agent_service: {e}")
            return {
                "response": f"Serena error: Cannot reach agent service - {str(e)}",
                "status": "error",
            }

    except Exception as e:
        logger.error(f"Serena execution failed: {e}")
        import traceback

        traceback.print_exc()
        return {"response": f"Serena error: {str(e)}", "status": "error"}


async def execute_local_tool(name: str, args: Dict[str, Any]) -> Any:
    """Execute UI/Management tools locally in the User Interaction Agent"""

    if name == "list_tasks":
        status_filter = args.get("status_filter")
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"http://maintainer_agents:8090/tasks"
            )  # Assume this exists or will exist
            if resp.status_code == 200:
                tasks = resp.json().get("tasks", [])
                if status_filter:
                    tasks = [t for t in tasks if t.get("status") == status_filter]
                return {"count": len(tasks), "tasks": tasks[:10]}  # Limit to 10
            return {"error": f"Failed to list tasks: {resp.status_code}"}

    elif name == "edit_task":
        task_id = args.get("task_id")
        updates = args.get("updates")
        if isinstance(updates, str):
            updates = json.loads(updates)

        async with httpx.AsyncClient(timeout=10.0) as client:
            # Assume update endpoint
            # In a real scenario, we might need to conform to maintainer API
            return {
                "status": "mock_edited",
                "message": f"Task {task_id} updated with {updates}",
            }

    elif name == "submit_task":
        agent_type = args.get("agent_type")
        operation = args.get("operation")
        params = args.get("params")
        if isinstance(params, str):
            params = json.loads(params)

        payload = {"agent_type": agent_type, "operation": operation, "params": params}

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"http://maintainer_agents:8090/execute", json=payload
            )
            return resp.json()

    elif name == "observer_task":
        query = args.get("query")
        # Route to Observer Agent (likely via agent_service or distinct endpoint)
        # For now, we mock or route to agent_service as 'observer'
        return {"status": "observed", "message": f"Observer noted: {query}"}

    elif name == "submit_draft_prompt":
        draft_text = args.get("draft_text")
        action = args.get("action")
        # Logic to save to a database or specific file for the UI to pick up
        # For now, log it
        logger.info(f"DRAFT PROMPT SUBMITTED: [{action}] {draft_text}")
        return {"status": "saved", "action": action, "length": len(draft_text)}

    return {"error": f"Unknown local tool: {name}"}


def parse_suggestions(response_text: str, session_id: str) -> List[Dict[str, Any]]:
    """Parse proactive suggestions from Serena's response"""
    suggestions = []

    pattern = r"<suggestion>\s*(\{.*?\})\s*</suggestion>"
    matches = re.findall(pattern, response_text, re.DOTALL)

    for match in matches:
        try:
            suggestion = json.loads(match)
            if "action" in suggestion:
                action_name = suggestion.get("action", "").lower()

                # Check if this is a read-only action - no approval needed
                is_read_only = any(ro in action_name for ro in READ_ONLY_ACTIONS)

                if is_read_only:
                    # Read actions don't need approval - auto-approve
                    suggestion["requires_approval"] = False
                    suggestion["auto_approved"] = True
                    logger.info(f"Auto-approving read-only action: {action_name}")
                else:
                    # Write/modify actions need approval
                    approval_id = str(uuid.uuid4())[:8]
                    suggestion["approval_id"] = approval_id
                    suggestion["session_id"] = session_id
                    suggestion["requires_approval"] = True

                    pending_approvals[approval_id] = {
                        "action": suggestion.get("action"),
                        "details": suggestion,
                        "session_id": session_id,
                        "timestamp": datetime.now().isoformat(),
                    }

                suggestions.append(suggestion)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse suggestion: {match}")
            continue

    return suggestions


async def approve_serena_action(
    approval_id: str, approved: bool = True
) -> Dict[str, Any]:
    """Approve or reject a pending Serena action"""
    if approval_id not in pending_approvals:
        return {"error": f"Approval ID {approval_id} not found", "success": False}

    action_info = pending_approvals.pop(approval_id)

    if not approved:
        return {
            "message": "Action rejected",
            "action": action_info["action"],
            "success": True,
        }

    # Execute the approved action
    action = action_info["action"]
    details = action_info.get("details", {})
    session_id = action_info.get("session_id")

    # Map common actions to tool calls
    if action == "check_logs":
        container = details.get("container", details.get("service", ""))
        result = await serena_mcp.call_tool(
            "container_logs", {"container_name": container}
        )
    elif action == "restart_service":
        service = details.get("service", "")
        # This would need an MCP tool for restart
        result = {
            "message": f"Restart of {service} would be executed here",
            "success": True,
        }
    else:
        result = {"message": f"Unknown action: {action}", "success": False}

    return {"action": action, "result": result, "success": True}


@app.get("/")
async def root():
    """Serve the ARCA terminal interface."""
    static_file_path = os.path.join(static_dir, "index.html")
    if not os.path.isfile(static_file_path):
        return JSONResponse(
            status_code=404, content={"message": "Static UI not found."}
        )
    return FileResponse(static_file_path)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "user_interaction_agent",
        "version": "3.2.2",
        "features": {
            "psutil": PSUTIL_AVAILABLE,
            "docker": DOCKER_AVAILABLE,
            "gemini": True,
            "mcp": True,
            "health_alerts": health_subscription_active,
        },
    }


@app.get("/api/health-alerts")
async def get_health_alerts():
    """Get pending health alerts that Serena will analyze"""
    with health_alert_lock:
        alerts = list(health_alerts_queue)
    return {
        "alerts": alerts,
        "count": len(alerts),
        "subscription_active": health_subscription_active,
    }


@app.post("/api/health-alerts/analyze")
async def trigger_health_analysis():
    """Manually trigger Serena to analyze pending health alerts"""
    alerts = await get_pending_health_alerts()
    results = []
    for alert in alerts:
        result = await analyze_health_alert_with_serena(alert)
        results.append({"alert": alert, "analysis": result})
    return {"analyzed": len(results), "results": results}


@app.get("/api/telemetry")
async def get_telemetry():
    """Get system telemetry metrics"""
    if telemetry_cache["last_update"]:
        return {
            "telemetry": telemetry_cache["data"],
            "timestamp": telemetry_cache["last_update"],
        }
    else:
        # First request, get fresh data
        data = get_system_telemetry()
        return {"telemetry": data, "timestamp": datetime.utcnow().isoformat()}


@app.post("/api/chat")
async def chat_api(request: ChatRequest):
    """REST API for chat"""
    payload = {
        "user_input": request.message,
        "session_id": request.session_id or str(uuid.uuid4()),
        "user_id": request.user_id,
    }

    # --- OCI Holographic Loop (Living Mind) ---
    try:
        # 1. Get Embedding (Dense Vector) - Proprioception
        embedding = await get_embedding(request.message)

        if embedding:
            # 2. ASYNC GEOMETRIC INGESTION (User into Manifold)
            # Create a task so we don't block the response
            asyncio.create_task(
                ingest_into_geometry_kernel(
                    request.message,
                    source="user_interaction",
                    embedding=embedding,
                    title=f"User Thought ({request.session_id[:6]})",
                )
            )

            # 3. Send to OCI (Physics/HDC) and Get Context - Dream/Resonate
            hdc_result = await call_conversational_hdc(
                session_id=payload["session_id"],
                user_id=payload["user_id"],
                content=request.message,
                embedding=embedding,
            )

            if hdc_result:
                # 3. Inject Context into Prompt (Influence)
                context_str = hdc_result.get("hdc_context", "")
                resonance = hdc_result.get("resonance", {})

                # THRESHOLDING LOGIC: Bubble up to Consciousness
                conscious_flags = []

                # Check Topics
                topics = resonance.get("topics", [])
                for topic in topics:
                    name = topic.get("name")
                    score = topic.get("score", 0)
                    if score > 0.6:  # High Resonance Threshold
                        conscious_flags.append(
                            f"SIGNAL: Topic '{name}' is RESONATING (Score: {score:.2f}). Consider researching this."
                        )

                # Check Sentiment
                # (Can add sentiment logic here)

                # Construct Final Injection
                injection_parts = [context_str]
                if conscious_flags:
                    injection_parts.append(
                        "\n!!! SUBCONSCIOUS ALERTS (HIGH RELEVANCE) !!!"
                    )
                    injection_parts.extend(conscious_flags)
                    injection_parts.append("!!! END ALERTS !!!\n")

                final_injection = "\n".join(injection_parts)
                payload["user_input"] = f"{final_injection}\n\nUser: {request.message}"

                logger.info(
                    f"Injected HDC Context with {len(conscious_flags)} alerts for session {payload['session_id']}"
                )

    except Exception as e:
        logger.error(f"Holographic Loop Error (Non-blocking): {e}")

    response = await call_agent_service(payload)

    # --- CURIOSITY FEEDBACK LOOP (SATISFACTION) ---
    try:
        if redis_client and "output" in response:
            agent_text = response.get("output", "").lower()

            # Check if currently active concepts were mentioned
            raw_data = redis_client.get("arca:blackboard:working_model")
            if raw_data:
                model = json.loads(raw_data)
                objects = model.get("objects", [])

                for obj in objects[:5]:
                    name = obj.get("id", "Unnamed")
                    # If Agent mentioned the concept, we are satisfied
                    if name.lower() in agent_text:
                        # Mark satisfied for 1 hour (3600s)
                        redis_client.setex(
                            f"arca:curiosity:satisfied:{name}", 3600, "1"
                        )
                        logger.info(f"Curiosity Satisfied for concept: {name}")

    except Exception as e:
        logger.error(f"Error in Curiosity Feedback Loop: {e}")

    return response


@app.post("/api/serena/execute")
async def execute_serena_api(request: SerenaRequest):
    """Execute Serena code analysis via REST API"""
    result = await execute_serena_gemma(request.command, "default")
    return result


# --- ARCA → Serena Prompt Builder ---
# Allows ARCA to build a prompt collaboratively with the user before submitting to Serena
serena_prompt_drafts: Dict[
    str, Dict[str, Any]
] = {}  # session_id -> {"prompt": str, "context": list, "status": str}


class SerenaPromptDraft(BaseModel):
    """Request for building/editing Serena prompt"""

    session_id: str
    action: str  # "create", "append", "edit", "view", "submit", "clear"
    content: Optional[str] = None
    context_files: Optional[List[str]] = None


@app.post("/api/serena/prompt-builder")
async def serena_prompt_builder(request: SerenaPromptDraft):
    """
    ARCA's Serena Prompt Builder - Build prompts collaboratively before submission.

    Actions:
    - create: Start a new prompt draft
    - append: Add to the existing prompt
    - edit: Replace the current prompt
    - view: View the current draft
    - submit: Submit to Serena
    - clear: Clear the draft
    """
    session_id = request.session_id

    if request.action == "create":
        serena_prompt_drafts[session_id] = {
            "prompt": request.content or "",
            "context": request.context_files or [],
            "status": "draft",
            "created_at": datetime.utcnow().isoformat(),
        }
        return {"status": "created", "draft": serena_prompt_drafts[session_id]}

    elif request.action == "append":
        if session_id not in serena_prompt_drafts:
            serena_prompt_drafts[session_id] = {
                "prompt": "",
                "context": [],
                "status": "draft",
            }
        serena_prompt_drafts[session_id]["prompt"] += "\n" + (request.content or "")
        if request.context_files:
            serena_prompt_drafts[session_id]["context"].extend(request.context_files)
        return {"status": "appended", "draft": serena_prompt_drafts[session_id]}

    elif request.action == "edit":
        if session_id not in serena_prompt_drafts:
            return {"error": "No draft exists for this session"}
        serena_prompt_drafts[session_id]["prompt"] = request.content or ""
        return {"status": "edited", "draft": serena_prompt_drafts[session_id]}

    elif request.action == "view":
        if session_id not in serena_prompt_drafts:
            return {"status": "no_draft", "draft": None}
        return {"status": "viewing", "draft": serena_prompt_drafts[session_id]}

    elif request.action == "submit":
        if session_id not in serena_prompt_drafts:
            return {"error": "No draft to submit"}

        draft = serena_prompt_drafts[session_id]
        prompt = draft["prompt"]

        # Add context files if any
        if draft.get("context"):
            context_text = "\n\n--- Context Files ---\n"
            for file_path in draft["context"]:
                try:
                    result = await serena_mcp.call_tool(
                        "read_file", {"path": file_path}
                    )
                    if result.get("success"):
                        content = result.get("result", {}).get("content", "")[
                            :5000
                        ]  # Limit
                        context_text += f"\n[{file_path}]:\n{content}\n"
                except Exception as e:
                    context_text += f"\n[{file_path}]: Error reading - {e}\n"
            prompt = context_text + "\n\n--- Task ---\n" + prompt

        # Submit to Serena
        result = await execute_serena_gemma(
            prompt,
            user="arca_prompt_builder",
            session_id=f"serena_from_arca_{session_id}",
        )

        # Mark as submitted
        serena_prompt_drafts[session_id]["status"] = "submitted"
        serena_prompt_drafts[session_id]["submitted_at"] = datetime.utcnow().isoformat()
        serena_prompt_drafts[session_id]["result"] = result.get("response", "")[:1000]

        return {"status": "submitted", "serena_response": result}

    elif request.action == "clear":
        if session_id in serena_prompt_drafts:
            del serena_prompt_drafts[session_id]
        return {"status": "cleared"}

    return {"error": f"Unknown action: {request.action}"}


@app.get("/api/serena/prompt-builder/{session_id}")
async def get_serena_prompt_draft(session_id: str):
    """Get current Serena prompt draft for a session"""
    if session_id in serena_prompt_drafts:
        return {"status": "found", "draft": serena_prompt_drafts[session_id]}
    return {"status": "no_draft", "draft": None}


@app.post("/api/genesis/thread/{thread_id}/pause")
async def pause_thread(thread_id: str):
    """Pause Genesis thread"""
    if thread_id in genesis_threads:
        genesis_threads[thread_id]["paused"] = True
        genesis_threads[thread_id]["status"] = "paused"
        return {"status": "paused", "thread_id": thread_id}
    return {"error": "Thread not found", "thread_id": thread_id}


@app.post("/api/genesis/thread/{thread_id}/resume")
async def resume_thread(thread_id: str):
    """Resume Genesis thread"""
    if thread_id in genesis_threads:
        genesis_threads[thread_id]["paused"] = False
        genesis_threads[thread_id]["status"] = "running"
        return {"status": "running", "thread_id": thread_id}
    return {"error": "Thread not found", "thread_id": thread_id}


@app.get("/api/genesis/thread/{thread_id}/status")
async def get_thread_status(thread_id: str):
    """Get Genesis thread status"""
    if thread_id in genesis_threads:
        return genesis_threads[thread_id]
    return {"error": "Thread not found", "thread_id": thread_id}


@app.post("/api/reasoning/analyze")
async def analyze_with_reasoning(request: ReasoningRequest):
    """Analyze conversation with MiniMax reasoning"""
    session_id = request.session_id or "default"
    history = conversation_history.get(session_id, [])

    if not history:
        return {"error": "No conversation history for session"}

    try:
        workflow = GeminiReasoningWorkflow(history, mcp_url=MCP_SERVER_URL)
        result = await workflow.invoke_reasoning_with_tools(
            context_depth=request.context_depth
        )
        return result
    except Exception as e:
        logger.error(f"Error in Gemini reasoning: {e}")
        return {"error": str(e), "status": "failed"}


@app.get("/api/reasoning/proposals")
async def list_proposals():
    """List all reasoning proposals"""
    # TODO: Implement proposal storage/retrieval
    return {"proposals": [], "message": "Proposal storage not yet implemented"}


@app.post("/api/reasoning/approve/{proposal_id}")
async def approve_proposal(proposal_id: str):
    """Approve a reasoning proposal"""
    # TODO: Implement proposal approval workflow
    return {"status": "not_implemented", "proposal_id": proposal_id}


# --- Serena Action Approval API ---
@app.get("/api/serena/pending-actions")
async def list_pending_actions():
    """List all pending Serena actions awaiting approval"""
    return {
        "pending_actions": [
            {
                "approval_id": aid,
                "action": info["action"],
                "details": info["details"],
                "timestamp": info["timestamp"],
            }
            for aid, info in pending_approvals.items()
        ]
    }


@app.post("/api/serena/approve/{approval_id}")
async def approve_action(approval_id: str, approved: bool = True):
    """Approve or reject a pending Serena action"""
    result = await approve_serena_action(approval_id, approved)
    return result


@app.get("/api/serena/memory/{session_id}")
async def get_session_memory(session_id: str):
    """Get Serena's conversation memory for a session"""
    if session_id not in serena_memory:
        return {
            "session_id": session_id,
            "memory": [],
            "message": "No memory found for this session",
        }
    return {
        "session_id": session_id,
        "memory": serena_memory[session_id],
        "count": len(serena_memory[session_id]),
    }


@app.delete("/api/serena/memory/{session_id}")
async def clear_session_memory(session_id: str):
    """Clear Serena's conversation memory for a session"""
    if session_id in serena_memory:
        serena_memory[session_id] = []
    return {"session_id": session_id, "message": "Memory cleared"}


# --- Project Visualization APIs ---
@app.get("/api/kernel/document-state")
async def get_kernel_document_state():
    """Get the current document processing state from the kernel via Redis"""
    try:
        if not redis_client:
            return {"error": "Redis unavailable", "status": "disconnected"}

        # Fetch document processing state from Redis
        working_model = redis_client.get("arca:blackboard:working_model")
        doc_chunks = redis_client.keys("arca:doc:chunks:*")
        doc_vectors = redis_client.keys("arca:doc:vectors:*")

        result = {
            "input": None,
            "chunks": [],
            "vectors": {"count": 0, "dimensions": 384, "model": "nomic-embed-text"},
            "redis_keys": [],
        }

        if working_model:
            model_data = json.loads(working_model)
            result["input"] = {
                "filename": model_data.get("gravity_well", {}).get(
                    "concept", "document"
                ),
                "size": len(working_model),
                "preview": str(model_data.get("objects", [])[:2])[:200],
            }
            result["chunks"] = [
                {"id": obj.get("id"), "tokens": len(obj.get("desc", "").split())}
                for obj in model_data.get("objects", [])[:10]
            ]
            result["vectors"]["count"] = len(model_data.get("objects", []))

        # Collect all relevant Redis keys
        all_keys = redis_client.keys("arca:*")
        result["redis_keys"] = [
            k.decode() if isinstance(k, bytes) else k for k in all_keys[:50]
        ]

        return result

    except Exception as e:
        logger.error(f"Document state fetch failed: {e}")
        return {"error": str(e), "status": "error"}


@app.get("/api/neo4j/architecture")
async def get_neo4j_architecture():
    """Get the system architecture from Neo4j for Mermaid visualization"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Query Neo4j via MCP server
            cypher_query = """
            MATCH (s:System)
            OPTIONAL MATCH (s)-[r:CONNECTS_TO|IMPLEMENTS|REGISTERED_IN]->(t)
            RETURN s.id as source_id, s.type as source_type, s.role as source_role,
                   type(r) as relationship, t.id as target_id, t.type as target_type
            LIMIT 100
            """
            resp = await client.post(
                f"{MCP_SERVER_URL}/neo4j/query",
                json={"query": cypher_query},
                timeout=10.0,
            )
            if resp.status_code == 200:
                return resp.json()
            return {
                "nodes": [],
                "relationships": [],
                "error": f"Neo4j returned {resp.status_code}",
            }
    except Exception as e:
        logger.warning(f"Neo4j architecture fetch failed: {e}")
        # Return a default structure if Neo4j is unavailable
        return {
            "nodes": [
                {"id": "redis", "type": "database", "role": "blackboard"},
                {"id": "neo4j", "type": "database", "role": "knowledge_graph"},
                {"id": "agent_service", "type": "service", "role": "orchestration"},
                {"id": "mcp_server", "type": "service", "role": "tools"},
            ],
            "relationships": [
                {"source": "agent_service", "target": "redis", "type": "CONNECTS_TO"},
                {"source": "agent_service", "target": "neo4j", "type": "CONNECTS_TO"},
                {
                    "source": "agent_service",
                    "target": "mcp_server",
                    "type": "CONNECTS_TO",
                },
            ],
            "note": "Fallback data - Neo4j unavailable",
        }


# --- WebSocket Endpoint with Full Message Handling ---
# --- Geometry Kernel Proxy ---
@app.get("/api/geometry/state")
async def get_geometry_state():
    """Proxy to MCP Server Geometry State"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Note: mcp_server is on port 8086
            resp = await client.get(f"{MCP_SERVER_URL}/geometry/state")
            if resp.status_code == 200:
                return resp.json()
            return {
                "error": f"Geometry Kernel returned {resp.status_code}",
                "status": "error",
            }
    except Exception as e:
        logger.error(f"Geometry proxy state failed: {e}")
        return {"error": str(e), "status": "error"}


@app.get("/api/system/metrics")
async def get_system_metrics():
    """Get system resource usage and model activity metrics"""
    try:
        telemetry = get_system_telemetry()

        cpu_val = 0
        if telemetry.get("cpu", "N/A") != "N/A":
            cpu_val = float(telemetry["cpu"].replace("%", ""))

        mem_val = 0
        if telemetry.get("memory", "N/A") != "N/A":
            mem_val = float(telemetry["memory"].replace("%", ""))

        disk_val = 0
        if PSUTIL_AVAILABLE:
            disk_val = psutil.disk_usage("/").percent

        # Real Inference Metrics from Redis
        inference_data = {"active": False, "tps": 0, "buffer": 0}
        if redis_client:
            try:
                # LLM performance metrics from native llama.cpp
                perf_raw = redis_client.get("arca:telemetry:llm:tps")
                if perf_raw:
                    inference_data["tps"] = float(perf_raw)
                    inference_data["active"] = inference_data["tps"] > 0

                buffer_raw = redis_client.get("arca:telemetry:llm:buffer")
                if buffer_raw:
                    inference_data["buffer"] = int(buffer_raw)
            except Exception:
                pass

        # Fetch Neural System Vitals
        neural_vitals = {
            "mamba_pulse_l2": 0.0,
            "kuramoto_coherence": 0.0,
            "hamiltonian_energy": 0.0,
            "hopfield_capacity": 0,
            "gate_entropy": 0.0,
            "expert_load": [0.0, 0.0, 0.0, 0.0]
        }
        try:
            import httpx
            # Assume neural system is accessible here
            async with httpx.AsyncClient(timeout=2.0) as client:
                # We use the internal Docker hostname or localhost if running locally
                ns_url = os.getenv("NEURAL_SYSTEM_URL", "http://neural_system:8086")
                resp = await client.get(f"{ns_url}/system/vitals")
                if resp.status_code == 200:
                    neural_vitals = resp.json()
        except Exception as e:
            logger.debug(f"Could not fetch neural vitals: {e}")

        # Health Alerts for System Status Indicator
        health_alert = "System Normal"
        if redis_client:
            try:
                # Check for critical alerts in history
                alerts_raw = redis_client.lrange("arca:health:alerts:history", 0, 0)
                if alerts_raw:
                    latest = json.loads(alerts_raw[0])
                    health_alert = f"{latest.get('service', 'System')}: {latest.get('details', 'Condition Alert')}"
            except Exception:
                pass

        return {
            "cpu": cpu_val,
            "memory": mem_val,
            "disk": disk_val,
            "inference": inference_data,
            "neural_vitals": neural_vitals,
            "embedding": {"active": False, "tps": 0, "buffer": 0},
            "vision": {"active": False, "tps": 0, "buffer": 0},
            "geometry": {"active": False},
            "health_status": health_alert,
        }
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        return {"cpu": 0, "memory": 0, "disk": 0, "health_status": "Metrics Error"}


@app.get("/api/geometry/render")
async def get_geometry_render(mode: str = "system"):
    """Proxy to MCP Server Geometry Render Data"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{MCP_SERVER_URL}/geometry/render", headers={"X-Geometry-Mode": mode}
            )
            if resp.status_code == 200:
                return resp.json()
            return {
                "error": f"Geometry Kernel returned {resp.status_code}",
                "status": "error",
            }
    except Exception as e:
        logger.error(f"Geometry proxy render failed: {e}")
        return {"error": str(e), "status": "error"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint with complete message type support"""
    session_id = str(uuid.uuid4())
    await manager.connect(websocket, session_id)

    # Initialize conversation history
    conversation_history[session_id] = []

    await manager.send_message(
        {"type": "session_created", "session_id": session_id}, session_id
    )

    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            message_type = message_data.get("type")

            # Handle ping/pong (keepalive)
            if message_type == "pong":
                # Client responded to our ping, connection is alive
                continue

            if message_type == "ping":
                # Client is checking if we're alive
                await manager.send_message(
                    {"type": "pong", "timestamp": datetime.utcnow().isoformat()},
                    session_id,
                )
                continue

            # Handle telemetry requests
            if message_type == "telemetry_request":
                await manager.send_message(
                    {"type": "telemetry_update", "data": telemetry_cache["data"]},
                    session_id,
                )
                continue

            # Handle thread status requests
            elif message_type == "thread_status_request":
                thread_id = message_data.get("thread_id")
                if thread_id and thread_id in genesis_threads:
                    await manager.send_message(
                        {
                            "type": "genesis_thread_update",
                            "data": genesis_threads[thread_id],
                        },
                        session_id,
                    )
                else:
                    await manager.send_message(
                        {
                            "type": "genesis_thread_update",
                            "data": {"status": "no_active_thread"},
                        },
                        session_id,
                    )
                continue

            # Handle pause thread
            elif message_type == "pause_thread":
                thread_id = message_data.get("thread_id")
                if thread_id:
                    genesis_threads[thread_id] = genesis_threads.get(thread_id, {})
                    genesis_threads[thread_id]["paused"] = True
                    genesis_threads[thread_id]["status"] = "paused"
                    await manager.send_message(
                        {
                            "type": "system_status",
                            "message": f"Thread {thread_id} paused",
                        },
                        session_id,
                    )
                continue

            # Handle resume thread
            elif message_type == "resume_thread":
                thread_id = message_data.get("thread_id")
                if thread_id:
                    genesis_threads[thread_id] = genesis_threads.get(thread_id, {})
                    genesis_threads[thread_id]["paused"] = False
                    genesis_threads[thread_id]["status"] = "running"
                    await manager.send_message(
                        {
                            "type": "system_status",
                            "message": f"Thread {thread_id} resumed",
                        },
                        session_id,
                    )
                continue

            # Handle Serena reset
            elif message_type == "serena_reset":
                # Clear Serena memory for this session
                if session_id in serena_memory:
                    serena_memory[session_id] = []
                await manager.send_message(
                    {
                        "type": "serena_message",
                        "role": "system",
                        "content": "Serena session reset - conversation memory cleared",
                    },
                    session_id,
                )
                continue

            # Handle Serena action approval
            elif message_type == "serena_approve":
                approval_id = message_data.get("approval_id")
                approved = message_data.get("approved", True)
                if approval_id:
                    result = await approve_serena_action(approval_id, approved)
                    await manager.send_message(
                        {
                            "type": "serena_message",
                            "role": "system",
                            "content": f"Action {'approved and executed' if approved else 'rejected'}: {json.dumps(result)}",
                        },
                        session_id,
                    )
                continue

            # Handle read_file request for Document Viewer
            elif message_type == "read_file_request":
                path = message_data.get("uri") or message_data.get("path")
                if path:
                    # Notify client loading started
                    await manager.send_message(
                        {
                            "type": "status",
                            "content": f"Reading file: {os.path.basename(path)}...",
                        },
                        session_id,
                    )

                    # Use Serena's MCP client which has system access
                    # Note: Using read_file tool
                    result = await serena_mcp.call_tool("read_file", {"path": path})

                    content = ""
                    success = result.get("success", False)

                    if success:
                        mcp_res = result.get("result", {})
                        # Handle MCP content list format
                        if isinstance(mcp_res, dict) and "content" in mcp_res:
                            items = mcp_res["content"]
                            if isinstance(items, list) and len(items) > 0:
                                content = items[0].get("text", "")
                            else:
                                content = str(items)
                        # Handle direct text return (some tools)
                        elif isinstance(mcp_res, str):
                            content = mcp_res
                        else:
                            content = str(mcp_res)
                    else:
                        content = f"Error reading file: {result.get('error', 'Unknown error')}"

                    await manager.send_message(
                        {
                            "type": "file_content",
                            "content": content,
                            "filename": os.path.basename(path),
                            "path": path,
                            "success": success,
                        },
                        session_id,
                    )
                continue

            # Handle chat/message requests
            elif message_type == "serena_request":
                # Handle Serena via Gemma 27b
                user_input = (
                    message_data.get("message") or message_data.get("command") or ""
                )
                if not user_input:
                    continue

                await manager.send_message(
                    {
                        "type": "serena_message",
                        "role": "system",
                        "content": "Serena is thinking...",
                    },
                    session_id,
                )

                try:
                    # Pass session_id for conversation memory
                    serena_result = await execute_serena_gemma(
                        user_input, message_data.get("user", "default"), session_id
                    )
                    response_content = serena_result.get(
                        "response", "No response from Serena"
                    )

                    # Build response message
                    response_msg = {
                        "type": "serena_message",
                        "role": "assistant",
                        "content": response_content,
                        "model": serena_result.get("model", SERENA_MODEL),
                    }

                    # Include suggestions if any
                    suggestions = serena_result.get("suggestions", [])
                    if suggestions:
                        response_msg["suggestions"] = suggestions
                        # Append suggestion info to content
                        suggestion_text = "\n\n**Suggestions:**\n"
                        for s in suggestions:
                            suggestion_text += f"- {s.get('action')}: {s.get('reason', 'No reason given')}"
                            if s.get("requires_approval"):
                                suggestion_text += f" [Approve: {s.get('approval_id')}]"
                            suggestion_text += "\n"
                        response_msg["content"] += suggestion_text

                    await manager.send_message(response_msg, session_id)

                    # Parse and execute tools from response content
                    # Handles formats:
                    # 1. ```tool_code name(args)``` or tool_code name(args)
                    # --- Serena Tool Execution Loop ---
                    # Parse and execute tools using unified parser (supports GLM-4.7 and Gemma formats)
                    try:
                        # Use unified parse_tool_calls which handles:
                        # - <tool_call> (Gemma)
                        # - <|tool_call|> (GLM-4.7)
                        # - tool_code
                        # - Action/Action Input (ReAct)
                        tool_calls_parsed = parse_tool_calls(response_content)
                        tool_matches = [
                            (call["name"], call["arguments"])
                            for call in tool_calls_parsed
                        ]

                        # Legacy format fallback: tool_code name(args)
                        if not tool_matches:
                            func_pattern = r"tool_code\s+(\w+)\((.*?)\)"
                            func_matches = re.findall(func_pattern, response_content)
                            for tool_name, args_str in func_matches:
                                try:
                                    args_dict = eval(f"dict({args_str})")
                                    tool_matches.append((tool_name, args_dict))
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to parse func-style args: {e}"
                                    )

                        for tool_name, args_dict in tool_matches:
                            logger.info(
                                f"Serena Tool Call: {tool_name} args={args_dict}"
                            )

                            # Notify user of execution
                            await manager.send_message(
                                {
                                    "type": "status",
                                    "content": f"Serena executing tool: {tool_name}...",
                                },
                                session_id,
                            )

                            # --- Handle Serena Maintainer Delegation ---
                            if tool_name in [
                                "delegate_to_docker_maintainer",
                                "delegate_to_git_maintainer",
                            ]:
                                maintainer_type = (
                                    "docker" if "docker" in tool_name else "git"
                                )
                                task = args_dict.get("task", "")
                                params = args_dict.get("params", {})

                                # Call maintainer_agents service
                                try:
                                    maintainer_url = os.environ.get(
                                        "MAINTAINER_AGENTS_URL",
                                        "http://maintainer_agents:8087",
                                    )
                                    async with httpx.AsyncClient(
                                        timeout=60.0
                                    ) as client:
                                        response = await client.post(
                                            f"{maintainer_url}/invoke",
                                            json={
                                                "agent_type": maintainer_type,
                                                "operation": task,
                                                "params": params,
                                            },
                                        )
                                        tool_result = (
                                            response.json()
                                            if response.status_code == 200
                                            else {"error": response.text}
                                        )
                                except Exception as e:
                                    tool_result = {
                                        "error": f"Maintainer delegation failed: {e}"
                                    }
                            else:
                                # Execute tool via MCP
                                tool_result = await serena_mcp.call_tool(
                                    tool_name, args_dict
                                )

                            # Send result back to chat (HIDDEN from user, used for memory)
                            result_content = json.dumps(
                                tool_result.get("result", tool_result), indent=2
                            )
                            await manager.send_message(
                                {
                                    "type": "internal_log",
                                    "role": "system",
                                    "name": tool_name,
                                    "content": f"Tool Output ({tool_name}):\n```json\n{result_content}\n```",
                                },
                                session_id,
                            )

                            # Update memory with tool result
                            add_to_serena_memory(
                                session_id,
                                "system",
                                f"Tool Output ({tool_name}): {result_content}",
                            )

                    except Exception as e:
                        logger.error(f"Serena tool execution loop failed: {e}")

                except Exception as e:
                    logger.error(f"Serena error: {e}")
                    await manager.send_message(
                        {
                            "type": "serena_message",
                            "role": "system",
                            "content": f"Serena error: {str(e)}",
                        },
                        session_id,
                    )
                continue

            # --- ARCA Agent Handler (Main Identity) ---
            # Handles standard chat interactions where the system speaks as ARCA
            elif message_type in [
                "chat",
                "message",
                "genesis_message",
                "arca_request",
                "genesis_request",
            ]:
                user_input = (
                    message_data.get("message")
                    or message_data.get("command")
                    or message_data.get("objective")
                )
                if not user_input:
                    continue

                # Store in conversation history
                conversation_history[session_id].append(
                    {
                        "role": "user",
                        "content": user_input,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

                payload = {
                    "user_input": user_input,
                    "session_id": session_id,
                    "user_id": message_data.get("user", "default"),
                }

                # Notify client
                await manager.send_message(
                    {"type": "status", "content": "Processing request..."}, session_id
                )

                try:
                    # Start keepalive task for long-running requests
                    keepalive_task = asyncio.create_task(
                        send_keepalives_during_processing(session_id)
                    )

                    try:
                        # Call backend service (ARCA)
                        agent_response = await call_agent_service(payload)
                        logger.info(
                            f"ARCA response received for {session_id}: {str(agent_response)[:100]}"
                        )
                    finally:
                        # Stop keepalive once we have a response
                        keepalive_task.cancel()
                        try:
                            await keepalive_task
                        except asyncio.CancelledError:
                            pass

                    response_content = agent_response.get(
                        "response", "No content received."
                    )
                    logger.info(
                        f"Sending response to WebSocket {session_id}, connected={manager.is_connected(session_id)}"
                    )

                    # Store assistant response
                    conversation_history[session_id].append(
                        {
                            "role": "assistant",
                            "content": response_content,
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                    )

                    # Determine response type - default to genesis_message for chat
                    response_type = "genesis_message"
                    if message_type == "serena_request":
                        response_type = "serena_message"

                    # --- Pythia Raw Output (Option B: show both raw vector
                    #     interpretation AND LLM-synthesized response) ---
                    pythia_raw = agent_response.get("pythia_raw")
                    if pythia_raw:
                        await manager.send_message(
                            {
                                "type": "pythia_insight",
                                "role": "pythia",
                                "content": pythia_raw,
                                "energy": agent_response.get("pythia_vector_energy", 0),
                                "processing_ms": agent_response.get("pythia_processing_ms", 0),
                            },
                            session_id,
                        )

                    await manager.send_message(
                        {
                            "type": response_type,
                            "role": "assistant",
                            "content": response_content,
                            "metadata": agent_response,
                        },
                        session_id,
                    )
                    logger.info(f"Response sent to {session_id}")

                    # --- ARCA Tool Execution Loop ---
                    # Parse and execute tools from response content using unified parser
                    # Supports: <tool_call>, <|tool_call|>, tool_code, Action/Action Input
                    try:
                        # Use the unified parse_tool_calls function
                        tool_calls_parsed = parse_tool_calls(response_content)

                        # Also check for legacy tool_code format
                        tool_matches = [
                            (call["name"], call["arguments"])
                            for call in tool_calls_parsed
                        ]

                        # Legacy format support: tool_code name(args)
                        if not tool_matches:
                            func_pattern = r"tool_code\s+(\w+)\((.*?)\)"
                            func_matches = re.findall(func_pattern, response_content)
                            for tool_name, args_str in func_matches:
                                try:
                                    args_dict = eval(f"dict({args_str})")
                                    tool_matches.append((tool_name, args_dict))
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to parse func-style args: {e}"
                                    )

                        for tool_name, args_dict in tool_matches:
                            logger.info(f"ARCA Tool Call: {tool_name} args={args_dict}")

                            # Notify user
                            await manager.send_message(
                                {
                                    "type": "status",
                                    "content": f"ARCA executing tool: {tool_name}...",
                                },
                                session_id,
                            )

                            # --- Handle ARCA→Serena Coordination Tools ---
                            if tool_name == "serena_draft_prompt":
                                # Create a new Serena prompt draft
                                serena_prompt_drafts[session_id] = {
                                    "prompt": args_dict.get("initial_content", ""),
                                    "context": args_dict.get("context_files", []),
                                    "status": "draft",
                                    "created_at": datetime.utcnow().isoformat(),
                                }
                                tool_result = {
                                    "success": True,
                                    "result": {
                                        "status": "draft_created",
                                        "draft": serena_prompt_drafts[session_id],
                                    },
                                }

                            elif tool_name == "serena_append_prompt":
                                if session_id not in serena_prompt_drafts:
                                    serena_prompt_drafts[session_id] = {
                                        "prompt": "",
                                        "context": [],
                                        "status": "draft",
                                    }
                                serena_prompt_drafts[session_id]["prompt"] += (
                                    "\n" + args_dict.get("content", "")
                                )
                                if args_dict.get("context_files"):
                                    serena_prompt_drafts[session_id]["context"].extend(
                                        args_dict["context_files"]
                                    )
                                tool_result = {
                                    "success": True,
                                    "result": {
                                        "status": "appended",
                                        "draft": serena_prompt_drafts[session_id],
                                    },
                                }

                            elif tool_name == "serena_view_draft":
                                if session_id in serena_prompt_drafts:
                                    tool_result = {
                                        "success": True,
                                        "result": {
                                            "status": "viewing",
                                            "draft": serena_prompt_drafts[session_id],
                                        },
                                    }
                                else:
                                    tool_result = {
                                        "success": False,
                                        "result": {
                                            "status": "no_draft",
                                            "message": "No draft exists. Use serena_draft_prompt first.",
                                        },
                                    }

                            elif tool_name == "serena_submit":
                                if session_id not in serena_prompt_drafts:
                                    tool_result = {
                                        "success": False,
                                        "error": "No draft to submit",
                                    }
                                else:
                                    draft = serena_prompt_drafts[session_id]
                                    prompt = draft["prompt"]

                                    # Add context files
                                    if draft.get("context"):
                                        context_text = "\n\n--- Context Files ---\n"
                                        for file_path in draft["context"]:
                                            try:
                                                file_result = (
                                                    await serena_mcp.call_tool(
                                                        "read_file", {"path": file_path}
                                                    )
                                                )
                                                if file_result.get("success"):
                                                    content = str(
                                                        file_result.get("result", {})
                                                    )[:5000]
                                                    context_text += (
                                                        f"\n[{file_path}]:\n{content}\n"
                                                    )
                                            except Exception as e:
                                                context_text += (
                                                    f"\n[{file_path}]: Error - {e}\n"
                                                )
                                        prompt = (
                                            context_text + "\n\n--- Task ---\n" + prompt
                                        )

                                    # Submit to Serena
                                    serena_result = await execute_serena_gemma(
                                        prompt,
                                        user="arca",
                                        session_id=f"serena_from_arca_{session_id}",
                                    )
                                    serena_prompt_drafts[session_id]["status"] = (
                                        "submitted"
                                    )
                                    serena_prompt_drafts[session_id]["submitted_at"] = (
                                        datetime.utcnow().isoformat()
                                    )
                                    tool_result = {
                                        "success": True,
                                        "result": {
                                            "serena_response": serena_result.get(
                                                "response", ""
                                            ),
                                            "status": "submitted",
                                        },
                                    }

                                    # Send Serena's response to the user
                                    await manager.send_message(
                                        {
                                            "type": "serena_message",
                                            "role": "assistant",
                                            "content": f"**Serena's Response:**\n\n{serena_result.get('response', '')}",
                                        },
                                        session_id,
                                    )

                            elif tool_name == "serena_delegate":
                                # Direct delegation to Serena
                                task = args_dict.get("task", "")
                                maintainer = args_dict.get("maintainer", "auto")

                                enhanced_task = (
                                    f"[Maintainer preference: {maintainer}]\n\n{task}"
                                )
                                serena_result = await execute_serena_gemma(
                                    enhanced_task,
                                    user="arca_delegate",
                                    session_id=f"serena_delegate_{session_id}",
                                )
                                tool_result = {
                                    "success": True,
                                    "result": {
                                        "serena_response": serena_result.get(
                                            "response", ""
                                        )
                                    },
                                }

                                # Send Serena's response
                                await manager.send_message(
                                    {
                                        "type": "serena_message",
                                        "role": "assistant",
                                        "content": f"**Serena (delegated):**\n\n{serena_result.get('response', '')}",
                                    },
                                    session_id,
                                )

                            # --- Standard tool handling ---
                            else:
                                # Tool implementations wrapper
                                if tool_name == "geometry_ingest":
                                    # Handle alias document -> file_path
                                    if (
                                        "document" in args_dict
                                        and "file_path" not in args_dict
                                    ):
                                        args_dict["file_path"] = args_dict.pop(
                                            "document"
                                        )

                                # Execute tool via MCP
                                tool_result = await serena_mcp.call_tool(
                                    tool_name, args_dict
                                )

                            # Send result back (HIDDEN from user, used for memory)
                            # Changed type to 'internal_log' so UI doesn't render it
                            result_content = json.dumps(
                                tool_result.get("result", tool_result), indent=2
                            )
                            await manager.send_message(
                                {
                                    "type": "internal_log",  # WAS: genesis_message
                                    "role": "system",
                                    "name": tool_name,
                                    "content": f"Tool Output ({tool_name}):\n```json\n{result_content}\n```",
                                },
                                session_id,
                            )

                            # Store in history so ARCA remembers it
                            conversation_history[session_id].append(
                                {
                                    "role": "system",
                                    "content": f"Tool Output ({tool_name}): {result_content}",
                                }
                            )

                            # FIX: Sync to Unified Memory System
                            # This ensures agent_service sees this result in the next turn
                            try:
                                memory_system_url = os.environ.get(
                                    "MEMORY_SYSTEM_URL", "http://memory_system:8001"
                                )
                                async with httpx.AsyncClient(timeout=2.0) as mem_client:
                                    await mem_client.post(
                                        f"{memory_system_url}/conversation",
                                        json={
                                            "session_id": session_id,
                                            "user_id": "system_tool_sync",
                                            "user_message": f"[System Event] Executed tool: {tool_name}",
                                            "assistant_response": f"Tool Output ({tool_name}): {result_content}",
                                            "metadata": {
                                                "type": "tool_output",
                                                "tool": tool_name,
                                            },
                                        },
                                    )
                                    logger.info(
                                        f"Synced {tool_name} output to Memory System"
                                    )

                                    # FIX: Update Conversation Focus (TTL Model)
                                    if tool_name == "geometry_ingest":
                                        try:
                                            # Using the global redis_client
                                            subject = (
                                                args_dict.get("file_path")
                                                or args_dict.get("document")
                                                or "Ingested Document"
                                            )

                                            # Link to previous focus
                                            try:
                                                prev_focus_raw = redis_client.get(
                                                    "arca:conversation:focus"
                                                )
                                                if prev_focus_raw:
                                                    prev_focus = json.loads(
                                                        prev_focus_raw.decode()
                                                        if isinstance(
                                                            prev_focus_raw, bytes
                                                        )
                                                        else prev_focus_raw
                                                    )
                                                    prev_subject = prev_focus.get(
                                                        "subject"
                                                    )
                                                    if (
                                                        prev_subject
                                                        and prev_subject != subject
                                                    ):
                                                        link = {
                                                            "source": prev_subject,
                                                            "target": subject,
                                                            "type": "conversation_flow",
                                                            "timestamp": datetime.utcnow().isoformat(),
                                                        }
                                                        redis_client.rpush(
                                                            "arca:conversation:graph",
                                                            json.dumps(link),
                                                        )
                                            except Exception as link_e:
                                                logger.warning(
                                                    f"Link creation failed: {link_e}"
                                                )

                                            focus_data = {
                                                "subject": subject,
                                                "type": "document",
                                                "ttl": 10,  # User requested 10 turns
                                            }
                                            redis_client.set(
                                                "arca:conversation:focus",
                                                json.dumps(focus_data),
                                            )
                                        except Exception as focus_e:
                                            logger.warning(
                                                f"Failed to update focus: {focus_e}"
                                            )

                            except Exception as mem_e:
                                logger.warning(
                                    f"Failed to sync tool output to Memory System: {mem_e}"
                                )
                            else:
                                logger.info(
                                    f"Synced {tool_name} output to Memory System"
                                )

                    except Exception as e:
                        logger.error(f"ARCA tool execution error: {e}")

                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await manager.send_message(
                        {"type": "error", "content": f"Error: {str(e)}"}, session_id
                    )

            else:
                logger.info(f"Received message type: {message_type}")

    except WebSocketDisconnect:
        manager.disconnect(session_id)
        # Cleanup
        if session_id in conversation_history:
            del conversation_history[session_id]
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
        await manager.send_message(
            {"type": "error", "content": f"An unexpected error occurred: {str(e)}"},
            session_id,
        )
        manager.disconnect(session_id)


# --- Startup Event ---
@app.on_event("startup")
async def startup_event():
    """Initialize background tasks"""
    logger.info("Starting ARCA User Interaction Agent v3.2.2")
    logger.info(f"Features: psutil={PSUTIL_AVAILABLE}, docker={DOCKER_AVAILABLE}")

    # Start telemetry cache updater
    asyncio.create_task(update_telemetry_cache())

    # Start health alert listener in background thread
    if REDIS_AVAILABLE:
        health_thread = threading.Thread(target=health_alert_listener, daemon=True)
        health_thread.start()
        logger.info("Health alert listener thread started")
    else:
        logger.warning("Health alert listener skipped: Redis unavailable")

    # Start periodic health alert processor
    asyncio.create_task(process_health_alerts_periodically())

    # Start Attention Model decay thread
    if ATTENTION_MODEL_AVAILABLE:
        try:
            attention_model = get_attention_model(redis_client)
            attention_model.start_decay_thread()
            logger.info("Attention model decay thread started")
        except Exception as e:
            logger.warning(f"Failed to start attention decay thread: {e}")

    logger.info("Background tasks started")


async def process_health_alerts_periodically():
    """Periodically check for health alerts and have Serena analyze them"""
    await asyncio.sleep(30)  # Wait 30s before first check

    while True:
        try:
            alerts = await get_pending_health_alerts()
            for alert in alerts:
                logger.info(
                    f"Processing health alert for {alert.get('alert', {}).get('service', 'unknown')}"
                )
                # Analyze with Serena
                result = await analyze_health_alert_with_serena(alert)
                logger.info(
                    f"Serena health analysis: {result.get('status', 'unknown')}"
                )
        except Exception as e:
            logger.error(f"Health alert processing error: {e}")

        await asyncio.sleep(60)  # Check every 60 seconds


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app", host="0.0.0.0", port=USER_AGENT_PORT, reload=True, log_level="info"
    )

# --- MIGRATED ENDPOINTS FROM app/main.py ---

# Log Capture for UI
log_capture_buffer = []
LOG_BUFFER_SIZE = 100
log_lock = threading.Lock()


class ListHandler(logging.Handler):
    def emit(self, record):
        entry = self.format(record)
        with log_lock:
            log_capture_buffer.append(entry)
            if len(log_capture_buffer) > LOG_BUFFER_SIZE:
                log_capture_buffer.pop(0)


list_handler = ListHandler()
list_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logging.getLogger().addHandler(list_handler)


@app.get("/api/system/logs")
async def get_system_logs():
    with log_lock:
        return {"logs": list(log_capture_buffer)}


@app.get("/monitor")
@app.get("/monitor/")
async def monitor_page():
    """Redirect or return metrics for the manual monitor URL check"""
    return await get_system_metrics()


@app.get("/api/library/browse")
async def browse_library(path: str = ""):
    """Browse files in shared_storage (root)"""
    try:
        from pathlib import Path

        root_base = Path("/app/shared_storage")

        # Clean the path to prevent traversal
        path = path.strip("/")
        target_path = root_base / path

        if not target_path.exists():
            return {"files": [], "error": "Path not found"}

        # Security check
        try:
            target_path.resolve().relative_to(root_base.resolve())
        except ValueError:
            return {"files": [], "error": "Access denied"}

        files_data = []
        # List contents
        if target_path.is_dir():
            for item in target_path.iterdir():
                try:
                    is_dir = item.is_dir()
                    # Skip hidden files
                    if item.name.startswith("."):
                        continue

                    file_info = {
                        "name": item.name,
                        "path": f"/{item.relative_to(root_base)}",  # Client sees paths relative to root
                        "type": "directory" if is_dir else "file",
                        "size": item.stat().st_size if not is_dir else None,
                        "modified": item.stat().st_mtime,
                    }
                    if not is_dir:
                        file_info["extension"] = item.suffix.lower()
                    files_data.append(file_info)
                except Exception as e:
                    logger.warning(f"Error reading file {item}: {e}")

        # Sort: directories first, then files
        files_data.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))

        return {"files": files_data, "current_path": path}

    except Exception as e:
        logger.error(f"Error browsing library: {e}")
        return {"files": [], "error": str(e)}


@app.post("/api/library/upload")
async def upload_file(files: List[Any], path: str = ""):
    """Upload files to the specified path"""
    # Note: Using Any for files because exact type depends on FastAPI version in container
    try:
        from fastapi import UploadFile
        import shutil
        from pathlib import Path

        root_base = Path("/app/shared_storage")
        path = path.strip("/")
        target_dir = root_base / path

        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)

        uploaded_names = []
        for file in files:
            if isinstance(file, UploadFile):
                file_path = target_dir / file.filename
                with file_path.open("wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                uploaded_names.append(file.filename)

        return {"uploaded": uploaded_names}
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return {"error": str(e)}


@app.post("/api/library/pin")
async def pin_directory(path: str = ""):
    """Mock endpoint to pin a directory"""
    # In a real implementation this would save to user preferences DB
    logger.info(f"Pinning directory: {path}")
    return {"status": "pinned", "path": path}


@app.get("/api/library/read")
async def read_file(path: str):
    """Read file content from shared_storage"""
    try:
        from pathlib import Path

        root_base = Path("/app/shared_storage")

        # Clean the path
        path = path.strip("/")
        target_path = root_base / path

        # Security check
        try:
            target_path.resolve().relative_to(root_base.resolve())
        except ValueError:
            return {"error": "Access denied", "content": "Access denied"}

        if not target_path.exists() or not target_path.is_file():
            return {"error": "File not found", "content": "File not found"}

        # Read content (text only for now)
        try:
            content = target_path.read_text(errors="replace")
            return {
                "filename": target_path.name,
                "path": f"/{target_path.relative_to(root_base)}",
                "content": content,
            }
        except Exception as e:
            return {"error": "Read error", "content": str(e)}

    except Exception as e:
        logger.error(f"Error reading file: {e}")
        return {"error": str(e), "content": str(e)}
