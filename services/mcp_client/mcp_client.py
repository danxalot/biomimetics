#!/usr/bin/env python3
"""
ARCA MCP Client - Multi-Instance Communication
Connects to Data-Hub MCP Server for skills-based reasoning
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import aiohttp
from dataclasses import dataclass

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("arca-mcp-client")

# Configuration
ARCA_ROOT = Path(os.getenv("ARCA_ROOT", "/home/ubuntu/ARCA"))
DATA_HUB_URL = os.getenv("DATA_HUB_MCP_URL", "http://10.0.0.10:8086")
INSTANCE_ID = os.getenv("INSTANCE_ID", "unknown-instance")
CLIENT_PORT = int(os.getenv("MCP_CLIENT_PORT", "8092"))


@dataclass
class MCPRequest:
    method: str
    params: Dict[str, Any]
    id: Optional[str] = None


class MCPClient:
    """MCP Client for connecting to Data-Hub reasoning server"""

    def __init__(self, server_url: str, instance_id: str):
        self.server_url = server_url
        self.instance_id = instance_id
        # Support default API key for MCP operations via env var
        self.api_key = (
            os.getenv("MCP_API_KEY")
            or os.getenv("X_LITELLM_API_KEY")
            or os.getenv("LITELLM_API_KEY")
        )
        self.default_headers = {}
        if self.api_key:
            # Header used in many GHCR/Proxy examples
            self.default_headers["x-litellm-api-key"] = (
                f"Bearer {self.api_key}"
                if not self.api_key.startswith("Bearer ")
                else self.api_key
            )
        self.session = None
        self.connected = False

    async def __aenter__(self):
        # Default headers applied to client session if provided
        if self.default_headers:
            self.session = aiohttp.ClientSession(headers=self.default_headers)
        else:
            self.session = aiohttp.ClientSession()
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def connect(self):
        """Connect to the MCP server"""
        try:
            async with self.session.get(f"{self.server_url}/health") as response:
                if response.status == 200:
                    self.connected = True
                    logger.info(f"Connected to MCP server at {self.server_url}")
                    return True
                else:
                    logger.error(f"Failed to connect to MCP server: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    async def call_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call a tool on the MCP server using the unified /mcp RPC endpoint.

        The MCP server exposes a single POST /mcp route which accepts a JSON
        object with 'method' and 'params' keys. We wrap the tool_name as the
        method and pass arguments as 'params'.
        """
        if not self.connected:
            await self.connect()

        try:
            request_data = {
                "method": tool_name,
                "params": arguments or {},
                "id": self.instance_id,
            }

            async with self.session.post(
                f"{self.server_url}/mcp", json=request_data
            ) as response:
                if response.status == 200:
                    result_payload = await response.json()
                    # MCPResponse has either 'result' or 'error'
                    if isinstance(result_payload, dict) and "result" in result_payload:
                        return result_payload["result"]
                    elif isinstance(result_payload, dict) and "error" in result_payload:
                        return {"error": result_payload["error"]}
                    return result_payload
                else:
                    error_text = await response.text()
                    logger.error(f"Tool call failed: {response.status} - {error_text}")
                    return {"error": f"HTTP {response.status}: {error_text}"}

        except Exception as e:
            logger.error(f"Tool call error: {e}")
            return {"error": str(e)}

    async def get_skill_recommendations(self, context: str) -> List[str]:
        """Get skill recommendations for a given context"""
        result = await self.call_tool("get_skill_recommendations", {"context": context})
        return result if isinstance(result, list) else []

    async def record_learning_event(
        self,
        skill_name: str,
        success: bool,
        context: str,
        details: Dict[str, Any] = None,
    ):
        """Record a learning event"""
        return await self.call_tool(
            "record_learning_event",
            {
                "skill_name": skill_name,
                "success": success,
                "context": context,
                "details": details or {},
            },
        )

    async def analyze_skill_performance(
        self, skill_name: str, time_period: str = "30d"
    ) -> Dict[str, Any]:
        """Analyze skill performance"""
        return await self.call_tool(
            "analyze_skill_performance",
            {"skill_name": skill_name, "time_period": time_period},
        )

    async def query_gordon_ai(
        self, prompt: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Query Gordon AI through the MCP server"""
        return await self.call_tool(
            "query_gordon_ai", {"prompt": prompt, "context": context or {}}
        )

    async def get_skills_needing_improvement(self) -> List[Dict[str, Any]]:
        """Get skills that need improvement"""
        result = await self.call_tool("get_skills_needing_improvement", {})
        return result if isinstance(result, list) else []

    async def get_resource(self, resource_uri: str) -> Dict[str, Any]:
        """Get a resource by calling the MCP server's read_resource method.

        Many MCP servers implement resources as a tool method (read_resource).
        Use call_tool to invoke it to keep a single RPC mapping between client and server.
        """
        return await self.call_tool("read_resource", {"uri": resource_uri})


class SkillsAwareAgent:
    """Skills-aware agent that uses MCP for reasoning enhancement"""

    def __init__(self, instance_id: str, data_hub_url: str):
        self.instance_id = instance_id
        self.data_hub_url = data_hub_url
        self.local_performance = {}

    async def execute_with_skills_tracking(
        self, task_description: str, execution_func, *args, **kwargs
    ):
        """Execute a task with skills tracking"""
        async with MCPClient(self.data_hub_url, self.instance_id) as mcp:
            # Get skill recommendations
            recommended_skills = await mcp.get_skill_recommendations(task_description)
            logger.info(
                f"Recommended skills for '{task_description}': {recommended_skills}"
            )

            start_time = datetime.now()
            success = False
            error_details = None

            try:
                # Execute the task
                result = (
                    await execution_func(*args, **kwargs)
                    if asyncio.iscoroutinefunction(execution_func)
                    else execution_func(*args, **kwargs)
                )
                success = True
                logger.info(f"Task completed successfully: {task_description}")
                return result

            except Exception as e:
                error_details = {"error": str(e), "type": type(e).__name__}
                logger.error(f"Task failed: {task_description} - {e}")
                raise

            finally:
                # Record learning events for all recommended skills
                execution_time = (datetime.now() - start_time).total_seconds()
                context = f"{task_description} (executed in {execution_time:.2f}s on {self.instance_id})"
                details = {
                    "execution_time": execution_time,
                    "instance_id": self.instance_id,
                    "error_details": error_details,
                }

                # Batch learning events to avoid creating many individual records per task
                if recommended_skills:
                    # Limit the list to a reasonable length to avoid oversized skill names
                    skill_list = recommended_skills[:10]
                    skill_tag = ",".join(skill_list)
                else:
                    skill_tag = "no_skills_recommended"

                try:
                    await mcp.record_learning_event(
                        skill_tag, success, context, details
                    )
                    logger.info(
                        f"Recorded batched learning event for skills: {skill_tag} -> {'success' if success else 'failure'}"
                    )
                except Exception as e:
                    logger.error(f"Failed to record batched learning event: {e}")

    async def get_improvement_suggestions(self) -> Dict[str, Any]:
        """Get suggestions for improving skills"""
        async with MCPClient(self.data_hub_url, self.instance_id) as mcp:
            skills_needing_improvement = await mcp.get_skills_needing_improvement()

            suggestions = {
                "skills_to_focus_on": skills_needing_improvement[:3],  # Top 3
                "recommended_actions": [],
                "learning_opportunities": [],
            }

            for skill in skills_needing_improvement[:3]:
                suggestions["recommended_actions"].extend(skill.get("improvements", []))
                suggestions["learning_opportunities"].append(
                    f"Practice {skill['name']} with simpler tasks first"
                )

            return suggestions

    async def enhanced_reasoning(
        self, prompt: str, context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Use Gordon AI for enhanced reasoning"""
        async with MCPClient(self.data_hub_url, self.instance_id) as mcp:
            enhanced_context = {
                "instance_id": self.instance_id,
                "timestamp": datetime.now().isoformat(),
                **(context or {}),
            }

            return await mcp.query_gordon_ai(prompt, enhanced_context)


# Example usage functions for different instance types
async def workhorse_enhanced_execution(task_description: str, command: str):
    """Workhorse instance with skills tracking"""
    agent = SkillsAwareAgent("workhorse", DATA_HUB_URL)

    def execute_command():
        import subprocess

        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"Command failed: {result.stderr}")
        return result.stdout

    return await agent.execute_with_skills_tracking(task_description, execute_command)


