import os
import uuid
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from langgraph_agent import AgentWorkflowEngine
from user_interaction_agent import UserInteractionAgent
from memory_system import UnifiedMemorySystem
from rabbitmq_consumer import RabbitMQConsumer
from llm_gateway_client import LLMGatewayClient

# Configure unified structured logging with trace ID support
from arca_logging import configure_logging, get_trace_id
logger = configure_logging(
    "agent_service",
    log_level=os.environ.get("LOG_LEVEL", "INFO"),
    log_file=os.environ.get("LOG_FILE")
)

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

# Initialize the components
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://mcp_server:8086/mcp")

# Load secrets from mounted directory
SECRETS_DIR = os.environ.get("SECRETS_DIR", "/app/secrets")

def load_secret(secret_name: str, env_var_name: str):
    """Load a secret from file and set as environment variable"""
    secret_path = os.path.join(SECRETS_DIR, secret_name)
    if os.path.exists(secret_path):
        try:
            with open(secret_path, 'r') as f:
                # Handle both JSON and plain text secrets
                content = f.read().strip()
                try:
                    data = json.loads(content)
                    # If JSON, try to find a key matching the env var or use the whole content
                    value = data.get(env_var_name) or data.get("api_key") or content
                except json.JSONDecodeError:
                    # Handle KEY=value format (common in .env-style files)
                    if '=' in content and content.split('=')[0].strip().isupper():
                        value = content.split('=', 1)[1].strip()
                    else:
                        value = content
                
                if value:
                    os.environ[env_var_name] = str(value)
                    logger.info(f"Loaded secret for {env_var_name}")
        except Exception as e:
            logger.error(f"Failed to load secret {secret_name}: {e}")

# Load required API keys
load_secret("MINIMAX_API_KEY.json", "ARCA_MiniMax")
load_secret("google_api_key", "GOOGLE_API_KEY")
load_secret("google_ai_studio", "GOOGLE_AI_STUDIO_API")
load_secret("openai_api_key", "OPENAI_API_KEY")
load_secret("anthropic_api_key", "ANTHROPIC_API_KEY")
load_secret("LANGSEARCH_API", "LANGSEARCH_API_KEY")  # For web search capabilities

# UserInteractionAgent handles chat - lightweight LangGraph with ARCA identity & Groq/Llama
# AgentWorkflowEngine is for the full agentic workflow (reasoning + action + review)
# Initialize with graceful degradation for Genesis/RabbitMQ consumer mode
# (Genesis tasks don't need LLMs during consumer initialization)

chat_agent = None
agent_engine = None

try:
    chat_agent = UserInteractionAgent(mcp_server_url=MCP_SERVER_URL)  # For /invoke (chat)
    logger.info("UserInteractionAgent initialized successfully")
except Exception as e:
    logger.warning(f"WARNING: UserInteractionAgent initialization failed (OK for RabbitMQ consumer mode): {e}")
    # Don't raise - allow RabbitMQ consumer to still function for Genesis tasks

try:
    agent_engine = AgentWorkflowEngine(mcp_server_url=MCP_SERVER_URL)  # For /workflow (complex tasks)
    logger.info("AgentWorkflowEngine initialized successfully")
except Exception as e:
    logger.warning(f"WARNING: AgentWorkflowEngine initialization failed (OK for RabbitMQ consumer mode): {e}")
    # Don't raise - allow RabbitMQ consumer to still function for Genesis tasks
    # Only fail if someone tries to call /workflow endpoint

genesis_engine = None  # Lazy-loaded on first Genesis call (one-time initialization only)

# MEMORY_SYSTEM_URL is loaded from docker-compose env
MEMORY_SYSTEM_URL = os.environ.get("MEMORY_SYSTEM_URL", "http://memory_system:8001")
memory_system = UnifiedMemorySystem(base_url=MEMORY_SYSTEM_URL)

app = FastAPI(
    title="ARCA Agent Service",
    description="Backend service for the ARCA agent, providing core agent functionality.",
    version="1.0.0"
)

# Instrument the FastAPI app
FastAPIInstrumentor.instrument_app(app)

# Instrument HTTP clients
RequestsInstrumentor().instrument()
HTTPXClientInstrumentor().instrument()

class AgentRequest(BaseModel):
    user_input: str
    session_id: str
    user_id: Optional[str] = "default"
    model: Optional[str] = None  # Override model for specific requests (e.g., Serena)

