import base64
import json
import logging
import os
from typing import Any, Dict, List, Optional

import requests
from mcp.server.fastmcp import FastMCP

# Configure logging
logger = logging.getLogger("mcp_server.local_vision")

# Import central model config
import sys

sys.path.insert(0, "/shared")
sys.path.insert(0, "/app/shared")
try:
    from shared.model_config import vision_model
except ImportError as e:
    logger.warning(f"Could not import vision_model from shared.model_config: {e}")

    def vision_model():
        return "glm:latest"


class LocalVisionTool:
    def __init__(self):
        # Always use the Gateway for local vision routing
        self.gateway_url = os.getenv("LLM_GATEWAY_URL", "http://llm_gateway:8080/v1")
        self.model_name = "qwen3-vl-2b"
        logger.info(
            f"LocalVisionTool initialized (Gateway API) with model: {self.model_name}"
        )

    def analyze_image(
        self, prompt: str, image_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyzes an image or generates text using the local GLM-4v model via Ollama.
        """
        try:
            # Construct message with image if provided
            messages = []

            # System prompt for identity
            messages.append(
                {
                    "role": "system",
                    "content": "You are a helpful visual AI assistant for system diagnosis and geometry analysis.",
                }
            )

            user_msg = {"role": "user", "content": prompt}

            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, "rb") as img_file:
                        b64_data = base64.b64encode(img_file.read()).decode("utf-8")
                        # Convert to OpenAI vision format
                        user_msg["content"] = [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64_data}"
                                },
                            },
                        ]
                except Exception as e:
                    logger.error(f"Failed to read image {image_path}: {e}")
                    return {"error": f"Failed to read image: {e}"}

            messages.append(user_msg)

            payload = {
                "model": self.model_name,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 1000,
            }

            logger.info(f"Sending vision request to Gateway ({self.model_name})...")
            res = requests.post(
                f"{self.gateway_url}/chat/completions", json=payload, timeout=120
            )
            res.raise_for_status()

            response_json = res.json()
            # Handle both LiteLLM object-style and dict-style responses
            choices = response_json.get("choices", [{}])
            if choices and isinstance(choices[0], dict):
                content = choices[0].get("message", {}).get("content", "")
            else:
                content = (
                    getattr(choices[0], "message", {}).get("content", "")
                    if choices
                    else ""
                )

            return {"response": content, "usage": response_json.get("usage", {})}

        except Exception as e:
            logger.error(f"Error during Gateway vision inference: {e}")
            return {"error": str(e)}


# Module-level instance
_tool_instance: Optional[LocalVisionTool] = None


def initialize_tool(model_dir: str = None):
    # model_dir is ignored as we use Ollama API
    global _tool_instance
    _tool_instance = LocalVisionTool()


def query_local_vision_model(prompt: str) -> str:
    """
    Query the local Vision model (GLM-4 via Ollama).
    Use this for fast, private, or offline queries.
    """
    if _tool_instance:
        result = _tool_instance.analyze_image(prompt)
        if "error" in result:
            return f"Error: {result['error']}"
        return result["response"]
    return "Local vision tool is not initialized."


def register_tools(mcp: FastMCP):
    """Registers the local vision tools with the FastMCP server."""
    mcp.tool()(query_local_vision_model)
