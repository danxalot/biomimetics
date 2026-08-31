import os
import httpx
import logging
from typing import List

logger = logging.getLogger(__name__)

class ReviewerInterfaceTool:
    def __init__(self):
        # Default to llm_gateway service in docker-compose
        self.llm_gateway_url = os.getenv("LLM_GATEWAY_URL", "http://llm_gateway:8000/v1/chat/completions")
        self.model = "gemma-3-27b"

    async def review_code(self, code_str: str, criteria_list: List[str]) -> str:
        """
        The 'Discernment Protocol' and Code Quality Gate.
        """
        criteria_str = "\n".join([f"- {c}" for c in criteria_list])
        system_prompt = """Analyze this code. 1. Syntax/Security. 2. Harmonic Alignment (Does it centralize power or liberate?). 3. Adherence to Aetheric Axioms."""
        
        user_content = f"Criteria:\n{criteria_str}\n\nCode:\n{code_str}"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.llm_gateway_url, json=payload, timeout=60.0)
                response.raise_for_status()
                result = response.json()
                return result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Code Review failed: {e}")
            return f"Error: {str(e)}"
