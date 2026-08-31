"""
Optimized State Schemas for LangGraph Multi-Agent System
Implements best practices from architectural document:
- Strict separation of control data vs conversational context
- Prevents "information saturation" failure mode
- Efficient token usage through structured state
"""

from typing import TypedDict, Annotated, List, Dict, Any, Optional, Literal
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from dataclasses import dataclass, field
from datetime import datetime
import json


# ============================================================================
# Global State Schema - Primary Orchestrator
# ============================================================================

class GlobalState(TypedDict):
    """
    Global state for the primary orchestrator's reasoning.
    
    Architectural principle: Strict separation between:
    1. Large, unstructured conversational data (messages)
    2. Small, structured control data (other fields)
    
    This prevents "information saturation" by ensuring only necessary
    context is passed to LLM for reasoning while control flow uses
    efficient programmatic data.
    """
    
    # ---- Conversational Context (for LLM reasoning) ----
    # Uses add_messages reducer to append (not overwrite) messages
    messages: Annotated[List[BaseMessage], add_messages]
    
    # ---- Workflow Control Data (for programmatic routing) ----
    # Small, token-efficient data for conditional edges
    main_task_description: str
    overall_plan: List[str]
    sub_task_queue: List[Dict[str, Any]]
    completed_sub_tasks: Dict[str, Any]
    last_action_status: Literal["success", "failure", "pending", ""]
    
    # ---- Agent Assignment ----
    current_agent: str  # supervisor, architect, engineer, reviewer
    next_agent: str
    
    # ---- Error Handling ----
    error_count: int
    last_error: str
    retry_strategy: str
    
    # ---- Session Metadata ----
    session_id: str
    user_id: str
    task_id: str
    started_at: str
    
    # ---- Memory Integration ----
    retrieved_context: List[Dict[str, Any]]  # From vector DB
    relevant_skills: List[str]  # From skills bank
    graph_insights: List[Dict[str, Any]]  # From Neo4j


# ============================================================================
# Sub-Agent State Schemas - Specialized Workflows
# ============================================================================

class EngineerAgentState(TypedDict):
    """
    Independent state for Engineer Agent (MiniMax M2).
    Uses "Invoke from Node" pattern - completely separate from GlobalState.
    
    Optimized for MiniMax M2's strengths:
    - Multi-file edits
    - Compile-run-fix loops
    - Test-validated repairs
    """
    messages: Annotated[List[BaseMessage], add_messages]
    
    # Task specification
    task_description: str
    requirements: List[str]
    target_files: List[str]
    
    # Execution tracking
    test_status: Literal["pending", "passed", "failed", ""]
    test_output: str
    compile_status: Literal["success", "error", ""]
    compile_output: str
    
    # Iteration control
    attempt_number: int
    max_attempts: int
    
    # Result
    modified_files: Dict[str, str]  # filename -> new content
    summary: str
    success: bool


class ArchitectAgentState(TypedDict):
    """
    Independent state for Architect Agent (Grok Code Fast).
    
    Optimized for Grok's strengths:
    - Fast reasoning
    - System design
    - Planning
    """
    messages: Annotated[List[BaseMessage], add_messages]
    
    # Input
    task_description: str
    current_architecture: str
    constraints: List[str]
    
    # Output
    design_document: str
    implementation_plan: List[Dict[str, Any]]
    risk_analysis: List[str]
    success: bool


class ReviewerAgentState(TypedDict):
    """
    Independent state for Reviewer Agent (Gemini).
    
    Optimized for review tasks:
    - Code quality analysis
    - Bug detection
    - Style validation
    """
    messages: Annotated[List[BaseMessage], add_messages]
    
    # Input
    code_to_review: Dict[str, str]  # filename -> content
    requirements: List[str]
    style_guide: str
    
    # Output
    issues_found: List[Dict[str, Any]]
    suggestions: List[str]
    approval_status: Literal["approved", "needs_changes", "rejected"]
    feedback: str
    success: bool


class WorkerAgentState(TypedDict):
    """
    State for background Worker Agent (IBM Granite 3B).
    
    Used for overnight batch processing:
    - Summarization
    - Topic modeling
    - ReasoningBank refinement
    """
    messages: Annotated[List[BaseMessage], add_messages]
    
    # Input
    job_type: Literal["summarize", "topic_model", "analyze_trace", "forge_skill"]
    input_data: Any
    
    # Processing
    progress: float  # 0.0 to 1.0
    
    # Output
    result: Any
    metadata: Dict[str, Any]
    success: bool


# ============================================================================
# Task Delegation - Input/Output Transformations
# ============================================================================

