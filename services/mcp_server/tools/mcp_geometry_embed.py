
import os
import requests
import json
import logging
from typing import List, Dict, Any, Union
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP
mcp = FastMCP("mcp-geometry-embed")
logger = logging.getLogger(__name__)

class GeometryEmbedTool:
    def __init__(self):
        # Point to the formalized OCI Llama Hub - VL (High Fidelity)
        self.base_url = os.getenv("LLAMA_HUB_VL_URL", "http://llama-hub-vl:8082")
        self.embed_endpoint = f"{self.base_url}/v1/embeddings"
        self.model_name = "qwen3-vl-embedding-2b-q8_0.gguf"
        logger.info(f"GeometryEmbedTool initialized with OCI 2B High-Fidelity model: {self.model_name} at {self.base_url}")

    def embed_geometry_description(self, text: str) -> List[float]:
        """
        Generate an embedding vector for a geometry description using Qwen 3 VL (2B).
        Uses the formalized OCI Llama Hub.
        
        Args:
            text: The text description of the geometry to embed.
            
        Returns:
            A list of floats representing the embedding vector.
        """
        try:
            payload = {
                "model": self.model_name,
                "input": text
            }
            
            response = requests.post(self.embed_endpoint, json=payload, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            embedding = result.get("embedding")
            
            if not embedding:
                raise ValueError("No embedding returned in response")
                
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise

# Create tool instance
_tool_instance = GeometryEmbedTool()

@mcp.tool()
def embed_geometry_description(text: str) -> str:
    """
    Generate an embedding vector for a geometry description using Qwen 3 VL (2B).
    Returns the embedding as a JSON string.
    """
    try:
        if not text:
            return json.dumps({"error": "Text cannot be empty"})
            
        embedding = _tool_instance.embed_geometry_description(text)
        return json.dumps({"embedding": embedding, "dimensions": len(embedding)})
    except Exception as e:
        return json.dumps({"error": str(e)})
