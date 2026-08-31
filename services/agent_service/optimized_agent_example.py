"""
Example Integration: Optimized LangGraph Agent with New Modules
This shows how to integrate the optimization modules into the existing system.
"""

import os
import logging
from typing import Dict, List, Any, TypedDict, Annotated, Literal
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

# Import new optimization modules
from prompt_templates import MinimaxPromptOptimizer, StateManagementOptimizer
from state_schemas import GlobalState, TaskDelegation, create_initial_state
from litellm_integration import LiteLLMGateway, ModelRouter

# Import existing components
from langgraph_agent import MinimaxAnthropicWrapper  # Keep this for MiniMax

logger = logging.getLogger(__name__)


class OptimizedAgentSystem:
    """
    Optimized multi-agent system implementing architectural patterns.
    
    Key improvements:
    1. Structured state with control/conversation separation
    2. Optimized prompts for MiniMax M2
    3. LiteLLM gateway for Gemini/Grok/Granite routing
    4. Dynamic model selection based on task type
    """
    
    def __init__(self):
        # Initialize MiniMax wrapper (keep existing custom wrapper)
        self.minimax = MinimaxAnthropicWrapper(
            base_url=os.getenv("MINIMAX_API_BASE", "https://api.minimax.io/anthropic"),
            api_key=os.getenv("MINIMAX_API_KEY"),
            model="MiniMax-M2"
        )
        
        # Initialize LiteLLM gateway with MiniMax wrapper
        self.litellm = LiteLLMGateway(
            gateway_url=os.getenv("LITELLM_GATEWAY_URL", "http://llm_gateway:4000"),
            master_key=os.getenv("LITELLM_MASTER_KEY"),
            minimax_wrapper=self.minimax  # Pass MiniMax wrapper for engineer_model
        )
        
        # Initialize prompt optimizer
        self.prompt_optimizer = MinimaxPromptOptimizer()
        self.state_optimizer = StateManagementOptimizer()
        
        # Build workflow
        self.workflow = self._build_workflow()
    
    def _build_workflow(self) -> StateGraph:
        """Build LangGraph workflow with optimized structure"""
        workflow = StateGraph(GlobalState)
        
        # Add nodes
        workflow.add_node("supervisor", self.supervisor_node)
        workflow.add_node("architect", self.architect_node)
        workflow.add_node("engineer", self.engineer_node)
        workflow.add_node("reviewer", self.reviewer_node)
        workflow.add_node("tools", self.tools_node)
        
        # Add edges
        workflow.add_edge(START, "supervisor")
        workflow.add_conditional_edges(
            "supervisor",
            self.route_from_supervisor,
            {
                "architect": "architect",
                "engineer": "engineer",
                "reviewer": "reviewer",
                "end": END
            }
        )
        workflow.add_conditional_edges(
            "engineer",
            self.route_from_engineer,
            {
                "tools": "tools",
                "reviewer": "reviewer",
                "supervisor": "supervisor"
            }
        )
        workflow.add_edge("tools", "engineer")
        workflow.add_edge("architect", "supervisor")
        workflow.add_edge("reviewer", "supervisor")
        
        return workflow.compile()
    
    # ========================================================================
    # NODE IMPLEMENTATIONS
    # ========================================================================
    
    def supervisor_node(self, state: GlobalState) -> Dict[str, Any]:
        """
        Supervisor agent: Orchestrates workflow, decomposes tasks
        Uses Gemini via LiteLLM gateway
        """
        logger.info("🎯 Supervisor Node")
        
        # Extract recent context (prevent "lost in middle")
        messages = self.state_optimizer.extract_conversational_context(
            state["messages"],
            window_size=10
        )
        
        # Add system prompt if not present
        if not any(isinstance(msg, SystemMessage) for msg in messages):
            system_prompt = """You are a supervisor agent coordinating a team of specialists:
- Architect: System design and planning
- Engineer: Code implementation and testing  
- Reviewer: Code quality and validation

Analyze the task and decide which specialist to delegate to, or if the task is complete."""
            messages.insert(0, SystemMessage(content=system_prompt))
        
        # Route to appropriate model (Gemini for supervisor)
        model = ModelRouter.route_task("orchestration")
        
        # Call via LiteLLM gateway
        response = self.litellm.completion(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=8192
        )
        
        # Update state with response
        return {
            "messages": [AIMessage(content=response.content)],
            "current_agent": "supervisor"
        }
    
    def architect_node(self, state: GlobalState) -> Dict[str, Any]:
        """
        Architect agent: High-level design and planning
        Uses Grok via LiteLLM gateway
        """
        logger.info("🏗️  Architect Node")
        
        messages = self.state_optimizer.extract_conversational_context(
            state["messages"],
            window_size=10
        )
        
        # Add architect system prompt
        if not any(isinstance(msg, SystemMessage) for msg in messages):
            system_prompt = """You are a system architect specializing in:
- High-level system design
- Technical planning and risk analysis
- Breaking down complex requirements
- Defining implementation roadmaps

Provide architectural guidance and implementation plans."""
            messages.insert(0, SystemMessage(content=system_prompt))
        
        # Route to Grok (fast reasoning)
        model = ModelRouter.route_task("system_design")
        
        response = self.litellm.completion(
            model=model,
            messages=messages,
            temperature=0.5,
            max_tokens=4096
        )
        
        return {
            "messages": [AIMessage(content=response.content)],
            "current_agent": "architect"
        }
    
    def engineer_node(self, state: GlobalState) -> Dict[str, Any]:
        """
        Engineer agent: Code implementation
        Uses MiniMax M2 via LiteLLM gateway (preserves thinking blocks)
        """
        logger.info("👨‍💻 Engineer Node")
        
        messages = self.state_optimizer.extract_conversational_context(
            state["messages"],
            window_size=10
        )
        
        # Add optimized engineer system prompt (NEW!)
        if not any(isinstance(msg, SystemMessage) for msg in messages):
            engineer_prompt = self.prompt_optimizer.create_engineer_system_prompt()
            messages.insert(0, SystemMessage(content=engineer_prompt))
        
        # Get available tools
        tools = self._get_engineer_tools()
        
        # Route to MiniMax M2 via LiteLLM gateway (preserves thinking blocks)
        model = ModelRouter.route_task("code_generation")
        
        response = self.litellm.completion(
            model=model,
            messages=messages,
            tools=tools,
            temperature=0.7,
            max_tokens=6144  # Optimized for MiniMax M2
        )
        
        # Check if model wants to use tools
        if response.tool_calls:
            logger.info(f"🔧 Engineer wants to use tools: {[tc['name'] for tc in response.tool_calls]}")
            return {
                "messages": [AIMessage(content=response.content, tool_calls=response.tool_calls)],
                "current_agent": "engineer",
                "last_action_status": "pending"  # Will route to tools node
            }
        
        # No tool calls, task complete
        return {
            "messages": [AIMessage(content=response.content)],
            "current_agent": "engineer",
            "last_action_status": "success"
        }
    
    def reviewer_node(self, state: GlobalState) -> Dict[str, Any]:
        """
        Reviewer agent: Code quality and validation
        Uses Gemini via LiteLLM gateway
        """
        logger.info("🔍 Reviewer Node")
        
        messages = self.state_optimizer.extract_conversational_context(
            state["messages"],
            window_size=10
        )
        
        # Add reviewer system prompt
        if not any(isinstance(msg, SystemMessage) for msg in messages):
            system_prompt = """You are a code reviewer specializing in:
- Code quality and maintainability
- Bug detection and security issues
- Style consistency and best practices
- Test coverage validation

Provide specific, actionable feedback."""
            messages.insert(0, SystemMessage(content=system_prompt))
        
        # Route to Gemini (review capabilities)
        model = ModelRouter.route_task("code_review")
        
        response = self.litellm.completion(
            model=model,
            messages=messages,
            temperature=0.3,  # Lower temp for consistent reviews
            max_tokens=8192
        )
        
        return {
            "messages": [AIMessage(content=response.content)],
            "current_agent": "reviewer"
        }
    
    def tools_node(self, state: GlobalState) -> Dict[str, Any]:
        """
        Execute tools requested by engineer
        """
        logger.info("🔧 Tools Node")
        
        # Get last message (should have tool calls)
        last_message = state["messages"][-1]
        if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
            logger.warning("Tools node called but no tool calls found")
            return {"last_action_status": "failure"}
        
        tool_results = []
        for tool_call in last_message.tool_calls:
            try:
                # Execute tool (simplified - implement actual tool execution)
                result = self._execute_tool(tool_call["name"], tool_call["args"])
                
                # Create optimized tool result prompt (NEW!)
                result_prompt = self.prompt_optimizer.create_tool_result_prompt(
                    tool_name=tool_call["name"],
                    result=result,
                    next_step="Analyze the result and determine next action"
                )
                
                tool_results.append(ToolMessage(
                    content=result_prompt,
                    tool_call_id=tool_call["id"]
                ))
                
            except Exception as e:
                logger.error(f"Tool execution error: {e}")
                
                # Create error recovery prompt (NEW!)
                error_prompt = self.prompt_optimizer.create_error_recovery_prompt(
                    error=str(e),
                    attempted_action=f"Execute {tool_call['name']}"
                )
                
                tool_results.append(ToolMessage(
                    content=error_prompt,
                    tool_call_id=tool_call["id"]
                ))
        
        return {
            "messages": tool_results,
            "last_action_status": "success" if tool_results else "failure"
        }
    
    # ========================================================================
    # ROUTING FUNCTIONS
    # ========================================================================
    
    def route_from_supervisor(self, state: GlobalState) -> str:
        """Route from supervisor based on task analysis"""
        last_message = state["messages"][-1].content.lower()
        
        # Simple keyword-based routing (can be enhanced with LLM decision)
        if "design" in last_message or "architecture" in last_message:
            return "architect"
        elif "implement" in last_message or "code" in last_message:
            return "engineer"
        elif "review" in last_message or "check" in last_message:
            return "reviewer"
        elif "complete" in last_message or "done" in last_message:
            return "end"
        
        # Default: continue with engineer
        return "engineer"
    
    def route_from_engineer(self, state: GlobalState) -> str:
        """Route from engineer based on action status"""
        status = state.get("last_action_status", "")
        
        if status == "pending":
            # Engineer wants to use tools
            return "tools"
        elif status == "success":
            # Task complete, route to reviewer
            return "reviewer"
        else:
            # Go back to supervisor for guidance
            return "supervisor"
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def _get_engineer_tools(self) -> List[Dict[str, Any]]:
        """Get tool definitions for engineer (Anthropic format)"""
        return [
            {
                "name": "file_write",
                "description": "Write content to a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                        "content": {"type": "string", "description": "File content"}
                    },
                    "required": ["path", "content"]
                }
            },
            {
                "name": "file_read",
                "description": "Read content from a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"}
                    },
                    "required": ["path"]
                }
            },
            {
                "name": "run_shell",
                "description": "Run a shell command",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command"}
                    },
                    "required": ["command"]
                }
            }
        ]
    
    def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Execute a tool and return result"""
        # Simplified - implement actual tool execution
        logger.info(f"Executing tool: {tool_name} with args: {args}")
        
        if tool_name == "file_write":
            # Implement file writing
            return f"Successfully wrote to {args.get('path')}"
        elif tool_name == "file_read":
            # Implement file reading
            return f"File content: [content from {args.get('path')}]"
        elif tool_name == "run_shell":
            # Implement shell execution
            return f"Command output: [output from {args.get('command')}]"
        
        return "Tool not implemented"
    
    # ========================================================================
    # PUBLIC API
    # ========================================================================
    
    def invoke(self, user_input: str, session_id: str, user_id: str) -> str:
        """
        Process user input through optimized workflow
        
        Args:
            user_input: User's request
            session_id: Session identifier
            user_id: User identifier
        
        Returns:
            Final response content
        """
        # Create initial state with new schema (NEW!)
        initial_state = create_initial_state(
            user_input=user_input,
            session_id=session_id,
            user_id=user_id
        )
        
        # Run workflow
        final_state = self.workflow.invoke(initial_state)
        
        # Extract final response
        if final_state["messages"]:
            return final_state["messages"][-1].content
        
        return "No response generated"


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Initialize optimized system
    agent_system = OptimizedAgentSystem()
    
    # Example invocation
    response = agent_system.invoke(
        user_input="Add JWT authentication to the FastAPI application",
        session_id="example_session",
        user_id="example_user"
    )
    
    print(f"\n{'='*80}")
    print(f"Final Response:")
    print(f"{'='*80}")
    print(response)
    print(f"{'='*80}\n")
