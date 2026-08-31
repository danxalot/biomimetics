import os
import requests
import logging
import json

logger = logging.getLogger(__name__)

class GatewayClient:
    def __init__(self, model_name=None):
        self.gateway_url = os.environ.get("LLM_GATEWAY_URL", "http://llm_gateway:8080")
        if self.gateway_url.endswith("/v1/chat/completions"):
            self.gateway_url = self.gateway_url.replace("/v1/chat/completions", "")
            
        # Default to Gemma 3 27b for high quality synthesis, or fallback to environment default
        self.model_name = model_name or os.environ.get("ARCA_LEARN_MODEL", "gemma-3-27b-it")

    def invoke(self, prompt, system_prompt="You are ARCA, an advanced architectural AI."):
        """
        Sends a prompt to the LLM Gateway and returns the text response.
        Compatible with the .invoke() interface expected by Architect.
        """
        try:
            logger.info(f"GatewayClient invoking model {self.model_name}...")
            resp = requests.post(
                f"{self.gateway_url}/v1/chat/completions",
                json={
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 8192, # Large context for architecture synthesis
                    "temperature": 0.3
                },
                timeout=300.0  # Increase to 5 minutes for large documents
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            logger.info(f"GatewayClient received response ({len(content)} chars)")
            return content
        except requests.exceptions.Timeout as e:
            logger.error(f"GatewayClient Timeout after 300s: {e}")
            raise Exception(f"LLM Gateway timeout - document too large or model overloaded")
        except requests.exceptions.HTTPError as e:
            logger.error(f"GatewayClient HTTP Error: {e.response.status_code} - {e.response.text[:200]}")
            raise Exception(f"LLM Gateway HTTP error: {e.response.status_code}")
        except Exception as e:
            import traceback
            logger.error(f"GatewayClient Invoke Failed: {e}\nTraceback:\n{traceback.format_exc()}")
            raise e
