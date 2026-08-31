
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import numpy as np

import os
from .conversational_state import ConversationalHDCState
from .memory_integration import ConversationMemoryIntegration

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ConversationalHDC_API")

app = FastAPI(title="ARCA Conversational HDC Service", version="1.0.0")

# --- In-Memory State Management ---
# In a production scaled env, this would be Redis-backed.
# For now, we keep state in memory per user session.
active_sessions: dict[str, ConversationalHDCState] = {}

# Use environment variables for Qdrant configuration
qdrant_host = os.getenv("QDRANT_HOST", "qdrant")
qdrant_port = int(os.getenv("QDRANT_PORT", 6333))

memory_service = ConversationMemoryIntegration(qdrant_host=qdrant_host, qdrant_port=qdrant_port)

# --- Pydantic Models ---
class MessageRequest(BaseModel):
    user_id: str
    session_id: str
    role: str
    content: str
    embedding: List[float] # Dense embedding input
    detected_topics: Optional[List[str]] = None
    detected_sentiment: Optional[str] = None
    detected_intent: Optional[str] = None

class ContextRequest(BaseModel):
    user_id: str
    session_id: str
    query: str
    query_embedding: List[float]

class SaveRequest(BaseModel):
    user_id: str
    session_id: str
    metadata: Optional[dict] = {}

# --- Helper ---
def get_session(session_id: str) -> ConversationalHDCState:
    if session_id not in active_sessions:
        # Initialize new state
        active_sessions[session_id] = ConversationalHDCState(hv_dim=10000)
    return active_sessions[session_id]

# --- Endpoints ---

@app.post("/conversation/message")
async def add_message(req: MessageRequest):
    try:
        state = get_session(req.session_id)
        
        # Convert list -> numpy
        emb = np.array(req.embedding)
        
        state.add_message(
            role=req.role,
            content=req.content,
            content_embedding=emb,
            detected_topics=req.detected_topics,
            detected_sentiment=req.detected_sentiment,
            detected_intent=req.detected_intent
        )
        return {"status": "bound", "message_count": state.message_count}
    except Exception as e:
        logger.error(f"Error adding message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/conversation/context")
async def get_context(req: ContextRequest):
    try:
        state = get_session(req.session_id)
        emb = np.array(req.query_embedding)
        
        context_str = state.extract_context_for_llm(req.query, emb)
        
        # Also grab past conversations
        past = await memory_service.get_relevant_past_conversations(state, req.user_id)
        
        return {
            "hdc_context": context_str,
            "past_conversations": past
        }
    except Exception as e:
         logger.error(f"Error getting context: {e}")
         raise HTTPException(status_code=500, detail=str(e))

@app.post("/conversation/save")
async def save_session(req: SaveRequest):
    try:
        session_id = req.session_id
        if session_id not in active_sessions:
            return {"status": "ignored", "reason": "no_active_session"}
            
        state = active_sessions[session_id]
        
        # Save to Qdrant
        await memory_service.save_conversation(req.user_id, state, req.metadata)
        
        # Clear from memory
        del active_sessions[session_id]
        
        return {"status": "saved"}
    except Exception as e:
        logger.error(f"Error saving session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "healthy", "active_sessions": len(active_sessions)}
