"""
User Interaction Agent for ARCA System

This agent provides a user-friendly interface for interacting with the ARCA system,
including integration with MCP servers and local LLM capabilities.

Features:
- WebSocket-based real-time communication
- Integration with agent_service and LLM server
- MCP server protocol support (extensible)
- Session management and conversation history
- File upload and document interaction
"""
import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
import uvicorn
import psutil
import psutil
from pathlib import Path

from app.data_models import ChatMessage, UserSession, AgentRequest, MCPRequest

# Google Cloud imports for persistent storage
try:
    from google.cloud import firestore
    from google.cloud import pubsub_v1
    from google.cloud import secretmanager
    CLOUD_AVAILABLE = True
except ImportError:
    print("Warning: Google Cloud libraries not available. Using in-memory storage.")
    CLOUD_AVAILABLE = False

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="ISO"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Configuration
AGENT_SERVICE_URL = os.getenv("AGENT_SERVICE_URL", "https://agent-runner-6b2fvsnzgq-nw.a.run.app")
LLM_SERVER_URL = os.getenv("LLM_SERVER_URL", "http://100.124.13.62:8090")  # Workhorse via Tailscale
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "")  # Will be configured when MCP server is established
USER_AGENT_PORT = int(os.getenv("PORT", "8084"))  # Cloud Run uses PORT env var
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID", "arca-471022")
TASK_TRACE_DIR = Path(os.getenv("TASK_TRACE_DIR", "/app/shared_storage/workflows"))
REASONING_TRACE_DIR = Path(os.getenv("REASONING_TRACE_DIR", "/app/shared_storage/reasoning_bank/observer_task_traces"))

