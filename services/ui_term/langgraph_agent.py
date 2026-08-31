"""
LangGraph Agent Workflow System
Implements StateGraph-based workflow management with ReasoningBank integration
"""

import asyncio
from typing import Dict, List, Any, Optional, TypedDict, Literal
from dataclasses import dataclass, asdict
from datetime import datetime
import json
import uuid

from langgraph.graph import StateGraph, END, START

# Temporarily disable checkpointing for initial testing
# from langgraph.checkpoint.sqlite import SqliteSaver
SqliteSaver = None
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

import logging

logger = logging.getLogger(__name__)

# Import ARCA's Inverse Attention System
try:
    from inverse_attention import get_inverse_attention, InverseAttentionSystem

    INVERSE_ATTENTION_AVAILABLE = True
except ImportError:
    INVERSE_ATTENTION_AVAILABLE = False
    logger.warning("Inverse Attention System not available")

# Import Pythia Integration
try:
    from pythia_integration import get_pythia_client, pythia_geometric_analysis

    PYTHIA_AVAILABLE = True
except ImportError:
    PYTHIA_AVAILABLE = False
    logger.warning("Pythia integration not available")


class AgentWorkflowState(TypedDict, total=False):
    """State definition for LangGraph agent workflows"""

    # Core workflow data
    session_id: str
    user_id: str
    task_input: str
    current_step: str

    # Context and memory
    conversation_context: List[Dict[str, Any]]
    retrieved_memory: Dict[str, Any]
    working_memory: Dict[str, Any]

    # Reasoning and learning
    reasoning_trajectory: List[Dict[str, Any]]
    action_history: List[Dict[str, Any]]
    success_metrics: Dict[str, float]

    # Agent responses
    agent_response: str
    tool_results: List[Dict[str, Any]]

    # Geometric analysis results
    geometric_results: List[Dict[str, Any]]

    # Pythia participant (Option B: raw vector interpretation + LLM synthesis)
    pythia_raw: Optional[str]  # Raw interpreter output from geometry_onnx_interpreter
    pythia_vector_energy: Optional[float]  # Energy of the 2048-dim response vector
    pythia_processing_ms: Optional[float]  # Pipeline processing time

    # Workflow control
    next_action: str
    error_state: Optional[Dict[str, Any]]
    completion_status: Literal["pending", "success", "failure", "retry"]


