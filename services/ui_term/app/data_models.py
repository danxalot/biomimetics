
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

class ChatMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    role: str = "user"  # user, assistant, system
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = None

class UserSession(BaseModel):
    session_id: str
    user_email: str = "admin@localhost"
    messages: List[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    context: Dict[str, Any] = Field(default_factory=dict)

class AgentRequest(BaseModel):
    objective: str
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class MCPRequest(BaseModel):
    method: str
    params: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None