async def knowledge_processor_enhanced_analysis(
    data_description: str, analysis_func, data
):
    """Knowledge processor with skills tracking"""
    agent = SkillsAwareAgent("knowledge-processor", DATA_HUB_URL)
    return await agent.execute_with_skills_tracking(
        data_description, analysis_func, data
    )


async def gateway_enhanced_coordination(
    coordination_task: str, coordination_func, *args
):
    """Gateway instance with skills tracking"""
    agent = SkillsAwareAgent("gateway", DATA_HUB_URL)
    return await agent.execute_with_skills_tracking(
        coordination_task, coordination_func, *args
    )


# FastAPI app for local MCP client interface
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title=f"ARCA MCP Client - {INSTANCE_ID}", version="1.0.0")


# JSON-RPC handling
@app.post("/mcp")
async def handle_mcp_request(request: Dict[str, Any]):
    """Handle JSON-RPC 2.0 requests from Antigravity Bridge"""
    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id")

    response = {
        "jsonrpc": "2.0",
        "id": req_id,
    }

    try:
        if method == "tools/list":
            response["result"] = {
                "tools": [
                    {
                        "name": "delegate_task",
                        "description": "Delegate a complex task to the ARCA Maintainer Agents via the Smart Interface. Handles SOPs, Logic, and Skills Tracking automatically.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "task": {
                                    "type": "string",
                                    "description": "Natural language description of the task (e.g. 'Build Pythia image on OCI')",
                                },
                                "agent_hint": {
                                    "type": "string",
                                    "description": "Optional hint for which agent to use (docker, git, serena)",
                                    "enum": ["docker", "git", "serena", "auto"],
                                },
                            },
                            "required": ["task"],
                        },
                    }
                ]
            }

        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})

            if tool_name == "delegate_task":
                task = tool_args.get("task")
                agent_hint = tool_args.get("agent_hint", "auto")

                # Execute via SkillsAwareAgent
                agent = SkillsAwareAgent(INSTANCE_ID, DATA_HUB_URL)

                # Logic to route the task to the real MCP Server tools
                async def actual_execution():
                    async with MCPClient(DATA_HUB_URL, INSTANCE_ID) as mcp:
                        # categorization logic
                        agent_type = "docker"  # Default

                        # Use hint if explicitly provided and valid
                        if agent_hint in [
                            "docker",
                            "git",
                            "serena",
                            "code_maintainer",
                            "security",
                            "observer",
                        ]:
                            agent_type = agent_hint
                        elif "git" in task.lower():
                            agent_type = "git"
                        elif "docker" in task.lower() or "build" in task.lower():
                            agent_type = "docker"
                        elif "security" in task.lower():
                            agent_type = "security"
                        elif "code" in task.lower() or "implement" in task.lower():
                            agent_type = "code_maintainer"

                        # Parameter mapping
                        params = {"target": "system", "details": task}
                        if agent_type == "git":
                            params = {"message": task}
                        elif agent_type == "code_maintainer" or agent_type == "serena":
                            params = {"task_description": task}

                        operation = "execute"
                        # For code/serena, the operation IS the task description usually
                        if agent_type in ["code_maintainer", "serena"]:
                            operation = task

                        logger.info(
                            f"Delegating '{task}' -> dispatch_agent({agent_type})"
                        )
                        return await mcp.call_tool(
                            "dispatch_agent",
                            {
                                "agent_type": agent_type,
                                "operation": operation,
                                "params": params,
                            },
                        )

                result = await agent.execute_with_skills_tracking(
                    task, actual_execution
                )

                response["result"] = {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Task Delegated via Smart Interface.\nResult: {str(result)}",
                        }
                    ]
                }
            else:
                # Forward generic tool calls to the upstream MCP server
                # This enables 'gateway_request', 'redis_command', etc.
                logger.info(
                    f"Forwarding tool call '{tool_name}' to upstream MCP server"
                )
                async with MCPClient(DATA_HUB_URL, INSTANCE_ID) as mcp:
                    result = await mcp.call_tool(tool_name, tool_args)
                    if isinstance(result, dict) and "error" in result:
                        response["error"] = result["error"]
                    else:
                        response["result"] = result

    except Exception as e:
        logger.error(f"MCP JSON-RPC Error: {e}")
        response["error"] = {"code": -32000, "message": str(e)}

    return response