@dataclass
class TaskDelegation:
    """
    Encapsulates task delegation to sub-agent.
    Implements the "Invoke from Node" pattern with state transformations.
    """
    task_type: str
    target_agent: str
    input_data: Dict[str, Any]
    parent_task_id: str
    
    def to_subagent_state(self, agent_type: str) -> Dict[str, Any]:
        """
        Transform global state data into sub-agent's input state.
        This is the "input transformation function" from the architectural doc.
        """
        if agent_type == "engineer":
            return {
                "task_description": self.input_data.get("description", ""),
                "requirements": self.input_data.get("requirements", []),
                "target_files": self.input_data.get("files", []),
                "attempt_number": 1,
                "max_attempts": 3,
                "messages": [self._create_engineer_system_message()],
            }
        
        elif agent_type == "architect":
            return {
                "task_description": self.input_data.get("description", ""),
                "current_architecture": self.input_data.get("current_arch", ""),
                "constraints": self.input_data.get("constraints", []),
                "messages": [self._create_architect_system_message()],
            }
        
        elif agent_type == "reviewer":
            return {
                "code_to_review": self.input_data.get("code", {}),
                "requirements": self.input_data.get("requirements", []),
                "style_guide": self.input_data.get("style_guide", ""),
                "messages": [self._create_reviewer_system_message()],
            }
        
        elif agent_type == "worker":
            return {
                "job_type": self.input_data.get("job_type", "summarize"),
                "input_data": self.input_data.get("data", ""),
                "progress": 0.0,
                "messages": [self._create_worker_system_message()],
            }
        
        raise ValueError(f"Unknown agent type: {agent_type}")
    
    def from_subagent_result(self, agent_type: str, result_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract result from sub-agent's output state for parent graph.
        This is the "output transformation function" from the architectural doc.
        """
        return {
            "agent_type": agent_type,
            "task_type": self.task_type,
            "success": result_state.get("success", False),
            "result": self._extract_result_data(agent_type, result_state),
            "metadata": {
                "task_id": self.parent_task_id,
                "completed_at": datetime.utcnow().isoformat(),
            }
        }
    
    def _extract_result_data(self, agent_type: str, state: Dict[str, Any]) -> Any:
        """Extract relevant result data based on agent type"""
        if agent_type == "engineer":
            return {
                "modified_files": state.get("modified_files", {}),
                "test_status": state.get("test_status", ""),
                "summary": state.get("summary", ""),
            }
        elif agent_type == "architect":
            return {
                "design_document": state.get("design_document", ""),
                "implementation_plan": state.get("implementation_plan", []),
                "risk_analysis": state.get("risk_analysis", []),
            }
        elif agent_type == "reviewer":
            return {
                "issues_found": state.get("issues_found", []),
                "approval_status": state.get("approval_status", ""),
                "feedback": state.get("feedback", ""),
            }
        elif agent_type == "worker":
            return state.get("result", None)
        
        return None
    
    def _create_engineer_system_message(self):
        from langchain_core.messages import SystemMessage
        from prompt_templates import MinimaxPromptOptimizer
        return SystemMessage(content=MinimaxPromptOptimizer.create_engineer_system_prompt())
    
    def _create_architect_system_message(self):
        from langchain_core.messages import SystemMessage
        return SystemMessage(content="You are an expert system architect...")
    
    def _create_reviewer_system_message(self):
        from langchain_core.messages import SystemMessage
        return SystemMessage(content="You are an expert code reviewer...")
    
    def _create_worker_system_message(self):
        from langchain_core.messages import SystemMessage
        return SystemMessage(content="You are a background processing agent...")


# ============================================================================
# Memory Integration Data Structures
# ============================================================================

@dataclass
class VectorSearchResult:
    """Result from Oracle 26ai vector database (Layer 2 memory)"""
    document_id: str
    content_preview: str  # First 500 chars
    similarity_score: float
    metadata: Dict[str, Any]
    source: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.document_id,
            "preview": self.content_preview,
            "score": self.similarity_score,
            "metadata": self.metadata,
            "source": self.source,
        }


@dataclass
class GraphSearchResult:
    """Result from Neo4j knowledge graph (Layer 3 memory)"""
    node_id: str
    node_type: str  # Concept, Skill, Document, etc.
    properties: Dict[str, Any]
    relationships: List[Dict[str, Any]]
    relevance_score: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.node_id,
            "type": self.node_type,
            "properties": self.properties,
            "relationships": self.relationships,
            "score": self.relevance_score,
        }


@dataclass
class SkillReference:
    """Reference to a skill from the MCP skills bank"""
    skill_id: str
    skill_name: str
    description: str
    tags: List[str]
    usage_count: int
    success_rate: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.skill_id,
            "name": self.skill_name,
            "description": self.description,
            "tags": self.tags,
            "usage": self.usage_count,
            "success_rate": self.success_rate,
        }


# ============================================================================
# Helper Functions
# ============================================================================

def create_initial_state(user_input: str, session_id: str, user_id: str) -> GlobalState:
    """Create initial GlobalState from user request"""
    from langchain_core.messages import HumanMessage
    
    return {
        "messages": [HumanMessage(content=user_input)],
        "main_task_description": user_input,
        "overall_plan": [],
        "sub_task_queue": [],
        "completed_sub_tasks": {},
        "last_action_status": "",
        "current_agent": "supervisor",
        "next_agent": "",
        "error_count": 0,
        "last_error": "",
        "retry_strategy": "",
        "session_id": session_id,
        "user_id": user_id,
        "task_id": f"task_{datetime.utcnow().timestamp()}",
        "started_at": datetime.utcnow().isoformat(),
        "retrieved_context": [],
        "relevant_skills": [],
        "graph_insights": [],
    }


def serialize_state_for_checkpoint(state: GlobalState) -> str:
    """Serialize state for checkpointing (SQLite)"""
    # Convert messages to serializable format
    serializable = dict(state)
    serializable["messages"] = [
        {"type": msg.__class__.__name__, "content": msg.content}
        for msg in state["messages"]
    ]
    return json.dumps(serializable)


if __name__ == "__main__":
    # Example: Create initial state
    state = create_initial_state(
        user_input="Add authentication to the API",
        session_id="test_session",
        user_id="user_123"
    )
    print("Initial State:")
    print(json.dumps({k: v for k, v in state.items() if k != "messages"}, indent=2))
    
    # Example: Task delegation
    delegation = TaskDelegation(
        task_type="code_implementation",
        target_agent="engineer",
        input_data={
            "description": "Implement JWT authentication",
            "requirements": ["Use FastAPI", "Store tokens in Redis"],
            "files": ["main.py", "auth.py"]
        },
        parent_task_id="task_123"
    )
    
    engineer_input = delegation.to_subagent_state("engineer")
    print("\nEngineer Agent Input State:")
    print(json.dumps({k: v for k, v in engineer_input.items() if k != "messages"}, indent=2))
