import os
import json
import httpx
import logging
from typing import Dict, Any, List, Optional
import sys
import traceback

# Configure logging
# Configure logging
logger = logging.getLogger(__name__)

from mcp.server.fastmcp import FastMCP
mcp = FastMCP("system_analysis")

class SystemAnalysisTool:
    """
    MCP Tool for Observer Agent to perform system analysis.
    Implements:
    1. Log Review (Loki/Logs)
    2. Resource Review (Resource Monitor)
    3. State Review (Redis)
    4. Synthesis (LLM)
    """
    def __init__(self):
        self.resource_monitor_url = os.getenv("RESOURCE_MONITOR_URL", "http://resource_monitor:9090")
        self.redis_host = os.getenv("REDIS_HOST", "redis")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.loki_url = os.getenv("LOKI_URL", "http://loki:3100")
        self.llm_gateway_url = os.getenv("LLM_GATEWAY_URL", "http://llm_gateway:8080/v1/chat/completions")
        self.model_name = os.getenv("OBSERVER_MODEL", "gemma-3-4b-it") # Fast cloud model

    async def analyze(self, query: str, depth: str = "summary", headers: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Performs system analysis based on query and depth.
        """
        # 1. Gather Context
        resources = await self._get_resources()
        logs = await self._get_recent_logs(query)
        # state = self._get_redis_state() # Reduced scope for now
        
        # 2. Synthesize
        analysis = await self._synthesize(query, depth, resources, logs, headers=headers)
        
        return analysis

    async def _get_resources(self) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{self.resource_monitor_url}/health") # Or /metrics if available
                return resp.json() if resp.status_code == 200 else {"error": "Resource Monitor unreachable"}
        except Exception as e:
            logger.error(f"Error checking resources: {traceback.format_exc()}")
            return {"error": str(e)}

    async def _get_recent_logs(self, query: str) -> str:
        """
        Fetches raw logs from key system containers.
        """
        containers = ["agent_service", "llm_gateway", "maintainer_agents", "mcp_server"]
        log_bundle = []
        
        import subprocess
        for container in containers:
            try:
                # Fetch last 100 lines for context
                cmd = ["docker", "logs", "--tail", "100", container]
                result = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
                log_bundle.append(f"--- LOGS: {container} ---\n{result}\n")
            except Exception as e:
                log_bundle.append(f"--- LOGS: {container} ---\nError fetching logs: {e}\n")
                
        return "\n".join(log_bundle)


    async def _synthesize(self, query: str, depth: str, resources: Dict, logs: str, headers: Optional[Dict] = None) -> Dict[str, Any]:
        prompt = f"""
        You are the Observer Agent (System Analyst).
        Query: {query}
        Depth: {depth}
        
        System State:
        - Resources: {resources}
        - Logs: {logs}
        
        Analyze the situation and provide a status report.
        If depth is 'root_cause', provide specific hypothesis.
        """
        
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        # Genesis Chain Signing
        import hmac
        import hashlib
        api_key = os.getenv("GENESIS_CHAIN_API_KEY")
        
        final_headers = {"Content-Type": "application/json"}
        if headers:
            # Propagate incoming Genesis headers
            genesis = {k: v for k, v in headers.items() if k.lower().startswith("x-genesis-")}
            final_headers.update(genesis)
        
        # Ensure consistent serialization for signing
        body_str = json.dumps(payload, sort_keys=True)
        
        if api_key:
            signature = hmac.new(
                api_key.encode("utf-8"),
                body_str.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()
            
            final_headers.update({
                "X-Genesis-Chain": "true",
                "X-Genesis-Agent": "mcp_observer",
                "X-Genesis-Signature": signature
            })
        
        try:
            # Increased timeout to 300s for slow CPU inference
            async with httpx.AsyncClient(timeout=300.0) as client:
                if api_key:
                    # Use pre-serialized body matching signature
                    response = await client.post(self.llm_gateway_url, data=body_str, headers=final_headers)
                else:
                    response = await client.post(self.llm_gateway_url, json=payload, headers=final_headers)
                    
                if response.status_code == 200:
                    return {"status": "success", "analysis": response.json()['choices'][0]['message']['content']}
                logger.error(f"LLM Synthesis failed: {response.status_code} - {response.text}")
                return {"status": "error", "message": f"Analysis failed: Code {response.status_code}, Body: {response.text}"}
        except Exception as e:
            logger.error(f"Synthesis exception: {traceback.format_exc()}")
            return {"status": "error", "message": f"Analysis failed: {e}"}

@mcp.tool()
def system_analysis(query: str, depth: str = "summary") -> Dict[str, Any]:
    """
    Perform a system analysis scan.
    Args:
        query: Specific area of concern (e.g., "Why is inference slow?")
        depth: Level of inspection ("summary", "detailed", "root_cause")
    """
    import asyncio
    tool = SystemAnalysisTool()
    return asyncio.run(tool.analyze(query, depth))
