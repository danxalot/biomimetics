import os
import uuid
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncio

import httpx
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketDisconnect
from pydantic import BaseModel
import logging

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

# Import MiniMax reasoning integration
from minimax_reasoning_integration import MinimaxReasoningWorkflow

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
AGENT_SERVICE_URL = os.environ.get("AGENT_SERVICE_URL", "http://agent_service:8000")
USER_AGENT_PORT = int(os.environ.get("USER_AGENT_PORT", 8084))
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8085")

# Global state
conversation_history: Dict[str, List[Dict]] = {}  # session_id -> messages
genesis_threads: Dict[str, Dict] = {}  # thread_id -> thread_info
telemetry_cache: Dict[str, Any] = {"data": {}, "last_update": None}

# --- Pydantic Models for API ---
class AgentRequest(BaseModel):
    objective: str
    session_id: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = "default"

class InterpreterRequest(BaseModel):
    command: str
    session_id: Optional[str] = None

class ReasoningRequest(BaseModel):
    context_depth: Optional[int] = 10
    session_id: Optional[str] = None


# --- FastAPI App Setup ---
app = FastAPI(
    title="ARCA User Interaction Agent",
    description="Real-time user interface for the ARCA system with full MiniMax integration",
    version="3.0.0"
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


# --- System Telemetry Functions ---
def get_system_telemetry() -> Dict[str, Any]:
    """Collect real system metrics"""
    telemetry = {
        "cpu": "N/A",
        "memory": "N/A",
        "swap": "N/A",
        "containers": "N/A",
        "llm_perf": "6.3 tok/s",  # Mock for now
        "neo4j": "Unknown"
    }
    
    if PSUTIL_AVAILABLE:
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            telemetry["cpu"] = f"{cpu_percent}%"
            telemetry["memory"] = f"{mem.used / (1024**3):.1f}GB/{mem.total / (1024**3):.1f}GB"
            telemetry["swap"] = f"{swap.used / (1024**2):.0f}MB/{swap.total / (1024**3):.1f}GB"
        except Exception as e:
            logger.error(f"Error getting system metrics: {e}")
    
    if DOCKER_AVAILABLE:
        try:
            client = docker.from_env()
            containers = client.containers.list()
            telemetry["containers"] = f"{len(containers)} running"
            
            # Check Neo4j
            neo4j_containers = [c for c in containers if 'neo4j' in c.name.lower()]
            telemetry["neo4j"] = "Online" if neo4j_containers else "Offline"
        except Exception as e:
            logger.error(f"Error getting Docker metrics: {e}")
    
    return telemetry

async def update_telemetry_cache():
    """Update telemetry cache periodically"""
    global telemetry_cache
    while True:
        try:
            telemetry_cache["data"] = get_system_telemetry()
            telemetry_cache["last_update"] = datetime.utcnow().isoformat()
        except Exception as e:
            logger.error(f"Error updating telemetry cache: {e}")
        await asyncio.sleep(5)  # Update every 5 seconds


# --- WebSocket Connection Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"WebSocket connected: {session_id}")

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"WebSocket disconnected: {session_id}")

    async def send_message(self, message: Dict[str, Any], session_id: str):
        if session_id in self.active_connections:
            try:
                await self.active_connections[session_id].send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Failed to send WebSocket message to {session_id}: {e}")

manager = ConnectionManager()


