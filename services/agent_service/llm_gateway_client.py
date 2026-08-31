"""
LLM Gateway Client for agent_service

Routes all LLM calls through the centralized llm_gateway service.
Ensures:
- Single point of authentication
- Centralized rate limiting and cost tracking
- Ability to switch models globally
- Graceful fallback support
"""

import os
import asyncio
import logging
import json
from typing import Dict, List, Any, Optional
from datetime import datetime

import httpx
import hmac
import hashlib
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class LLMGatewayClient:
    """
    Async client for calling LLMs through the central gateway.
    
    Gateway handles:
    - API key management (GOOGLE_API_KEY from environment)
    - Model routing (supports gemini, claude, gpt, etc)
    - Rate limiting per model
    - Cost tracking
    - Fallback to alternate models
    """
    
    def __init__(
        self,
        gateway_url: Optional[str] = None,
        model: str = "gemini-2.5-flash",
        timeout: float = 60.0,
        max_retries: int = 3
    ):
        """
        Initialize LLM Gateway client.
        
        Args:
            gateway_url: URL of llm_gateway service (default from env or http://llm_gateway:8080)
            model: Default model to use
            timeout: Request timeout in seconds
            max_retries: Number of retry attempts for failed requests
        """
        self.gateway_url = gateway_url or os.getenv("LLM_GATEWAY_URL", "http://llm_gateway:8080")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.client = None # Deprecated: Do not hold persistent client across loops
        
        self.genesis_api_key = os.getenv("GENESIS_CHAIN_API_KEY")
        if not self.genesis_api_key:
            logger.warning("GENESIS_CHAIN_API_KEY not set - Request signing disabled")

        logger.info(f"LLMGatewayClient initialized with gateway: {self.gateway_url}, model: {model}")

    def _create_genesis_headers(self, payload: Dict[str, Any]) -> Dict[str, str]:
        """Create headers for Genesis Chain authentication"""
        if not self.genesis_api_key:
            return {}

        try:
            # Create HMAC signature of request body
            message = json.dumps(payload, sort_keys=True)
            signature = hmac.new(
                self.genesis_api_key.encode(),
                message.encode(),
                hashlib.sha256
            ).hexdigest()

            return {
                "X-Genesis-Chain": "true",
                "X-Genesis-Signature": signature,
                "X-Genesis-Agent": "agent_service",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Failed to sign request: {e}")
            return {}
    
    async def health_check(self) -> bool:
        """Check if gateway is healthy and accessible"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.gateway_url}/health")
                response.raise_for_status()
            logger.info("✅ LLM Gateway health check passed")
            return True
        except Exception as e:
            logger.error(f"❌ LLM Gateway health check failed: {e}")
            return False
    
    async def call_llm(
        self,
        messages: List[BaseMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        system_instruction: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Call LLM through gateway.
        """
        model = model or self.model
        
        # Convert LangChain messages to gateway format
        formatted_messages = self._format_messages(messages, system_instruction)
        
        payload = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs
        }
        
        # Retry logic with exponential backoff
        last_error = None
        for attempt in range(self.max_retries):
            try:
                # Generate genesis headers
                genesis_headers = self._create_genesis_headers(payload)
                
                # Create a fresh client for each request to avoid Event Loop issues in threaded consumers
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    logger.info(f"Calling LLM gateway (attempt {attempt + 1}/{self.max_retries})")
                    
                    response = await client.post(
                        f"{self.gateway_url}/v1/chat/completions",
                        json=payload,
                        headers=genesis_headers, # Include signed headers
                        timeout=self.timeout
                    )
                    
                    response.raise_for_status()
                    result = response.json()
                    
                    # Extract response content
                    if "choices" in result and len(result["choices"]) > 0:
                        content = result["choices"][0].get("message", {}).get("content", "")
                        if content:
                            logger.info(f"✅ LLM response received ({len(content)} chars)")
                            return content
                    
                    raise ValueError(f"Unexpected response format: {result}")
                
            except httpx.TimeoutException as e:
                last_error = e
                wait_time = 2 ** attempt
                logger.warning(f"⏱️  Timeout on attempt {attempt + 1}, waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:  # Rate limited
                    wait_time = (2 ** attempt) * 10  # Longer backoff for rate limits
                    logger.warning(f"🚫 Rate limited (429), waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    last_error = e
                else:
                    logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
                    raise
                    
            except Exception as e:
                logger.error(f"Error calling LLM gateway: {e}")
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
        
        # All retries exhausted
        raise Exception(f"Failed to get LLM response after {self.max_retries} attempts: {last_error}")
    
    async def ainvoke(
        self,
        messages: List[BaseMessage],
        model: Optional[str] = None,
        **kwargs
    ) -> AIMessage:
        """
        Async invoke - compatible with LangChain LLM interface.
        
        Returns:
            AIMessage with response content
        """
        content = await self.call_llm(messages, model=model, **kwargs)
        return AIMessage(content=content)
    
    def invoke(
        self,
        messages: List[BaseMessage],
        model: Optional[str] = None,
        **kwargs
    ) -> AIMessage:
        """
        Synchronous invoke - compatible with LangChain LLM interface.
        
        Returns:
            AIMessage with response content
        """
        # Use asyncio.run for sync context
        content = asyncio.run(self.call_llm(messages, model=model, **kwargs))
        return AIMessage(content=content)
    
    def _format_messages(
        self,
        messages: List[BaseMessage],
        system_instruction: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Convert LangChain messages to gateway format"""
        formatted = []
        
        # Add system instruction if provided
        if system_instruction:
            formatted.append({
                "role": "system",
                "content": system_instruction
            })
        
        # Convert all message types
        for msg in messages:
            if isinstance(msg, SystemMessage):
                formatted.append({
                    "role": "system",
                    "content": msg.content
                })
            elif isinstance(msg, HumanMessage):
                formatted.append({
                    "role": "user",
                    "content": msg.content
                })
            elif isinstance(msg, AIMessage):
                formatted.append({
                    "role": "assistant",
                    "content": msg.content
                })
            else:
                # Generic message type
                formatted.append({
                    "role": getattr(msg, "role", "user"),
                    "content": msg.content
                })
        
        return formatted
    
    async def close(self):
        """Close the HTTP client (No-op now that clients are transient)"""
        pass


# Convenience function for getting configured gateway client
def get_llm_gateway_client(model: str = "gemini-2.0-flash") -> LLMGatewayClient:
    """Get configured LLM gateway client"""
    gateway_url = os.getenv("LLM_GATEWAY_URL", "http://llm_gateway:8080")
    return LLMGatewayClient(gateway_url=gateway_url, model=model)
