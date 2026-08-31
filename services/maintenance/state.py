from typing import TypedDict, Annotated, List, Dict, Any, Optional, Literal
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    """LangGraph state for Maintainer Agents"""
    # Messaging
    messages: Annotated[List[BaseMessage], add_messages]
    
    # Task context
    task_id: str
    agent_type: str
    operation: str
    params: Dict[str, Any]
    sop_content: str
    
    # Reasoning trajectory
    plan: Optional[str]
    execution_log: List[str]
    validation_results: List[str]
    
    # Control flow
    current_node: str
    next_node: str
    retry_count: int
    max_retries: int
    
    # Escalation and External calls
    escalation_requested: bool
    escalation_reason: Optional[str]
    serena_feedback: Optional[str]
    gordon_feedback: Optional[str] # For Docker agent
    
    # Security/Firewall
    headers: Optional[Dict[str, str]]
    
    # Final Result
    success: bool
    output: Optional[Any]
    error: Optional[str]
