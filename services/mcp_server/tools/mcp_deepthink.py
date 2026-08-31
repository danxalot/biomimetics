import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# Load Google AI Studio API key
def _load_api_key():
    """Load Google AI Studio API key from secrets or environment"""
    # Try environment variable first
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_AI_STUDIO_API")
    if api_key:
        return api_key

    # Try secrets file
    secrets_dir = os.getenv("SECRETS_DIR", "/app/secrets")
    secret_path = os.path.join(secrets_dir, "google_ai_studio")
    if os.path.exists(secret_path):
        try:
            with open(secret_path, "r") as f:
                content = f.read().strip()
                if "=" in content:
                    return content.split("=", 1)[1].strip()
                return content
        except Exception as e:
            logger.error(f"Failed to load API key from {secret_path}: {e}")
    return None


# Add shared module to path for model_config import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/shared")
try:
    from shared.model_config import deepthink_model
except ImportError as e:
    logger.warning(
        f"Could not import deepthink_model from shared.model_config: {e}, will use fallback"
    )

    def deepthink_model():
        return "deep-research-pro-preview-12-2025"


class DeepThinkTool:
    """
    Deep Research Analysis Tool for Architect Role

    Enables architects to perform specialized deep research using Google's
    deep-research-pro model for complex analysis tasks.

    This tool is designed for:
    - Complex architectural analysis requiring extended research
    - Knowledge synthesis across large document sets
    - Deep reasoning on system design decisions
    - Research-oriented problem decomposition

    Rate Limit: Depends on Google API tier (typically 250 RPD for free tier)
    Model: deep-research-pro-preview-12-2025 (or alternative from model_config)

    Authorization: Architect role recommended
    """

    def __init__(self):
        self.model_name = (
            deepthink_model()
        )  # From model_config: deep-research-pro-preview-12-2025
        self.api_key = _load_api_key()
        self._model = None
        self._initialized = False
        self._usage_count = 0
        self._usage_reset_time = None

    def _ensure_initialized(self):
        """Lazy initialization of Google Generative AI model"""
        if not self._initialized:
            if not self.api_key:
                raise ValueError(
                    "Google AI Studio API key not found. Set GOOGLE_API_KEY environment variable."
                )

            import google.generativeai as genai

            genai.configure(api_key=self.api_key)

            try:
                self._model = genai.GenerativeModel(self.model_name)
                logger.info(f"Initialized DeepThinkTool with {self.model_name}")
            except Exception as e:
                logger.error(f"Failed to initialize {self.model_name}: {e}")
                # Fallback to flash
                self._model = genai.GenerativeModel("gemini-2.5-flash")
                logger.warning("Falling back to gemini-2.5-flash")

            self._initialized = True
            self._usage_reset_time = datetime.now()

    def _check_rate_limit(self) -> bool:
        """
        Check if we're within daily rate limits.
        Note: Gateway also tracks this at llm_gateway:8000/usage endpoint
        """
        now = datetime.now()

        # Reset counter daily
        if self._usage_reset_time and (now - self._usage_reset_time).days >= 1:
            self._usage_count = 0
            self._usage_reset_time = now

        # Leave buffer of 10 requests
        if self._usage_count >= 240:
            logger.warning(
                f"DeepThink model near daily limit ({self._usage_count}/250 RPD)"
            )
            return False

        return True

    async def research(
        self,
        query: str,
        research_depth: str = "comprehensive",
        context: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> str:
        """
        Perform deep research on a complex topic.

        Args:
            query: The research question or topic
            research_depth: 'quick' (fast), 'thorough' (standard), 'comprehensive' (deep)
            context: Optional context (e.g., {"domain": "architecture", "scope": "..."})
            max_retries: Number of retries on rate limit

        Returns:
            Research synthesis/analysis as string

        Research Depths:
        - 'quick': Rapid synthesis, good for brainstorming
        - 'thorough': Standard deep analysis (default)
        - 'comprehensive': Extended analysis with multiple perspectives
        """

        depth_prompts = {
            "quick": "Provide a rapid, bullet-point synthesis of key insights.",
            "thorough": "Provide a thorough analysis with reasoning and evidence.",
            "comprehensive": "Perform deep analysis from multiple perspectives with extensive reasoning.",
        }

        depth_instruction = depth_prompts.get(research_depth, depth_prompts["thorough"])

        system_prompt = f"""You are a deep research assistant for ARCA's Architect role.
Your task is to synthesize complex information and provide actionable insights.

Research Depth: {research_depth}
{depth_instruction}

Approach:
1. Decompose the question into core components
2. Research each component thoroughly
3. Synthesize findings with reasoning
4. Provide actionable recommendations"""

        # Ensure model is initialized
        self._ensure_initialized()

        # Check rate limit
        if not self._check_rate_limit():
            return "Error: Daily rate limit approaching (250 RPD). Defer non-critical research."

        # Build context header
        context_header = f"Research Query:\n{query}"
        if context:
            if context.get("domain"):
                context_header += f"\nDomain: {context['domain']}"
            if context.get("scope"):
                context_header += f"\nScope: {context['scope']}"
            if context.get("constraints"):
                context_header += f"\nConstraints: {context['constraints']}"

        user_prompt = f"{context_header}"

        for attempt in range(max_retries):
            try:
                # Call Google generativeai
                logger.info(
                    f"Starting DeepThink research ({research_depth}): {query[:50]}..."
                )
                response = await asyncio.to_thread(
                    self._model.generate_content,
                    user_prompt,
                    generation_config={"temperature": 0.7, "max_output_tokens": 4000},
                )

                # Increment usage counter
                self._usage_count += 1
                logger.info(
                    f"DeepThink research complete. Usage: {self._usage_count}/250 RPD"
                )

                return response.text

            except Exception as e:
                error_str = str(e)
                if (
                    "429" in error_str
                    or "RESOURCE_EXHAUSTED" in error_str
                    or "quota" in error_str.lower()
                ):
                    wait_time = (2**attempt) * 10  # 10s, 20s, 40s
                    logger.warning(
                        f"DeepThink rate limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"DeepThink research failed: {e}")
                    return f"Error: {str(e)}"

        return f"Error: Max retries ({max_retries}) exceeded for DeepThink research"

    async def analyze_architecture(
        self,
        architecture_spec: str,
        focus_area: Optional[str] = None,
        max_retries: int = 3,
    ) -> str:
        """
        Deep architectural analysis using research capabilities.

        Args:
            architecture_spec: System architecture description or specification
            focus_area: Specific area to focus on (scalability, security, performance, etc.)
            max_retries: Number of retries on rate limit

        Returns:
            Detailed architectural analysis
        """

        focus_instruction = f"Focus especially on: {focus_area}" if focus_area else ""

        system_prompt = """You are a system architect's research assistant.
Your task is to provide deep architectural analysis with reasoning.

Analyze for:
1. Scalability implications
2. Failure modes and resilience
3. Complexity assessment
4. Integration challenges
5. Trade-offs and design decisions

Provide both strengths and areas for improvement."""

        # Ensure model is initialized
        self._ensure_initialized()

        # Check rate limit
        if not self._check_rate_limit():
            return "Error: Daily rate limit approaching (250 RPD). Defer analysis."

        user_prompt = f"""System Architecture to Analyze:

{architecture_spec}

{focus_instruction}

Provide comprehensive architectural analysis with detailed reasoning."""

        for attempt in range(max_retries):
            try:
                logger.info(f"Starting DeepThink architectural analysis...")
                response = await asyncio.to_thread(
                    self._model.generate_content,
                    user_prompt,
                    generation_config={"temperature": 0.8, "max_output_tokens": 4000},
                )

                # Increment usage counter
                self._usage_count += 1
                logger.info(
                    f"DeepThink architecture analysis complete. Usage: {self._usage_count}/250 RPD"
                )

                return response.text

            except Exception as e:
                error_str = str(e)
                if (
                    "429" in error_str
                    or "RESOURCE_EXHAUSTED" in error_str
                    or "quota" in error_str.lower()
                ):
                    wait_time = (2**attempt) * 10
                    logger.warning(
                        f"DeepThink rate limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"DeepThink architecture analysis failed: {e}")
                    return f"Error: {str(e)}"

        return f"Error: Max retries ({max_retries}) exceeded for architecture analysis"

    async def synthesize_knowledge(
        self, documents: Dict[str, str], synthesis_goal: str, max_retries: int = 3
    ) -> str:
        """
        Synthesize knowledge across multiple documents.

        Args:
            documents: Dict of {doc_name: doc_content}
            synthesis_goal: What you want to synthesize/understand from documents
            max_retries: Number of retries on rate limit

        Returns:
            Synthesized knowledge and insights
        """

        # Ensure model is initialized
        self._ensure_initialized()

        # Check rate limit
        if not self._check_rate_limit():
            return "Error: Daily rate limit approaching (250 RPD). Defer synthesis."

        doc_list = "\n\n---\n\n".join(
            [f"[Document: {name}]\n{content}" for name, content in documents.items()]
        )

        system_prompt = """You are a knowledge synthesis expert.
Your task is to synthesize information across multiple documents.

Approach:
1. Identify key themes and patterns
2. Extract actionable insights
3. Highlight contradictions or tensions
4. Synthesize coherent understanding
5. Provide conclusions and recommendations"""

        user_prompt = f"""Synthesis Goal: {synthesis_goal}

Documents to Synthesize:

{doc_list}

Please provide comprehensive synthesis and insights."""

        for attempt in range(max_retries):
            try:
                logger.info(f"Starting DeepThink knowledge synthesis...")
                response = await asyncio.to_thread(
                    self._model.generate_content,
                    user_prompt,
                    generation_config={"temperature": 0.7, "max_output_tokens": 4000},
                )

                # Increment usage counter
                self._usage_count += 1
                logger.info(
                    f"DeepThink knowledge synthesis complete. Usage: {self._usage_count}/250 RPD"
                )

                return response.text

            except Exception as e:
                error_str = str(e)
                if (
                    "429" in error_str
                    or "RESOURCE_EXHAUSTED" in error_str
                    or "quota" in error_str.lower()
                ):
                    wait_time = (2**attempt) * 10
                    logger.warning(
                        f"DeepThink rate limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"DeepThink knowledge synthesis failed: {e}")
                    return f"Error: {str(e)}"

        return f"Error: Max retries ({max_retries}) exceeded for knowledge synthesis"

    def get_status(self) -> Dict[str, Any]:
        """Get status of the DeepThink tool"""
        return {
            "model": self.model_name,
            "initialized": self._initialized,
            "usage_today": self._usage_count,
            "usage_limit": 250,
            "api_key_loaded": bool(self.api_key),
            "quota_tracking": "via llm_gateway:8000/usage endpoint",
            "reset_time": "midnight PT",
        }


# Singleton instance
_deepthink_instance = None


def get_deepthink_tool() -> DeepThinkTool:
    """Get or create the singleton DeepThink tool instance"""
    global _deepthink_instance
    if _deepthink_instance is None:
        _deepthink_instance = DeepThinkTool()
    return _deepthink_instance


if __name__ == "__main__":
    # Example usage
    import sys

    async def main():
        tool = get_deepthink_tool()

        # Example research
        result = await tool.research(
            "What are the key architectural patterns for distributed systems?",
            research_depth="comprehensive",
            context={"domain": "distributed systems", "scope": "microservices"},
        )
        print("Research Result:")
        print(result)
        print(f"\nTool Status: {tool.get_status()}")

    asyncio.run(main())
