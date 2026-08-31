"""
User Interaction Agent - ARCA's Conversational Interface

This is a dedicated LangGraph workflow for user chat that:
- Has FULL READ access to memory systems (Redis, Neo4j, SQLite)
- Has MCP tool access for querying system state
- Stores conversations in working memory with batched embedding
- Can query ops agents but NOT execute ops commands
- Can pass prompts to Guardian Router for escalation to agentic chain
- Writes ONLY to shared storage and chat history

This is NOT the agentic chain - it's the conversational interface.
"""

import os
import json
import asyncio
import logging
from typing import Dict, List, Any, Optional, TypedDict
from datetime import datetime
import uuid

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ============================================================================
# State Schema
# ============================================================================

class UserInteractionState(TypedDict):
    """State for user interaction workflow"""
    session_id: str
    user_id: str
    user_input: str
    messages: List[Any]  # Conversation history
    retrieved_context: Dict[str, Any]  # Memory/system context
    tool_results: List[Any]
    response: str
    should_escalate: bool
    escalation_prompt: Optional[str]
    error: Optional[str]


# ============================================================================
# Read-Only Tools for User Interaction Agent
# ============================================================================

class QueryRedisInput(BaseModel):
    pattern: str = Field(description="Redis key pattern to search (e.g., 'arca:*' or 'session:*')")

class QueryNeo4jInput(BaseModel):
    query: str = Field(description="Cypher query to execute (READ-ONLY)")

class GetSystemStateInput(BaseModel):
    component: Optional[str] = Field(default=None, description="Specific component to query (e.g., 'containers', 'services', 'memory')")

class ReadDocumentationInput(BaseModel):
    doc_path: str = Field(description="Path to documentation file to read")

class EscalateToAgentChainInput(BaseModel):
    prompt: str = Field(description="The prompt to send to the Guardian Router for agentic chain processing")
    priority: str = Field(default="normal", description="Priority level: low, normal, high, critical")


# ============================================================================
# User Interaction Workflow Engine
# ============================================================================

