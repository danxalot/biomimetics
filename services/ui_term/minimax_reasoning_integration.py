# MiniMax Reasoning Integration for ARCA User Interaction Terminal
# Uses MCP (Model Context Protocol) tools for file access and operations
import asyncio
import json
import os
from typing import Dict, Any, List
from datetime import datetime
import httpx

class MCPToolClient:
    """Client for calling MCP server tools"""
    def __init__(self, mcp_url: str = "http://localhost:8085"):
        self.mcp_url = mcp_url
        self.available = False
    
    async def check_availability(self) -> bool:
        """Check if MCP server is available"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.mcp_url}/health")
                self.available = response.status_code == 200
                return self.available
        except:
            self.available = False
            return False
    
    async def call_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call an MCP tool"""
        if not self.available:
            await self.check_availability()
        
        if not self.available:
            return {"error": "MCP server not available"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.mcp_url}/mcp",
                    json={
                        "method": tool_name,
                        "params": params,
                        "id": f"minimax_{tool_name}_{datetime.now().timestamp()}"
                    }
                )
                return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    async def read_file(self, path: str) -> str:
        """Read a file via MCP"""
        result = await self.call_tool("file_read", {"path": path})
        if "error" in result:
            return f"Error reading file: {result['error']}"
        return result.get("result", {}).get("content", "")
    
    async def list_directory(self, path: str) -> List[str]:
        """List directory contents via MCP"""
        result = await self.call_tool("file_list", {"path": path})
        if "error" in result:
            return []
        return result.get("result", {}).get("files", [])
    
    async def run_shell(self, command: str) -> str:
        """Run shell command via MCP"""
        result = await self.call_tool("run_shell", {"command": command})
        if "error" in result:
            return f"Error: {result['error']}"
        return result.get("result", {}).get("output", "")

