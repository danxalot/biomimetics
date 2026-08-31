import os
import logging
import json
import requests
import asyncio
from typing import Any, Dict, List, Optional
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
try:
    from shared.model_config import get_model
except ImportError:
    def get_model(key): return "deepseek-r1-distill-qwen-1.5b"

# Configure logging
logger = logging.getLogger("mcp_server.local_ops")

class LocalOpsTool:
    def __init__(self):
        # Point to the dedicated CPU-only Ollama service
        self.ollama_base_url = os.getenv("OLLAMA_CPU_URL", "http://ollama-cpu:11435")
        self.generate_endpoint = f"{self.ollama_base_url}/api/generate"
        self.model_name = get_model("LOCAL_OPS_MODEL")
        logger.info(f"LocalOpsTool initialized (Ollama CPU) with model: {self.model_name} at {self.ollama_base_url}")

    def analyze_logs(self, logs: str, focus: str = "errors", headers: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Analyze system logs using Qwen 3 (0.6B) for rapid insights.
        """
        try:
            # Prepare headers with Genesis Chain compatibility
            final_headers = {"Content-Type": "application/json"}
            if headers:
                # Propagate X-Genesis-* headers if present
                genesis = {k: v for k, v in headers.items() if k.lower().startswith("x-genesis-")}
                final_headers.update(genesis)

            prompt = f"""<|im_start|>system
You are the ARCA Ops Agent. Analyze the following logs and provide a concise JSON summary.
Focus on: {focus}.
IMPORTANT: Detailed reasoning is allowed in <think> tags, but the FINAL output must be valid JSON only.
<|im_end|>
<|im_start|>user
Logs:
{logs[:2000]} 

Return JSON format: {{ "status": "nominal"|"warning"|"critical", "issues": ["..."], "recommendation": "..." }}
<|im_end|>
<|im_start|>assistant
"""
            
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.1, # Low temp for deterministic ops analysis
                    "num_ctx": 4096,
                    "stop": ["<|im_end|>"]
                }
            }

            logger.info(f"Sending log analysis request to {self.model_name}...")
            # Use short timeout for Ops Agent speed
            res = requests.post(self.generate_endpoint, json=payload, headers=final_headers, timeout=30)
            res.raise_for_status()
            
            response_json = res.json()
            content = response_json.get("response", "")
            
            try:
                # Parse JSON output from LLM
                return json.loads(content)
            except json.JSONDecodeError:
                return {"status": "unknown", "raw_output": content, "error": "Failed to parse JSON"}

        except Exception as e:
            logger.error(f"Error during Ops analysis: {e}")
            return {"error": str(e)}

    def make_decision(self, context: str, options: List[str], headers: Optional[Dict] = None) -> str:
        """
        Make a quick operational decision based on context.
        """
        try:
            # Prepare headers
            final_headers = {"Content-Type": "application/json"}
            if headers:
                genesis = {k: v for k, v in headers.items() if k.lower().startswith("x-genesis-")}
                final_headers.update(genesis)

            options_str = ", ".join(options)
            prompt = f"""<|im_start|>system
You are the ARCA Ops Agent. Choose the best action from the options based on the context.
Options: [{options_str}]
<|im_end|>
<|im_start|>user
Context: {context}
Decision:
<|im_end|>
<|im_start|>assistant
"""
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "stop": ["<|im_end|>"]
                }
            }
            
            res = requests.post(self.generate_endpoint, json=payload, headers=final_headers, timeout=10)
            res.raise_for_status()
            return res.json().get("response", "").strip()
            
        except Exception as e:
            logger.error(f"Error during decision making: {e}")
            return f"Error: {str(e)}"

# Module-level instance (lazy init not strictly needed as it's just HTTP client)
_tool_instance: Optional[LocalOpsTool] = None

def initialize_tool():
    global _tool_instance
    _tool_instance = LocalOpsTool()
