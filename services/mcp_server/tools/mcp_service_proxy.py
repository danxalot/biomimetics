import json
import logging
import aiohttp
from typing import Dict, Any, List
from mcp.types import Tool

logger = logging.getLogger("arca-service-proxy")

PROXY_TOOLS = [
    {
        "name": "gateway_request",
        "description": "Proxy LLM requests directly to the local llm_gateway",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The specific API route to call on the gateway (e.g., '/v1/chat/completions')"
                },
                "method": {
                    "type": "string",
                    "description": "HTTP method (e.g., 'POST')"
                },
                "body": {
                    "type": "object",
                    "description": "The JSON payload to send to the gateway"
                },
                "headers": {
                    "type": "object",
                    "description": "Optional HTTP headers to include in the request",
                    "additionalProperties": {"type": "string"}
                }
            },
            "required": ["path", "body"]
        }
    },
    {
        "name": "service_request",
        "description": "Proxy generic requests to other mesh services",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "payload": {"type": "object"}
            },
            "required": ["service", "payload"]
        }
    },
    {
        "name": "redis_command",
        "description": "Execute a Redis command",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "args": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["command"]
        }
    },
    {
        "name": "embedding_request",
        "description": "Proxy embedding generation requests",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"}
            },
            "required": ["text"]
        }
    }
]

class ServiceProxy:
    """Proxies requests to other services on the ARCA mesh network"""
    
    def __init__(self):
        self.gateway_url = "http://llm_gateway:8080"
        
    async def gateway_request(self, path: str, body: Dict[str, Any], method: str = "POST", headers: Dict[str, str] = None) -> str:
        """Proxy request to llm_gateway"""
        url = f"{self.gateway_url}/{path.lstrip('/')}"
        logger.info(f"Proxying gateway_request {method} to {url} with custom headers: {bool(headers)}")
        
        request_headers = headers or {}
        # Ensure the security header is present to satisfy LLM_Gateway strict mode
        if "X-Genesis-Chain" not in request_headers:
            request_headers["X-Genesis-Chain"] = "geometry_kernel:proxy"
        
        try:
            async with aiohttp.ClientSession() as session:
                if method.upper() == "POST":
                    async with session.post(url, json=body, headers=request_headers, timeout=aiohttp.ClientTimeout(total=120)) as response:
                        if response.status == 200:
                            data = await response.json()
                            return json.dumps(data)
                        else:
                            error_text = await response.text()
                            logger.error(f"Gateway request failed: {response.status} - {error_text}")
                            return json.dumps({"error": f"Gateway request failed: {response.status}", "details": error_text})
                else:
                    return json.dumps({"error": f"Method {method} not implemented"})
        except Exception as e:
            logger.error(f"Error connecting to gateway: {e}")
            return json.dumps({"error": f"Connection error: {str(e)}"})
            
    async def service_request(self, service: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Placeholder for generic service proxying"""
        logger.warning(f"service_request placeholder called for {service}")
        return {"error": "Not implemented"}
        
    async def redis_command(self, command: str, args: List[str] = None) -> Dict[str, Any]:
        """Placeholder for redis proxying"""
        logger.warning(f"redis_command placeholder called for {command}")
        return {"error": "Not implemented"}
        
    async def embedding_request(self, text: str) -> Dict[str, Any]:
        """Placeholder for embedding proxying"""
        logger.warning("embedding_request placeholder called")
        return {"error": "Not implemented"}

service_proxy = ServiceProxy()
