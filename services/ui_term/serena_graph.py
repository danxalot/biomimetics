"""
Serena LangGraph - Code Agent Graph for ARCA
Modeled after maintainer_agents/graph.py

Serena is a code-monitoring agent that works with maintainer agents.
She uses GLM-4.7 (devstral-2) for tool calling and coordinates with:
- Docker Maintainer (more capable)
- Git Maintainer (standard ops)
"""

import logging
import json
import re
from typing import Dict, Any, List, Optional
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from datetime import datetime
import os
import httpx

logger = logging.getLogger("serena-graph")

# --- State Definition ---
from typing import TypedDict, Annotated
from langgraph.graph.message import add_messages

class SerenaState(TypedDict):
    """LangGraph state for Serena Code Agent"""
    # Messaging
    messages: Annotated[List, add_messages]
    
    # Session context
    session_id: str
    user_id: str
    
    # Task context
    task_id: str
    operation: str
    params: Dict[str, Any]
    
    # Tool execution
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    
    # Reasoning trajectory
    plan: Optional[str]
    execution_log: List[str]
    
    # Control flow
    current_node: str
    iteration_count: int
    max_iterations: int
    
    # Maintainer coordination
    escalated_to: Optional[str]  # 'docker' or 'git'
    maintainer_response: Optional[str]
    
    # Final Result
    success: bool
    output: Optional[Any]
    error: Optional[str]


# --- GLM-4.7 Tool Call Format ---
# GLM-4.7 uses this format for tool calls:
# <|tool_call|>
# {"name": "tool_name", "arguments": {"arg1": "value1"}}
# <|tool_call_end|>
#
# For multi-tool calls, GLM may output multiple <|tool_call|> blocks

GLM_TOOL_CALL_PATTERN = r'<\|tool_call\|>\s*(\{.*?\})\s*<\|tool_call_end\|>'
GLM_TOOL_CALL_SIMPLE = r'<tool_call>\s*(\{.*?\})\s*</tool_call>'  # Alternate format


def parse_glm_tool_calls(response_text: str) -> List[Dict[str, Any]]:
    """
    Parse tool calls from GLM-4.7 response.
    Supports multiple formats:
    1. <|tool_call|> JSON <|tool_call_end|>
    2. <tool_call> JSON </tool_call>
    3. tool_code {"name": "...", "arguments": {...}}
    4. Action: tool_name\nAction Input: {...}
    """
    tool_calls = []
    
    # Format 1: GLM native <|tool_call|>
    matches = re.findall(GLM_TOOL_CALL_PATTERN, response_text, re.DOTALL)
    for match in matches:
        try:
            call = json.loads(match.strip())
            if "name" in call:
                tool_calls.append({
                    "name": call["name"],
                    "arguments": call.get("arguments", call.get("params", {}))
                })
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse GLM tool call: {match[:100]}")
    
    # Format 2: XML-style <tool_call>
    if not tool_calls:
        matches = re.findall(GLM_TOOL_CALL_SIMPLE, response_text, re.DOTALL)
        for match in matches:
            try:
                call = json.loads(match.strip())
                if "name" in call:
                    tool_calls.append({
                        "name": call["name"],
                        "arguments": call.get("arguments", call.get("params", {}))
                    })
            except json.JSONDecodeError:
                continue
    
    # Format 3: tool_code style
    if not tool_calls:
        pattern = r'tool_code\s*(\{.*?\})'
        matches = re.findall(pattern, response_text, re.DOTALL)
        for match in matches:
            try:
                call = json.loads(match.strip())
                if "name" in call:
                    tool_calls.append({
                        "name": call["name"],
                        "arguments": call.get("arguments", call.get("params", {}))
                    })
            except json.JSONDecodeError:
                continue
    
    # Format 4: ReAct style
    if not tool_calls:
        action_match = re.search(r"Action:\s*(\w+)", response_text)
        input_match = re.search(r"Action Input:\s*(\{.*?\})", response_text, re.DOTALL)
        if action_match and input_match:
            try:
                args = json.loads(input_match.group(1).strip())
                tool_calls.append({
                    "name": action_match.group(1).strip(),
                    "arguments": args
                })
            except json.JSONDecodeError:
                pass
    
    return tool_calls