class TaskRequest(BaseModel):
    description: str
    context: Optional[Dict[str, Any]] = None


class SkillEvent(BaseModel):
    skill_name: str
    success: bool
    context: str
    details: Optional[Dict[str, Any]] = None


@app.post("/execute-with-tracking")
async def execute_with_tracking(request: TaskRequest):
    """Execute a task with skills tracking"""
    agent = SkillsAwareAgent(INSTANCE_ID, DATA_HUB_URL)

    # Placeholder execution - would be replaced with actual task logic
    def dummy_execution():
        return {"result": "Task completed", "instance": INSTANCE_ID}

    try:
        result = await agent.execute_with_skills_tracking(
            request.description, dummy_execution
        )
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/record-skill-event")
async def record_skill_event(event: SkillEvent):
    """Record a skill learning event"""
    async with MCPClient(DATA_HUB_URL, INSTANCE_ID) as mcp:
        result = await mcp.record_learning_event(
            event.skill_name, event.success, event.context, event.details
        )
        return result


@app.get("/improvement-suggestions")
async def get_improvement_suggestions():
    """Get skill improvement suggestions"""
    agent = SkillsAwareAgent(INSTANCE_ID, DATA_HUB_URL)
    return await agent.get_improvement_suggestions()


@app.post("/enhanced-reasoning")
async def enhanced_reasoning(request: TaskRequest):
    """Use enhanced reasoning via Gordon AI"""
    agent = SkillsAwareAgent(INSTANCE_ID, DATA_HUB_URL)
    return await agent.enhanced_reasoning(request.description, request.context)