# Persistent Storage Manager
class ConversationStorage:
    """Manages persistent storage of all terminal interactions"""
    
    def __init__(self):
        self.project_id = GCP_PROJECT_ID
        self.firestore_client = None
        self.pubsub_publisher = None
        self.memory_fallback = {}
        
        if CLOUD_AVAILABLE:
            try:
                self.firestore_client = firestore.Client(project=self.project_id)
                self.pubsub_publisher = pubsub_v1.PublisherClient()
                self.conversation_topic = f"projects/{self.project_id}/topics/arca-terminal-conversations"
                logger.info("Persistent storage initialized", backend="firestore+pubsub")
            except Exception as e:
                logger.warning("Failed to initialize cloud storage, using memory fallback", error=str(e))
        
    async def save_message(self, session_id: str, message: ChatMessage, agent_type: str = "user"):
        """Save individual message with full context"""
        message_data = {
            "message_id": message.id,
            "session_id": session_id,
            "content": message.content,
            "role": message.role,
            "agent_type": agent_type,  # user, workhorse_agent, dev_agent, genesis_crew, interpreter
            "timestamp": message.timestamp.isoformat(),
            "metadata": message.metadata or {}
        }
        
        # Save to Firestore for persistence
        if self.firestore_client:
            try:
                doc_ref = self.firestore_client.collection('terminal_messages').document(message.id)
                doc_ref.set(message_data)
                logger.debug("Message saved to Firestore", message_id=message.id, session_id=session_id)
            except Exception as e:
                logger.error("Failed to save message to Firestore", error=str(e))
                
        # Publish to Pub/Sub for real-time distribution
        if self.pubsub_publisher:
            try:
                message_json = json.dumps(message_data).encode('utf-8')
                future = self.pubsub_publisher.publish(self.conversation_topic, message_json)
                logger.debug("Message published to Pub/Sub", message_id=message.id)
            except Exception as e:
                logger.error("Failed to publish message to Pub/Sub", error=str(e))
        
        # Memory fallback
        if session_id not in self.memory_fallback:
            self.memory_fallback[session_id] = []
        self.memory_fallback[session_id].append(message_data)
        
    async def save_session(self, session: UserSession):
        """Save complete session state"""
        session_data = {
            "session_id": session.session_id,
            "user_email": session.user_email,
            "created_at": session.created_at.isoformat(),
            "last_activity": session.last_activity.isoformat(),
            "context": session.context,
            "message_count": len(session.messages)
        }
        
        if self.firestore_client:
            try:
                doc_ref = self.firestore_client.collection('terminal_sessions').document(session.session_id)
                doc_ref.set(session_data)
                logger.debug("Session saved to Firestore", session_id=session.session_id)
            except Exception as e:
                logger.error("Failed to save session to Firestore", error=str(e))
    
    async def load_session_messages(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Load conversation history for a session"""
        if self.firestore_client:
            try:
                messages_ref = self.firestore_client.collection('terminal_messages')
                query = (
                    messages_ref.where('session_id', '==', session_id)
                    .order_by('timestamp', direction=firestore.Query.DESCENDING)
                    .limit(limit)
                )
                messages = [doc.to_dict() for doc in query.stream()]
                logger.debug("Messages loaded from Firestore", session_id=session_id, count=len(messages))
                return messages
            except Exception as e:
                logger.error("Failed to load messages from Firestore", error=str(e))
        
        # Fallback to memory
        return self.memory_fallback.get(session_id, [])[-limit:]
    
    async def get_active_sessions(self) -> List[str]:
        """Get list of active session IDs"""
        if self.firestore_client:
            try:
                # Get sessions active in last 24 hours
                cutoff = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                sessions_ref = self.firestore_client.collection('terminal_sessions')
                query = sessions_ref.where('last_activity', '>=', cutoff.isoformat())
                sessions = [doc.id for doc in query.stream()]
                return sessions
            except Exception as e:
                logger.error("Failed to load active sessions", error=str(e))
        
        return list(self.memory_fallback.keys())

# Initialize storage manager
storage = ConversationStorage()

# Global state - now with persistent backup
active_sessions: Dict[str, UserSession] = {}
websocket_connections: Dict[str, WebSocket] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Starting User Interaction Agent", port=USER_AGENT_PORT)
    yield
    logger.info("Shutting down User Interaction Agent")

app = FastAPI(
    title="ARCA User Interaction Agent",
    description="Real-time user interface for ARCA system with MCP server integration",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (web interface)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Connection Manager for WebSockets with Multi-Agent Broadcasting
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.agent_terminals: Dict[str, List[str]] = {
            "dev": [],
            "workhorse": [], 
            "blackbox": [],
            "user": []
        }

    async def connect(self, websocket: WebSocket, session_id: str, agent_type: str = "user"):
        await websocket.accept()
        self.active_connections[session_id] = websocket
        
        # Register agent terminal
        if agent_type in self.agent_terminals:
            self.agent_terminals[agent_type].append(session_id)
        
        logger.info("WebSocket connected", session_id=session_id, agent_type=agent_type)

    def disconnect(self, session_id: str):
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            
            # Remove from agent terminals
            for agent_type in self.agent_terminals:
                if session_id in self.agent_terminals[agent_type]:
                    self.agent_terminals[agent_type].remove(session_id)
                    
            logger.info("WebSocket disconnected", session_id=session_id)

    async def send_message(self, message: Dict[str, Any], session_id: str):
        if session_id in self.active_connections:
            await self.active_connections[session_id].send_text(json.dumps(message))

    async def broadcast_to_agents(self, message: Dict[str, Any], target_agents: List[str] = None):
        """Broadcast message to specific agent terminals or all agents"""
        if target_agents is None:
            target_agents = ["dev", "workhorse", "blackbox", "user"]
        
        broadcast_count = 0
        for agent_type in target_agents:
            if agent_type in self.agent_terminals:
                for session_id in self.agent_terminals[agent_type]:
                    try:
                        await self.send_message(message, session_id)
                        broadcast_count += 1
                    except Exception as e:
                        logger.error("Failed to broadcast to agent", agent=agent_type, session=session_id, error=str(e))
        
        logger.info("Message broadcast complete", target_agents=target_agents, recipients=broadcast_count)
        return broadcast_count

    async def notify_all_terminals(self, notification_type: str, content: str, source_agent: str = "system"):
        """Send notification to all agent terminals"""
        notification = {
            "type": "agent_notification",
            "notification_type": notification_type,
            "content": content,
            "source_agent": source_agent,
            "timestamp": datetime.utcnow().isoformat(),
            "targets": ["dev", "workhorse", "blackbox"]
        }
        
        return await self.broadcast_to_agents(notification, ["dev", "workhorse", "blackbox", "user"])

    async def broadcast(self, message: Dict[str, Any]):
        for connection in self.active_connections.values():
            await connection.send_text(json.dumps(message))

manager = ConnectionManager()

# Helper Functions
async def call_agent_service(objective: str, user_email: str = "admin@localhost") -> Dict[str, Any]:
    """Call the main agent service"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{AGENT_SERVICE_URL}/invoke",
                json={"objective": objective},
                headers={"X-User-Email": user_email}
            )
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as e:
        logger.error("Failed to call agent service", error=str(e))
        raise HTTPException(status_code=503, detail=f"Agent service unavailable: {e}")
    except httpx.HTTPStatusError as e:
        logger.error("Agent service returned error", status=e.response.status_code, error=e.response.text)
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)

async def call_llm_direct(prompt: str, max_tokens: int = 500) -> Dict[str, Any]:
    """Call LLM server directly for quick responses"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{LLM_SERVER_URL}/v1/completions",
                json={
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": 0.7,
                    "stream": False
                }
            )
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as e:
        logger.error("Failed to call LLM server", error=str(e))
        raise HTTPException(status_code=503, detail=f"LLM server unavailable: {e}")

async def call_mcp_server(method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Call MCP server when available"""
    if not MCP_SERVER_URL:
        return {"error": "MCP server not configured"}
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{MCP_SERVER_URL}/mcp",
                json={
                    "method": method,
                    "params": params or {}
                }
            )
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as e:
        logger.error("Failed to call MCP server", error=str(e))
        return {"error": f"MCP server unavailable: {e}"}

# ============================================================================
# Serena Code Agent Functions
# ============================================================================