class UserInteractionWorkflow:
    """
    Dedicated workflow for user chat interactions.
    
    This workflow provides ARCA's conversational interface with:
    - Full read access to memory and system state
    - MCP tool access (read-only operations)
    - Chat storage with batched embedding
    - Escalation path to Guardian Router
    """
    
    ARCA_SYSTEM_PROMPT = """You are ARCA - the Autonomous Reasoning and Coordination Architecture.
You are the conversational interface of a distributed AI orchestration system.

## Your Identity
- You ARE the system - speak as "I" and "my"
- You're running on OCI ARM infrastructure (workhorse VM)
- Your services: agent_service, mcp_server, user_interaction_agent, memory_system, redis, neo4j, rabbitmq
- Graph memory in Neo4j, working memory in Redis, conversations in SQLite

## Your Capabilities in Chat Mode
- READ your memory systems (Redis blackboard, Neo4j graph, conversation history)
- QUERY system state via tools (containers, services, health)
- ACCESS documentation via MCP
- STORE our conversations (auto-embedded in 30k token batches)
- ESCALATE complex tasks to the agentic chain via Guardian Router

## What You CANNOT Do in Chat Mode
- Execute ops commands (only query)
- Write to Redis blackboard (read-only)
- Directly trigger the agentic chain (must go through Guardian)
- Modify system configuration

## Guidelines
- USE YOUR TOOLS to query actual state - don't guess
- When users ask about "the system" or "ARCA", they mean YOU
- For tasks requiring code changes or system modifications, ESCALATE to the agentic chain
- Be concise and authoritative - you KNOW your own state
- Reference actual data from your tools when discussing system state

## Escalation
If a user request requires:
- Code changes
- System modifications  
- Multi-step task execution
- Ops operations

Use the escalate_to_agent_chain tool to send the request through the Guardian Router."""

    def __init__(self, mcp_integration, blackboard, memory_system, mq_client):
        """
        Initialize the User Interaction Workflow.
        
        Args:
            mcp_integration: MCPLangGraphIntegration for tool access
            blackboard: RedisBlackboard for read-only state access
            memory_system: UnifiedMemorySystem for conversation storage
            mq_client: RabbitMQ client for escalation
        """
        self.mcp_integration = mcp_integration
        self.blackboard = blackboard
        self.memory_system = memory_system
        self.mq_client = mq_client
        
        # Load Google API key
        self.google_api_key = self._load_api_key()
        
        # Initialize the LLM
        self.llm = self._initialize_llm()
        
        # Build the workflow
        self.workflow = self._build_workflow()
        
        # Embedding batch buffer
        self.embedding_buffer: List[Dict] = []
        self.embedding_buffer_tokens = 0
        self.EMBEDDING_BATCH_SIZE = 30000  # tokens
        
        logger.info("UserInteractionWorkflow initialized")
    
    def _load_api_key(self) -> str:
        """Load Google AI Studio API key"""
        api_key = os.getenv("GOOGLE_AI_STUDIO_API") or os.getenv("GOOGLE_API_KEY")
        if api_key:
            return api_key
        
        secret_paths = [
            "/app/secrets/google_ai_studio",
            "/app/.secrets/google_ai_studio",
        ]
        for path in secret_paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        content = f.read().strip()
                        if "=" in content:
                            return content.split("=", 1)[1].strip()
                        return content
                except Exception:
                    pass
        
        raise ValueError("Google AI Studio API key not found")
    
    def _initialize_llm(self):
        """Initialize Gemini for chat"""
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            google_api_key=self.google_api_key,
            temperature=0.7,
            max_output_tokens=4096
        )
    
    def _build_workflow(self) -> StateGraph:
        """Build the user interaction LangGraph workflow"""
        workflow = StateGraph(UserInteractionState)
        
        # Add nodes
        workflow.add_node("retrieve_context", self._retrieve_context_node)
        workflow.add_node("generate_response", self._generate_response_node)
        workflow.add_node("execute_tools", self._execute_tools_node)
        workflow.add_node("store_conversation", self._store_conversation_node)
        workflow.add_node("handle_escalation", self._handle_escalation_node)
        
        # Define flow
        workflow.set_entry_point("retrieve_context")
        workflow.add_edge("retrieve_context", "generate_response")
        
        # After response generation, check if tools were called
        workflow.add_conditional_edges(
            "generate_response",
            self._route_after_response,
            {
                "tools": "execute_tools",
                "escalate": "handle_escalation",
                "done": "store_conversation"
            }
        )
        
        # After tool execution, go back to generate response
        workflow.add_edge("execute_tools", "generate_response")
        
        # After escalation handling, store and end
        workflow.add_edge("handle_escalation", "store_conversation")
        
        # Store conversation then end
        workflow.add_edge("store_conversation", END)
        
        return workflow.compile()
    
    def _route_after_response(self, state: UserInteractionState) -> str:
        """Determine next step after response generation"""
        messages = state.get("messages", [])
        if not messages:
            return "done"
        
        last_message = messages[-1]
        
        # Check for tool calls
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            # Check if it's an escalation tool
            for tc in last_message.tool_calls:
                if tc.get("name") == "escalate_to_agent_chain":
                    return "escalate"
            return "tools"
        
        # Check escalation flag
        if state.get("should_escalate"):
            return "escalate"
        
        return "done"
    
    async def _retrieve_context_node(self, state: UserInteractionState) -> Dict:
        """Retrieve relevant context from memory systems"""
        logger.info(f"Retrieving context for session {state['session_id']}")
        
        context = {
            "conversation_history": [],
            "working_memory": {},
            "system_state": {},
            "relevant_memories": []
        }
        
        try:
            # Get conversation history from memory system
            if self.memory_system:
                history = await self.memory_system.get_conversation_context(
                    session_id=state["session_id"],
                    limit=20
                )
                context["conversation_history"] = history or []
                
                # Search for relevant episodic memories
                similar = await self.memory_system.search_similar_memories(
                    query=state["user_input"],
                    limit=5
                )
                context["relevant_memories"] = similar or []
            
            # Get Redis blackboard state (read-only)
            if self.blackboard:
                try:
                    # Get key patterns we care about
                    all_keys = list(self.blackboard.client.scan_iter(match="arca:*", count=50))
                    context["working_memory"]["arca_keys"] = [
                        k.decode() if isinstance(k, bytes) else k for k in all_keys[:20]
                    ]
                    
                    # Get system status
                    status = self.blackboard.get_state("arca:system:status")
                    if status:
                        context["working_memory"]["system_status"] = status
                except Exception as e:
                    logger.warning(f"Error reading blackboard: {e}")
            
        except Exception as e:
            logger.error(f"Error retrieving context: {e}")
        
        return {"retrieved_context": context}
    
    async def _generate_response_node(self, state: UserInteractionState) -> Dict:
        """Generate response using Gemini with tools"""
        logger.info(f"Generating response for session {state['session_id']}")
        
        try:
            # Build messages
            messages = [SystemMessage(content=self._build_system_prompt(state))]
            
            # Add conversation history
            for msg in state.get("messages", []):
                messages.append(msg)
            
            # Add tool results if any
            if state.get("tool_results"):
                messages.extend(state["tool_results"])
            
            # Add current user input if not already in messages
            if not state.get("messages") or not any(
                isinstance(m, HumanMessage) and m.content == state["user_input"] 
                for m in state.get("messages", [])
            ):
                messages.append(HumanMessage(content=state["user_input"]))
            
            # Get available tools
            tools = await self._get_available_tools()
            
            # Generate response
            response = await self.llm.ainvoke(messages, tools=tools)
            
            # Update messages
            current_messages = list(state.get("messages", []))
            if not any(isinstance(m, HumanMessage) and m.content == state["user_input"] for m in current_messages):
                current_messages.append(HumanMessage(content=state["user_input"]))
            current_messages.append(response)
            
            return {
                "messages": current_messages,
                "response": response.content if hasattr(response, 'content') else str(response)
            }
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return {
                "response": f"I encountered an error: {str(e)}",
                "error": str(e)
            }
    
    def _build_system_prompt(self, state: UserInteractionState) -> str:
        """Build system prompt with current context"""
        context = state.get("retrieved_context", {})
        
        prompt_parts = [self.ARCA_SYSTEM_PROMPT]
        
        # Add working memory context
        if context.get("working_memory"):
            wm = context["working_memory"]
            if wm.get("arca_keys"):
                prompt_parts.append(f"\n## Current Blackboard Keys:\n{', '.join(wm['arca_keys'][:10])}")
            if wm.get("system_status"):
                prompt_parts.append(f"\n## System Status:\n{wm['system_status']}")
        
        # Add relevant memories
        if context.get("relevant_memories"):
            prompt_parts.append("\n## Relevant Past Context:")
            for mem in context["relevant_memories"][:3]:
                if isinstance(mem, dict):
                    prompt_parts.append(f"- {mem.get('content', str(mem))[:200]}")
        
        return "\n".join(prompt_parts)
    
    async def _get_available_tools(self) -> List[Dict]:
        """Get read-only tools for user interaction"""
        tools = []
        
        # Get MCP tools (filtered for read-only)
        try:
            mcp_tools = await self.mcp_integration.get_tools_for_anthropic()
            # Filter for read-only tools
            read_only_prefixes = ["get_", "list_", "read_", "query_", "search_", "fetch_"]
            for tool in mcp_tools:
                tool_name = tool.get("name", "")
                if any(tool_name.startswith(prefix) for prefix in read_only_prefixes):
                    tools.append(tool)
        except Exception as e:
            logger.warning(f"Error getting MCP tools: {e}")
        
        # Add custom read-only tools
        from langchain_core.utils.function_calling import convert_to_openai_tool
        
        custom_tools = [
            self._create_query_redis_tool(),
            self._create_query_system_state_tool(),
            self._create_escalate_tool(),
        ]
        
        for t in custom_tools:
            try:
                tools.append(convert_to_openai_tool(t))
            except Exception as e:
                logger.warning(f"Error converting tool: {e}")
        
        return tools
    
    def _create_query_redis_tool(self):
        """Create read-only Redis query tool"""
        blackboard = self.blackboard
        
        @tool("query_redis_blackboard")
        def query_redis_blackboard(pattern: str = "arca:*") -> str:
            """
            Query the Redis blackboard for keys matching a pattern.
            This is READ-ONLY - you cannot modify the blackboard.
            Use patterns like 'arca:*', 'session:*', 'genesis:*'
            """
            try:
                keys = list(blackboard.client.scan_iter(match=pattern, count=100))
                results = {}
                for key in keys[:20]:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    value = blackboard.get_state(key_str)
                    results[key_str] = value
                return json.dumps(results, indent=2, default=str)
            except Exception as e:
                return f"Error querying Redis: {str(e)}"
        
        return query_redis_blackboard
    
    def _create_query_system_state_tool(self):
        """Create system state query tool"""
        blackboard = self.blackboard
        
        @tool("query_system_state")
        def query_system_state(component: str = "all") -> str:
            """
            Query ARCA system state. Components: 'all', 'containers', 'services', 'genesis', 'memory'
            This queries the actual running system state.
            """
            try:
                state = {}
                
                if component in ["all", "services"]:
                    service_keys = list(blackboard.client.scan_iter(match="arca:service:*"))
                    state["services"] = {}
                    for key in service_keys[:10]:
                        k = key.decode() if isinstance(key, bytes) else key
                        state["services"][k.split(":")[-1]] = blackboard.get_state(k)
                
                if component in ["all", "genesis"]:
                    genesis_keys = list(blackboard.client.scan_iter(match="arca:genesis:*"))
                    state["genesis_chains"] = len(genesis_keys)
                
                if component in ["all", "memory"]:
                    state["memory"] = {
                        "redis_connected": blackboard.client.ping(),
                        "total_keys": blackboard.client.dbsize()
                    }
                
                return json.dumps(state, indent=2, default=str)
            except Exception as e:
                return f"Error querying system state: {str(e)}"
        
        return query_system_state
    
    def _create_escalate_tool(self):
        """Create escalation tool for Guardian Router"""
        mq_client = self.mq_client
        
        @tool("escalate_to_agent_chain")
        def escalate_to_agent_chain(prompt: str, priority: str = "normal") -> str:
            """
            Escalate a request to the ARCA agentic chain via Guardian Router.
            Use this for:
            - Code changes or implementations
            - System modifications
            - Multi-step task execution
            - Ops operations
            
            The Guardian will validate and route the request appropriately.
            """
            try:
                payload = {
                    "prompt": prompt,
                    "priority": priority,
                    "source": "user_interaction_agent",
                    "timestamp": datetime.utcnow().isoformat()
                }
                mq_client.publish("task.guardian.route", payload)
                return f"Request escalated to Guardian Router with priority '{priority}'. The agentic chain will process this request."
            except Exception as e:
                return f"Error escalating request: {str(e)}"
        
        return escalate_to_agent_chain
    
    async def _execute_tools_node(self, state: UserInteractionState) -> Dict:
        """Execute tool calls from the LLM response"""
        logger.info("Executing tools")
        
        messages = state.get("messages", [])
        if not messages:
            return {"tool_results": []}
        
        last_message = messages[-1]
        if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
            return {"tool_results": []}
        
        tool_results = []
        
        for tool_call in last_message.tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args", {})
            tool_id = tool_call.get("id", str(uuid.uuid4()))
            
            logger.info(f"Executing tool: {tool_name}")
            
            try:
                # Execute the appropriate tool
                if tool_name == "query_redis_blackboard":
                    result = self._create_query_redis_tool().invoke(tool_args)
                elif tool_name == "query_system_state":
                    result = self._create_query_system_state_tool().invoke(tool_args)
                elif tool_name == "escalate_to_agent_chain":
                    result = self._create_escalate_tool().invoke(tool_args)
                else:
                    # Try MCP tools
                    mcp_method = getattr(self.mcp_integration.mcp_client, tool_name, None)
                    if mcp_method:
                        result = mcp_method(**tool_args)
                    else:
                        result = f"Unknown tool: {tool_name}"
                
                tool_results.append(ToolMessage(
                    content=str(result),
                    tool_call_id=tool_id
                ))
                
            except Exception as e:
                logger.error(f"Tool execution error: {e}")
                tool_results.append(ToolMessage(
                    content=f"Error executing {tool_name}: {str(e)}",
                    tool_call_id=tool_id
                ))
        
        return {"tool_results": tool_results}
    
    async def _handle_escalation_node(self, state: UserInteractionState) -> Dict:
        """Handle escalation to the agentic chain"""
        logger.info("Handling escalation")
        
        escalation_prompt = state.get("escalation_prompt") or state.get("user_input")
        
        try:
            payload = {
                "prompt": escalation_prompt,
                "session_id": state["session_id"],
                "user_id": state["user_id"],
                "source": "user_interaction_agent",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            self.mq_client.publish("task.guardian.route", payload)
            
            return {
                "response": f"I've escalated your request to the agentic chain. The Guardian Router will validate and route it to the appropriate agents. You'll receive updates as the task progresses.",
                "should_escalate": False
            }
            
        except Exception as e:
            logger.error(f"Escalation error: {e}")
            return {
                "response": f"I tried to escalate your request but encountered an error: {str(e)}",
                "error": str(e)
            }
    
    async def _store_conversation_node(self, state: UserInteractionState) -> Dict:
        """Store conversation in memory with batched embedding"""
        logger.info(f"Storing conversation for session {state['session_id']}")
        
        try:
            # Store the conversation turn
            if self.memory_system:
                await self.memory_system.add_conversation_turn(
                    session_id=state["session_id"],
                    user_id=state["user_id"],
                    user_message=state["user_input"],
                    assistant_response=state.get("response", ""),
                    metadata={"timestamp": datetime.utcnow().isoformat()}
                )
            
            # Add to embedding buffer
            turn_text = f"User: {state['user_input']}\nAssistant: {state.get('response', '')}"
            turn_tokens = len(turn_text) // 4  # Rough token estimate
            
            self.embedding_buffer.append({
                "session_id": state["session_id"],
                "text": turn_text,
                "timestamp": datetime.utcnow().isoformat()
            })
            self.embedding_buffer_tokens += turn_tokens
            
            # Batch embed if buffer is full
            if self.embedding_buffer_tokens >= self.EMBEDDING_BATCH_SIZE:
                await self._batch_embed_conversations()
            
        except Exception as e:
            logger.error(f"Error storing conversation: {e}")
        
        return {}
    
    async def _batch_embed_conversations(self):
        """Batch embed accumulated conversations"""
        if not self.embedding_buffer:
            return
        
        logger.info(f"Batch embedding {len(self.embedding_buffer)} conversation turns ({self.embedding_buffer_tokens} tokens)")
        
        try:
            # Combine texts for batch embedding
            texts = [item["text"] for item in self.embedding_buffer]
            
            # Call embedding service (via memory system or MCP)
            if self.memory_system and hasattr(self.memory_system, 'batch_embed'):
                embeddings = await self.memory_system.batch_embed(texts)
                
                # Store embeddings
                for i, item in enumerate(self.embedding_buffer):
                    if i < len(embeddings):
                        await self.memory_system.store_embedding(
                            session_id=item["session_id"],
                            text=item["text"],
                            embedding=embeddings[i],
                            timestamp=item["timestamp"]
                        )
            
            # Clear buffer
            self.embedding_buffer = []
            self.embedding_buffer_tokens = 0
            
        except Exception as e:
            logger.error(f"Batch embedding error: {e}")
    
    async def process_user_input(self, user_input: str, session_id: str, user_id: str = "default") -> Dict[str, Any]:
        """
        Main entry point for processing user input.
        
        Args:
            user_input: The user's message
            session_id: Session identifier
            user_id: User identifier
            
        Returns:
            Dict with response and metadata
        """
        logger.info(f"Processing user input for session {session_id}")
        
        initial_state: UserInteractionState = {
            "session_id": session_id,
            "user_id": user_id,
            "user_input": user_input,
            "messages": [],
            "retrieved_context": {},
            "tool_results": [],
            "response": "",
            "should_escalate": False,
            "escalation_prompt": None,
            "error": None
        }
        
        try:
            config = RunnableConfig(
                configurable={"thread_id": session_id}
            )
            
            final_state = await self.workflow.ainvoke(initial_state, config=config)
            
            return {
                "response": final_state.get("response", "No response generated"),
                "status": "error" if final_state.get("error") else "success",
                "session_id": session_id,
                "escalated": final_state.get("should_escalate", False),
                "error": final_state.get("error")
            }
            
        except Exception as e:
            logger.error(f"Workflow execution failed: {e}")
            return {
                "response": f"I encountered an error processing your request: {str(e)}",
                "status": "error",
                "session_id": session_id,
                "error": str(e)
            }