def format_tools_for_glm(tools: List[Dict]) -> str:
    """
    Format tool definitions for GLM-4.7's system prompt.
    GLM-4.7 expects tools in a specific format in the system message.
    """
    tools_str = "You have access to the following tools:\n\n"
    for tool in tools:
        name = tool["name"]
        desc = tool.get("description", "No description")
        params = tool.get("parameters", {}).get("properties", {})
        required = tool.get("parameters", {}).get("required", [])
        
        params_desc = []
        for pname, pinfo in params.items():
            req_mark = "*" if pname in required else ""
            params_desc.append(f"  - {pname}{req_mark}: {pinfo.get('description', pinfo.get('type', 'any'))}")
        
        params_str = "\n".join(params_desc) if params_desc else "  (no parameters)"
        tools_str += f"**{name}**: {desc}\nParameters:\n{params_str}\n\n"
    
    tools_str += """
To call a tool, use this format:
<|tool_call|>
{"name": "tool_name", "arguments": {"param1": "value1"}}
<|tool_call_end|>

You can call multiple tools in sequence. After receiving tool results, continue your reasoning.
When you have completed the task, provide a final response without tool calls.
"""
    return tools_str


class SerenaGraph:
    """
    LangGraph for Serena Code Agent.
    Handles code analysis, maintainer coordination, and tool execution.
    """
    
    def __init__(self, llm_client, mcp_client):
        self.llm = llm_client
        self.mcp = mcp_client
        self.workflow = self._build_graph()
        
        # Maintainer tools available to Serena
        self.maintainer_docker_tools = [
            "docker_maintainer_operation",
            "container_logs",
            "list_containers",
            "docker_restart",
        ]
        self.maintainer_git_tools = [
            "git_maintainer_operation",
            "git_status",
            "git_add",
            "git_commit",
            "git_push",
        ]
        
        # Serena's direct tools
        self.serena_tools = [
            {"name": "read_file", "description": "Read a file from the system", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path"}}, "required": ["path"]}},
            {"name": "list_files", "description": "List files in a directory", "parameters": {"type": "object", "properties": {"directory": {"type": "string", "description": "Directory path"}}, "required": []}},
            {"name": "serena_analyze_code", "description": "Analyze code for patterns and issues", "parameters": {"type": "object", "properties": {"code": {"type": "string"}, "language": {"type": "string"}}, "required": ["code"]}},
            {"name": "skills_search", "description": "Search ARCA skills bank", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
            {"name": "delegate_to_docker_maintainer", "description": "Delegate task to Docker Maintainer (more capable)", "parameters": {"type": "object", "properties": {"task": {"type": "string"}, "params": {"type": "object"}}, "required": ["task"]}},
            {"name": "delegate_to_git_maintainer", "description": "Delegate task to Git Maintainer", "parameters": {"type": "object", "properties": {"task": {"type": "string"}, "params": {"type": "object"}}, "required": ["task"]}},
        ]
    
    def _build_graph(self) -> StateGraph:
        """Build the Serena LangGraph workflow"""
        builder = StateGraph(SerenaState)
        
        # Add Nodes
        builder.add_node("reasoning", self.reasoning_node)
        builder.add_node("tool_execution", self.tool_execution_node)
        builder.add_node("maintainer_delegation", self.maintainer_delegation_node)
        builder.add_node("synthesis", self.synthesis_node)
        
        # Set Entry Point
        builder.add_edge(START, "reasoning")
        
        # Edges from Reasoning
        builder.add_conditional_edges(
            "reasoning",
            self.reasoning_routing,
            {
                "execute_tools": "tool_execution",
                "delegate": "maintainer_delegation",
                "finish": "synthesis"
            }
        )
        
        # Edges from Tool Execution
        builder.add_conditional_edges(
            "tool_execution",
            self.tool_routing,
            {
                "continue": "reasoning",
                "finish": "synthesis"
            }
        )
        
        # Edges from Maintainer Delegation
        builder.add_edge("maintainer_delegation", "reasoning")
        
        # Edges from Synthesis
        builder.add_edge("synthesis", END)
        
        return builder.compile()
    
    # --- Routing Logic ---
    
    def reasoning_routing(self, state: SerenaState) -> str:
        """Route based on reasoning output"""
        if state.get("tool_calls"):
            # Check if any tool is a delegation
            for call in state["tool_calls"]:
                if call["name"].startswith("delegate_to_"):
                    return "delegate"
            return "execute_tools"
        
        if state.get("iteration_count", 0) >= state.get("max_iterations", 5):
            return "finish"
        
        # Check if we have a final answer
        last_msg = state.get("messages", [])[-1] if state.get("messages") else None
        if last_msg and hasattr(last_msg, 'content'):
            content = last_msg.content
            if "FINAL ANSWER:" in content or "Final Answer:" in content:
                return "finish"
        
        return "finish"
    
    def tool_routing(self, state: SerenaState) -> str:
        """Route after tool execution"""
        if state.get("iteration_count", 0) >= state.get("max_iterations", 5):
            return "finish"
        
        # Continue reasoning with tool results
        return "continue"
    
    # --- Node Implementations ---
    
    async def reasoning_node(self, state: SerenaState) -> Dict[str, Any]:
        """Main reasoning node - generates thoughts and tool calls"""
        logger.info(f"[{state.get('task_id', 'serena')}] 🧠 Serena Reasoning")
        
        iteration = state.get("iteration_count", 0) + 1
        
        # Build system prompt with tools
        tools_prompt = format_tools_for_glm(self.serena_tools)
        
        system_prompt = f"""You are Serena, ARCA's Code Analysis Agent.
Your role is to analyze code, monitor system health, and coordinate with maintainer agents.

{tools_prompt}

MAINTAINER AGENTS:
- Docker Maintainer: More capable, handles container operations, restarts, deployments
- Git Maintainer: Handles version control operations

When you need to perform system operations:
1. First analyze the situation with your direct tools (read_file, list_files, etc.)
2. Then delegate to the appropriate maintainer for execution

Current Task: {state.get('operation', 'General analysis')}
Parameters: {state.get('params', {})}
"""
        
        # Build conversation context
        messages_text = ""
        for msg in state.get("messages", []):
            if hasattr(msg, 'content'):
                role = "User" if isinstance(msg, HumanMessage) else "Assistant"
                messages_text += f"{role}: {msg.content}\n"
        
        # Add tool results if any
        if state.get("tool_results"):
            for result in state["tool_results"]:
                messages_text += f"Tool Result ({result.get('tool')}): {result.get('result', result.get('error', 'Unknown'))}\n"
        
        prompt = f"{system_prompt}\n\nConversation:\n{messages_text}\n\nProvide your analysis and next action:"
        
        try:
            response, model = await self.llm.generate(prompt, system="You are Serena, ARCA's code agent.")
            
            # Parse tool calls from response
            tool_calls = parse_glm_tool_calls(response)
            
            return {
                "messages": [AIMessage(content=response)],
                "tool_calls": tool_calls,
                "iteration_count": iteration,
                "execution_log": state.get("execution_log", []) + [f"Iteration {iteration}: {response[:200]}..."]
            }
            
        except Exception as e:
            logger.error(f"Serena reasoning error: {e}")
            return {
                "error": str(e),
                "success": False,
                "messages": [AIMessage(content=f"Reasoning error: {e}")]
            }
    
    async def tool_execution_node(self, state: SerenaState) -> Dict[str, Any]:
        """Execute pending tool calls"""
        logger.info(f"[{state.get('task_id', 'serena')}] 🛠️ Serena Tool Execution")
        
        tool_calls = state.get("tool_calls", [])
        results = []
        
        for call in tool_calls:
            tool_name = call["name"]
            arguments = call.get("arguments", {})
            
            logger.info(f"Executing tool: {tool_name} with {arguments}")
            
            try:
                # Execute via MCP
                result = await self.mcp.call_tool(tool_name, arguments)
                results.append({
                    "tool": tool_name,
                    "result": result.get("result", result),
                    "success": result.get("success", True)
                })
            except Exception as e:
                results.append({
                    "tool": tool_name,
                    "error": str(e),
                    "success": False
                })
        
        return {
            "tool_results": results,
            "tool_calls": [],  # Clear pending calls
            "execution_log": state.get("execution_log", []) + [f"Executed {len(results)} tools"]
        }
    
    async def maintainer_delegation_node(self, state: SerenaState) -> Dict[str, Any]:
        """Delegate task to maintainer agent"""
        logger.info(f"[{state.get('task_id', 'serena')}] 📤 Serena Delegating to Maintainer")
        
        tool_calls = state.get("tool_calls", [])
        
        for call in tool_calls:
            if call["name"] == "delegate_to_docker_maintainer":
                task = call["arguments"].get("task", "")
                params = call["arguments"].get("params", {})
                
                # Call maintainer_agents service
                try:
                    maintainer_url = os.getenv("MAINTAINER_AGENTS_URL", "http://maintainer_agents:8087")
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        response = await client.post(
                            f"{maintainer_url}/invoke",
                            json={
                                "agent_type": "docker",
                                "operation": task,
                                "params": params
                            }
                        )
                        result = response.json() if response.status_code == 200 else {"error": response.text}
                        
                        return {
                            "escalated_to": "docker",
                            "maintainer_response": json.dumps(result),
                            "tool_calls": [],
                            "execution_log": state.get("execution_log", []) + [f"Delegated to Docker Maintainer: {task}"]
                        }
                except Exception as e:
                    return {
                        "error": f"Docker maintainer delegation failed: {e}",
                        "tool_calls": []
                    }
            
            elif call["name"] == "delegate_to_git_maintainer":
                task = call["arguments"].get("task", "")
                params = call["arguments"].get("params", {})
                
                try:
                    maintainer_url = os.getenv("MAINTAINER_AGENTS_URL", "http://maintainer_agents:8087")
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        response = await client.post(
                            f"{maintainer_url}/invoke",
                            json={
                                "agent_type": "git",
                                "operation": task,
                                "params": params
                            }
                        )
                        result = response.json() if response.status_code == 200 else {"error": response.text}
                        
                        return {
                            "escalated_to": "git",
                            "maintainer_response": json.dumps(result),
                            "tool_calls": [],
                            "execution_log": state.get("execution_log", []) + [f"Delegated to Git Maintainer: {task}"]
                        }
                except Exception as e:
                    return {
                        "error": f"Git maintainer delegation failed: {e}",
                        "tool_calls": []
                    }
        
        return {"tool_calls": []}
    
    async def synthesis_node(self, state: SerenaState) -> Dict[str, Any]:
        """Final synthesis node - generates final output"""
        logger.info(f"[{state.get('task_id', 'serena')}] ✅ Serena Synthesis")
        
        # Compile execution log
        execution_summary = "\n".join(state.get("execution_log", []))
        
        # Get last AI message as output
        messages = state.get("messages", [])
        output = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                output = msg.content
                break
        
        return {
            "success": not state.get("error"),
            "output": output,
            "execution_log": state.get("execution_log", []) + ["Synthesis complete"]
        }
    
    async def invoke(self, operation: str, params: Dict[str, Any], session_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Main entry point to invoke Serena graph.
        
        Args:
            operation: The task/operation to perform
            params: Parameters for the operation
            session_id: Session identifier
            user_id: User identifier
        
        Returns:
            Dict with success, output, and execution details
        """
        import uuid
        
        initial_state: SerenaState = {
            "messages": [HumanMessage(content=operation)],
            "session_id": session_id or str(uuid.uuid4()),
            "user_id": user_id or "system",
            "task_id": f"serena_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "operation": operation,
            "params": params,
            "tool_calls": [],
            "tool_results": [],
            "plan": None,
            "execution_log": [],
            "current_node": "start",
            "iteration_count": 0,
            "max_iterations": 5,
            "escalated_to": None,
            "maintainer_response": None,
            "success": False,
            "output": None,
            "error": None
        }
        
        try:
            final_state = await self.workflow.ainvoke(initial_state)
            
            return {
                "success": final_state.get("success", False),
                "output": final_state.get("output", ""),
                "execution_log": final_state.get("execution_log", []),
                "escalated_to": final_state.get("escalated_to"),
                "maintainer_response": final_state.get("maintainer_response"),
                "error": final_state.get("error")
            }
            
        except Exception as e:
            logger.error(f"Serena graph invocation failed: {e}")
            return {
                "success": False,
                "output": "",
                "error": str(e)
            }