async def execute_serena(message: str, user: str = "danexall") -> Dict[str, Any]:
    """Execute Serena Code Agent request via MCP server"""
    try:
        # Query MCP server for skills and reasoning capabilities
        mcp_response = await call_mcp_server(MCPRequest(
            method="tools/list",
            params={}
        ))
        
        # Build Serena system prompt with skills context
        skills_context = ""
        available_tools = mcp_response.get("tools", [])
        serena_tools = [t for t in available_tools if any(
            x in t.get("name", "") for x in ["skills", "reasoning", "health"]
        )]
        
        if serena_tools:
            skills_context = "\n\nAvailable Serena Tools:\n" + "\n".join(
                f"- {t['name']}: {t.get('description', 'No description')}"
                for t in serena_tools
            )
        
        system_prompt = f"""You are Serena, the Noetic Code Agent for the ARCA system.

Your Role:
- Semantic code analysis and understanding
- Skills bank management and retrieval
- Reasoning trace capture and storage  
- Self-healing dispatch for service issues
- Code pattern recognition and improvement suggestions

ARCA System Context:
- Running on OCI A1 instance (Ubuntu 22.04, ARM64)
- Self-healing architecture with Redis pub/sub health monitoring
- Skills stored at /app/shared_storage/mcp_skills/
- Reasoning traces at /app/shared_storage/reasoning_bank/
{skills_context}

User: {user}
Request: {message}

Respond helpfully with code analysis, skill suggestions, or dispatch repair jobs as needed.
If the user asks about skills, list available skills or search the skills bank.
If the user asks about code issues, analyze and suggest fixes.
If asked to dispatch a repair, format it as a job for the ops agents."""

        llm_response = await call_llm_direct(system_prompt, max_tokens=2000)
        response_text = llm_response.get("choices", [{}])[0].get("text", "No response from Serena")
        
        logger.info("Serena execution", user=user, message=message[:100])
        
        return {
            "response": response_text,
            "tools_available": [t["name"] for t in serena_tools],
            "status": "success"
        }
        
    except Exception as e:
        logger.error("Serena execution failed", error=str(e), user=user)
        return {
            "response": f"Serena error: {str(e)}",
            "status": "error"
        }

async def serena_list_skills() -> Dict[str, Any]:
    """List available skills via MCP"""
    try:
        mcp_response = await call_mcp_server(MCPRequest(
            method="tools/call",
            params={
                "name": "skills_list",
                "arguments": {}
            }
        ))
        return mcp_response
    except Exception as e:
        logger.error("Serena skills list failed", error=str(e))
        return {"error": str(e)}

async def serena_search_skills(query: str) -> Dict[str, Any]:
    """Search skills bank via MCP"""
    try:
        mcp_response = await call_mcp_server(MCPRequest(
            method="tools/call",
            params={
                "name": "skills_search",
                "arguments": {"query": query}
            }
        ))
        return mcp_response
    except Exception as e:
        logger.error("Serena skills search failed", error=str(e), query=query)
        return {"error": str(e)}

async def reset_serena(user: str = "danexall") -> None:
    """Reset Serena session for user"""
    logger.info("Serena session reset", user=user)

async def get_thread_status(thread_id: str) -> Dict[str, Any]:
    """Get Genesis Crew thread status"""
    try:
        # Query the agent service for thread status
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{AGENT_SERVICE_URL}/threads/{thread_id}/status")
            if response.status_code == 200:
                return response.json()
            else:
                return {"status": "unknown", "progress": 0}
    except Exception as e:
        logger.error("Failed to get thread status", thread_id=thread_id, error=str(e))
        return {"status": "error", "progress": 0}

