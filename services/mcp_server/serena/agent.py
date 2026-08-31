import json
import logging
import os

# Add shared module to path for model_config import
import sys
from typing import Any, Dict, List, Optional

import requests
from mcp.types import Tool

sys.path.insert(0, "/shared")
sys.path.insert(0, "/app/shared")
try:
    from shared.model_config import serena_model
except ImportError as e:
    logger.warning(f"Could not import serena_model from shared.model_config: {e}")

    # Fallback
    def serena_model():
        return "glm:latest"


logger = logging.getLogger(__name__)


class SerenaAgent:
    """
    Noetic Code Agent: Serena.
    Provides semantic code analysis and refactoring assistance using Local GLM.
    """

    def __init__(self, project: str):
        self.project_root = project
        self.tools_handler = SerenaTools(self)
        logger.info(
            f"Serena Agent initialized for project: {project} using model {serena_model()}"
        )

    def get_exposed_tool_instances(self) -> List[Tool]:
        """Return a list of MCP Tool objects exposed by Serena."""
        return [
            Tool(
                name="serena_analyze_code",
                description="Analyze code for semantic meaning and potential refactoring",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Code to analyze"},
                        "context": {
                            "type": "string",
                            "description": "Context for analysis",
                        },
                    },
                    "required": ["code"],
                },
            ),
            Tool(
                name="serena_refactor_suggestion",
                description="Suggest refactoring for a specific goal",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Code to refactor"},
                        "goal": {"type": "string", "description": "Refactoring goal"},
                    },
                    "required": ["code", "goal"],
                },
            ),
            Tool(
                name="serena_semantic_diff",
                description="Analyze the semantic impact of code changes (diff)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "diff_content": {
                            "type": "string",
                            "description": "The git diff or code change",
                        },
                        "context": {
                            "type": "string",
                            "description": "Additional context (e.g. commit message)",
                        },
                    },
                    "required": ["diff_content"],
                },
            ),
            Tool(
                name="serena_security_scan",
                description="Scan code or config for security vulnerabilities",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Code or config to scan",
                        },
                        "context": {
                            "type": "string",
                            "description": "Context (e.g. filename, environment)",
                        },
                    },
                    "required": ["content"],
                },
            ),
            Tool(
                name="serena_chat",
                description="General interaction with Serena for architectural reasoning and task dispatch",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "Message or instruction",
                        },
                        "message": {
                            "type": "string",
                            "description": "Alias for prompt",
                        },
                        "context": {
                            "type": "string",
                            "description": "Context (JSON string or text)",
                        },
                    },
                    "required": [],
                },
            ),
        ]

    async def execute_tool(
        self,
        name: str,
        arguments: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> str:
        if name == "serena_analyze_code":
            return self.tools_handler.analyze_code(
                arguments["code"], arguments.get("context", ""), headers=headers
            )
        elif name == "serena_refactor_suggestion":
            return self.tools_handler.refactor_suggestion(
                arguments["code"], arguments["goal"], headers=headers
            )
        elif name == "serena_semantic_diff":
            return self.tools_handler.semantic_diff(
                arguments["diff_content"], arguments.get("context", ""), headers=headers
            )
        elif name == "serena_security_scan":
            return self.tools_handler.security_scan(
                arguments["content"], arguments.get("context", ""), headers=headers
            )
        elif name == "serena_chat":
            prompt = arguments.get("prompt") or arguments.get("message")
            if not prompt:
                raise ValueError("Either 'prompt' or 'message' is required")
            return self.tools_handler.chat(
                prompt, arguments.get("context", "{}"), headers=headers
            )
        else:
            raise ValueError(f"Unknown tool: {name}")


class SerenaTools:
    def __init__(self, agent: SerenaAgent):
        self.agent = agent
        self.model_name = serena_model()
        # Route through LLM Gateway per workspace-guard workflow
        self.llm_gateway_url = os.getenv("LLM_GATEWAY_URL", "http://llm_gateway:8080")
        self.generate_endpoint = f"{self.llm_gateway_url}/v1/chat/completions"

    def _call_ollama(
        self, prompt: str, headers: Optional[Dict[str, str]] = None
    ) -> str:
        """Call LLM through the LLM Gateway (OpenAI-compatible endpoint)."""
        # Ensure endpoint includes /v1/chat/completions
        endpoint = self.llm_gateway_url
        if not endpoint.endswith("/v1/chat/completions"):
            endpoint = f"{endpoint.rstrip('/')}/v1/chat/completions"

        # INJECT UNIVERSAL SKILL FRAME (USF) CONTEXT
        usf_context = ""
        try:
            # Dynamic import to avoid circular dep at module level if possible
            from tools.mcp_universal_context import retrieve_context

            # Naive subject extraction or default to 'project root' context
            # For now, we inject a high-level summary if possible, or just skip if no subject.
            # Ideally, we'd pass the subject from the calling tool.
            pass
        except ImportError:
            pass

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "You are Serena, the ARCA Principal Architect and Noetic Agent.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            # ZhipuAI GLM-4v-flash may not accept max_tokens parameter
        }

        final_headers = {"X-Genesis-Chain": "true", "Content-Type": "application/json"}
        if headers:
            # Propagate X-Genesis headers from incoming request
            genesis_headers = {
                k: v for k, v in headers.items() if k.lower().startswith("x-genesis-")
            }
            logger.info(f"Serena propagating headers: {list(genesis_headers.keys())}")
            final_headers.update(genesis_headers)

        headers = final_headers

        try:
            res = requests.post(endpoint, json=payload, headers=headers, timeout=90)
            res.raise_for_status()
            response_data = res.json()
            # OpenAI format: choices[0].message.content
            if "choices" in response_data and len(response_data["choices"]) > 0:
                return response_data["choices"][0]["message"]["content"]
            # Fallback for Ollama format
            return response_data.get("response", "Error: No response from model.")
        except Exception as e:
            logger.error(f"Serena GLM call failed: {e}")
            return f"Error calling Serena model: {str(e)}"

    def analyze_code(
        self, code: str, context: str = "", headers: Optional[Dict] = None
    ) -> str:
        """
        Analyze code for semantic meaning and potential refactoring using GLM.
        """
        prompt = f"""
        ROLE: You are Serena, an advanced Code Intelligence Agent.
        TASK: Analyze the following code snippet for semantic meaning, code quality, and potential issues.
        CONTEXT: {context}

        CODE:
        ```
        {code}
        ```

        OUTPUT:
        Provide a concise analysis focusing on:
        1. Semantic Purpose (What does it do?)
        2. Code Quality (Readability, structure)
        3. Potential Issues (Bugs, edge cases)
        """
        return self._call_ollama(prompt, headers=headers)

    def refactor_suggestion(
        self, code: str, goal: str, headers: Optional[Dict] = None
    ) -> str:
        """
        Suggest refactoring for a specific goal using GLM.
        """
        prompt = f"""
        ROLE: You are Serena, an advanced Code Intelligence Agent.
        TASK: Suggest a refactoring for the provided code to achieve a specific goal.
        GOAL: {goal}

        CODE:
        ```
        {code}
        ```

        OUTPUT:
        Provide the refactored code and a brief explanation of the changes.
        """
        return self._call_ollama(prompt, headers=headers)

    def semantic_diff(
        self, diff_content: str, context: str, headers: Optional[Dict] = None
    ) -> str:
        """Analyze semantic impact of a diff."""
        prompt = f"""
        ROLE: Serena (Noetic Code Agent).
        TASK: Analyze this git diff for semantic impact.
        CONTEXT: {context}

        DIFF:
        ```
        {diff_content}
        ```

        OUTPUT:
        Summarize the *meaning* of the change. Is it a fix, feature, or refactor? Any risks?
        """
        return self._call_ollama(prompt, headers=headers)

    def security_scan(
        self, content: str, context: str, headers: Optional[Dict] = None
    ) -> str:
        """Scan content for vulnerabilities."""
        prompt = f"""
        ROLE: Serena (Security Auditor).
        TASK: Scan the following content for security vulnerabilities, secrets, or unsafe patterns.
        CONTEXT: {context}

        CONTENT:
        ```
        {content}
        ```

        OUTPUT:
        Pass/Fail assessment. List any specific vulnerabilities found with severity.
        """
        return self._call_ollama(prompt, headers=headers)

    def chat(
        self, user_prompt: str, context: str, headers: Optional[Dict] = None
    ) -> str:
        """
        General chat with Serena for reasoning and task planning.
        """
        prompt = f"""
        ROLE: You are Serena, the ARCA Principal Architect and Noetic Agent.
        TASK: {user_prompt}
        CONTEXT: {context}

        Thinking Process:
        1. Contextualize the request within the ARCA architecture.
        2. Identify necessary capabilities (OCI, Git, Docker, etc.).
        3. Formulate a plan or direct answer.

        If you need to perform actions, describe them clearly as a plan.
        """
        return self._call_ollama(prompt, headers=headers)
