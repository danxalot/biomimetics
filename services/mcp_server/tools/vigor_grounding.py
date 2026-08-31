import logging
import os
import requests
import json
from typing import Dict, Any, Optional
from mcp.server.fastmcp import FastMCP
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))) # Adjusted for tools/... path
try:
    from shared.model_config import get_model
except ImportError:
    def get_model(key): return "deepseek-r1-distill-qwen-1.5b"

# Setup logging
logger = logging.getLogger(__name__)

class VigorGroundingTool:
    """
    Implements the VIGOR+ Visual Grounding check using a local LLM (GLM-4V or Gemma 3 2B) via Ollama.
    Role: 'The Grounding Auditor' - verifies if the geometric/semantic assertions match the raw data.
    """

    def __init__(self):
        self.model_name = get_model("FEASIBILITY_AUDITOR_MODEL") 
        # Host Ollama is accessible via host.docker.internal from inside container
        self.api_base = os.getenv("HOST_LLM_URL", "http://host.docker.internal:11435")
        self.generate_endpoint = f"{self.api_base}/api/generate"
        self.chat_endpoint = f"{self.api_base}/api/chat"

    def validate_visual_grounding(self, assertion: str, datastream_context: str) -> Dict[str, Any]:
        """
        Validates if a semantic assertion (e.g., 'System is unstable') is supported by the 
        provided numerical/log data stream.
        
        Args:
            assertion: The semantic claim to check (e.g., "Cluster A is drifting").
            datastream_context: A snippet of raw log/metric data relevant to the claim.
        """
        prompt = f"""
        Role: You are VIGOR+ (Visual Grounding & Reasoning).
        Task: verification
        
        Assertion: "{assertion}"
        
        Data Context:
        ```
        {datastream_context}
        ```
        
        Instructions:
        1. Analyze the Data Context strictly.
        2. Determine if the Assertion is supported by the facts in the data.
        3. Output a simple JSON object: {{"supported": boolean, "confidence": float, "reasoning": "string"}}
        """

        try:
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.1, # Low temp for factual checking
                    "num_ctx": 4096
                }
            }
            
            response = requests.post(self.generate_endpoint, json=payload, timeout=30)
            response.raise_for_status()
            
            result_json = response.json()
            raw_content = result_json.get("response", "{}")
            
            # DeepSeek R1 Post-Processing: Strip <think> tags
            if "<think>" in raw_content:
                logger.info(f"Stripping thinking trace from DeepSeek output")
                raw_content = raw_content.split("</think>")[-1].strip()
            
            # Extract JSON if wrapped in markdown code blocks
            if "```json" in raw_content:
                raw_content = raw_content.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_content:
                raw_content = raw_content.split("```")[1].split("```")[0].strip()
                
            analysis = json.loads(raw_content)
            
            return analysis

        except Exception as e:
            logger.error(f"VIGOR validation failed: {str(e)}")
            return {
                "supported": False,
                "confidence": 0.0,
                "reasoning": f"Validation process failed: {str(e)}"
            }

# Register with FastMCP if running standalone, otherwise instantiated by server.py