@app.get("/skills-dashboard")
async def get_skills_dashboard():
    """Get skills dashboard from data-hub"""
    async with MCPClient(DATA_HUB_URL, INSTANCE_ID) as mcp:
        return await mcp.get_resource("skills://performance-dashboard")


@app.get("/tools")
async def list_tools():
    """Expose available MCP tools for mesh routing - satellite capability declaration"""
    # Import the tool registry
    try:
        from tools.registry import ToolRegistry

        registry = ToolRegistry.get_instance()
        tools = registry.list_tools()

        return {
            "satellite": True,
            "instance_id": INSTANCE_ID,
            "data_hub_url": DATA_HUB_URL,
            "tools": tools,
            "mesh_routing": True,
            "capabilities": [
                "delegate_task",
                "reasoning_search",
                "reasoning_store",
                "list_skills",
                "list_tools",
            ],
        }
    except ImportError:
        # Fallback if registry not available
        return {
            "satellite": True,
            "instance_id": INSTANCE_ID,
            "data_hub_url": DATA_HUB_URL,
            "tools": [
                {
                    "name": "delegate_task",
                    "description": "Delegate tasks to ARCA MCP server",
                }
            ],
            "mesh_routing": True,
            "capabilities": ["delegate_task"],
        }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "instance_id": INSTANCE_ID,
        "data_hub_url": DATA_HUB_URL,
        "timestamp": datetime.now().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("mcp_client:app", host="0.0.0.0", port=CLIENT_PORT, log_level="info")
