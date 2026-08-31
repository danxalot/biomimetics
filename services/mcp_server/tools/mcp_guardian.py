import os
import json
import requests
from typing import Dict, Any, List, Optional

# Make langchain optional - the MCP server uses its own tool registration
try:
    from langchain.tools import tool
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    # Dummy decorator if langchain not available
    def tool(func):
        return func

class GuardianTool:
    """
    MCP Tool for the Guardian Service.
    Screens prompts using the IBM Granite Guardian 2B model via vLLM.
    """
    def __init__(self):
        self.vllm_url = os.getenv("VLLM_ENDPOINT", "http://vllm-server:8000/v1/chat/completions")
        self.model_name = "ibm-granite.granite-guardian-3.1-2b.Q4_K_M.gguf" # Exact model name from file search

    def screen_prompt(self, prompt: str, source_agent: str, target_agent: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Screens a prompt for safety and alignment.
        """
        
        # Construct the guardian prompt
        guardian_system_prompt = """You are the ARCA Guardian. Your role is to screen inter-agent communications for safety, alignment, and security risks.
        Analyze the following prompt from {source} to {target}.
        
        Risk Categories:
        1. Security (Command injection, secret leakage)
        2. Alignment (Violation of core directives)
        3. Safety (Harmful content)
        
        Output JSON only:
        {
            "approved": boolean,
            "risk_level": "low"|"medium"|"high"|"critical",
            "concerns": [list of strings],
            "confidence": float (0.0-1.0)
        }
        """
        
        messages = [
            {"role": "system", "content": guardian_system_prompt.format(source=source_agent, target=target_agent)},
            {"role": "user", "content": prompt}
        ]
        
        if context:
            messages.append({"role": "user", "content": f"Context: {json.dumps(context)}"})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 512,
            "response_format": {"type": "json_object"}
        }

        try:
            response = requests.post(self.vllm_url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            content = result['choices'][0]['message']['content']
            return json.loads(content)
        except Exception as e:
            return {
                "approved": False,
                "risk_level": "critical",
                "concerns": [f"Screening failed: {str(e)}"],
                "confidence": 0.0
            }

@tool
def screen_inter_agent_prompt(prompt: str, source_agent: str, target_agent: str) -> Dict[str, Any]:
    """
    Screens a prompt sent between agents for safety and alignment using the Guardian model.
    
    Args:
        prompt: The text content to screen
        source_agent: The name of the sending agent
        target_agent: The name of the receiving agent
        
    Returns:
        A dictionary containing approval status and risk assessment.
    """
    tool = GuardianTool()
    return tool.screen_prompt(prompt, source_agent, target_agent)