# --- Helper Functions ---
async def call_agent_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Calls the backend agent service with fallback"""
    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{AGENT_SERVICE_URL}/invoke",
                json=payload
            )
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as e:
        logger.error(f"Agent service unavailable: {e}")
        # Return fallback response
        return {
            "response": "Agent service is currently unavailable. Using local processing.",
            "status": "fallback",
            "error": str(e)
        }
    except httpx.HTTPStatusError as e:
        logger.error(f"Agent service error: {e.response.status_code} - {e.response.text}")
        return {
            "response": f"Agent service error: {e.response.status_code}",
            "status": "error",
            "error": e.response.text
        }


# --- REST API Endpoints ---
@app.get("/")
async def root():
    """Serve the ARCA terminal interface."""
    static_file_path = os.path.join(static_dir, "index.html")
    if not os.path.isfile(static_file_path):
        return JSONResponse(status_code=404, content={"message": "Static UI not found."})
    return FileResponse(static_file_path)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "user_interaction_agent",
        "version": "3.0.0",
        "features": {
            "psutil": PSUTIL_AVAILABLE,
            "docker": DOCKER_AVAILABLE,
            "minimax": True,
            "mcp": True
        }
    }

@app.get("/api/telemetry")
async def get_telemetry():
    """Get system telemetry metrics"""
    if telemetry_cache["last_update"]:
        return {
            "telemetry": telemetry_cache["data"],
            "timestamp": telemetry_cache["last_update"]
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
        "user_id": request.user_id
    }
    response = await call_agent_service(payload)
    return response

@app.post("/api/interpreter/execute")
async def execute_interpreter(request: InterpreterRequest):
    """Execute interpreter command (stub for now)"""
    # TODO: Implement safe command execution
    return {
        "status": "not_implemented",
        "message": "Interpreter execution not yet implemented for security",
        "command": request.command
    }

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
        workflow = MinimaxReasoningWorkflow(history, mcp_url=MCP_SERVER_URL)
        result = await workflow.invoke_reasoning_with_tools(context_depth=request.context_depth)
        return result
    except Exception as e:
        logger.error(f"Error in MiniMax reasoning: {e}")
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


# --- WebSocket Endpoint with Full Message Handling ---
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint with complete message type support"""
    session_id = str(uuid.uuid4())
    await manager.connect(websocket, session_id)
    
    # Initialize conversation history
    conversation_history[session_id] = []
    
    await manager.send_message({
        "type": "session_created",
        "session_id": session_id
    }, session_id)
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            message_type = message_data.get("type")
            
            # Handle telemetry requests
            if message_type == "telemetry_request":
                await manager.send_message({
                    "type": "telemetry_update",
                    "data": telemetry_cache["data"]
                }, session_id)
                continue
            
            # Handle thread status requests
            elif message_type == "thread_status_request":
                thread_id = message_data.get("thread_id")
                if thread_id and thread_id in genesis_threads:
                    await manager.send_message({
                        "type": "genesis_thread_update",
                        "data": genesis_threads[thread_id]
                    }, session_id)
                else:
                    await manager.send_message({
                        "type": "genesis_thread_update",
                        "data": {"status": "no_active_thread"}
                    }, session_id)
                continue
            
            # Handle pause thread
            elif message_type == "pause_thread":
                thread_id = message_data.get("thread_id")
                if thread_id:
                    genesis_threads[thread_id] = genesis_threads.get(thread_id, {})
                    genesis_threads[thread_id]["paused"] = True
                    genesis_threads[thread_id]["status"] = "paused"
                    await manager.send_message({
                        "type": "system_status",
                        "message": f"Thread {thread_id} paused"
                    }, session_id)
                continue
            
            # Handle resume thread
            elif message_type == "resume_thread":
                thread_id = message_data.get("thread_id")
                if thread_id:
                    genesis_threads[thread_id] = genesis_threads.get(thread_id, {})
                    genesis_threads[thread_id]["paused"] = False
                    genesis_threads[thread_id]["status"] = "running"
                    await manager.send_message({
                        "type": "system_status",
                        "message": f"Thread {thread_id} resumed"
                    }, session_id)
                continue
            
            # Handle interpreter reset
            elif message_type == "interpreter_reset":
                await manager.send_message({
                    "type": "interpreter_message",
                    "role": "system",
                    "content": "Interpreter reset complete"
                }, session_id)
                continue
            
            # Handle chat/message requests
            elif message_type in ["chat", "message", "interpreter_request", "genesis_message"]:
                user_input = message_data.get("message") or message_data.get("command") or message_data.get("objective")
                if not user_input:
                    continue

                # Store in conversation history
                conversation_history[session_id].append({
                    "role": "user",
                    "content": user_input,
                    "timestamp": datetime.utcnow().isoformat()
                })

                payload = {
                    "user_input": user_input,
                    "session_id": session_id,
                    "user_id": message_data.get("user", "default"),
                    "metadata": message_data
                }
                
                # Notify client
                await manager.send_message({
                    "type": "status",
                    "content": "Processing request..."
                }, session_id)

                try:
                    # Call backend service
                    agent_response = await call_agent_service(payload)
                    
                    response_content = agent_response.get("response", "No content received.")
                    
                    # Store assistant response
                    conversation_history[session_id].append({
                        "role": "assistant",
                        "content": response_content,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    
                    # Determine response type
                    response_type = "message"
                    if message_type == "genesis_message":
                        response_type = "genesis_message"
                    elif message_type == "interpreter_request":
                        response_type = "interpreter_message"
                    
                    await manager.send_message({
                        "type": response_type,
                        "role": "assistant",
                        "content": response_content,
                        "metadata": agent_response
                    }, session_id)

                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await manager.send_message({
                        "type": "error",
                        "content": f"Error: {str(e)}"
                    }, session_id)
            
            else:
                logger.info(f"Received message type: {message_type}")

    except WebSocketDisconnect:
        manager.disconnect(session_id)
        # Cleanup
        if session_id in conversation_history:
            del conversation_history[session_id]
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}")
        await manager.send_message({
            "type": "error",
            "content": f"An unexpected error occurred: {str(e)}"
        }, session_id)
        manager.disconnect(session_id)


# --- Startup Event ---
@app.on_event("startup")
async def startup_event():
    """Initialize background tasks"""
    logger.info("Starting ARCA User Interaction Agent v3.0.0")
    logger.info(f"Features: psutil={PSUTIL_AVAILABLE}, docker={DOCKER_AVAILABLE}")
    
    # Start telemetry cache updater
    asyncio.create_task(update_telemetry_cache())
    
    logger.info("Background tasks started")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=USER_AGENT_PORT,
        reload=True,
        log_level="info"
    )