@app.on_event("startup")
async def startup_event():
    # Initialize memory system (now safe with timeouts and fallbacks)
    await memory_system.initialize()
    logger.info("Memory system initialized")
    
    # Lazy-load MCP tools on first request instead of blocking startup
    # await chat_agent.initialize()  # Initialize the chat agent (MCP tools, etc.)
    
    # Start RabbitMQ Consumer
    try:
        # Use agent_engine if available, otherwise create a new AgentWorkflowEngine
        agent_system_for_consumer = agent_engine
        if agent_system_for_consumer is None:
            logger.warning("agent_engine is None, creating fresh AgentWorkflowEngine for consumer...")
            agent_system_for_consumer = AgentWorkflowEngine(mcp_server_url=MCP_SERVER_URL)
        
        consumer = RabbitMQConsumer(agent_system_for_consumer)
        consumer.start()
        logger.info("RabbitMQ Consumer started in background thread")
    except Exception as e:
        logger.error(f"Failed to start RabbitMQ Consumer: {e}", exc_info=True)

    # Initialize Serena (Self-Healing Agent)
    try:
        import redis
        from serena_integration import create_serena_agent
        from mcp_client import MCPClient

        # Create dedicated clients for Serena
        serena_redis = redis.Redis(
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=0,
            decode_responses=True # Serena expects string responses for JSON parsing
        )
        serena_mcp = MCPClient(mcp_server_url=MCP_SERVER_URL)
        
        # Initialize LLM Gateway client for Serena (using SSOT configured model)
        from shared.model_config import get_model
        serena_llm_model = get_model("SERENA_MODEL")
        serena_llm_gateway = LLMGatewayClient(model=serena_llm_model)

        global serena_agent
        serena_agent = create_serena_agent(serena_mcp, serena_redis, llm_gateway_client=serena_llm_gateway)
        logger.info(f"✨ Serena Agent initialized and monitoring system health (Model: {serena_llm_model})")
        
    except Exception as e:
        logger.error(f"Failed to initialize Serena Agent: {e}", exc_info=True)

@app.on_event("shutdown")
async def shutdown_event():
    await memory_system.close()

@app.post("/invoke")
async def invoke_agent(request: AgentRequest, raw_request: Request) -> Dict[str, Any]:
    """Invoke the chat agent - ARCA's user-facing interface with read-only system access."""
    if chat_agent is None:
        raise HTTPException(status_code=503, detail="Chat agent not available - missing LLM credentials")
    
    try:
        # Get comprehensive context from the memory system
        # Handle case where memory system is not fully initialized
        context = {}
        try:
            if memory_system and hasattr(memory_system, 'get_comprehensive_context'):
                context = await memory_system.get_comprehensive_context(
                    session_id=request.session_id,
                    query=request.user_input,
                    user_id=request.user_id
                )
        except Exception as ctx_error:
            logger.warning(f"Could not get context from memory system: {ctx_error}")
            context = {}

        # Process the user input through the UserInteractionAgent (LangGraph workflow)
        workflow_result = await chat_agent.process_user_input(
            user_input=request.user_input,
            session_id=request.session_id,
            user_id=request.user_id,
            context=context,
            model=request.model,
            headers={k: v for k, v in raw_request.headers.items() if k.lower().startswith("x-genesis-") or k.lower() == "x-workhorse-token"}
        )

        # Add the conversation turn to the memory system in background (non-blocking)
        # This ensures the response is returned immediately while memory persistence happens async
        import asyncio
        if memory_system and hasattr(memory_system, 'add_conversation_turn'):
            asyncio.create_task(
                memory_system.add_conversation_turn(
                    session_id=request.session_id,
                    user_id=request.user_id,
                    user_message=request.user_input,
                    assistant_response=workflow_result.get("response", ""),
                    metadata=workflow_result
                )
            )

        return workflow_result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in invoke_agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/workflow")
