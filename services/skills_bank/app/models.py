
# services/skills_bank/app/models.py
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime

class Skill(BaseModel):
    name: str = Field(..., description="Unique name of the skill")
    description: str = Field(..., description="What the skill does")
    code_snippet: Optional[str] = Field(None, description="Actual code or command template")
    parameters: Dict[str, str] = Field(default_factory=dict, description="Parameter names and descriptions")
    category: str = Field("general", description="Category: git, docker, db, etc.")
    tags: List[str] = Field(default_factory=list)
    
class ReasoningTrace(BaseModel):
    """A record of a reasoning path, successful or failed."""
    trace_id: Optional[str] = None
    task_description: str
    steps_taken: List[str]
    outcome: str = Field(..., description="success, failure, or partial")
    reasoning_summary: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class SearchResult(BaseModel):
    skill: Optional[Skill] = None
    trace: Optional[ReasoningTrace] = None
    score: float
    source: str = Field("qdrant", description="Where this result came from")
