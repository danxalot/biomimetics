import json
import logging
import os
import sys
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx

# Add shared module to path for model_config import
sys.path.insert(0, "/shared")
try:
    from shared.model_config import insight_synthesis_model, learn_model

    logger = logging.getLogger(__name__)
    logger.info("Successfully imported model config functions")
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.warning(
        f"Could not import model functions from shared.model_config: {e}, will use fallback"
    )

    def insight_synthesis_model():
        return "gemini-2.5-pro"

    def learn_model():
        return "learnlm-2.0-flash-experimental"


class RateLimiter:
    """Simple in-memory rate limiter for API calls."""

    def __init__(self, rpm: int = 15, rpd: int = 1500):
        self.rpm = rpm
        self.rpd = rpd
        self.minute_window = deque()
        self.day_window = deque()

    def acquire(self) -> bool:
        now = datetime.now()

        # Clean up old timestamps
        while self.minute_window and now - self.minute_window[0] > timedelta(minutes=1):
            self.minute_window.popleft()
        while self.day_window and now - self.day_window[0] > timedelta(days=1):
            self.day_window.popleft()

        if len(self.minute_window) >= self.rpm:
            logger.warning("RPM limit reached for Learning Agent")
            return False
        if len(self.day_window) >= self.rpd:
            logger.warning("RPD limit reached for Learning Agent")
            return False

        self.minute_window.append(now)
        self.day_window.append(now)
        return True


class InsightSynthesisTool:
    """
    MCP Tool for the Learning Agent (Insight Synthesis).
    Uses LearnLM Flash 2.0 (Gemini 2.0 Flash) via LLM Gateway to analyze failures and synthesize learnings.
    """

    def __init__(self):
        # Use LLM Gateway URL for all model calls (routing through gateway instead of direct API)
        self.llm_gateway_url = os.getenv(
            "LLM_GATEWAY_URL", "http://llm_gateway:8080/v1/chat/completions"
        )

        # Model configuration - all requests go through gateway
        # The gateway routes to Granite 2B or other models based on load balancing
        self.model_name = os.getenv(
            "LEARNING_MODEL", learn_model()
        )  # Use central config with env override
        self.rate_limiter = RateLimiter(
            rpm=15, rpd=1500
        )  # Limits for learnlm-2.0-flash-experimental

    def _fetch_related_logs(self, context_id: str) -> str:
        """
        Placeholder to fetch OTel data/logs related to a context ID.
        In a full implementation, this would query the OTel backend or log store.
        """
        # TODO: Implement actual OTel query
        return f"[System Logs] No direct OTel query backend available. Analyzing provided context for ID: {context_id}"

    async def analyze_failure(
        self,
        content: str,
        source_agent: str,
        failure_reason: str,
        context_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyzes a failure event to generate insights and recommendations.
        """
        if not self.rate_limiter.acquire():
            return {"error": "Rate limit exceeded"}

        logs = (
            self._fetch_related_logs(context_id)
            if context_id
            else "No context ID provided."
        )

        prompt = f"""
        You are the ARCA Insight Synthesis Engine (Learning Agent).
        Your goal is to analyze a failure event and provide actionable learning outcomes.

        Source Agent: {source_agent}
        Failure Reason: {failure_reason}

        Content/Context:
        {content}

        Related Logs:
        {logs}

        Analyze this failure.
        1. Identify the root cause.
        2. Suggest a specific correction for the agent's behavior or code.
        3. Formulate a general "Learning Rule" to prevent this in the future.

        Output JSON:
        {{
            "root_cause": "string",
            "correction": "string",
            "learning_rule": "string"
        }}
        """

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful AI assistant that outputs JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.llm_gateway_url, json=payload, timeout=60.0
                )
                response.raise_for_status()
                result = response.json()

                # Extract content from OpenAI-compatible response
                content_str = result["choices"][0]["message"]["content"]
                return json.loads(content_str)

        except Exception as e:
            logger.error(f"Error calling Learning Agent via Gateway: {e}")
            return {"error": str(e)}

    def synthesize_learning(self, content: str, topic: str) -> Dict[str, Any]:
        """
        Synthesizes a general learning event from successful or neutral content via llm_gateway.
        """
        if not self.rate_limiter.acquire():
            return {"error": "Rate limit exceeded"}

        prompt = f"""
        You are the ARCA Insight Synthesis Engine.
        Synthesize a structured learning entry from the following content.

        Topic: {topic}
        Content:
        {content}

        Output JSON:
        {{
            "insight_summary": "string",
            "key_concepts": ["list", "of", "concepts"],
            "application_rule": "string"
        }}
        """

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful AI assistant that outputs JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }

        try:
            import httpx

            # Use synchronous httpx since this is not async
            with httpx.Client() as client:
                response = client.post(self.llm_gateway_url, json=payload, timeout=60.0)
                response.raise_for_status()
                result = response.json()

                # Extract content from OpenAI-compatible response
                content_str = result["choices"][0]["message"]["content"]
                logger.info("Learning synthesis via llm_gateway complete")
                return json.loads(content_str)
        except Exception as e:
            logger.error(f"Learning synthesis via llm_gateway failed: {e}")
            return {"error": str(e)}


def analyze_agent_failure(
    content: str,
    source_agent: str,
    failure_reason: str,
    context_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analyzes an agent's failure to provide insights and corrections.
    Use this when an agent fails a task or a review.

    Args:
        content: The content or output that failed.
        source_agent: The name of the agent that failed.
        failure_reason: The reason for the failure (e.g., "Reviewer rejected due to security").
        context_id: Optional ID to trace related logs.
    """
    tool = InsightSynthesisTool()
    return tool.analyze_failure(content, source_agent, failure_reason, context_id)


def synthesize_insight(content: str, topic: str) -> Dict[str, Any]:
    """
    Synthesizes a learning insight from content.
    Use this to record successful patterns or general knowledge.

    Args:
        content: The content to analyze.
        topic: The general topic of the content.
    """
    tool = InsightSynthesisTool()
    return tool.synthesize_learning(content, topic)
