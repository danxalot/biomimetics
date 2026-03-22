# -*- coding: utf-8 -*-
"""Memory Interceptor hook for Copaw.

This hook intercepts prompts before they're sent to the LLM,
queries the GCP Memory Gateway for relevant context, and
silently injects it into the system prompt.
"""
import asyncio
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class MemoryInterceptorHook:
    """Hook for intercepting prompts and injecting memory context.

    This hook queries the GCP Cloud Function Gateway before the LLM
    generates a response, and injects the returned unified memory
    payload (MuninnDB + MemU) into the system prompt context.

    The injection is silent - the user doesn't see the memory retrieval,
    but the LLM has access to relevant context from:
    - MuninnDB (working memory with ACT-R decay)
    - MemU (archive memory with Gemini embeddings)

    Configuration via environment variables:
        GCP_GATEWAY_URL: Cloud Function Gateway URL
        MEMORY_MAX_TOKENS: Max tokens to inject (default: 2000)
        MEMORY_MIN_CONFIDENCE: Min confidence threshold (default: 0.3)
    """

    def __init__(
        self,
        gateway_url: Optional[str] = None,
        max_tokens: int = 2000,
        min_confidence: float = 0.3,
        timeout: float = 10.0,
    ):
        """Initialize memory interceptor hook.

        Args:
            gateway_url: GCP Cloud Function Gateway URL.
                Defaults to GCP_GATEWAY_URL env var.
            max_tokens: Maximum tokens to inject from memory.
                Defaults to 2000.
            min_confidence: Minimum confidence threshold for memories.
                Defaults to 0.3 (ACT-R retrieval threshold).
            timeout: HTTP request timeout in seconds.
                Defaults to 10.0.
        """
        self.gateway_url = gateway_url or os.environ.get(
            "GCP_GATEWAY_URL",
            "https://us-central1-arca-471022.cloudfunctions.net/memory-orchestrator"
        )
        self.max_tokens = max_tokens
        self.min_confidence = min_confidence
        self.timeout = timeout
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={"Content-Type": "application/json"}
            )
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def _query_gateway(self, query: str) -> Optional[dict]:
        """Query GCP Gateway for memory context.

        Args:
            query: The user's prompt/query text.

        Returns:
            Gateway response dict or None on error.
        """
        try:
            client = await self._get_client()

            payload = {
                "query": query,
                "user_id": "copaw",
                "max_tokens": self.max_tokens,
                "min_confidence": self.min_confidence
            }

            response = await client.post(self.gateway_url, json=payload)
            response.raise_for_status()

            result = response.json()

            if result.get("status") == "success" and result.get("results"):
                logger.debug(
                    "Memory Gateway returned %d results (tokens: %d)",
                    len(result.get("results", [])),
                    result.get("token_usage", {}).get("total", 0)
                )
                return result
            else:
                logger.debug("No relevant memories found for query")
                return None

        except httpx.TimeoutException:
            logger.warning("Memory Gateway timeout (%.1fs)", self.timeout)
            return None
        except httpx.HTTPError as e:
            logger.warning("Memory Gateway HTTP error: %s", e)
            return None
        except Exception as e:
            logger.warning("Memory Gateway error: %s", e)
            return None

    def _format_memory_context(self, gateway_result: dict) -> str:
        """Format gateway results as system prompt context.

        Args:
            gateway_result: Response from GCP Gateway.

        Returns:
            Formatted memory context string.
        """
        results = gateway_result.get("results", [])
        sources = gateway_result.get("sources", {})
        token_usage = gateway_result.get("token_usage", {})

        if not results:
            return ""

        # Build context header
        lines = [
            "\n--- RELEVANT MEMORY CONTEXT ---",
            f"(Retrieved {len(results)} memories, {token_usage.get('total', 0)} tokens)",
            f"(Sources: working={sources.get('working', 0)}, archive={sources.get('archive', 0)})",
            ""
        ]

        # Add each memory with confidence score
        for i, memory in enumerate(results, 1):
            content = memory.get("content", "")
            confidence = memory.get("confidence", 0)
            source = memory.get("source", "unknown")

            # Truncate long memories
            if len(content) > 500:
                content = content[:497] + "..."

            lines.append(f"[{i}] [{source}] (confidence: {confidence:.2f})")
            lines.append(f"    {content}")
            lines.append("")

        lines.append("--- END MEMORY CONTEXT ---\n")

        return "\n".join(lines)

    async def __call__(
        self,
        agent,
        kwargs: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Intercept prompt and inject memory context.

        This is called before the LLM generates a response.
        It queries the Gateway and injects results into the system prompt.

        Args:
            agent: The agent instance (CoPawAgent).
            kwargs: Input arguments to the _reasoning method.
                Contains 'messages' list with conversation history.

        Returns:
            Modified kwargs dict with injected memory context,
            or None if no memory was found or on error.
        """
        try:
            # Extract the latest user message for querying
            messages = kwargs.get("messages", [])
            if not messages:
                return None

            # Find the most recent user message
            latest_user_message = None
            for msg in reversed(messages):
                if hasattr(msg, "role") and msg.role == "user":
                    latest_user_message = msg
                    break

            if not latest_user_message:
                return None

            # Extract query text
            query_text = ""
            if hasattr(latest_user_message, "content"):
                content = latest_user_message.content
                if isinstance(content, str):
                    query_text = content[:500]  # Limit query length
                elif isinstance(content, list):
                    # Handle multi-part messages
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            query_text = part.get("text", "")[:500]
                            break

            if not query_text:
                return None

            # Query Gateway for memory context
            logger.debug("Querying Memory Gateway for: %s...", query_text[:50])
            gateway_result = await self._query_gateway(query_text)

            if not gateway_result:
                return None

            # Format memory context
            memory_context = self._format_memory_context(gateway_result)

            if not memory_context:
                return None

            # Inject into system prompt
            # Find or create system message
            system_message = None
            for msg in messages:
                if hasattr(msg, "role") and msg.role == "system":
                    system_message = msg
                    break

            if system_message:
                # Append to existing system prompt
                if hasattr(system_message, "content"):
                    if isinstance(system_message.content, str):
                        system_message.content += memory_context
                    elif isinstance(system_message.content, list):
                        # Find text block or append
                        found = False
                        for part in system_message.content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                part["text"] += memory_context
                                found = True
                                break
                        if not found:
                            system_message.content.append({
                                "type": "text",
                                "text": memory_context
                            })
            else:
                # Create new system message
                from agentscope.message import Msg
                system_msg = Msg(
                    name="system",
                    content=memory_context,
                    role="system"
                )
                # Insert after any existing system messages
                messages.insert(0, system_msg)

            logger.debug("Memory context injected into system prompt")

            # Return modified kwargs
            kwargs["messages"] = messages
            return kwargs

        except Exception as e:
            logger.error(
                "Memory Interceptor failed: %s",
                e,
                exc_info=True
            )
            # Don't block - return None to continue without memory
            return None

        finally:
            # Cleanup is handled by agent lifecycle
            pass


# Convenience function for creating hook with default settings
def create_memory_interceptor(
    gateway_url: Optional[str] = None,
    max_tokens: int = 2000,
    min_confidence: float = 0.3,
) -> MemoryInterceptorHook:
    """Create a Memory Interceptor hook with default settings.

    Args:
        gateway_url: GCP Gateway URL (defaults to env var).
        max_tokens: Max tokens to inject.
        min_confidence: Min confidence threshold.

    Returns:
        Configured MemoryInterceptorHook instance.
    """
    return MemoryInterceptorHook(
        gateway_url=gateway_url,
        max_tokens=max_tokens,
        min_confidence=min_confidence
    )
