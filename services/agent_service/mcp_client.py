"""
This file contains the MCPClient class, which is used to interact with the MCP server.
Refactored to be fully asynchronous using httpx to prevent blocking the event loop.
"""

import httpx
import os
import json
import logging
import asyncio
import contextvars
from typing import Optional, Dict, List, Any, Union

logger = logging.getLogger(__name__)

# Context var for propagating headers (authorization, etc.)
headers_context = contextvars.ContextVar('mcp_headers', default={})

class MCPClient:
    """A client for interacting with the MCP server (Async)."""

    def __init__(self, mcp_server_url: Optional[str] = None):
        """
        Initialize the Async MCP Client.
        
        Args:
            mcp_server_url: Optional URL override. If None, tries to auto-detect.
        """
        # Determine URL with smart defaults
        if not mcp_server_url:
            mcp_server_url = os.getenv("MCP_SERVER_URL", "http://mcp_server:8086/mcp")
            
        # Robust URL normalization
        url = mcp_server_url.rstrip('/')
        if url.endswith('/mcp'):
            url = url[:-4]
            
        self.base_url = url
        self.mcp_url = f"{url}/mcp"
        self.legacy_url = mcp_server_url 
        
        # Initialize async client with timeouts
        # We use a single client instance for connection pooling
        self.timeout = httpx.Timeout(60.0, connect=5.0)
        self.limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
        
        logger.info(f"Initialized Async MCPClient with URL: {self.mcp_url}")

    @staticmethod
    def set_headers(headers: Dict[str, str]):
        """Set headers in the thread-local/task-local context."""
        return headers_context.set(headers)

    @staticmethod
    def reset_headers(token):
        """Reset headers in the context."""
        headers_context.reset(token)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create an httpx client (helper for context management preferred)"""
        return httpx.AsyncClient(timeout=self.timeout, limits=self.limits)

    async def _call_mcp(self, method: str, params: dict, headers: Optional[dict] = None) -> dict:
        """A helper method to call the MCP server asynchronously."""
        payload = {
            "method": method,
            "params": params,
        }
        merged_headers = {"Content-Type": "application/json"}
        
        # Merge headers from context if not provided
        if not headers:
            headers = headers_context.get()
            
        if headers:
            # Propagate Genesis and Workhorse headers
            allowed_headers = ["x-genesis-", "x-workhorse-token"]
            propagated_headers = {k: v for k, v in headers.items() if any(str(k).lower().startswith(p) or str(k).lower() == p for p in allowed_headers)}
            merged_headers.update(propagated_headers)
        
        headers = merged_headers
        
        # Add client API key header if configured
        client_key = os.getenv("MCP_CLIENT_API_KEY")
        if client_key:
            headers["X-MCP-API-KEY"] = client_key
            headers["Authorization"] = f"Bearer {client_key}"

        async with httpx.AsyncClient(timeout=self.timeout, limits=self.limits) as client:
            try:
                response = await client.post(self.mcp_url, json=payload, headers=headers)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"MCP HTTP Error {e.response.status_code} for {method}: {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"MCP Connection Error for {method} at {self.mcp_url}: {e}")
                # Try fallback for localhost if likely running outside docker
                if "mcp_server" in self.mcp_url and "Name or service not known" in str(e):
                    logger.warning("DNS lookup failed for 'mcp_server'. Are you running outside Docker? Trying localhost...")
                    try:
                        fallback_url = self.mcp_url.replace("mcp_server", "localhost")
                        logger.info(f"Retrying with fallback URL: {fallback_url}")
                        response = await client.post(fallback_url, json=payload, headers=headers)
                        response.raise_for_status()
                        return response.json()
                    except Exception as fallback_e:
                        logger.error(f"Fallback connection also failed: {fallback_e}")
                        raise e
                raise

    async def call_tool(self, tool_name: str, arguments: dict, headers: Optional[dict] = None) -> dict:
        """
        Call any MCP tool by name with arguments (Async).
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": 1
        }
        merged_headers = {"Content-Type": "application/json"}
        
        # Merge headers from context if not provided
        if not headers:
            headers = headers_context.get()
            
        if headers:
            # Propagate Genesis and Workhorse headers
            allowed_headers = ["x-genesis-", "x-workhorse-token"]
            propagated_headers = {k: v for k, v in headers.items() if any(str(k).lower().startswith(p) or str(k).lower() == p for p in allowed_headers)}
            merged_headers.update(propagated_headers)
            
        headers = merged_headers
        client_key = os.getenv("MCP_CLIENT_API_KEY")
        if client_key:
            headers["X-MCP-API-KEY"] = client_key
            headers["Authorization"] = f"Bearer {client_key}"

        async with httpx.AsyncClient(timeout=self.timeout, limits=self.limits) as client:
            try:
                response = await client.post(self.mcp_url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
                logger.info(f"MCP Tool {tool_name} executed successfully")
                return result.get("result", result)
            except Exception as e:
                logger.error(f"MCP Tool {tool_name} failed: {e}")
                return {"error": str(e)}

    # Robotics tools (Physics Engine)
    async def robotics_analyze(self, content: str, mode: str = "structure", headers: Optional[dict] = None) -> dict:
        return await self.call_tool("robotics_analyze", {"content": content, "mode": mode}, headers=headers)

    async def robotics_dry_run(self, script: str, headers: Optional[dict] = None) -> dict:
        return await self.call_tool("robotics_dry_run", {"script": script}, headers=headers)

    async def robotics_symbiosis_check(self, policy: str, headers: Optional[dict] = None) -> dict:
        return await self.call_tool("robotics_symbiosis_check", {"policy": policy}, headers=headers)

    async def robotics_blackboard_health(self, blackboard_json: str, headers: Optional[dict] = None) -> dict:
        return await self.call_tool("robotics_blackboard_health", {"blackboard_json": blackboard_json}, headers=headers)

    # Blackboard tools
    async def blackboard_write(self, key: str, value: any, headers: Optional[dict] = None) -> dict:
        return await self.call_tool("blackboard_write", {"key": key, "value": value}, headers=headers)

    async def blackboard_read(self, key: str, headers: Optional[dict] = None) -> dict:
        return await self.call_tool("blackboard_read", {"key": key}, headers=headers)

    async def blackboard_health_check(self, headers: Optional[dict] = None) -> dict:
        return await self.call_tool("blackboard_health_check", {}, headers=headers)

    # Neo4j tools
    async def neo4j_query(self, cypher: str, headers: Optional[dict] = None) -> dict:
        return await self.call_tool("neo4j_run_cypher", {"query": cypher}, headers=headers)

    async def neo4j_write(self, cypher: str, headers: Optional[dict] = None) -> dict:
        return await self.call_tool("neo4j_run_cypher", {"query": cypher}, headers=headers)

    async def neo4j_run_cypher(self, cypher: str, headers: Optional[dict] = None) -> dict:
        return await self.call_tool("neo4j_run_cypher", {"query": cypher}, headers=headers)

    async def neo4j_verify_connectivity(self, headers: Optional[dict] = None) -> dict:
        return await self.call_tool("neo4j_verify_connectivity", {}, headers=headers)

    # Compressor tool
    async def compress_context(self, context: str) -> dict:
        return await self.call_tool("compress_context", {"context": context})

    # Serena code tools
    async def serena_analyze_code(self, file_path: str) -> dict:
        return await self.call_tool("serena_analyze_code", {"file_path": file_path})

    async def serena_refactor_suggestion(self, file_path: str, context: str = "") -> dict:
        return await self.call_tool("serena_refactor_suggestion", {"file_path": file_path, "context": context})

    # Memory methods
    async def get_state(self, key: str) -> dict:
        return await self._call_mcp("get_state", {"key": key})

    async def set_state(self, key: str, value: any) -> dict:
        return await self._call_mcp("set_state", {"key": key, "value": value})

    async def query_graph(self, query: str) -> dict:
        return await self._call_mcp("query_graph", {"query": query})

    async def add_to_graph(self, nodes: list, edges: list) -> dict:
        return await self._call_mcp("add_to_graph", {"nodes": nodes, "edges": edges})

    async def query_vector(self, vector: list) -> dict:
        return await self._call_mcp("query_vector", {"vector": vector})

    async def add_to_vector(self, vectors: list) -> dict:
        return await self._call_mcp("add_to_vector", {"vectors": vectors})

    # Tool methods
    async def list_tools(self) -> dict:
        return await self._call_mcp("list_tools", {})

    # File system tool methods
    async def file_read(self, path: str) -> dict:
        return await self._call_mcp("file_read", {"path": path})

    async def file_write(self, path: str, content: str) -> dict:
        return await self._call_mcp("file_write", {"path": path, "content": content})

    async def file_list(self, path: str) -> dict:
        return await self._call_mcp("file_list", {"path": path})

    async def file_delete(self, path: str) -> dict:
        return await self._call_mcp("file_delete", {"path": path})

    # Git tool methods
    async def git_commit(self, message: str) -> dict:
        return await self._call_mcp("git_commit", {"message": message})

    async def git_push(self) -> dict:
        return await self._call_mcp("git_push", {})

    async def git_pull(self) -> dict:
        return await self._call_mcp("git_pull", {})

    async def git_branch(self, branch: str) -> dict:
        return await self._call_mcp("git_branch", {"branch": branch})
        
    async def git_diff(self) -> dict:
        return await self._call_mcp("git_diff", {})

    # Shell tool method
    async def run_shell(self, command: str) -> dict:
        return await self._call_mcp("run_shell", {"command": command})

    # ===== MCP SKILL MANAGEMENT FRAMEWORK =====
    
    # Skill Query Methods
    async def list_skills(self, category: str = None) -> dict:
        """List all available MCP skills from the Skills Bank"""
        return await self.call_tool("skills_list", {})
    
    async def search_skills(self, query: str) -> dict:
        """Search the Skills Bank for relevant repair procedures"""
        return await self.call_tool("skills_search", {"query": query})
    
    async def get_skill(self, skill_name: str) -> dict:
        """Get the full content of a specific skill document"""
        return await self.call_tool("skills_get", {"skill_name": skill_name})
    
    async def analyze_skill_performance(self, skill_name: str, time_period: str = "30d") -> dict:
        """Analyze performance of a specific skill (7d, 30d, all)"""
        return await self.call_tool("analyze_skill_performance", {"skill_name": skill_name, "time_period": time_period})
    
    async def get_skill_recommendations(self, context: str) -> dict:
        """Get skill recommendations for a given context"""
        return await self.call_tool("get_skill_recommendations", {"context": context})
    
    async def get_skills_needing_improvement(self) -> dict:
        """Get list of skills that need improvement"""
        return await self.call_tool("get_skills_needing_improvement", {})

    # Skill Creation & Capture Methods
    async def capture_skill(self, skill_name: str, category: str, description: str, 
                     problem: str, solution_steps: list, verification: str,
                     mcp_tools_used: list = None, related_services: list = None) -> dict:
        return await self.call_tool("skill_capture", {
            "skill_name": skill_name,
            "category": category,
            "description": description,
            "problem": problem,
            "solution_steps": solution_steps,
            "verification": verification,
            "mcp_tools_used": mcp_tools_used or [],
            "related_services": related_services or []
        })
    
    async def create_skill_file(self, skill_name: str, content: str, category: str = "docs") -> dict:
        filename = skill_name.replace(" ", "_").replace("-", "_").upper()
        path = f"skills/{filename}.md"
        
        return await self.call_tool("create_file", {
            "path": path,
            "content": content,
            "category": category
        })
    
    async def update_skill_file(self, skill_name: str, content: str) -> dict:
        filename = skill_name.replace(" ", "_").replace("-", "_").upper()
        path = f"skills/{filename}.md"
        
        return await self.call_tool("write_file", {
            "path": path,
            "content": content
        })
    
    async def read_skill_file(self, skill_name: str) -> dict:
        filename = skill_name.replace(" ", "_").replace("-", "_").upper()
        path = f"skills/{filename}.md"
        
        return await self.call_tool("read_file", {"path": path})
    
    async def archive_skill(self, skill_name: str) -> dict:
        registry = await self.call_tool("read_file", {"path": "databases/skills/skills_registry.json"})
        
        if "error" in registry:
            return {"error": f"Failed to read registry: {registry['error']}"}
        
        try:
            import json
            skills_data = json.loads(registry) if isinstance(registry, str) else registry
            
            for skill in skills_data:
                if skill.get("name", "").lower() == skill_name.lower():
                    skill["archived"] = True
                    skill["archived_at"] = datetime.now().isoformat()
            
            updated_registry = json.dumps(skills_data, indent=2)
            return await self.call_tool("write_file", {
                "path": "databases/skills/skills_registry.json",
                "content": updated_registry
            })
        except Exception as e:
            return {"error": f"Failed to archive skill: {str(e)}"}
    
    async def restore_skill(self, skill_name: str) -> dict:
        registry = await self.call_tool("read_file", {"path": "databases/skills/skills_registry.json"})
        
        if "error" in registry:
            return {"error": f"Failed to read registry: {registry['error']}"}
        
        try:
            import json
            skills_data = json.loads(registry) if isinstance(registry, str) else registry
            
            for skill in skills_data:
                if skill.get("name", "").lower() == skill_name.lower():
                    skill["archived"] = False
                    if "archived_at" in skill:
                        del skill["archived_at"]
            
            updated_registry = json.dumps(skills_data, indent=2)
            return await self.call_tool("write_file", {
                "path": "databases/skills/skills_registry.json",
                "content": updated_registry
            })
        except Exception as e:
            return {"error": f"Failed to restore skill: {str(e)}"}

    # Gemini/LLM Integration Methods
    async def get_gemini_pricing_info(self) -> dict:
        """Get Google Gemini API pricing and quota information (Async)"""
        try:
            result = await self.call_tool("skills_get", {"skill_name": "google_gemini_api_pricing_quotas"})
            if result and 'error' not in result:
                return result
        except:
            pass
        
        try:
            result = await self.call_tool("read_file", {"path": "skills/Google_Gemini_API_Pricing_Quotas.md"})
            if result:
                return {
                    "skill_name": "google_gemini_api_pricing_quotas",
                    "content": result if isinstance(result, str) else result.get("content", ""),
                    "source": "file_read",
                    "available": True
                }
        except Exception as e:
            logger.warning(f"Failed to read Gemini skill file: {e}")
        
        return {
            "skill_name": "google_gemini_api_pricing_quotas",
            "error": "Skill not available",
            "available": False
        }
    
    async def refresh_skills(self) -> dict:
        try:
            refresh_request = {
                "action": "refresh_skills",
                "timestamp": datetime.now().isoformat()
            }
            await self.blackboard_write("mcp:skills:refresh_request", refresh_request)
            return {
                "status": "refresh_requested",
                "message": "Skills will refresh automatically - check mcp_server logs"
            }
        except Exception as e:
            logger.error(f"Failed to request skills refresh: {e}")
            return {"error": str(e)}

    def create_tool_in_mcp(self, tool_name: str, description: str, 
                          input_schema: dict, implementation: str = None) -> dict:
        # Purely local helper, no network call - can remain sync
        tool_definition = {
            "name": tool_name,
            "description": description,
            "input_schema": input_schema,
            "implementation": implementation or "See MCP server service for implementation",
            "status": "registered_in_mcp"
        }
        return {
            "status": "tool_definition_created",
            "tool_definition": tool_definition,
            "next_step": "Implement in MCP server and restart mcp_server container",
            "mcp_server_location": "services/mcp_server/"
        }

    # Alias methods for compatibility
    async def query_skill(self, skill_name: str, query: str = None) -> dict:
        return await self.call_tool("skills_get", {"skill_name": skill_name})

    # Test methods (Quota Safe) - kept sync as they use google genai directly or use async executor if needed
    # But since they don't call MCP, they don't strictly *need* to be async for the MCP refactor, 
    # but for consistent async agent, let's make them async.
    async def test_model_responsiveness(self, model_name: str, max_retries: int = 2) -> dict:
        """Async wrapper for model testing"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._test_model_responsiveness_sync, model_name, max_retries)

    def _test_model_responsiveness_sync(self, model_name: str, max_retries: int) -> dict:
        """Internal sync implementation of model testing"""
        # ... logic as before ...
        try:
            import google.generativeai as genai
            import time
            from datetime import datetime
            
            genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
            
            for attempt in range(max_retries):
                try:
                    start_time = time.time()
                    model = genai.GenerativeModel(model_name)
                    response = model.count_tokens("Test message")
                    end_time = time.time()
                    latency_ms = (end_time - start_time) * 1000
                    
                    return {
                        "model_name": model_name,
                        "responsive": True,
                        "latency_ms": round(latency_ms, 1),
                        "token_count": response.total_tokens,
                        "test_method": "countTokens (quota-safe)",
                        "timestamp": datetime.now().isoformat(),
                        "quota_safe": True,
                        "attempt": attempt + 1
                    }
                except Exception as e:
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    raise
        except Exception as e:
            return {
                "model_name": model_name,
                "responsive": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
                "quota_safe": True
            }

    async def test_multiple_models(self, model_names: list) -> dict:
        results = {}
        for model_name in model_names:
            results[model_name] = await self.test_model_responsiveness(model_name)
        
        responsive_count = sum(1 for r in results.values() if r.get("responsive"))
        return {
            "summary": {
                "total_tested": len(model_names),
                "responsive": responsive_count,
                "failed": len(model_names) - responsive_count,
                "timestamp": datetime.now().isoformat(),
                "quota_consumed": 0
            },
            "models": results
        }