async def invoke_workflow(request: AgentRequest, raw_request: Request) -> Dict[str, Any]:
    """
    Invoke the full LangGraph tiered workflow for complex tasks.
    This runs through all tiers: Context Compressor -> Architect -> Structural Analyst -> Planner -> etc.
    Use this for complex tasks requiring multi-agent coordination.
    """
    if agent_engine is None:
        raise HTTPException(status_code=503, detail="Workflow engine not available - missing LLM credentials")
    
    try:
        # Get comprehensive context from the memory system
        context = await memory_system.get_comprehensive_context(
            session_id=request.session_id,
            query=request.user_input,
            user_id=request.user_id
        )

        # Process through the full LangGraph workflow
        workflow_result = await agent_engine.invoke_workflow(
            user_input=request.user_input,
            session_id=request.session_id,
            user_id=request.user_id,
            headers={k: v for k, v in raw_request.headers.items() if k.lower().startswith("x-genesis-") or k.lower() == "x-workhorse-token"}
        )

        # Add the conversation turn to the memory system
        await memory_system.add_conversation_turn(
            session_id=request.session_id,
            user_id=request.user_id,
            user_message=request.user_input,
            assistant_response=workflow_result.get("response", ""),
            metadata=workflow_result
        )

        return workflow_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint with component status."""
    components = {
        "working_memory": "healthy",  # SQLite - always available
        "episodic_memory": "degraded",  # Oracle - check pool
        "structural_memory": "degraded",  # Neo4j - check driver
        "mcp_connection": "unknown"
    }
    
    # Check Memory System Connection
    try:
        if memory_system:
            # We are a client, so we assume the remote system handles its own health.
            # Ideally we would call await memory_system.health_check() if implemented.
            components["episodic_memory"] = "healthy" 
            components["structural_memory"] = "healthy"
    except Exception as e:
        logger.error(f"Failed to verify memory system connection: {e}")
    
    # Determine overall status
    critical_components = ["episodic_memory", "structural_memory"]
    degraded = any(components[c] == "degraded" for c in critical_components)
    
    return {
        "status": "degraded" if degraded else "healthy",
        "components": components,
        "message": "Some memory systems unavailable" if degraded else "All systems operational"
    }


class GenesisRequest(BaseModel):
    """Request model for Genesis prompt submission."""
    genesis_prompt: str
    session_id: Optional[str] = None


@app.post("/genesis")
async def run_genesis(request: GenesisRequest, raw_request: Request) -> Dict[str, Any]:
    """
    Execute the Genesis one-shot chain (ONE-TIME INITIALIZATION ONLY).
    
    This runs the full agent cascade for system initialization:
    Architect -> Planner -> Engineer -> Ops -> Reviewer -> Complete
    
    Each agent uses its designated model from llm_config.json.
    This endpoint should only be called once during system bootstrap.
    """
    global genesis_engine
    
    # Check if Genesis has already been run
    try:
        from redis_blackboard import RedisBlackboard
        blackboard = RedisBlackboard()
        genesis_status = blackboard.read("genesis_completed")
        if genesis_status:
            return {
                "status": "already_initialized",
                "message": "Genesis has already been executed. System is initialized.",
                "genesis_timestamp": genesis_status.get("timestamp")
            }
    except Exception as e:
        logger.warning(f"Could not check genesis status from Redis: {e}")
        # Continue with genesis execution if Redis is unavailable
    
    try:
        logger.info(f"🌅 GENESIS INITIALIZATION STARTING - session: {request.session_id}")
        
        # Lazy-load the Genesis engine (only created once)
        if genesis_engine is None:
            logger.info("Creating Genesis engine (one-time)")
            genesis_engine = AgentWorkflowEngine(mcp_server_url=MCP_SERVER_URL)
        
        result = await genesis_engine.run_genesis(
            genesis_prompt=request.genesis_prompt,
            session_id=request.session_id,
            headers={k: v for k, v in raw_request.headers.items() if k.lower().startswith("x-genesis-") or k.lower() == "x-workhorse-token"}
        )
        
        # Mark Genesis as completed (store in Redis via blackboard)
        try:
            from redis_blackboard import RedisBlackboard
            blackboard = RedisBlackboard()
            blackboard.write("genesis_completed", {
                "timestamp": str(datetime.utcnow()),
                "session_id": request.session_id,
                "status": "success"
            })
        except Exception as e:
            logger.warning(f"Could not store genesis completion status: {e}")
        
        logger.info(f"🌅 GENESIS INITIALIZATION COMPLETE")
        return result
        
    except Exception as e:
        logger.error(f"Genesis chain failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================================================================================
# AUDIT LOGGER INTEGRATION (Consolidated from separate service)
# ==================================================================================

class AuditLogEntry(BaseModel):
    timestamp: datetime = datetime.now()
    service_name: str
    event_type: str
    details: Dict[str, Any]
    severity: str = "INFO"
    user_id: Optional[str] = None
    trace_id: Optional[str] = None

@app.post("/audit/log")
async def log_audit_event(entry: AuditLogEntry):
    """
    Receives an audit log entry and records it.
    Consolidated endpoint from the retired audit_logger service.
    """
    try:
        # Structured logging with trace correlation (using existing logger)
        log_data = entry.dict()
        log_data['timestamp'] = log_data['timestamp'].isoformat()
        
        # Ensure trace_id is present for correlation
        if not log_data.get('trace_id'):
            # Try to get from current span context if not provided
            pass 
        
        # Log to Agent Service logs (which go to Loki via Docker)
        logger.info(f"AUDIT_LOG: {json.dumps(log_data)}")
        
        # --- SILENT LISTENER INTEGRATION ---
        # asynchronously commit to Memory System for permanent record
        try:
            # We use direct HTTP call to ensure decoupled logging even if internal memory objects are degraded
            memory_url = os.getenv("MEMORY_SYSTEM_URL", "http://memory_system:8001")
            import aiohttp
            async with aiohttp.ClientSession() as session:
                # Create a concise memory string
                memory_text = f"Audit Log [{entry.severity}] {entry.service_name}: {entry.event_type} - {str(entry.details)[:500]}"
                
                # Use the /document endpoint which accepts {content, source, document_type}
                payload = {
                    "content": memory_text,
                    "source": f"audit_logger_{entry.service_name}",
                    "document_type": "system_log"
                }
                
                async with session.post(f"{memory_url}/document", json=payload, timeout=2) as resp:
                     if resp.status >= 400:
                         logger.warning(f"Memory push failed: {resp.status}")
        except Exception as mem_err:
             # Do not fail request if memory push fails, just log error
            logger.warning(f"Failed to push to memory system: {mem_err}")
        # -----------------------------------

        return {"status": "logged", "trace_id": log_data.get('trace_id')}
    except Exception as e:
        logger.error(f"Failed to log audit event: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