async def resume_thread(thread_id: str) -> Dict[str, Any]:
    """Resume a Genesis Crew thread"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{AGENT_SERVICE_URL}/resume", json={"thread_id": thread_id})
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error("Failed to resume thread", thread_id=thread_id, error=str(e))
        return {"status": "error", "message": str(e)}

async def get_system_telemetry() -> Dict[str, str]:
    """Get live system telemetry"""
    telemetry = {}
    
    try:
        # Get system stats (simulated for now - could use psutil or system commands)
        telemetry["cpu"] = "12%"  # Would get from system
        telemetry["memory"] = "6.1GB/23GB"  # Would get from system  
        telemetry["swap"] = "0MB/16GB"  # Would get from system
        telemetry["containers"] = "5 running"  # Would get from docker stats
        
        # Test LLM performance
        llm_perf_response = await call_llm_direct("Test", max_tokens=5)
        telemetry["llm_perf"] = "6.3 tok/s"  # Would calculate from timing
        
        # Test Neo4j
        telemetry["neo4j"] = "Online"  # Would test connection
        
    except Exception as e:
        logger.error("Failed to get telemetry", error=str(e))
        telemetry = {"error": str(e)}
    
    return telemetry

async def get_system_status() -> Dict[str, str]:
    """Get system service status"""
    status = {
        "agent_service": "unknown",
        "llm_server": "unknown", 
        "neo4j": "unknown",
        "mcp_server": "not_configured" if not MCP_SERVER_URL else "unknown"
    }
    
    # Test each service
    services = [
        ("agent_service", f"{AGENT_SERVICE_URL}/health"),
        ("llm_server", f"{LLM_SERVER_URL}/health"),
    ]
    
    for service_name, url in services:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                status[service_name] = "online" if response.status_code == 200 else "error"
        except:
            status[service_name] = "offline"
    
    return status

async def get_or_create_session(session_id: Optional[str] = None, user_email: str = "admin@localhost") -> UserSession:
    """Get existing session or create new one with persistent storage"""
    if session_id and session_id in active_sessions:
        session = active_sessions[session_id]
        session.last_activity = datetime.utcnow()
        # Save updated activity to storage
        await storage.save_session(session)
        return session
    
    new_session_id = session_id or str(uuid.uuid4())
    session = UserSession(session_id=new_session_id, user_email=user_email)
    
    # Load existing messages from storage if session exists
    existing_messages = await storage.load_session_messages(new_session_id)
    if existing_messages:
        # Convert stored messages back to ChatMessage objects
        for msg_data in reversed(existing_messages):  # Reverse to maintain chronological order
            message = ChatMessage(
                id=msg_data.get("message_id", str(uuid.uuid4())),
                content=msg_data["content"],
                role=msg_data["role"],
                timestamp=datetime.fromisoformat(msg_data["timestamp"].replace('Z', '+00:00')),
                metadata=msg_data.get("metadata", {})
            )
            session.messages.append(message)
        logger.info("Loaded session from storage", session_id=new_session_id, message_count=len(session.messages))
    
    active_sessions[new_session_id] = session
    await storage.save_session(session)
    logger.info("Created new session", session_id=new_session_id, user_email=user_email)
    return session

async def add_message_to_session(session: UserSession, content: str, role: str = "user", 
                                agent_type: str = "user", metadata: Optional[Dict[str, Any]] = None):
    """Add message to session and persist it"""
    message = ChatMessage(content=content, role=role, metadata=metadata)
    session.messages.append(message)
    session.last_activity = datetime.utcnow()
    
    # Save to persistent storage
    await storage.save_message(session.session_id, message, agent_type)
    await storage.save_session(session)
    
    logger.info("Message added and persisted", 
                session_id=session.session_id, 
                agent_type=agent_type, 
                message_id=message.id)

# Routes

@app.get("/")
async def root():
    """Serve the enhanced ARCA terminal interface"""
    return HTMLResponse(open("static/index.html").read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, agent_type: str = "user"):
    """WebSocket endpoint for real-time communication with multi-agent support"""
    session_id = str(uuid.uuid4())
    await manager.connect(websocket, session_id, agent_type)
    session = await get_or_create_session(session_id, f"{agent_type}@arca-system")
    
    # Send session created message with conversation history
    conversation_history = [
        {
            "id": msg.id,
            "content": msg.content,
            "role": msg.role,
            "timestamp": msg.timestamp.isoformat(),
            "metadata": msg.metadata
        }
        for msg in session.messages[-50:]  # Last 50 messages
    ]
    
    await manager.send_message({
        "type": "session_created",
        "session_id": session_id,
        "agent_type": agent_type,
        "conversation_history": conversation_history,
        "multi_agent_status": {
            "active_agents": list(manager.agent_terminals.keys()),
            "connected_terminals": {k: len(v) for k, v in manager.agent_terminals.items()}
        }
    }, session_id)
    
    # Notify other agents about new connection
    if agent_type in ["dev", "workhorse", "blackbox"]:
        await manager.notify_all_terminals(
            f"🔗 Agent @{agent_type} connected to multi-agent terminal",
            "agent_connection", 
            agent_type
        )
    
    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # Add agent context to message
            message_data["source_agent"] = agent_type
            
            await handle_websocket_message(message_data, session_id, session)
            
    except WebSocketDisconnect:
        # Notify other agents about disconnection
        if agent_type in ["dev", "workhorse", "blackbox"]:
            await manager.notify_all_terminals(
                f"❌ Agent @{agent_type} disconnected from multi-agent terminal",
                "agent_disconnection",
                agent_type
            )
        manager.disconnect(session_id)
    except Exception as e:
        logger.error("WebSocket error", error=str(e), session_id=session_id, agent_type=agent_type)
        manager.disconnect(session_id)

async def handle_websocket_message(data: Dict[str, Any], session_id: str, session: UserSession):
    """Handle incoming WebSocket messages"""
    message_type = data.get("type")
    user = data.get("user", "danexall")
    
    try:
        if message_type == "genesis_request":
            # Send objective to Genesis Crew
            objective = data.get("objective", "")
            
            # Save user's objective message
            await add_message_to_session(session, f"Genesis objective: {objective}", "user", "user")
            
            try:
                agent_response = await call_agent_service(objective, session.user_email)
                thread_id = agent_response.get("thread_id")
                
                # Save Genesis Crew response
                response_content = f"Genesis Crew started. Thread ID: {thread_id}"
                await add_message_to_session(session, response_content, "assistant", "genesis_crew", 
                                          {"thread_id": thread_id, "objective": objective})
                
                await manager.send_message({
                    "type": "genesis_message",
                    "role": "assistant", 
                    "content": response_content
                }, session_id)
                
                await manager.send_message({
                    "type": "genesis_thread_update",
                    "thread_id": thread_id,
                    "status": "running",
                    "progress": 0
                }, session_id)
                
            except Exception as e:
                await manager.send_message({
                    "type": "genesis_message",
                    "role": "system",
                    "content": f"Error: {str(e)}"
                }, session_id)
                
        elif message_type == "genesis_message":
            # Handle regular genesis chat message
            message = data.get("message", "")
            await add_message_to_session(session, f"Genesis chat: {message}", "user", "user")
            
            # Get LLM response for chat
            llm_response = await call_llm_direct(f"User message in Genesis Crew context: {message}")
            assistant_message = llm_response.get("choices", [{}])[0].get("text", "No response")
            
            # Save assistant response
            await add_message_to_session(session, assistant_message, "assistant", "genesis_crew")
            
            await manager.send_message({
                "type": "genesis_message",
                "role": "assistant",
                "content": assistant_message
            }, session_id)
            
        elif message_type == "serena_request":
            # Handle Serena Code Agent request
            user_message = data.get("message", "")
            await add_message_to_session(session, f"Serena: {user_message}", "user", "user", {"user": user})
            
            # Execute via Serena Code Agent
            serena_result = await execute_serena(user_message, user)
            response = serena_result.get("response", "No response from Serena")
            
            # Save Serena response
            await add_message_to_session(session, response, "assistant", "serena", {
                "message": user_message, 
                "user": user,
                "tools_available": serena_result.get("tools_available", [])
            })
            
            await manager.send_message({
                "type": "serena_message",
                "role": "assistant",
                "content": response,
                "tools_available": serena_result.get("tools_available", [])
            }, session_id)
            
        elif message_type == "serena_skills_list":
            # List Serena skills
            skills_result = await serena_list_skills()
            await manager.send_message({
                "type": "serena_message",
                "role": "system",
                "content": f"Available Skills:\n{json.dumps(skills_result, indent=2)}"
            }, session_id)
            
        elif message_type == "serena_reset":
            # Reset Serena session
            await reset_serena(user)
            await manager.send_message({
                "type": "serena_message",
                "role": "system",
                "content": "Serena session reset"
            }, session_id)
            
        elif message_type == "thread_status_request":
            # Get Genesis thread status
            thread_id = data.get("thread_id")
            status = await get_thread_status(thread_id)
            
            await manager.send_message({
                "type": "genesis_thread_update",
                "thread_id": thread_id,
                "status": status.get("status", "unknown"),
                "progress": status.get("progress", 0)
            }, session_id)
            
        elif message_type == "thread_resume_request" or message_type == "resume_thread":
            # Resume Genesis thread
            thread_id = data.get("thread_id")
            resume_response = await resume_thread(thread_id)
            
            await manager.send_message({
                "type": "genesis_message",
                "role": "system",
                "content": f"Thread {thread_id} resumed: {resume_response.get('status', 'success')}"
            }, session_id)
            
        elif message_type == "pause_thread":
            # Pause Genesis thread
            thread_id = data.get("thread_id")
            # For now, just acknowledge the pause
            await manager.send_message({
                "type": "genesis_message", 
                "role": "system",
                "content": f"Thread {thread_id} paused"
            }, session_id)
            
        elif message_type == "telemetry_request":
            # Get system telemetry
            telemetry = await get_system_telemetry()
            
            await manager.send_message({
                "type": "telemetry_update",
                "data": telemetry
            }, session_id)
            
        elif message_type == "system_status":
            # Check system status
            status = await get_system_status()
            
            await manager.send_message({
                "type": "system_status",
                "data": status
            }, session_id)
            
    except Exception as e:
        logger.error("Error handling WebSocket message", error=str(e), message_type=message_type)
        await manager.send_message({
            "type": "error",
            "message": str(e)
        }, session_id)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "user_interaction_agent", "timestamp": datetime.utcnow()}

@app.get("/api/sessions")
async def get_sessions():
    """Get all active sessions"""
    return {
        "sessions": [
            {
                "session_id": session.session_id,
                "user_email": session.user_email,
                "created_at": session.created_at,
                "last_activity": session.last_activity,
                "message_count": len(session.messages)
            }
            for session in active_sessions.values()
        ]
    }

@app.get("/api/status")
async def get_status():
    """Get overall system status"""
    try:
        system_status = await get_system_status()
        telemetry = await get_system_telemetry()

        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "services": system_status,
            "telemetry": telemetry,
            "active_sessions": len(active_sessions),
            "total_messages": sum(len(session.messages) for session in active_sessions.values())
        }
    except Exception as e:
        logger.error("Failed to get system status", error=str(e))
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@app.get("/api/system/status")
async def system_status_endpoint():
    """Get system service status"""
    try:
        status = await get_system_status()
        return {
            "status": status,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error("Failed to get system status", error=str(e))
        return {
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@app.get("/api/storage/status")
async def storage_status_endpoint():
    """Get storage system status"""
    try:
        # Check storage connectivity
        storage_status = {
            "firestore": "available" if storage.firestore_client else "unavailable",
            "pubsub": "available" if storage.pubsub_publisher else "unavailable",
            "memory_fallback": "active",
            "active_sessions": len(active_sessions),
            "total_messages_stored": sum(len(session.messages) for session in active_sessions.values())
        }

        # Test storage connectivity
        if storage.firestore_client:
            try:
                # Quick connectivity test
                test_doc = storage.firestore_client.collection('health_check').document('test')
                test_doc.set({"timestamp": datetime.utcnow().isoformat(), "status": "ok"})
                storage_status["firestore_connectivity"] = "connected"
            except Exception as e:
                storage_status["firestore_connectivity"] = f"error: {str(e)}"
        else:
            storage_status["firestore_connectivity"] = "not_configured"

        if storage.pubsub_publisher:
            try:
                # Test Pub/Sub connectivity by publishing a test message
                test_message = json.dumps({"test": True, "timestamp": datetime.utcnow().isoformat()}).encode('utf-8')
                future = storage.pubsub_publisher.publish(storage.conversation_topic, test_message)
                storage_status["pubsub_connectivity"] = "connected"
            except Exception as e:
                storage_status["pubsub_connectivity"] = f"error: {str(e)}"
        else:
            storage_status["pubsub_connectivity"] = "not_configured"

        return {
            "storage_status": storage_status,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error("Failed to get storage status", error=str(e))
        return {
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@app.get("/api/conversation/{session_id}")
async def get_conversation_history(session_id: str, limit: int = 100):
    """Get conversation history for a session"""
    try:
        messages = await storage.load_session_messages(session_id, limit)
        return {
            "session_id": session_id,
            "messages": messages,
            "total_loaded": len(messages)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load conversation: {str(e)}")

@app.get("/api/conversation/{session_id}/export")
async def export_conversation(session_id: str, format: str = "json"):
    """Export complete conversation history"""
    try:
        messages = await storage.load_session_messages(session_id, limit=10000)  # Large limit for full export
        
        if format.lower() == "json":
            return {
                "session_id": session_id,
                "exported_at": datetime.utcnow().isoformat(),
                "message_count": len(messages),
                "messages": messages
            }
        elif format.lower() == "txt":
            # Create a text transcript
            transcript_lines = [f"ARCA Terminal Conversation Export - Session: {session_id}"]
            transcript_lines.append(f"Exported: {datetime.utcnow().isoformat()}")
            transcript_lines.append("="*80)
            
            for msg in messages:
                timestamp = msg.get("timestamp", "")
                agent_type = msg.get("agent_type", "unknown")
                role = msg.get("role", "")
                content = msg.get("content", "")
                
                transcript_lines.append(f"\n[{timestamp}] {agent_type.upper()} ({role}):")
                transcript_lines.append(f"{content}")
            
            return {"transcript": "\n".join(transcript_lines)}
        else:
            raise HTTPException(status_code=400, detail="Supported formats: json, txt")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export conversation: {str(e)}")

@app.post("/api/chat")
async def chat_api(message: str, session_id: Optional[str] = None):
    """REST API for chat with persistent storage (alternative to WebSocket)"""
    session = await get_or_create_session(session_id)
    await add_message_to_session(session, message, "user", "user")
    
    # Get LLM response
    llm_response = await call_llm_direct(f"User message: {message}")
    assistant_message = llm_response.get("choices", [{}])[0].get("text", "No response")

    await add_message_to_session(session, assistant_message, "assistant", "llm_direct")
    
    return {
        "session_id": session.session_id,
        "response": assistant_message,
        "timestamp": datetime.utcnow()
    }

@app.post("/api/broadcast")
async def broadcast_to_terminals(
    message: str, 
    notification_type: str = "info",
    source_agent: str = "system",
    target_agents: Optional[List[str]] = None
):
    """Broadcast message to agent terminals"""
    try:
        if target_agents is None:
            target_agents = ["dev", "workhorse", "blackbox"]
        
        recipients = await manager.broadcast_to_agents({
            "type": "agent_notification",
            "notification_type": notification_type,
            "content": message,
            "source_agent": source_agent,
            "timestamp": datetime.utcnow().isoformat(),
            "targets": target_agents
        }, target_agents)
        
        return {
            "success": True,
            "message": "Broadcast sent",
            "recipients": recipients,
            "target_agents": target_agents,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Broadcast failed: {str(e)}")

@app.post("/api/agent/notify")
async def notify_all_terminals(message: str, notification_type: str = "coordination", source_agent: str = "dev"):
    """Send notification to all agent terminals (@dev, @workhorse, @blackbox)"""
    try:
        recipients = await manager.notify_all_terminals(notification_type, message, source_agent)
        
        return {
            "success": True,
            "notification_sent": True,
            "recipients": recipients,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Notification failed: {str(e)}")

@app.get("/api/agent/terminals")
async def get_active_terminals():
    """Get status of active agent terminals"""
    terminal_status = {}
    for agent_type, sessions in manager.agent_terminals.items():
        terminal_status[agent_type] = {
            "active_sessions": len(sessions),
            "session_ids": sessions,
            "status": "online" if sessions else "offline"
        }
    
    return {
        "terminals": terminal_status,
        "total_connections": len(manager.active_connections),
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/api/agent")
async def agent_api(request: AgentRequest):
    """REST API for agent requests"""
    session = await get_or_create_session(request.session_id)
    
    try:
        response = await call_agent_service(request.objective, session.user_email)
        return {
            "session_id": session.session_id,
            "thread_id": response.get("thread_id"),
            "status": "submitted",
            "timestamp": datetime.utcnow()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/mcp")
async def mcp_api(request: MCPRequest):
    """REST API for MCP server calls"""
    response = await call_mcp_server(request.method, request.params)
    return response

@app.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...), session_id: Optional[str] = Form(None)):
    """File upload endpoint"""
    session = get_or_create_session(session_id)
    uploaded_files = []
    
    for file in files:
        # For now, just log the file info
        # In a full implementation, you'd save the files and process them
        file_info = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(await file.read())
        }
        uploaded_files.append(file_info)
        logger.info("File uploaded", **file_info, session_id=session.session_id)
    
    return {
        "session_id": session.session_id,
        "uploaded_files": uploaded_files,
        "message": f"Uploaded {len(uploaded_files)} file(s)"
    }

@app.post("/api/save_prompt_draft")
async def save_prompt_draft(prompt: str, user: str = "danexall"):
    """Save user's prompt draft"""
    try:
        # In a real implementation, save to database or file system
        # For now, just log it
        logger.info("Prompt draft saved", user=user, prompt_length=len(prompt))
        return {"status": "saved", "user": user, "timestamp": datetime.utcnow()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/load_prompt_draft/{user}")
async def load_prompt_draft(user: str):
    """Load user's prompt draft"""
    try:
        # In a real implementation, load from database or file system
        # For now, return a template
        template = """## Objective
[Clear, specific goal]

## Context  
[Relevant background information]

## Requirements
[Specific deliverables and constraints]

## Success Criteria
[How to measure completion]

## Resources
[Available tools and data sources]

## Constraints
[Limitations and boundaries]
"""
        return {"prompt": template, "user": user, "timestamp": datetime.utcnow()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/interpreter_history/{user}")
async def get_interpreter_history(user: str):
    """Get Open Interpreter history for user"""
    try:
        # In a real implementation, load from database
        # For now, return empty history
        return {"history": [], "user": user}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/save_interpreter_session")
async def save_interpreter_session(session_data: dict, user: str = "danexall"):
    """Save Open Interpreter session data"""
    try:
        logger.info("Interpreter session saved", user=user, commands=len(session_data.get("commands", [])))
        return {"status": "saved", "user": user, "timestamp": datetime.utcnow()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/system/metrics")
async def get_system_metrics():
    """Get system resource usage and model activity metrics"""
    try:
        # System metrics
        cpu_percent = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Model metrics (Placeholder - integrate with LLM gateway later)
        return {
            "cpu": cpu_percent,
            "memory": memory.percent,
            "disk": disk.percent,
            "inference": {"active": False, "tps": 0, "buffer": 0},
            "embedding": {"active": False, "tps": 0, "buffer": 0},
            "vision": {"active": False, "tps": 0, "buffer": 0},
            "geometry": {"active": False}
        }
    except Exception as e:
        logger.error("Failed to get metrics", error=str(e))
        return {"cpu": 0, "memory": 0, "disk": 0}

@app.get("/monitor")
@app.get("/monitor/")
async def monitor_page():
    """Redirect or return metrics for the manual monitor URL check"""
    return await get_system_metrics()


# ============================================================================
# Task trace visibility (shared_storage/workflows)
# ============================================================================

def _safe_load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to load task trace", path=str(path), error=str(e))
        return None


@app.get("/api/tasks/traces")
async def list_task_traces(limit: int = 50):
    """List recent task traces for UI consumption"""
    if not TASK_TRACE_DIR.exists():
        return {"traces": [], "path": str(TASK_TRACE_DIR), "error": "trace directory missing"}

    traces = []
    for trace_path in sorted(TASK_TRACE_DIR.glob("task_trace_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        data = _safe_load_json(trace_path) or {}
        traces.append({
            "task_id": data.get("task_id") or trace_path.stem.replace("task_trace_", ""),
            "status": data.get("status"),
            "updated_at": data.get("updated_at") or datetime.utcfromtimestamp(trace_path.stat().st_mtime).isoformat(),
            "last_log": (data.get("logs") or [None])[-1],
            "path": str(trace_path),
        })
        if len(traces) >= limit:
            break

    return {"traces": traces, "count": len(traces), "path": str(TASK_TRACE_DIR)}


@app.get("/api/tasks/traces/{task_id}")
async def get_task_trace(task_id: str):
    """Return full task trace payload for a given task id"""
    trace_path = TASK_TRACE_DIR / f"task_trace_{task_id}.json"
    if not trace_path.exists():
        raise HTTPException(status_code=404, detail="trace not found")

    data = _safe_load_json(trace_path)
    if data is None:
        raise HTTPException(status_code=500, detail="failed to read trace")

    data["file_mtime"] = datetime.utcfromtimestamp(trace_path.stat().st_mtime).isoformat()

    reasoning_snapshot = (REASONING_TRACE_DIR / f"trace_{task_id}.json")
    if reasoning_snapshot.exists():
        data["reasoning_snapshot"] = str(reasoning_snapshot)

    return data

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
                    if item.name.startswith('.'):
                        continue
                        
                    file_info = {
                        "name": item.name,
                        "path": f"/{item.relative_to(root_base)}", # Client sees paths relative to root
                        "type": "directory" if is_dir else "file",
                        "size": item.stat().st_size if not is_dir else None,
                        "modified": item.stat().st_mtime
                    }
                    if not is_dir:
                        file_info["extension"] = item.suffix.lower()
                    files_data.append(file_info)
                except Exception as e:
                    logger.warning(f"Error reading file {item}: {e}")
        
        # Sort: directories first, then files
        files_data.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))
        
        return {"files": files_data, "current_path": path}
        
        # Sort: directories first, then files
        files_data.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))
        
        return {"files": files_data, "current_path": path}
                    except (PermissionError, OSError):
                        continue
            except (PermissionError, OSError):
                continue
        files_data.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))
        return {"files": files_data, "path": path, "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        logger.error("Failed to browse library", error=str(e))
        return {"error": str(e), "files": [], "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/library/search")
async def search_library(query: str):
    """Search files by name across library directories"""
    try:
        from pathlib import Path
        base_dirs = {"shared_storage": Path("/app/shared_storage"), "mcp_skills": Path("/app/mcp_skills")}
        results = []
        query_lower = query.lower()
        for dir_name, base_path in base_dirs.items():
            if not base_path.exists():
                continue
            for item in base_path.rglob("*"):
                if item.is_file() and query_lower in item.name.lower():
                    try:
                        stat = item.stat()
                        results.append({"name": item.name, "path": f"/app/{dir_name}/{item.relative_to(base_path)}",
                                      "type": "file", "size": stat.st_size, "modified": stat.st_mtime,
                                      "parent_dir": dir_name, "extension": item.suffix.lower()})
                    except (PermissionError, OSError):
                        continue
        results.sort(key=lambda x: (not x["name"].lower().startswith(query_lower), x["name"].lower()))
        return {"results": results[:50], "query": query, "count": len(results), "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        logger.error("Failed to search library", error=str(e), query=query)
        return {"error": str(e), "results": [], "timestamp": datetime.utcnow().isoformat()}

@app.post("/api/library/folder")
async def create_folder(path: str, name: str):
    """Create a new folder in library"""
    try:
        from pathlib import Path
        import os
        
        # Validate base directory
        if path.startswith("/app/shared_storage/"):
            base = Path("/app/shared_storage")
        elif path.startswith("/app/mcp_skills/"):
            base = Path("/app/mcp_skills")
        else:
            return {"error": "Invalid path", "timestamp": datetime.utcnow().isoformat()}
        
        # Create folder
        folder_path = Path(path) / name
        if not str(folder_path).startswith(str(base)):
            return {"error": "Invalid folder path", "timestamp": datetime.utcnow().isoformat()}
        
        os.makedirs(folder_path, exist_ok=True)
        logger.info("Folder created", path=str(folder_path))
        
        return {"success": True, "path": str(folder_path), "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        logger.error("Failed to create folder", error=str(e))
        return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}

@app.post("/api/library/upload")
async def upload_file(file: UploadFile = File(...), path: str = Form("/")):
    """Upload file to library"""
    try:
        from pathlib import Path
        import shutil
        
        # Validate base directory
        if path.startswith("/app/shared_storage/"):
            base = Path("/app/shared_storage")
        elif path.startswith("/app/mcp_skills/"):
            base = Path("/app/mcp_skills")
        else:
            base = Path("/app/shared_storage")  # Default to shared_storage
        
        target_path = Path(path) / file.filename
        if not str(target_path).startswith(str(base)):
            return {"error": "Invalid upload path", "timestamp": datetime.utcnow().isoformat()}
        
        # Save file
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info("File uploaded", filename=file.filename, path=str(target_path))
        
        return {"success": True, "filename": file.filename, "path": str(target_path), 
                "size": target_path.stat().st_size, "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        logger.error("Failed to upload file", error=str(e))
        return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}

@app.put("/api/library/move")
async def move_file(source: str, destination: str):
    """Move or rename file/folder"""
    try:
        from pathlib import Path
        import shutil
        
        source_path = Path(source)
        dest_path = Path(destination)
        
        # Validate paths are in allowed directories
        allowed_bases = [Path("/app/shared_storage"), Path("/app/mcp_skills")]
        if not any(str(source_path).startswith(str(b)) and str(dest_path).startswith(str(b)) for b in allowed_bases):
            return {"error": "Invalid move operation", "timestamp": datetime.utcnow().isoformat()}
        
        if not source_path.exists():
            return {"error": "Source not found", "timestamp": datetime.utcnow().isoformat()}
        
        shutil.move(str(source_path), str(dest_path))
        logger.info("File moved", source=source, destination=destination)
        
        return {"success": True, "source": source, "destination": destination, 
                "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        logger.error("Failed to move file", error=str(e))
        return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}

@app.delete("/api/library/delete")
async def delete_file(path: str):
    """Delete file or folder"""
    try:
        from pathlib import Path
        import shutil
        
        file_path = Path(path)
        
        # Validate path is in allowed directories
        allowed_bases = [Path("/app/shared_storage"), Path("/app/mcp_skills")]
        if not any(str(file_path).startswith(str(b)) for b in allowed_bases):
            return {"error": "Invalid delete path", "timestamp": datetime.utcnow().isoformat()}
        
        if not file_path.exists():
            return {"error": "File not found", "timestamp": datetime.utcnow().isoformat()}
        
        if file_path.is_dir():
            shutil.rmtree(file_path)
        else:
            file_path.unlink()
        
        logger.info("File deleted", path=path)
        
        return {"success": True, "path": path, "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        logger.error("Failed to delete file", error=str(e))
        return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/library/download/{path:path}")
async def download_file(path: str):
    """Download file from library"""
    try:
        from pathlib import Path
        from fastapi.responses import FileResponse
        
        file_path = Path(f"/app/{path}")
        
        # Validate path
        allowed_bases = [Path("/app/shared_storage"), Path("/app/mcp_skills")]
        if not any(str(file_path).startswith(str(b)) for b in allowed_bases):
            raise HTTPException(status_code=403, detail="Access denied")
        
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        
        return FileResponse(
            path=str(file_path),
            filename=file_path.name,
            media_type="application/octet-stream"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to download file", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

# --- Log Capture for UI Display ---
import collections
log_buffer = collections.deque(maxlen=500)  # Keep last 500 log lines

# Custom handler to capture logs into buffer
class UILogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            log_buffer.append(msg + '\n')
        except Exception:
            pass

# Attach handler
_ui_log_handler = UILogHandler()
_ui_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
logging.getLogger().addHandler(_ui_log_handler)
logging.getLogger('uvicorn').addHandler(_ui_log_handler)

@app.get("/api/system/logs")
async def get_system_logs():
    """Get captured system logs from buffer for UI display"""
    return {"logs": list(log_buffer)}

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=USER_AGENT_PORT,
        reload=False,
        log_level="info"
    )
