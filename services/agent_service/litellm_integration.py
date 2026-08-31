"""
LiteLLM Integration Layer for ARCA Multi-Agent System
Implements unified API gateway per architectural document Section 4.1

Benefits:
- Single consistent interface for all LLM providers
- Normalized request/response formats
- Centralized API key management
- Automated fallbacks and retries
- Model agility (swap models via config)
"""

import os
import logging
from typing import List, Dict, Any, Optional, Literal
from openai import OpenAI, AsyncOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Normalized response format across all providers"""
    content: str
    tool_calls: List[Dict[str, Any]]
    thinking: str  # For models that support thinking blocks
    stop_reason: str
    usage: Dict[str, int]
    model: str
    raw_response: Any


class LiteLLMGateway:
    """
    Unified LLM gateway using LiteLLM.
    
    Provides abstraction over multiple providers:
    - Gemini (via LiteLLM gateway)
    - Grok (via LiteLLM gateway)
    - MiniMax (via custom wrapper - special auth requirements)
    - Local models (via LiteLLM gateway)
    
    Architecture principle: Decouple agent logic from model implementation.
    Agents call llm.completion(model="engineer_model") - the gateway handles
    provider-specific details.
    """
    
    def __init__(
        self,
        gateway_url: str = "http://llm_gateway:4000",
        master_key: Optional[str] = None,
        minimax_wrapper: Optional[Any] = None,
    ):
        """
        Initialize LiteLLM gateway client.
        
        Args:
            gateway_url: URL of LiteLLM gateway service
            master_key: Master API key for gateway authentication
            minimax_wrapper: Custom MiniMax wrapper for M2 model
        """
        self.gateway_url = gateway_url
        self.master_key = master_key or os.getenv("LITELLM_MASTER_KEY", "test-key")
        self.minimax_wrapper = minimax_wrapper
        
        # Initialize OpenAI client pointing to LiteLLM gateway
        self.client = OpenAI(
            base_url=gateway_url,
            api_key=self.master_key
        )
        
        self.async_client = AsyncOpenAI(
            base_url=gateway_url,
            api_key=self.master_key
        )
        
        logger.info(f"LiteLLM Gateway initialized: {gateway_url}")
    
    def _convert_to_openai_messages(self, messages: List[BaseMessage]) -> List[Dict[str, Any]]:
        """
        Convert LangChain messages to OpenAI format.
        
        LiteLLM expects OpenAI-compatible message format, so we normalize
        LangChain messages to that format.
        """
        openai_messages = []
        
        for msg in messages:
            if isinstance(msg, SystemMessage):
                openai_messages.append({
                    "role": "system",
                    "content": msg.content
                })
            elif isinstance(msg, HumanMessage):
                openai_messages.append({
                    "role": "user",
                    "content": msg.content
                })
            elif isinstance(msg, AIMessage):
                message = {"role": "assistant", "content": msg.content}
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    message["tool_calls"] = msg.tool_calls
                openai_messages.append(message)
            elif isinstance(msg, ToolMessage):
                openai_messages.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": msg.tool_call_id
                })
        
        return openai_messages
    
    def completion(
        self,
        model: str,
        messages: List[BaseMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Synchronous completion call via LiteLLM gateway.
        
        Args:
            model: Logical model name (e.g., "supervisor_model", "engineer_model")
            messages: LangChain message history
            tools: Optional tool definitions (OpenAI format)
            temperature: Sampling temperature
            max_tokens: Maximum tokens in response
            **kwargs: Additional provider-specific parameters
        
        Returns:
            Normalized LLMResponse object
        """
        # Special handling for MiniMax M2 (uses custom wrapper)
        if model == "engineer_model" and self.minimax_wrapper:
            return self._minimax_completion(messages, tools, temperature, max_tokens, **kwargs)
        
        try:
            openai_messages = self._convert_to_openai_messages(messages)
            
            # Build request parameters
            request_params = {
                "model": model,
                "messages": openai_messages,
                "temperature": temperature,
            }
            
            if max_tokens:
                request_params["max_tokens"] = max_tokens
            
            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = "auto"
            
            # Add any additional kwargs
            request_params.update(kwargs)
            
            logger.debug(f"Calling LiteLLM gateway: model={model}, messages={len(openai_messages)}")
            
            # Make the call
            response = self.client.chat.completions.create(**request_params)
            
            # Extract response data
            choice = response.choices[0]
            message = choice.message
            
            content = message.content or ""
            tool_calls = []
            
            if hasattr(message, "tool_calls") and message.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "args": tc.function.arguments,
                    }
                    for tc in message.tool_calls
                ]
            
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            }
            
            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                thinking="",  # LiteLLM doesn't expose thinking blocks (model-specific)
                stop_reason=choice.finish_reason,
                usage=usage,
                model=response.model,
                raw_response=response
            )
        
        except Exception as e:
            logger.error(f"LiteLLM gateway error: {e}")
            raise
    
    def _minimax_completion(
        self,
        messages: List[BaseMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Handle MiniMax M2 completion via custom wrapper.
        Preserves thinking blocks and native tool calling.
        """
        if not self.minimax_wrapper:
            raise RuntimeError("MiniMax wrapper not configured")
        
        try:
            import asyncio
            
            # Convert to Anthropic format for MiniMax wrapper
            anthropic_messages = self._convert_to_anthropic_messages(messages)
            
            # Call MiniMax wrapper (async)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            response = loop.run_until_complete(
                self.minimax_wrapper.ainvoke(
                    messages=anthropic_messages,
                    tools=tools,
                    temperature=temperature,
                    max_tokens=max_tokens or 6144,
                    **kwargs
                )
            )
            
            loop.close()
            
            # Extract response data
            content = response.content or ""
            tool_calls = []
            
            # MiniMax preserves thinking blocks in content
            thinking = ""
            if "<thinking>" in content and "</thinking>" in content:
                # Extract thinking block (preserve for next call)
                start = content.find("<thinking>")
                end = content.find("</thinking>") + len("</thinking>")
                thinking = content[start:end]
            
            if hasattr(response, "tool_calls") and response.tool_calls:
                tool_calls = [
                    {
                        "id": tc.get("id", ""),
                        "name": tc.get("name", ""),
                        "args": tc.get("arguments", tc.get("args", "")),
                    }
                    for tc in response.tool_calls
                ]
            
            # Estimate usage (MiniMax doesn't provide detailed usage)
            usage = {
                "prompt_tokens": len(str(messages)) // 4,  # Rough estimate
                "completion_tokens": len(content) // 4,
                "total_tokens": (len(str(messages)) + len(content)) // 4,
            }
            
            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                thinking=thinking,  # Preserve thinking blocks
                stop_reason=response.stop_reason if hasattr(response, "stop_reason") else "stop",
                usage=usage,
                model="minimax-m2",
                raw_response=response
            )
        
        except Exception as e:
            logger.error(f"MiniMax completion error: {e}")
            raise
    
    def _convert_to_anthropic_messages(self, messages: List[BaseMessage]) -> List[Dict[str, Any]]:
        """
        Convert LangChain messages to Anthropic format for MiniMax M2.
        MiniMax uses Anthropic-compatible API.
        """
        anthropic_messages = []
        
        for msg in messages:
            if isinstance(msg, SystemMessage):
                # System messages are handled separately in Anthropic
                continue
            elif isinstance(msg, HumanMessage):
                anthropic_messages.append({
                    "role": "user",
                    "content": msg.content
                })
            elif isinstance(msg, AIMessage):
                content = msg.content
                message = {"role": "assistant", "content": content}
                
                # Add tool calls if present
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    # Anthropic format for tool calls
                    tool_uses = []
                    for tc in msg.tool_calls:
                        tool_uses.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc.get("args", tc.get("arguments", {}))
                        })
                    
                    # Combine text content with tool calls
                    content_parts = []
                    if content:
                        content_parts.append({"type": "text", "text": content})
                    content_parts.extend(tool_uses)
                    
                    message["content"] = content_parts
                
                anthropic_messages.append(message)
            elif isinstance(msg, ToolMessage):
                anthropic_messages.append({
                    "role": "user",  # Tool results come back as user messages
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_call_id": msg.tool_call_id,
                            "content": msg.content
                        }
                    ]
                })
        
        return anthropic_messages
    
    async def acompletion(
        self,
        model: str,
        messages: List[BaseMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Async completion call via LiteLLM gateway.
        Same interface as completion() but async.
        """
        # Special handling for MiniMax M2 (uses custom wrapper)
        if model == "engineer_model" and self.minimax_wrapper:
            return await self._aminimax_completion(messages, tools, temperature, max_tokens, **kwargs)
        
        try:
            openai_messages = self._convert_to_openai_messages(messages)
            
            request_params = {
                "model": model,
                "messages": openai_messages,
                "temperature": temperature,
            }
            
            if max_tokens:
                request_params["max_tokens"] = max_tokens
            
            if tools:
                request_params["tools"] = tools
                request_params["tool_choice"] = "auto"
            
            request_params.update(kwargs)
            
            logger.debug(f"Async calling LiteLLM gateway: model={model}")
            
            response = await self.async_client.chat.completions.create(**request_params)
            
            choice = response.choices[0]
            message = choice.message
            
            content = message.content or ""
            tool_calls = []
            
            if hasattr(message, "tool_calls") and message.tool_calls:
                tool_calls = [
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "args": tc.function.arguments,
                    }
                    for tc in message.tool_calls
                ]
            
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            }
            
            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                thinking="",
                stop_reason=choice.finish_reason,
                usage=usage,
                model=response.model,
                raw_response=response
            )
        
        except Exception as e:
            logger.error(f"Async LiteLLM gateway error: {e}")
            raise
    
    async def _aminimax_completion(
        self,
        messages: List[BaseMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Handle async MiniMax M2 completion via custom wrapper.
        Preserves thinking blocks and native tool calling.
        """
        if not self.minimax_wrapper:
            raise RuntimeError("MiniMax wrapper not configured")
        
        try:
            # Convert to Anthropic format for MiniMax wrapper
            anthropic_messages = self._convert_to_anthropic_messages(messages)
            
            # Call MiniMax wrapper (async)
            response = await self.minimax_wrapper.ainvoke(
                messages=anthropic_messages,
                tools=tools,
                temperature=temperature,
                max_tokens=max_tokens or 6144,
                **kwargs
            )
            
            # Extract response data (same as sync version)
            content = response.content or ""
            tool_calls = []
            
            # MiniMax preserves thinking blocks in content
            thinking = ""
            if "<thinking>" in content and "</thinking>" in content:
                # Extract thinking block (preserve for next call)
                start = content.find("<thinking>")
                end = content.find("</thinking>") + len("</thinking>")
                thinking = content[start:end]
            
            if hasattr(response, "tool_calls") and response.tool_calls:
                tool_calls = [
                    {
                        "id": tc.get("id", ""),
                        "name": tc.get("name", ""),
                        "args": tc.get("arguments", tc.get("args", "")),
                    }
                    for tc in response.tool_calls
                ]
            
            # Estimate usage (MiniMax doesn't provide detailed usage)
            usage = {
                "prompt_tokens": len(str(messages)) // 4,  # Rough estimate
                "completion_tokens": len(content) // 4,
                "total_tokens": (len(str(messages)) + len(content)) // 4,
            }
            
            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                thinking=thinking,  # Preserve thinking blocks
                stop_reason=response.stop_reason if hasattr(response, "stop_reason") else "stop",
                usage=usage,
                model="minimax-m2",
                raw_response=response
            )
        
        except Exception as e:
            logger.error(f"Async MiniMax completion error: {e}")
            raise


class ModelRouter:
    """
    Intelligent model routing based on task characteristics.
    Implements the model specialization strategy from Section 4.2.
    
    Routes tasks to optimal models:
    - MiniMax M2: Code generation, multi-file edits, testing
    - Grok Code Fast: System design, planning, fast reasoning
    - Gemini: Orchestration, review, general purpose
    - Granite 3B: Batch processing, overnight jobs
    """
    
    # Model capabilities from architectural document
    MODEL_SPECS = {
        "supervisor_model": {
            "provider": "gemini",
            "strengths": ["orchestration", "task_decomposition", "general"],
            "max_tokens": 8192,
            "cost_per_1k": 0.00,  # Free tier
            "daily_limit": 250,
            "rpm_limit": 10,
        },
        "architect_model": {
            "provider": "gemini",
            "strengths": ["planning", "design", "architecture", "deep_reasoning", "large_context"],
            "max_tokens": 8192,
            "cost_per_1k": 0.00,  # Free tier
            "daily_limit": 200,
            "rpm_limit": 15,
            "context_window": 1000000,  # 1M tokens!
        },
        "fast_coder_model": {
            "provider": "github_models",  # Grok Code Fast via GitHub
            "strengths": ["fast_iteration", "coding", "testing", "debugging"],
            "max_tokens": 4096,
            "cost_per_1k": 0.00,  # Free tier (800 requests/month)
            "daily_limit": None,  # Monthly quota
            "monthly_limit": 800,
        },
        "engineer_model": {
            "provider": "minimax",  # Note: Uses custom wrapper, not LiteLLM
            "strengths": ["code_gen", "multi_file", "testing", "debugging"],
            "max_tokens": 6144,  # Optimized to avoid timeouts
            "cost_per_1k": 0.015,  # Estimated
        },
        "reviewer_model": {
            "provider": "gemini",
            "strengths": ["review", "quality", "bug_detection", "advanced_reasoning"],
            "max_tokens": 8192,
            "cost_per_1k": 0.00,  # Free tier
            "daily_limit": 100,
            "rpm_limit": 5,
        },
        "worker_model": {
            "provider": "local",
            "strengths": ["batch", "summarize", "topic_model"],
            "max_tokens": 2048,
            "cost_per_1k": 0.00,  # Self-hosted
        },
        "embeddings_model": {
            "provider": "gemini",
            "strengths": ["vectorization", "semantic_search", "rag"],
            "cost_per_1k": 0.00,  # Free tier
            "daily_limit": 1000,
            "rpm_limit": 100,
            "output_dimensions": 768,
        }
    }
    
    @classmethod
    def route_task(cls, task_type: str, complexity: Literal["low", "medium", "high"] = "medium") -> str:
        """
        Select optimal model for task.
        
        Args:
            task_type: Type of task
            complexity: Task complexity level
        
        Returns:
            Model name (e.g., "engineer_model")
        """
        # Task type to model mapping per architectural doc
        routing_map = {
            "code_generation": "gemini-2.5-flash",  # Engineer (Tier 1) - 1500 RPD
            "multi_file_edit": "gemini-2.5-flash",
            "debugging": "gemini-2.5-flash",
            "testing": "gemini-2.5-flash",
            "compile_fix": "gemini-2.5-flash",
            
            "fast_iteration": "gemini-2.5-flash",
            "quick_coding": "gemini-2.5-flash",
            "rapid_prototyping": "gemini-2.5-flash",
            "iterative_dev": "gemini-2.5-flash",
            
            "system_design": "gemini-3-pro",  # Architect (Tier 3) - 50 RPD
            "architecture": "gemini-3-pro",
            "planning": "gemini-3-pro",
            "risk_analysis": "gemini-3-pro",
            
            "orchestration": "gemini-2.5-flash-lite",  # Supervisor (Tier 2) - 1500 RPD
            "task_decomposition": "gemini-2.5-flash-lite",
            "user_interaction": "gemini-2.5-flash-lite",
            
            "code_review": "local-llm",  # Reviewer - Local Model (Granite 3B)
            "quality_check": "local-llm",
            "bug_detection": "local-llm",
            "style_validation": "local-llm",
            
            "summarization": "gemini-2.5-flash-lite",
            "topic_modeling": "gemini-2.5-flash-lite",
            "batch_processing": "gemini-2.5-flash-lite",
            "skill_forging": "gemini-2.5-flash-lite",
        }
        
        model = routing_map.get(task_type, "gemini-2.5-flash-lite")
        
        # For high complexity tasks, might want to upgrade model
        if complexity == "high" and model == "gemini-2.5-flash-lite":
            model = "gemini-2.5-flash"
        
        return model
    
    @classmethod
    def get_model_config(cls, model_name: str) -> Dict[str, Any]:
        """Get configuration for specific model"""
        return cls.MODEL_SPECS.get(model_name, {
            "provider": "unknown",
            "strengths": [],
            "max_tokens": 4096,
            "cost_per_1k": 0.0
        })
    
    @classmethod
    def estimate_cost(cls, model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost for model usage"""
        config = cls.get_model_config(model_name)
        total_tokens = prompt_tokens + completion_tokens
        cost_per_1k = config.get("cost_per_1k", 0.0)
        return (total_tokens / 1000.0) * cost_per_1k


# Example usage
if __name__ == "__main__":
    # Example 1: Initialize gateway
    gateway = LiteLLMGateway(
        gateway_url="http://llm_gateway:4000",
        master_key="test-key"
    )
    
    # Example 2: Route a task
    task_type = "code_generation"
    model = ModelRouter.route_task(task_type, complexity="high")
    print(f"Task '{task_type}' routed to: {model}")
    
    config = ModelRouter.get_model_config(model)
    print(f"Model config: {config}")
    
    # Example 3: Make a completion call (would fail without running gateway)
    # messages = [
    #     SystemMessage(content="You are a helpful assistant"),
    #     HumanMessage(content="Write a Python function to calculate fibonacci")
    # ]
    # response = gateway.completion(model="supervisor_model", messages=messages)
    # print(f"Response: {response.content}")