class MinimaxReasoningWorkflow:
    def __init__(self, conversation_history: List[Dict] = None, mcp_url: str = None):
        self.conversation_history = conversation_history or []
        self.proposals = {}
        self.minimax_model = "claude-3-5-sonnet-20241022"
        self.api_base = "https://api.minimax.io/anthropic/v1/messages"
        self.api_key = self._load_api_key()
        
        # Initialize MCP client for tool-based file access
        self.mcp_client = MCPToolClient(mcp_url or os.getenv("MCP_SERVER_URL", "http://localhost:8085"))
        self.use_mcp_tools = True  # Always prefer MCP tools over direct file access

    def _load_api_key(self) -> str:
        """Load MiniMax API key from secrets"""
        secrets_paths = [
            "/home/ubuntu/mcp_storage/ARCA/.secrets/MINIMAX_API_KEY.json",
            "/home/ubuntu/ARCA/.secrets/MINIMAX_API_KEY.json"
        ]
        
        for path in secrets_paths:
            if os.path.exists(path):
                try:
                    with open(path) as f:
                        secrets = json.load(f)
                        return secrets.get("ARCA_MiniMax", "")
                except Exception as e:
                    print(f"Warning: Failed to load API key from {path}: {e}")
        
        # Fallback to environment variable
        return os.environ.get("ARCA_MiniMax", "")

    async def invoke_reasoning(self, context_depth: int = 10) -> Dict[str, Any]:
        '''Analyze recent conversation and generate proposal'''
        recent_context = self.conversation_history[-context_depth:]
        analysis = await self._call_minimax_analyze(recent_context)
        proposal = await self._create_proposal_from_analysis(analysis)
        
        return {
            "context_used": len(recent_context),
            "analysis": analysis,
            "proposal": proposal,
            "status": "awaiting_approval"
        }

    async def _call_minimax_analyze(self, context: List[Dict]) -> Dict[str, Any]:
        """Actually call MiniMax API for analysis"""
        if not self.api_key:
            return {
                "error": "MiniMax API key not found",
                "summary": "Unable to analyze - API key missing",
                "key_requirements": [],
                "technical_approach": "",
                "reasoning_chain": []
            }
        
        # Format conversation context
        formatted_context = "\n".join([
            f"{msg.get('role', 'user')}: {msg.get('content', '')}"
            for msg in context
        ])
        
        # Create analysis prompt with MCP tool availability
        tool_info = ""
        if self.use_mcp_tools:
            mcp_available = await self.mcp_client.check_availability()
            if mcp_available:
                tool_info = """

**Available MCP Tools** (use these to access files and system information):
- file_read: Read file contents from ARCA system
- file_list: List directory contents
- run_shell: Execute shell commands (read-only queries)
- web_search: Search the web for information
- git_diff: Check current repository changes
- read_development_log: Read development activity logs

Example tool usage:
To analyze the user_interaction_agent service, you can:
1. Read the main file: use file_read with path="/home/ubuntu/ARCA/services/user_interaction_agent/main.py"
2. List service directory: use file_list with path="/home/ubuntu/ARCA/services/user_interaction_agent"
3. Check logs: use run_shell with command="docker logs user_interaction_agent --tail 50"

When you need to access files, request tool calls and I will execute them for you.
"""
        
        prompt = f"""Analyze the following conversation and provide:
1. A concise summary of what was discussed
2. Key requirements or objectives mentioned
3. Recommended technical approach
4. Step-by-step reasoning chain
{tool_info}

Conversation:
{formatted_context}

Provide your analysis in JSON format with these keys:
- summary: Brief overview
- key_requirements: List of main requirements
- technical_approach: Recommended implementation strategy
- reasoning_chain: Step-by-step logical breakdown
- tool_requests: (optional) List of MCP tools you need to call for more information"""

        return await self._call_minimax_api(prompt)
    
    async def _call_minimax_api(self, prompt: str) -> Dict[str, Any]:
        """Low-level API call to MiniMax"""
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.minimax_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4096
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(self.api_base, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                
                # Extract content from MiniMax response
                content = result.get("content", [])
                if content and isinstance(content, list):
                    # MiniMax returns content with 'thinking' and 'text' fields
                    thinking = content[0].get("thinking", "")
                    text_content = content[0].get("text", "")
                    
                    # Combine thinking and text for full response
                    full_response = f"{thinking}\n\n{text_content}" if thinking else text_content
                    
                    # Try to parse as JSON first
                    try:
                        analysis = json.loads(text_content)
                        # Add thinking process if available
                        if thinking:
                            analysis["reasoning_process"] = thinking
                        return analysis
                    except json.JSONDecodeError:
                        # If not JSON, structure the text response intelligently
                        return {
                            "summary": text_content[:500] if text_content else thinking[:500],
                            "key_requirements": self._extract_requirements(full_response),
                            "technical_approach": text_content if text_content else thinking,
                            "reasoning_chain": [thinking, text_content] if thinking and text_content else [full_response],
                            "thinking_process": thinking,
                            "response_text": text_content,
                            "raw_response": full_response
                        }
                
                return {
                    "summary": "Analysis completed but no content received",
                    "raw_response": str(result),
                    "key_requirements": [],
                    "technical_approach": "",
                    "reasoning_chain": []
                }
                
        except Exception as e:
            return {
                "error": str(e),
                "summary": f"API call failed: {str(e)}",
                "key_requirements": [],
                "technical_approach": "",
                "reasoning_chain": []
            }
    
    def _extract_requirements(self, text: str) -> List[str]:
        """Extract requirements from text response"""
        requirements = []
        lines = text.split('\n')
        for line in lines:
            if any(keyword in line.lower() for keyword in ['requirement', 'need', 'must', 'should']):
                requirements.append(line.strip())
        return requirements[:5]  # Limit to 5 key requirements
    
    async def execute_tool_requests(self, tool_requests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute MCP tool requests from MiniMax"""
        results = {}
        
        for tool_req in tool_requests:
            tool_name = tool_req.get("tool")
            params = tool_req.get("params", {})
            
            if tool_name == "file_read":
                content = await self.mcp_client.read_file(params.get("path", ""))
                results[tool_name] = content
            elif tool_name == "file_list":
                files = await self.mcp_client.list_directory(params.get("path", ""))
                results[tool_name] = files
            elif tool_name == "run_shell":
                output = await self.mcp_client.run_shell(params.get("command", ""))
                results[tool_name] = output
            else:
                result = await self.mcp_client.call_tool(tool_name, params)
                results[tool_name] = result
        
        return results
    
    async def invoke_reasoning_with_tools(self, context_depth: int = 10, max_iterations: int = 3) -> Dict[str, Any]:
        """Invoke reasoning with iterative tool use"""
        iteration = 0
        analysis = {}
        tool_results_history = []
        
        while iteration < max_iterations:
            # Get analysis from MiniMax
            if iteration == 0:
                analysis = await self._call_minimax_analyze(self.conversation_history[-context_depth:])
            else:
                # Include tool results in follow-up request
                analysis = await self._call_minimax_with_tool_results(
                    self.conversation_history[-context_depth:],
                    tool_results_history
                )
            
            # Check if MiniMax requested tools
            tool_requests = analysis.get("tool_requests", [])
            if not tool_requests or not isinstance(tool_requests, list):
                break  # No more tools needed
            
            # Execute tool requests
            tool_results = await self.execute_tool_requests(tool_requests)
            tool_results_history.append({
                "iteration": iteration + 1,
                "requests": tool_requests,
                "results": tool_results
            })
            
            iteration += 1
        
        # Create final proposal with all context
        proposal = await self._create_proposal_from_analysis(analysis)
        proposal["tool_executions"] = tool_results_history
        proposal["iterations"] = iteration
        
        return {
            "context_used": context_depth,
            "analysis": analysis,
            "proposal": proposal,
            "status": "awaiting_approval",
            "tool_history": tool_results_history
        }
    
    async def _call_minimax_with_tool_results(self, context: List[Dict], tool_history: List[Dict]) -> Dict[str, Any]:
        """Continue analysis with tool results"""
        formatted_context = "\n".join([
            f"{msg.get('role', 'user')}: {msg.get('content', '')}"
            for msg in context
        ])
        
        # Format tool results
        tool_results_text = "\n\n**Tool Execution Results:**\n"
        for execution in tool_history:
            tool_results_text += f"\nIteration {execution['iteration']}:\n"
            for tool_name, result in execution['results'].items():
                result_preview = str(result)[:500]
                tool_results_text += f"- {tool_name}: {result_preview}...\n"
        
        prompt = f"""Continue your analysis using the tool results below.

Original Conversation:
{formatted_context}
{tool_results_text}

Provide updated analysis or request additional tools if needed.
Return JSON with: summary, key_requirements, technical_approach, reasoning_chain, tool_requests (if more tools needed)"""
        
        return await self._call_minimax_api(prompt)

    async def _create_proposal_from_analysis(self, analysis: Dict) -> Dict[str, Any]:
        proposal_id = f"proposal_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        proposal = {
            "id": proposal_id,
            "timestamp": datetime.utcnow().isoformat(),
            "summary": analysis.get("summary", ""),
            "implementation_plan": {"tasks": [], "job_submissions": []},
            "approval_status": "pending"
        }
        self.proposals[proposal_id] = proposal
        return proposal

    async def approve_proposal(self, proposal_id: str) -> Dict[str, Any]:
        if proposal_id not in self.proposals:
            return {"error": "Proposal not found"}
        
        proposal = self.proposals[proposal_id]
        proposal["approval_status"] = "approved"
        return {"status": "approved_and_submitted", "proposal": proposal}

async def handle_reasoning_trigger(message: str, conversation_history: List[Dict]) -> Dict[str, Any]:
    triggers = ["execute this", "create proposal", "implement this", "make this happen"]
    
    if any(trigger in message.lower() for trigger in triggers):
        workflow = MinimaxReasoningWorkflow(conversation_history)
        result = await workflow.invoke_reasoning()
        return {"reasoning_triggered": True, "result": result}
    
    return {"reasoning_triggered": False}