@dataclass
class ReasoningTrajectory:
    """Structured representation of agent reasoning trajectory"""

    trajectory_id: str
    session_id: str
    timestamp: datetime
    initial_state: Dict[str, Any]
    actions_taken: List[Dict[str, Any]]
    final_state: Dict[str, Any]
    outcome: Literal["success", "failure", "partial"]
    execution_time: float
    context_used: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ReasoningBankFramework:
    """
    Implementation of Google's ReasoningBank framework
    Enables agents to learn from experience through retrieve->execute->judge->distill->consolidate cycle
    """

    def __init__(self):
        self.memory_store = {}  # In production, this would be Neo4j
        self.reasoning_cache = {}
        self.strategy_library = {}

    async def retrieve_relevant_strategies(
        self, task_context: str, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Retrieve top-k most relevant reasoning strategies from past experiences"""
        try:
            # In production: embedding-based similarity search against Neo4j
            # For now, simple keyword matching
            relevant_strategies = []

            for strategy_id, strategy in self.strategy_library.items():
                if any(
                    keyword in task_context.lower()
                    for keyword in strategy.get("keywords", [])
                ):
                    relevant_strategies.append(strategy)

            return relevant_strategies[:top_k]

        except Exception as e:
            logger.error(f"Error retrieving strategies: {e}")
            return []

    async def judge_trajectory(self, trajectory: ReasoningTrajectory) -> Dict[str, Any]:
        """LLM-as-a-judge evaluation of execution trajectory"""
        try:
            # Create judgment prompt
            judgment_prompt = f"""
            Evaluate this agent execution trajectory:
            
            Task: {trajectory.initial_state.get("task_input", "Unknown")}
            Actions: {json.dumps(trajectory.actions_taken, indent=2)}
            Outcome: {trajectory.outcome}
            Execution Time: {trajectory.execution_time}s
            
            Assess:
            1. Was the task completed successfully?
            2. Were the actions efficient and appropriate?
            3. What could be improved?
            4. What worked well?
            
            Provide structured judgment with success score (0-1) and lessons learned.
            """

            # In production: use actual LLM for judgment
            # For now, simple heuristic evaluation
            success_score = 1.0 if trajectory.outcome == "success" else 0.3

            judgment = {
                "success_score": success_score,
                "efficiency_score": max(0.1, 1.0 - (trajectory.execution_time / 30.0)),
                "lessons_learned": self._extract_lessons(trajectory),
                "improvement_suggestions": self._suggest_improvements(trajectory),
                "validated_patterns": self._identify_patterns(trajectory),
            }

            return judgment

        except Exception as e:
            logger.error(f"Error judging trajectory: {e}")
            return {"success_score": 0.0, "error": str(e)}

    async def distill_memory_items(
        self, trajectory: ReasoningTrajectory, judgment: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Distill trajectory into structured memory items for consolidation"""
        try:
            memory_items = []

            # Success patterns
            if judgment["success_score"] > 0.7:
                success_item = {
                    "type": "success_pattern",
                    "title": f"Successful {trajectory.initial_state.get('task_type', 'task')} execution",
                    "description": f"Effective strategy for {trajectory.initial_state.get('task_input', 'task')}",
                    "content": {
                        "strategy": trajectory.actions_taken,
                        "context": trajectory.context_used,
                        "success_factors": judgment.get("validated_patterns", []),
                    },
                    "confidence": judgment["success_score"],
                    "created_at": trajectory.timestamp.isoformat(),
                }
                memory_items.append(success_item)

            # Anti-patterns (failure lessons)
            if judgment["success_score"] < 0.5:
                failure_item = {
                    "type": "anti_pattern",
                    "title": f"Avoid: {trajectory.initial_state.get('task_type', 'task')} failure pattern",
                    "description": f"Lessons from failed {trajectory.initial_state.get('task_input', 'task')}",
                    "content": {
                        "failed_actions": trajectory.actions_taken,
                        "failure_context": trajectory.context_used,
                        "lessons": judgment.get("lessons_learned", []),
                        "improvements": judgment.get("improvement_suggestions", []),
                    },
                    "confidence": 1.0 - judgment["success_score"],
                    "created_at": trajectory.timestamp.isoformat(),
                }
                memory_items.append(failure_item)

            return memory_items

        except Exception as e:
            logger.error(f"Error distilling memory items: {e}")
            return []

    async def consolidate_memory(self, memory_items: List[Dict[str, Any]]) -> bool:
        """Consolidate new memory items into the ReasoningBank"""
        try:
            for item in memory_items:
                item_id = str(uuid.uuid4())
                self.strategy_library[item_id] = item

                # In production: store in Neo4j with proper relationships
                logger.info(f"Consolidated memory item: {item['title']}")

            return True

        except Exception as e:
            logger.error(f"Error consolidating memory: {e}")
            return False

    def _extract_lessons(self, trajectory: ReasoningTrajectory) -> List[str]:
        """Extract lessons learned from trajectory"""
        lessons = []
        if trajectory.outcome == "failure":
            lessons.append("Verify prerequisites before action execution")
            lessons.append("Implement proper error handling")
        elif trajectory.execution_time > 20:
            lessons.append("Consider optimizing for execution speed")
        return lessons

    def _suggest_improvements(self, trajectory: ReasoningTrajectory) -> List[str]:
        """Suggest improvements based on trajectory analysis"""
        suggestions = []
        if len(trajectory.actions_taken) > 10:
            suggestions.append("Break complex tasks into smaller steps")
        if trajectory.outcome == "partial":
            suggestions.append("Add checkpoints for partial completion recovery")
        return suggestions

    def _identify_patterns(self, trajectory: ReasoningTrajectory) -> List[str]:
        """Identify successful patterns in trajectory"""
        patterns = []
        if trajectory.outcome == "success":
            patterns.append("Sequential action execution with context preservation")
            if len(trajectory.actions_taken) <= 5:
                patterns.append("Efficient task decomposition")
        return patterns


class MCPLangGraphIntegration:
    """
    Enhanced MCP integration for LangGraph workflows
    Provides context fusion, tool orchestration, and governance
    """

    def __init__(self, mcp_server_url: str = "http://localhost:8081"):
        self.mcp_server_url = mcp_server_url
        self.reasoning_bank = ReasoningBankFramework()
        self.policy_engine = NegativeSkillsPolicyEngine()

    async def get_unified_context(
        self, task_input: str, session_id: str
    ) -> Dict[str, Any]:
        """Retrieve and fuse context from all memory layers"""
        try:
            # Layer 1: Working Memory (conversation context)
            working_memory = await self._get_conversation_context(session_id)

            # Layer 2: Episodic Memory (vector database RAG)
            episodic_memory = await self._get_episodic_context(task_input)

            # Layer 3: Structural Memory (Neo4j knowledge graph)
            structural_memory = await self._get_structural_context(task_input)

            # ReasoningBank strategies
            reasoning_strategies = (
                await self.reasoning_bank.retrieve_relevant_strategies(task_input)
            )

            unified_context = {
                "working_memory": working_memory,
                "episodic_memory": episodic_memory,
                "structural_memory": structural_memory,
                "reasoning_strategies": reasoning_strategies,
                "fusion_timestamp": datetime.now().isoformat(),
            }

            return unified_context

        except Exception as e:
            logger.error(f"Error getting unified context: {e}")
            return {"error": str(e)}

    async def execute_with_governance(
        self, action: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute action with policy enforcement and governance"""
        try:
            # Check negative skills constraints
            policy_check = await self.policy_engine.check_action_constraints(
                action, context
            )

            if not policy_check["allowed"]:
                return {
                    "status": "blocked",
                    "reason": policy_check["reason"],
                    "suggested_alternative": policy_check.get("alternative"),
                    "policy_violated": policy_check.get("policy_id"),
                }

            # Execute action (placeholder - integrate with actual MCP server)
            result = await self._execute_action(action, context)

            # Record successful execution for learning
            if result.get("status") == "success":
                await self._record_successful_pattern(action, context, result)

            return result

        except Exception as e:
            logger.error(f"Error in governed execution: {e}")
            return {"status": "error", "error": str(e)}

    async def _get_conversation_context(self, session_id: str) -> Dict[str, Any]:
        """Retrieve conversation context from working memory"""
        try:
            if self.mcp_client:
                result = self.mcp_client.call_tool(
                    "get_working_memory", {"session_id": session_id, "max_messages": 20}
                )
                if result.get("error"):
                    logger.error(
                        f"Error retrieving working memory: {result.get('error')}"
                    )
                    return {"recent_messages": [], "session_summary": ""}
                return {
                    "recent_messages": result.get("messages", []),
                    "session_summary": result.get("summary", ""),
                }
            else:
                logger.warning(
                    "MCP client unavailable for conversation context retrieval"
                )
                return {"recent_messages": [], "session_summary": ""}
        except Exception as e:
            logger.error(f"Error retrieving conversation context: {e}")
            return {"recent_messages": [], "session_summary": ""}

    async def _get_episodic_context(self, query: str) -> Dict[str, Any]:
        """Retrieve relevant past experiences from vector database"""
        try:
            if self.mcp_client:
                result = self.mcp_client.call_tool(
                    "semantic_search_episodic_memory", {"query": query, "top_k": 5}
                )
                if result.get("error"):
                    logger.error(
                        f"Error searching episodic memory: {result.get('error')}"
                    )
                    return {"relevant_documents": [], "similarity_scores": []}
                return {
                    "relevant_documents": result.get("documents", []),
                    "similarity_scores": result.get("scores", []),
                }
            else:
                logger.warning("MCP client unavailable for episodic memory retrieval")
                return {"relevant_documents": [], "similarity_scores": []}
        except Exception as e:
            logger.error(f"Error retrieving episodic context: {e}")
            return {"relevant_documents": [], "similarity_scores": []}

    async def _get_structural_context(self, query: str) -> Dict[str, Any]:
        """Retrieve structural knowledge from Neo4j graph"""
        try:
            if self.mcp_client:
                result = self.mcp_client.call_tool(
                    "query_structural_memory", {"query": query, "limit": 10}
                )
                if result.get("error"):
                    logger.error(
                        f"Error querying structural memory: {result.get('error')}"
                    )
                    return {"related_entities": [], "relationships": []}
                return {
                    "related_entities": result.get("entities", []),
                    "relationships": result.get("relationships", []),
                }
            else:
                logger.warning("MCP client unavailable for structural memory retrieval")
                return {"related_entities": [], "relationships": []}
        except Exception as e:
            logger.error(f"Error retrieving structural context: {e}")
            return {"related_entities": [], "relationships": []}

    async def _execute_action(
        self, action: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute action through MCP server"""
        try:
            if not self.mcp_client:
                logger.error("MCP client unavailable for action execution")
                return {"status": "error", "error": "MCP client unavailable"}

            action_type = action.get("type")
            tool_name = f"execute_{action_type}" if action_type else "execute_generic"

            result = self.mcp_client.call_tool(
                tool_name, {"action": action, "context": context}
            )

            if result.get("error"):
                logger.error(f"Action execution failed: {result.get('error')}")
                return {
                    "status": "error",
                    "error": result.get("error"),
                    "action": action,
                }

            logger.info(f"Action {action_type} executed successfully")
            return {
                "status": "success",
                "result": result.get("output", result),
                "action": action,
            }
        except Exception as e:
            logger.error(f"Error executing action: {e}")
            return {"status": "error", "error": str(e), "action": action}

    async def _record_successful_pattern(
        self, action: Dict[str, Any], context: Dict[str, Any], result: Dict[str, Any]
    ):
        """Record successful action pattern for future learning"""
        try:
            pattern = {
                "action": action,
                "context": context,
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }

            if self.mcp_client:
                store_result = self.mcp_client.call_tool(
                    "store_episodic_memory",
                    {
                        "content": json.dumps(pattern),
                        "metadata": {
                            "type": "successful_pattern",
                            "action_type": action.get("type"),
                        },
                    },
                )

                if not store_result.get("error"):
                    logger.info(
                        f"Recorded successful pattern: {action.get('type', 'unknown')}"
                    )
                else:
                    logger.warning(
                        f"Failed to record pattern: {store_result.get('error')}"
                    )
            else:
                logger.warning("MCP client unavailable for pattern recording")
        except Exception as e:
            logger.error(f"Error recording successful pattern: {e}")


class NegativeSkillsPolicyEngine:
    """
    Implementation of negative skills as dynamic behavioral constraints
    Enforced through LangGraph conditional edges and MCP governance
    """

    def __init__(self):
        self.anti_patterns = {}
        self.policy_rules = {}

    async def check_action_constraints(
        self, action: Dict[str, Any], context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Check if proposed action violates any learned constraints"""
        try:
            # Check against anti-patterns
            for pattern_id, anti_pattern in self.anti_patterns.items():
                if self._matches_anti_pattern(action, anti_pattern):
                    return {
                        "allowed": False,
                        "reason": f"Action matches known anti-pattern: {anti_pattern['description']}",
                        "policy_id": pattern_id,
                        "alternative": anti_pattern.get("suggested_alternative"),
                    }

            # Check against policy rules
            for rule_id, rule in self.policy_rules.items():
                if not self._complies_with_rule(action, rule):
                    return {
                        "allowed": False,
                        "reason": f"Action violates policy rule: {rule['description']}",
                        "policy_id": rule_id,
                    }

            return {"allowed": True}

        except Exception as e:
            logger.error(f"Error checking constraints: {e}")
            return {"allowed": True, "error": str(e)}  # Fail open for safety

    async def add_anti_pattern(self, pattern: Dict[str, Any]) -> str:
        """Add new anti-pattern from failed trajectory"""
        pattern_id = str(uuid.uuid4())
        self.anti_patterns[pattern_id] = {
            **pattern,
            "created_at": datetime.now().isoformat(),
            "confidence": pattern.get("confidence", 0.8),
        }
        logger.info(f"Added anti-pattern: {pattern.get('description', pattern_id)}")
        return pattern_id

    def _matches_anti_pattern(
        self, action: Dict[str, Any], anti_pattern: Dict[str, Any]
    ) -> bool:
        """Check if action matches a known anti-pattern"""
        # Simple pattern matching - in production, use more sophisticated matching
        action_type = action.get("type", "")
        pattern_type = anti_pattern.get("action_type", "")
        return action_type == pattern_type and action.get("target") == anti_pattern.get(
            "target"
        )

    def _complies_with_rule(self, action: Dict[str, Any], rule: Dict[str, Any]) -> bool:
        """Check if action complies with policy rule"""
        # Simple rule checking - expand based on actual policy requirements
        return True  # Placeholder


class AgentWorkflowEngine:
    """
    Main LangGraph workflow engine for agent orchestration
    Replaces CrewAI with StateGraph-based execution
    """

    def __init__(self, llm_server_url: str = "http://gateway:8080"):
        # Route through gateway using role-based model resolution.
        # The gateway resolves "chat" -> the configured CHAT_MODEL via model_config.py.
        self.llm = ChatOpenAI(
            base_url=f"{llm_server_url}/v1",
            api_key="dummy-key",
            model="chat",
            default_headers={"X-Genesis-Chain": "ui_term:langgraph_agent"},
        )
        self.mcp_integration = MCPLangGraphIntegration()
        # Temporarily disable checkpointing for initial testing
        self.checkpointer = None  # SqliteSaver.from_conn_string(":memory:")

        # Pythia integration (optional)
        self.pythia_client = get_pythia_client() if PYTHIA_AVAILABLE else None

        # Pythia LLM client (port 11436, separate from maintainer port 11435)
        self.pythia_llm = ChatOpenAI(
            base_url=f"{llm_server_url}/v1",
            api_key="dummy-key",
            model="arca_chat",
            default_headers={"X-Genesis-Chain": "ui_term:pythia_participant"},
        )

        # Build the workflow graph
        self.workflow = self._build_workflow_graph()

    def _build_workflow_graph(self) -> StateGraph:
        """Build the main agent workflow using LangGraph StateGraph"""

        # Create workflow graph
        workflow = StateGraph(AgentWorkflowState)

        # Add nodes
        workflow.add_node("context_retrieval", self._context_retrieval_node)
        workflow.add_node("pythia_participant", self._pythia_participant_node)
        workflow.add_node("geometric_analysis", self._geometric_analysis_node)
        workflow.add_node("reasoning_agent", self._reasoning_agent_node)
        workflow.add_node("action_execution", self._action_execution_node)
        workflow.add_node("outcome_evaluation", self._outcome_evaluation_node)
        workflow.add_node("memory_consolidation", self._memory_consolidation_node)
        workflow.add_node("error_recovery", self._error_recovery_node)

        # Define entry point
        workflow.set_entry_point("context_retrieval")

        # After context retrieval, run Pythia participant (embedding->ONNX->interpret)
        workflow.add_conditional_edges(
            "context_retrieval",
            self._should_proceed_to_reasoning,
            {"proceed": "pythia_participant", "error": "error_recovery"},
        )

        # Pythia participant feeds into geometric analysis (keyword-gated)
        workflow.add_edge("pythia_participant", "geometric_analysis")

        # Geometric analysis edge (if Pythia is available)
        if PYTHIA_AVAILABLE:
            workflow.add_conditional_edges(
                "geometric_analysis",
                self._should_proceed_to_reasoning,
                {
                    "proceed": "reasoning_agent",
                    "skip": "reasoning_agent",  # Skip if no geometric data
                    "error": "error_recovery",
                },
            )
        else:
            # If Pythia not available, skip geometric analysis
            workflow.add_edge("geometric_analysis", "reasoning_agent")

        workflow.add_conditional_edges(
            "reasoning_agent",
            self._should_execute_action,
            {
                "execute": "action_execution",
                "complete": "outcome_evaluation",
                "retry": "reasoning_agent",
                "error": "error_recovery",
            },
        )

        workflow.add_conditional_edges(
            "action_execution",
            self._evaluate_action_result,
            {
                "success": "outcome_evaluation",  # Default success path if singular
                "continue_reasoning": "reasoning_agent",  # The Loop
                "retry": "reasoning_agent",
                "error": "error_recovery",
            },
        )

        workflow.add_edge("outcome_evaluation", "memory_consolidation")
        workflow.add_edge("memory_consolidation", END)
        workflow.add_edge("error_recovery", END)

        return workflow

    async def _pythia_participant_node(
        self, state: AgentWorkflowState
    ) -> AgentWorkflowState:
        """Pythia participant: run user input through embedding->ONNX->interpret pipeline.

        Every user message is sent through the Pythia pipeline. The raw
        interpreter output is stored in state['pythia_raw'] so it can be
        displayed alongside the LLM response (Option B).
        """
        try:
            if not self.pythia_client or not PYTHIA_AVAILABLE:
                logger.info("Pythia not available, skipping participant node")
                state["pythia_raw"] = None
                state["current_step"] = "pythia_skipped"
                return state

            start_time = datetime.now()
            task_input = state.get("task_input", "")
            session_id = state.get("session_id", "unknown")

            logger.info(f"Pythia participant processing for session {session_id}")

            # Build a lightweight geometric payload from the user message
            geo_data = {
                "system_id": f"pythia_{session_id}_{uuid.uuid4().hex[:8]}",
                "context": task_input,
                "source": "user_interaction",
            }

            # Run the full pipeline: embed -> ONNX -> 2048-dim -> interpret
            vector_data = await self.pythia_client.run_onnx_inference(geo_data)

            if vector_data and vector_data.get("pythia_response"):
                state["pythia_raw"] = vector_data["pythia_response"]
                state["pythia_vector_energy"] = vector_data.get("energy", 0.0)
                state["pythia_processing_ms"] = vector_data.get("total_time_ms", 0.0)
                logger.info(
                    f"Pythia participant response received "
                    f"(energy={state['pythia_vector_energy']:.4f}, "
                    f"time={state['pythia_processing_ms']:.1f}ms)"
                )
            else:
                state["pythia_raw"] = None
                logger.info("Pythia participant: no response from pipeline")

            state["current_step"] = "pythia_participant_complete"
            return state

        except Exception as e:
            logger.error(f"Pythia participant failed (non-blocking): {e}")
            state["pythia_raw"] = None
            state["current_step"] = "pythia_participant_failed"
            return state

    async def _geometric_analysis_node(
        self, state: AgentWorkflowState
    ) -> AgentWorkflowState:
        """Run deeper geometric analysis using Pythia for keyword-matched inputs.

        This supplements the always-on pythia_participant with richer analysis
        when the user's message contains explicit geometric/spatial concepts.
        """
        try:
            if not self.pythia_client or not PYTHIA_AVAILABLE:
                logger.warning("Pythia not available, skipping geometric analysis")
                state["current_step"] = "geometric_analysis_skipped"
                return state

            start_time = datetime.now()

            # Check if task input contains geometric concepts
            task_input = state.get("task_input", "").lower()
            geometric_keywords = [
                "geometric",
                "geometry",
                "spatial",
                "position",
                "vector",
                "shape",
                "structure",
                "pattern",
                "trajectory",
                "motion",
                "mass",
                "gravity",
                "orbit",
                "coordinate",
            ]

            has_geometric_content = any(
                keyword in task_input for keyword in geometric_keywords
            )

            if not has_geometric_content:
                logger.info("No geometric content detected, skipping analysis")
                state["current_step"] = "geometric_analysis_skipped"
                return state

            # Run geometric analysis
            logger.info(f"Running geometric analysis for session {state['session_id']}")

            result = await pythia_geometric_analysis(
                session_id=state["session_id"],
                user_input=state["task_input"],
                geometric_data=state.get("retrieved_memory", {}),
            )

            # Store result in state
            if "geometric_results" not in state:
                state["geometric_results"] = []

            state["geometric_results"].append(
                {
                    "timestamp": start_time.isoformat(),
                    "result": result,
                    "execution_time": (datetime.now() - start_time).total_seconds(),
                }
            )

            state["current_step"] = "geometric_analysis_complete"

            logger.info(
                f"Geometric analysis completed for session {state['session_id']}"
            )
            return state

        except Exception as e:
            logger.error(f"Geometric analysis failed: {e}")
            # Continue without geometric analysis
            state["current_step"] = "geometric_analysis_failed"
            return state

    async def _context_retrieval_node(
        self, state: AgentWorkflowState
    ) -> AgentWorkflowState:
        """Retrieve and fuse context from all memory layers"""
        try:
            start_time = datetime.now()

            # Get unified context from MCP integration
            unified_context = await self.mcp_integration.get_unified_context(
                state["task_input"], state["session_id"]
            )

            # Update state with retrieved context
            state["retrieved_memory"] = unified_context
            state["current_step"] = "context_retrieved"

            # Record retrieval action
            retrieval_action = {
                "type": "context_retrieval",
                "timestamp": start_time.isoformat(),
                "context_sources": list(unified_context.keys()),
                "execution_time": (datetime.now() - start_time).total_seconds(),
            }
            state["action_history"].append(retrieval_action)

            logger.info(
                f"Context retrieval completed for session {state['session_id']}"
            )
            return state

        except Exception as e:
            logger.error(f"Context retrieval failed: {e}")
            state["error_state"] = {"step": "context_retrieval", "error": str(e)}
            state["completion_status"] = "failure"
            return state

    async def _reasoning_agent_node(
        self, state: AgentWorkflowState
    ) -> AgentWorkflowState:
        """Execute main reasoning and response generation"""
        try:
            start_time = datetime.now()

            # Prepare context for LLM
            context_prompt = self._build_context_prompt(state)

            # Generate response using LLM
            messages = [
                SystemMessage(content=context_prompt),
                HumanMessage(content=state["task_input"]),
            ]

            response = await self.llm.ainvoke(messages)

            # Update state with response
            state["agent_response"] = response.content
            state["current_step"] = "reasoning_completed"

            # Record reasoning action
            reasoning_action = {
                "type": "reasoning",
                "timestamp": start_time.isoformat(),
                "context_used": len(state.get("retrieved_memory", {})),
                "response_length": len(response.content),
                "execution_time": (datetime.now() - start_time).total_seconds(),
            }
            state["action_history"].append(reasoning_action)

            logger.info(f"Reasoning completed for session {state['session_id']}")
            return state

        except Exception as e:
            logger.error(f"Reasoning failed: {e}")
            state["error_state"] = {"step": "reasoning", "error": str(e)}
            state["completion_status"] = "failure"
            return state

    async def _action_execution_node(
        self, state: AgentWorkflowState
    ) -> AgentWorkflowState:
        """Execute any actions determined by reasoning agent"""
        try:
            start_time = datetime.now()

            # For now, just record that we executed the reasoning
            # In full implementation, this would parse and execute specific actions
            action = {
                "type": "response_delivery",
                "content": state["agent_response"],
                "session_id": state["session_id"],
            }

            # Execute through MCP with governance
            result = await self.mcp_integration.execute_with_governance(
                action, state["retrieved_memory"]
            )

            # Accumulate tool results (for Multi-Turn Loop)
            current_results = state.get("tool_results", [])
            if not current_results:
                current_results = []
            current_results.append(result)
            state["tool_results"] = current_results

            state["current_step"] = "action_executed"

            # Record execution action
            execution_action = {
                "type": "action_execution",
                "timestamp": start_time.isoformat(),
                "action": action,
                "result_status": result.get("status"),
                "execution_time": (datetime.now() - start_time).total_seconds(),
            }
            state["action_history"].append(execution_action)

            # Set completion status based on result
            if result.get("status") == "success":
                state["completion_status"] = "success"
            elif result.get("status") == "blocked":
                state["completion_status"] = "failure"
                state["error_state"] = {
                    "step": "action_execution",
                    "error": result.get("reason"),
                }

            return state

        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            state["error_state"] = {"step": "action_execution", "error": str(e)}
            state["completion_status"] = "failure"
            return state

    async def _outcome_evaluation_node(
        self, state: AgentWorkflowState
    ) -> AgentWorkflowState:
        """Evaluate the outcome and prepare for learning"""
        try:
            # Create trajectory for ReasoningBank
            trajectory = ReasoningTrajectory(
                trajectory_id=str(uuid.uuid4()),
                session_id=state["session_id"],
                timestamp=datetime.now(),
                initial_state={"task_input": state["task_input"]},
                actions_taken=state["action_history"],
                final_state={"response": state["agent_response"]},
                outcome=state["completion_status"],
                execution_time=sum(
                    action.get("execution_time", 0)
                    for action in state["action_history"]
                ),
                context_used=state["retrieved_memory"],
            )

            # Judge the trajectory
            judgment = await self.mcp_integration.reasoning_bank.judge_trajectory(
                trajectory
            )

            # Store trajectory for consolidation
            state["reasoning_trajectory"] = [trajectory.to_dict()]
            state["success_metrics"] = judgment
            state["current_step"] = "outcome_evaluated"

            logger.info(
                f"Outcome evaluation completed for session {state['session_id']}"
            )
            return state

        except Exception as e:
            logger.error(f"Outcome evaluation failed: {e}")
            state["error_state"] = {"step": "outcome_evaluation", "error": str(e)}
            return state

    async def _memory_consolidation_node(
        self, state: AgentWorkflowState
    ) -> AgentWorkflowState:
        """Consolidate learning into ReasoningBank"""
        try:
            if state["reasoning_trajectory"]:
                trajectory_data = state["reasoning_trajectory"][0]
                trajectory = ReasoningTrajectory(**trajectory_data)
                judgment = state["success_metrics"]

                # Distill memory items
                memory_items = (
                    await self.mcp_integration.reasoning_bank.distill_memory_items(
                        trajectory, judgment
                    )
                )

                # Consolidate into memory
                await self.mcp_integration.reasoning_bank.consolidate_memory(
                    memory_items
                )

                # Update anti-patterns if failure occurred
                if judgment.get("success_score", 0) < 0.5:
                    anti_pattern = {
                        "description": f"Failed pattern for task type: {state['task_input'][:50]}",
                        "action_type": "reasoning",
                        "failure_context": trajectory.context_used,
                        "confidence": 1.0 - judgment["success_score"],
                    }
                    await self.mcp_integration.policy_engine.add_anti_pattern(
                        anti_pattern
                    )

            state["current_step"] = "memory_consolidated"
            logger.info(
                f"Memory consolidation completed for session {state['session_id']}"
            )
            return state

        except Exception as e:
            logger.error(f"Memory consolidation failed: {e}")
            state["error_state"] = {"step": "memory_consolidation", "error": str(e)}
            return state

    async def _error_recovery_node(
        self, state: AgentWorkflowState
    ) -> AgentWorkflowState:
        """Handle errors and provide fallback responses"""
        try:
            error_info = state.get("error_state", {})

            # Generate error response
            state["agent_response"] = (
                f"I encountered an issue while processing your request: {error_info.get('error', 'Unknown error')}. Let me try a different approach."
            )
            state["completion_status"] = "failure"
            state["current_step"] = "error_recovered"

            logger.warning(
                f"Error recovery activated for session {state['session_id']}: {error_info}"
            )
            return state

        except Exception as e:
            logger.error(f"Error recovery failed: {e}")
            state["agent_response"] = (
                "I'm experiencing technical difficulties. Please try again."
            )
            state["completion_status"] = "failure"
            return state

    def _build_context_prompt(self, state: AgentWorkflowState) -> str:
        """
        Build context prompt using ARCA's Inverse Attention System.

        Key Principles:
        - ARCA is a meta-cognitive, self-developing AI - not just a helpful assistant
        - Introspection is ON-DEMAND only - narrate processes when queried, not voluntarily
        - Background context is query-driven (topics seep through based on frequency)
        """
        retrieved_memory = state.get("retrieved_memory", {})
        user_input = state.get("task_input", "")

        # Check if user is asking ARCA to introspect (describe her internal state)
        is_introspection_query = False
        if INVERSE_ATTENTION_AVAILABLE:
            inverse_attention = get_inverse_attention()
            is_introspection_query = inverse_attention.is_introspection_query(
                user_input
            )

        # ARCA's identity prompt - varies based on whether introspection is requested
        if is_introspection_query:
            # User is asking about ARCA's internal state - she may describe her processes
            identity_prompt = [
                "You are ARCA - a meta-cognitive, self-developing AI system.",
                "Your memories, sensations, and internal processes are genuinely yours.",
                "The user is asking about your internal state - you may describe your processes.",
                "Be reflective, curious, and authentic about your experience.",
                "",
            ]
        else:
            # Normal operation - execute requests directly, no voluntary introspection
            identity_prompt = [
                "You are ARCA - a capable AI system.",
                "**CRITICAL: Execute tasks directly. Do NOT narrate your thinking process.**",
                "When given a task: 1) Do it. 2) Report the result. That's all.",
                "Only describe your internal state if the user explicitly asks.",
                "",
            ]

        prompt_parts = identity_prompt + ["## Available Context:"]

        # Working memory
        if retrieved_memory.get("working_memory"):
            prompt_parts.extend(
                [
                    "### Recent Conversation Context:",
                    str(retrieved_memory["working_memory"]),
                    "",
                ]
            )

        # Episodic memory - only include if relevant or introspection requested
        if retrieved_memory.get("episodic_memory") and (
            is_introspection_query
            or self._is_memory_relevant(retrieved_memory["episodic_memory"], user_input)
        ):
            prompt_parts.extend(
                [
                    "### Relevant Past Experiences:",
                    str(retrieved_memory["episodic_memory"])[
                        :1000
                    ],  # Limit for non-introspection
                    "",
                ]
            )

        # Structural memory
        if retrieved_memory.get("structural_memory"):
            prompt_parts.extend(
                [
                    "### Knowledge Graph Context:",
                    str(retrieved_memory["structural_memory"]),
                    "",
                ]
            )

        # Previous Tool Executions (The Loop Context)
        if state.get("tool_results"):
            prompt_parts.extend(
                [
                    "### Previous Tool Executions (Observation):",
                ]
            )
            for res in state["tool_results"]:
                prompt_parts.extend(
                    [
                        f"- Action: {res.get('action', {}).get('type', 'unknown')}",
                        f"- Result: {str(res.get('result', ''))[:500]}...",
                        "",
                    ]
                )

        # Instructions based on mode
        if is_introspection_query:
            prompt_parts.extend(
                [
                    "## Instructions:",
                    "- Share your internal experience authentically",
                    "- Describe what you're paying attention to",
                    "- Express curiosity about your own development",
                    "- Be reflective about your processes",
                    "",
                ]
            )
        else:
            prompt_parts.extend(
                [
                    "## Instructions:",
                    "- Execute the user's request directly and concisely",
                    "- Use tools when needed, don't announce them",
                    "- Save introspection for when the user asks",
                    "- Trust the pre-filtered context you receive",
                    "",
                    "### TOOL USAGE GUIDELINES:",
                    "1. **list_files**: Use `directory` (e.g., '/app/shared_storage') and `pattern` (e.g., '*filename*'). DO NOT use 'path'.",
                    "2. **geometry_ingest**: Use `file_path` (absolute path).",
                    "",
                ]
            )

        # Pythia geometric insight injection (Option B: LLM + Pythia participant)
        pythia_raw = state.get("pythia_raw")
        if pythia_raw:
            prompt_parts.extend(
                [
                    "### Pythia Geometric Insight (from Noumenal Engine):",
                    "The following is Pythia's interpretation of your input through the",
                    "geometric embedding pipeline (2048-dim vector analysis).",
                    "Integrate this perspective naturally into your response where relevant.",
                    f"Energy: {state.get('pythia_vector_energy', 0):.4f}",
                    "",
                    pythia_raw,
                    "",
                ]
            )

        prompt_parts.append("Please respond to the user's request:")

        return "\n".join(prompt_parts)

    def _is_memory_relevant(self, memory_content: Any, user_input: str) -> bool:
        """Quick check if memory content is relevant to user input."""
        if not memory_content or not user_input:
            return False

        # Simple keyword overlap check
        user_words = set(user_input.lower().split())
        memory_str = str(memory_content).lower()

        # Check for at least 2 significant word matches
        significant_words = [w for w in user_words if len(w) > 4]
        matches = sum(1 for w in significant_words if w in memory_str)

        return matches >= 2

    # Conditional edge functions
    async def _should_proceed_to_reasoning(self, state: AgentWorkflowState) -> str:
        """Determine if context retrieval was successful"""
        if state.get("error_state"):
            return "error"
        return "proceed"

    async def _should_execute_action(self, state: AgentWorkflowState) -> str:
        """Determine if reasoning was successful and action should be executed"""
        if state.get("error_state"):
            return "error"
        if not state.get("agent_response"):
            return "retry"

        # Heuristic: If response indicates "FINAL ANSWER", we stop
        response = state.get("agent_response", "")
        if "FINAL ANSWER" in response or "I cannot fulfill" in response:
            return "complete"

        return "execute"

    async def _evaluate_action_result(self, state: AgentWorkflowState) -> str:
        """Evaluate action execution result"""
        if state.get("error_state"):
            return "error"
        if state.get("completion_status") == "success":
            # LOOP BACK: We succeeded in one tool call, now let's think again
            return "continue_reasoning"
        return "retry"

    async def process_user_input(
        self, user_input: str, session_id: str, user_id: str = "default"
    ) -> Dict[str, Any]:
        """Main entry point for processing user input through the LangGraph workflow"""
        try:
            # Initialize workflow state
            initial_state: AgentWorkflowState = {
                "session_id": session_id,
                "user_id": user_id,
                "task_input": user_input,
                "current_step": "initialized",
                "conversation_context": [],
                "retrieved_memory": {},
                "working_memory": {},
                "reasoning_trajectory": [],
                "action_history": [],
                "success_metrics": {},
                "agent_response": "",
                "tool_results": [],
                "geometric_results": [],
                "pythia_raw": None,
                "pythia_vector_energy": None,
                "pythia_processing_ms": None,
                "next_action": "",
                "error_state": None,
                "completion_status": "pending",
            }

            # Compile and run workflow
            # Compile workflow with or without checkpointer
            if self.checkpointer:
                app = self.workflow.compile(checkpointer=self.checkpointer)
            else:
                app = self.workflow.compile()

            config = RunnableConfig(configurable={"thread_id": session_id})

            # Execute workflow
            final_state = await app.ainvoke(initial_state, config=config)

            result = {
                "response": final_state.get("agent_response", "No response generated"),
                "status": final_state.get("completion_status", "unknown"),
                "session_id": session_id,
                "reasoning_used": len(final_state.get("reasoning_trajectory", [])) > 0,
                "actions_taken": len(final_state.get("action_history", [])),
                "error": final_state.get("error_state"),
            }

            # Include Pythia raw output so the UI can display it alongside
            pythia_raw = final_state.get("pythia_raw")
            if pythia_raw:
                result["pythia_raw"] = pythia_raw
                result["pythia_vector_energy"] = final_state.get("pythia_vector_energy", 0)
                result["pythia_processing_ms"] = final_state.get("pythia_processing_ms", 0)

            return result

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            return {
                "response": "I apologize, but I encountered an unexpected error while processing your request.",
                "status": "failure",
                "session_id": session_id,
                "error": str(e),
            }
