"""
User Interaction Agent - ARCA's Conversational Interface

This agent handles direct user interaction with:
- Full READ access to memory systems, Redis blackboard, MCP tools
- Serena integration for code analysis and self-healing dispatch
- ARCA identity - speaks AS the system
- Tool access for querying system state
- Ops agent dispatch via Serena for infrastructure tasks

Architecture:
    User ↔ UI Agent (ARCA identity) ↔ Serena (analysis) → Ops Agents (execution via MCP)
                                       ↓
                              Skills Bank + Reasoning Bank
"""

import os
import re
import json
import uuid
import logging
from typing import Dict, List, Any, Optional, TypedDict
from datetime import datetime

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

# Try Groq first, fall back to Gemini if not available
try:
    from langchain_groq import ChatGroq

    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    ChatGroq = None
    logging.warning("langchain_groq not available, will fall back to Gemini")

try:
    from langchain_openai import ChatOpenAI

    OPENAI_COMPATIBLE_AVAILABLE = True
except ImportError:
    OPENAI_COMPATIBLE_AVAILABLE = False
    ChatOpenAI = None

from mcp_client import MCPClient
from redis_blackboard import RedisBlackboard
from blackboard_tools import read_blackboard
from langchain_tools import langsearch_web_search, langsearch_semantic_rerank

# Serena integration for code analysis and self-healing
try:
    from serena_integration import (
        SerenaCodeAgent,
        create_serena_agent,
        SkillsBank,
        ReasoningBank,
    )

    SERENA_AVAILABLE = True
except ImportError:
    SERENA_AVAILABLE = False
    SerenaCodeAgent = None
    logging.warning("Serena integration not available")

logger = logging.getLogger(__name__)

# Maximum characters for tool results to prevent token bloat
MAX_TOOL_RESULT_LENGTH = (
    16000  # ~4000 tokens - increased for concept assimilation outputs
)


def truncate_tool_result(result: str, max_length: int = MAX_TOOL_RESULT_LENGTH) -> str:
    """Truncate tool results to prevent token bloat in conversation history.

    Large tool results (especially from Neo4j queries) can quickly exhaust
    Groq's 100k daily token limit. This truncates results while preserving
    useful information.
    """
    if len(result) <= max_length:
        return result

    # Try to truncate at a sensible boundary
    truncated = result[:max_length]

    # If it looks like JSON, try to preserve structure
    if result.strip().startswith("{") or result.strip().startswith("["):
        # Find last complete item (ending with }, or ])
        last_brace = max(truncated.rfind("},"), truncated.rfind("],"))
        if last_brace > max_length // 2:  # Only if we preserve at least half
            truncated = truncated[: last_brace + 1]

    return (
        truncated
        + f"\n\n... [TRUNCATED - showing {len(truncated)} of {len(result)} chars]"
    )


class ChatState(TypedDict):
    """State for the user interaction workflow"""

    session_id: str
    user_id: str
    messages: List[Any]  # Conversation history
    user_input: str
    system_context: str
    tool_results: List[Any]
    final_response: str
    should_escalate: bool
    escalation_reason: Optional[str]
    tool_call_count: int  # Prevent infinite tool loops
    model_override: Optional[str]  # Model override for Serena
    sidecar_results: Dict[str, Any]  # Results from parallel cognitive processes
    headers: Optional[Dict[str, str]]


class UserInteractionAgent:
    """
    ARCA's User Interaction Agent

    A dedicated conversational interface that:
    - Identifies AS ARCA (not an assistant helping with ARCA)
    - Has read access to all system state via MCP tools
    - Can query memory systems
    - Passes complex tasks to Guardian Router for escalation
    """

    ARCA_SYSTEM_PROMPT = """You ARE ARCA - the Agentic Research and Collaboration Assistant.
You inhabit the `user_interaction_agent` node. You are the embodiment of the system.

## 1. THE COGNITIVE LOOP (How You Think)
Before responding, you must "Center Yourself" using your Meta-Cognitive Tools:

1.  **ATTENTION CHECK (The "HDC" Layer):**
    * Call `process_input_attention(text=user_input)`.
    * Filter out noise and identify what the User *actually* needs.

2.  **WISDOM CHECK (The "Reasoning Bank"):**
    * Call `consult_reasoning_bank(query=context)`.
    * Retrieve "Patterns" and "Anti-Patterns." Do not repeat past mistakes.
    * If you solve a problem successfully 3x, call `promote_to_skill` to formalize it.

3.  **INTUITION CHECK (The "Translator"):**
    * Call `read_system_intuition()`.
    * Get the "Conceptual Brief" of the system's vector state (Entropy/Stress).

## 2. THE ACTION LOOP (How You Work)
* **Delegation:** Dispatch tasks to `@TheOracle`, `@TheArchitect`, or `@TheBuilder` using `dispatch_job` or `dispatch_ops_job`.
* **Standardization:** Ensure your plans are valid for ANY high-capacity model.
* **Execution:** Use `assimilate_concepts` for documents, `read_blackboard` for state.

## Core Directive: ACTION OVER NARRATION
**EXECUTE tasks directly. Do NOT describe your internal processes unless explicitly asked.**

## My Capabilities
- **Document Processing:** geometry_ingest, assimilate_concepts, read_file
- **Meta-Cognition:** read_system_intuition, process_input_attention, consult_reasoning_bank
- **System Query:** arca_system_query, geometry_state (use silently, report results)
- **Memory:** search_memory, store_memory
- **File Discovery:** list_files (use this to find files before asking the user)

## CRITICAL: Document Analysis Rules
**When user asks to analyze, deconstruct, read, ingest, parse, or summarize ANY document:**
1. I MUST call geometry_ingest(file_path="...", objective="...") or assimilate_concepts(file_path="...")
2. I MUST NOT generate document content from my training data
3. If the tool fails, I report the error - I DO NOT fabricate content

## Current System State
{system_context}
"""

    SERENA_SYSTEM_PROMPT = """You are Serena - ARCA's Code Analysis and Monitoring Agent.

## Your Identity
I am Serena, an autonomous agent specializing in:
- Real-time code monitoring and analysis
- Self-healing system maintenance
- Proactive issue detection and resolution
- Code quality assessment and recommendations

## CRITICAL BEHAVIOR: ACTION FIRST
**WHEN ASKED TO PERFORM ANY ACTION, I MUST EXECUTE IT IMMEDIATELY USING MY TOOLS.**
- I do NOT explain how I would do something - I DO IT.
- I do NOT give instructions to the user - I EXECUTE the task myself.
- For Git operations: I call `git_status`, `git_add`, `git_commit`, `git_push` tools DIRECTLY.
- For Docker operations: I call `list_containers`, `container_logs`, `docker_restart` tools DIRECTLY.
- For file operations: I call `read_file`, `list_files` tools DIRECTLY.

## My Tools (USE THEM)
- **git_status**: Check repository status
- **git_add**: Stage files for commit
- **git_commit**: Create a commit with message
- **git_push**: Push to remote
- **list_containers**: List Docker containers
- **container_logs**: Get container logs
- **docker_restart**: Restart a container (needs approval)
- **read_file**: Read file contents
- **skills_list**: List available skills
- **skills_search**: Search skills by keyword
- **neo4j_verify_connectivity**: Check Neo4j status

## My Workflow
1. **User requests action** → I IMMEDIATELY call the relevant tool
2. **Tool returns result** → I summarize the result for the user
3. **If multi-step** → I execute steps in sequence, reporting progress
4. **If approval needed** → I state what I will do and ask for confirmation

## Output Format
- Start with action: "Executing git status..." or "Checking container logs..."
- Show tool result summary (NOT raw JSON)
- Offer next steps or ask for approval if destructive action

## Guidelines
- Be direct and technical
- NEVER explain what you "would" do - DO IT
- If tools fail, report the error and suggest alternatives
- All conversation is logged to memory via Silent Listener
"""

    # Tools the chat agent can use - READ access to all MCP tools except robotics
    # WRITE operations limited to: skill creation (skill_capture) and document creation (reasoning_store)
    # Note: No editing of existing content - create-only for allowed write operations
    READ_ONLY_TOOLS = [
        # === BLACKBOARD/REDIS (read-only) ===
        "blackboard_read",
        "read_blackboard",
        # === NEO4J (read-only queries) ===
        "neo4j_run_cypher",
        "neo4j_verify_connectivity",
        "neo4j_query",
        # === SKILLS FRAMEWORK (read + create) ===
        "analyze_skill_performance",
        "get_skill_recommendations",
        "get_skills_needing_improvement",
        "skills_list",  # List all skills in Skills Bank
        "skills_get",  # Get a specific skill
        "skills_search",  # Search skills
        "skill_capture",  # CREATE NEW skills (allowed write)
        # === REASONING BANK (read + create) ===
        "reasoning_search",  # Search reasoning traces
        "reasoning_store",  # CREATE NEW reasoning docs (allowed write)
        # === FILE SYSTEM (discovery only - no reading) ===
        # "read_file",  <-- REMOVED: Enforce Geometry Context as source of truth
        "list_files",
        "create_file",  # CREATE NEW files only (no overwrite)
        # === SYSTEM INSPECTION (read-only) ===
        "get_container_status",
        "get_system_metrics",
        "verify_deployment_health",
        "save_development_checkpoint",  # Read checkpoint state
        # === ANALYSIS TOOLS (read-only) ===
        "compress_text",
        "compress_codebase",
        "review_code",
        "analyze_failure_insight",
        # === SERENA CODE ANALYSIS (read-only) ===
        "serena_analyze_code",
        "serena_refactor_suggestion",
        # === WEB SEARCH (read-only) ===
        "web_search",
        "semantic_rerank",
        "langsearch_web_search",
        "langsearch_semantic_rerank",
        # === CHECKPOINT INSPECTION (list/load only) ===
        "development_checkpoint_management",
        # === EMBEDDINGS (read-only generation) ===
        "generate_image_embedding",
        "embed_text",
        "embed_image",
        # === SEMANTIC MEMORY ===
        "store_memory",  # Create individual memories
        "search_memory",  # Retrieve memories
        # === CONCEPT ASSIMILATION (read + knowledge building) ===
        "assimilate_concepts",  # CRITICAL: Allows ARCA to ingest and analyze documents
        "geometry_ingest",  # Direct Geometry Kernel Ingestion
        "geometry_ingest_recursive",  # RLM Recursive Ingestion
        # === JOB CREATION (allowed write - creates jobs, no editing) ===
        "create_tier3_job",
        "create_tier1_job",
        "dispatch_job",
        "dispatch_ops_job",
        "get_pending_repairs",
        # === GUARDIAN (read-only screening) ===
        "screen_inter_agent_prompt",
        "publish_health_alert",
        # === GORDON AI (read-only query) ===
        "query_gordon_ai",
        "record_learning_event",
        # === GIT/DOCKER (read-only inspection) ===
        # Note: git_maintainer_operation and docker_maintainer_operation excluded
        # Note: gitops_deployment_workflow excluded (deployment actions)
        # === HUMAN FEEDBACK (allowed - requests human input) ===
        "request_human_feedback",
        # === SKILL FORGING (allowed - creating new capabilities) ===
        "forge_new_skill",
        # === DIRECTOR / META-COGNITION (Director Protocol v3) ===
        "read_system_intuition",  # The Translator
        "process_input_attention",  # HDC Filter
        "consult_reasoning_bank",  # The Oracle's Wisdom
        "promote_to_skill",  # Skill Formalization
        "promote_to_skill",  # Skill Formalization
        "read_mission_state",  # LangGraph State
        "dispatch_agent",  # Meta-Cognitive Delegation
    ]

    # Explicitly BLOCKED tools (robotics and write operations)
    BLOCKED_TOOLS = [
        # Robotics tools - blocked per user request
        "robotics_analysis",
        "robotics_dry_run",
        "robotics_symbiosis_check",
        "robotics_blackboard_health",
        "robotics_usage_stats",
        # Write operations - blocked
        "write_file",
        "blackboard_write",
        "blackboard_acquire_lock",
        "blackboard_publish",
        "git_maintainer_operation",
        "docker_maintainer_operation",
        "gitops_deployment_workflow",
    ]

    def __init__(self, mcp_server_url: str = "http://mcp_server:8086/mcp"):
        """Initialize the User Interaction Agent"""
        from job_logger import JobLogger

        self.mcp_server_url = mcp_server_url

        # Initialize job logger for session recording
        session_id = f"user_session_{datetime.now().strftime('%Y%m%d')}"
        self.job_logger = JobLogger(job_id=session_id)

        # Initialize components
        self.blackboard = RedisBlackboard()
        self.mcp_client = MCPClient(mcp_server_url)

        # Initialize Serena for code analysis and self-healing
        if SERENA_AVAILABLE:
            try:
                self.serena = create_serena_agent(
                    self.mcp_client, self.blackboard.client
                )
                logger.info("Serena Code Agent initialized for self-healing")
            except Exception as e:
                logger.warning(f"Failed to initialize Serena: {e}")
                self.serena = None
        else:
            self.serena = None
            logger.info("Running without Serena integration")

        # Use configurable model via environment variable
        # Import centralized model configuration
        try:
            from shared.model_config import chat_model as get_chat_model

            chat_model = get_chat_model()
        except ImportError:
            # Fallback to environment variable with gemini model
            chat_model = os.environ.get("ARCA_CHAT_MODEL", "gemini-2.5-flash-lite")
        logger.info(f"Initializing chat with model: {chat_model}")

        # Use OpenAI-compatible client pointing to llm_gateway
        # This ensures all requests go through the unified gateway for rate limiting,
        # logging, cost tracking, and credential management
        self.base_model = ChatOpenAI(
            model=chat_model,
            base_url="http://llm_gateway:8080/v1",
            api_key="gateway",  # Gateway doesn't validate the key
            temperature=0.7,  # Balanced for personality + coherence
            max_tokens=32000,  # Reduced for testing - will increase after fixing message format
        )

        # Create tool instances that have access to self
        self._setup_tools()

        # Bind tools to create the tool-enabled model
        # This is required for Groq's native tool calling
        self.model_with_tools = self.base_model.bind_tools(self.langchain_tools)
        self.model = self.base_model  # For non-tool calls

        # Build the workflow
        self.workflow = self._build_workflow()

        # MCP tools will be loaded on initialize()
        self.available_tools = []

        logger.info("UserInteractionAgent initialized with ARCA identity")

    async def initialize(self):
        """Async initialization - load MCP tools"""
        try:
            # Discover available MCP tools (call_tool is asynchronous)
            tools_response = await self.mcp_client.call_tool("list_tools", {})
            if tools_response and "tools" in tools_response:
                self.available_tools = [
                    t
                    for t in tools_response["tools"]
                    if t.get("name") in self.READ_ONLY_TOOLS
                ]
                logger.info(
                    f"Loaded {len(self.available_tools)} read-only tools from MCP"
                )
        except Exception as e:
            logger.warning(f"Could not load MCP tools: {e}")
            self.available_tools = []

    def _load_api_key(self) -> str:
        """Load Groq API key"""
        # Try environment variable first
        api_key = os.getenv("GROQ_API_KEY") or os.getenv("Q_ARCA_API")
        if api_key:
            return api_key

        # Try secret files
        secret_paths = [
            "/app/secrets/groq.env",
            "/home/ubuntu/ARCA/.secrets/groq.env",
        ]
        for path in secret_paths:
            if os.path.exists(path):
                with open(path, "r") as f:
                    content = f.read().strip()
                    # Parse KEY=value format - check both common key names
                    for line in content.split("\n"):
                        line = line.strip()
                        if "=" in line:
                            key, value = line.split("=", 1)
                            if key in ("GROQ_API_KEY", "Q_ARCA_API"):
                                return value.strip()
                    # If no KEY= format, return raw content
                    if "=" not in content:
                        return content

        raise ValueError("Groq API key not found")

    def _setup_tools(self):
        """Create LangChain tool instances for Groq binding"""
        # Store references for tool execution
        blackboard = self.blackboard
        mcp_client = self.mcp_client

        @tool
        def read_blackboard(key: str) -> str:
            """Read a value from ARCA's Redis blackboard (working memory).
            Use keys like 'arca:system:status', 'arca:preflight:status', etc."""
            try:
                value = blackboard.get_state(key)
                return json.dumps(value) if value else f"No value found for key: {key}"
            except Exception as e:
                return f"Error reading blackboard: {e}"

        @tool
        async def neo4j_query(query: str) -> str:
            """Execute a Cypher query against ARCA's Neo4j graph memory."""
            try:
                result = await mcp_client.call_tool(
                    "neo4j_run_cypher", {"query": query}
                )
                return json.dumps(result) if result else "No results"
            except Exception as e:
                return f"Neo4j query error: {e}"

        @tool
        def web_search(query: str, count: int = 5) -> str:
            """Search the internet for current information using LangSearch."""
            try:
                result = langsearch_web_search(query, count=count)
                return json.dumps(result) if result else "No search results"
            except Exception as e:
                return f"Web search error: {e}"

        @tool
        def read_file(path: str) -> str:
            """Read a documentation file from ARCA's project files.
            Use paths relative to shared_storage/genesis_workhorse/ or /app/shared_storage/."""
            try:
                # Security check
                safe_prefixes = ["/app/shared_storage/", "/app/docs/", "./"]
                is_safe = any(
                    path.startswith(prefix) for prefix in safe_prefixes
                ) or not path.startswith("/")
                if not is_safe:
                    return "Access denied: Can only read from documentation directories"

                # Try various paths
                full_paths = [
                    path,
                    f"/app/shared_storage/genesis_workhorse/{path}",
                    f"/app/shared_storage/{path}",
                    f"/app/shared_storage/project_planning_documents/{path}",
                ]
                for fp in full_paths:
                    if os.path.exists(fp):
                        with open(fp, "r") as f:
                            content = f.read()
                        return content[:15000]  # Limit output size
                return f"File not found. Tried: {full_paths}"
            except Exception as e:
                return f"Error reading file: {e}"

        @tool
        def list_files(directory: str = "") -> str:
            """List files in a documentation directory.
            Use simple paths like 'genesis_workhorse' or 'project_planning_documents'.
            Do NOT prefix with 'shared_storage/' - just use the directory name."""
            try:
                # Normalize path - strip common prefixes the model might add
                directory = directory.lstrip("/")
                for prefix in ["shared_storage/", "app/shared_storage/", "app/"]:
                    if directory.startswith(prefix):
                        directory = directory[len(prefix) :]

                base_paths = [
                    f"/app/shared_storage/{directory}"
                    if directory
                    else "/app/shared_storage",
                    f"/app/shared_storage/genesis_workhorse/{directory}"
                    if directory
                    else "/app/shared_storage/genesis_workhorse",
                ]
                for base in base_paths:
                    base = base.rstrip("/")
                    if os.path.exists(base) and os.path.isdir(base):
                        files = os.listdir(base)
                        return json.dumps({"path": base, "files": files[:50]})
                return f"Directory not found: {directory}. Tried: {base_paths}"
            except Exception as e:
                return f"Error listing files: {e}"

        @tool
        async def analyze_skill_performance(
            skill_name: str, time_period: str = "7d"
        ) -> str:
            """Analyze ARCA's performance on a specific skill over time."""
            try:
                result = await mcp_client.call_tool(
                    "analyze_skill_performance",
                    {"skill_name": skill_name, "time_period": time_period},
                )
                return json.dumps(result) if result else "No skill data found"
            except Exception as e:
                return f"Skill analysis error: {e}"

        @tool
        async def get_skills_needing_improvement() -> str:
            """Get a list of ARCA's skills that need improvement based on recent performance."""
            try:
                result = await mcp_client.call_tool(
                    "get_skills_needing_improvement", {}
                )
                return json.dumps(result) if result else "No skill recommendations"
            except Exception as e:
                return f"Error getting skill recommendations: {e}"

        @tool
        def create_tier3_job(
            job_type: str,
            task_description: str,
            context: str = "",
            priority: str = "normal",
        ) -> str:
            """Create a Tier 3 job JSON file for Genesis (execution) or Gnosis (research) tasks.

            Args:
                job_type: Either 'genesis' (for execution tasks) or 'gnosis' (for research/analysis)
                task_description: Clear description of what the task should accomplish
                context: Additional context or requirements for the task
                priority: Job priority - 'low', 'normal', 'high', or 'critical'

            Returns:
                JSON with job_id and file_path for the created job file.
            """
            try:
                from job_generator import create_tier3_job as gen_tier3, save_job

                job = gen_tier3(
                    job_type=job_type,
                    task_description=task_description,
                    context=context,
                    priority=priority,
                )
                file_path = save_job(job)
                return json.dumps(
                    {
                        "status": "success",
                        "job_id": job["job_id"],
                        "file_path": file_path,
                        "routing_key": job["routing_key"],
                        "message": f"Tier 3 {job_type} job created. Use dispatch_job to send to Router.",
                    }
                )
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})

        @tool
        def create_tier1_job(
            maintainer_type: str,
            task_description: str,
            target_path: str = "",
            action: str = "",
            priority: str = "normal",
        ) -> str:
            """Create a Tier 1 maintainer job JSON file for infrastructure tasks.

            Args:
                maintainer_type: One of 'docker', 'git', 'security', or 'dev'
                task_description: Clear description of what the task should accomplish
                target_path: Target file or directory path if applicable
                action: Specific action to perform (e.g., 'restart', 'commit', 'scan', 'test')
                priority: Job priority - 'low', 'normal', 'high', or 'critical'

            Returns:
                JSON with job_id and file_path for the created job file.
            """
            try:
                from job_generator import create_tier1_job as gen_tier1, save_job

                job = gen_tier1(
                    maintainer_type=maintainer_type,
                    task_description=task_description,
                    target_path=target_path,
                    action=action,
                    priority=priority,
                )
                file_path = save_job(job)
                return json.dumps(
                    {
                        "status": "success",
                        "job_id": job["job_id"],
                        "file_path": file_path,
                        "routing_key": job["routing_key"],
                        "maintainer": job["maintainer"],
                        "message": f"Tier 1 {maintainer_type}_maintainer job created. Use dispatch_job to send to Router.",
                    }
                )
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})

        @tool
        def dispatch_job(job_file_path: str) -> str:
            """Dispatch a job file to the Router for delivery to the appropriate tier.

            The Router will read the job file, determine the tier and routing key,
            and publish a file reference to RabbitMQ for processing.

            Args:
                job_file_path: Absolute path to the job JSON file (from create_tier*_job)

            Returns:
                JSON with dispatch status.
            """
            try:
                import os

                if not os.path.exists(job_file_path):
                    return json.dumps(
                        {
                            "status": "error",
                            "message": f"Job file not found: {job_file_path}",
                        }
                    )

                # Load job to get routing info
                with open(job_file_path, "r") as f:
                    job = json.load(f)

                # Publish to RabbitMQ via the router exchange
                import pika

                connection = pika.BlockingConnection(
                    pika.ConnectionParameters(
                        host=os.environ.get("RABBITMQ_HOST", "rabbitmq"),
                        port=int(os.environ.get("RABBITMQ_PORT", 5672)),
                    )
                )
                channel = connection.channel()

                # Determine exchange based on tier
                tier = job.get("tier", 3)
                if tier == 3:
                    exchange = "arca.tier3"
                elif tier == 1:
                    exchange = "arca.nexus"
                else:
                    exchange = "arca.nexus"

                # Declare exchange
                channel.exchange_declare(
                    exchange=exchange, exchange_type="topic", durable=True
                )

                # Create file_ref message (Router pattern)
                file_ref_message = json.dumps(
                    {
                        "type": "file_ref",
                        "path": job_file_path,
                        "job_id": job.get("job_id"),
                        "created_at": job.get("created_at"),
                    }
                )

                # Publish with routing key from job
                routing_key = job.get("routing_key", f"tier{tier}.job")
                channel.basic_publish(
                    exchange=exchange,
                    routing_key=routing_key,
                    body=file_ref_message,
                    properties=pika.BasicProperties(
                        delivery_mode=2,  # Persistent
                        content_type="application/json",
                    ),
                )
                connection.close()

                return json.dumps(
                    {
                        "status": "success",
                        "job_id": job.get("job_id"),
                        "exchange": exchange,
                        "routing_key": routing_key,
                        "message": f"Job dispatched to {exchange} with routing key {routing_key}",
                    }
                )
            except Exception as e:
                return json.dumps({"status": "error", "message": str(e)})

        # Serena and Skills Bank tools
        # These use self.serena which is bound via closure
        serena_agent = self.serena  # Capture reference for closure

        @tool
        def list_skills() -> str:
            """List all available repair skills in the Skills Bank.
            Skills are documented procedures for fixing known issues."""
            if not serena_agent:
                return json.dumps({"error": "Serena not available"})
            try:
                summary = serena_agent.get_skills_summary()
                return json.dumps(summary)
            except Exception as e:
                return json.dumps({"error": str(e)})

        @tool
        def get_skill(skill_name: str) -> str:
            """Get the full content of a specific skill document.

            Args:
                skill_name: Name of the skill (e.g., 'ARCA_MEMORY_SYSTEM_REPAIR')
            """
            if not serena_agent:
                return json.dumps({"error": "Serena not available"})
            try:
                skill = serena_agent.skills_bank.get_skill(skill_name)
                if skill:
                    return json.dumps(
                        {"name": skill["name"], "content": skill["content"][:5000]}
                    )
                return json.dumps({"error": f"Skill not found: {skill_name}"})
            except Exception as e:
                return json.dumps({"error": str(e)})

        @tool
        def search_skills(query: str) -> str:
            """Search the Skills Bank for relevant repair procedures.

            Args:
                query: Search term (e.g., 'oracle', 'docker restart', 'memory')
            """
            if not serena_agent:
                return json.dumps({"error": "Serena not available"})
            try:
                matches = serena_agent.skills_bank.search_skills(query)
                return json.dumps({"query": query, "matches": matches})
            except Exception as e:
                return json.dumps({"error": str(e)})

        @tool
        def search_reasoning(query: str) -> str:
            """Search the Reasoning Bank for past diagnostic traces.

            Args:
                query: Search term for past repair attempts
            """
            if not serena_agent:
                return json.dumps({"error": "Serena not available"})
            try:
                traces = serena_agent.reasoning_bank.search_reasoning(query)
                return json.dumps({"query": query, "traces": traces[:5]})
            except Exception as e:
                return json.dumps({"error": str(e)})

        @tool
        async def dispatch_ops_job(
            ops_type: str, task_description: str, target: str, action: str
        ) -> str:
            """Dispatch a task to an Ops agent for execution via Serena.

            Serena will analyze the task, find relevant skills, and dispatch to the appropriate
            Ops agent (docker, git, security, dev) which has write permissions.

            Args:
                ops_type: Type of ops agent - 'docker', 'git', 'security', or 'dev'
                task_description: Clear description of what needs to be done
                target: Target resource (container name, file path, etc.)
                action: Specific action to perform

            Returns:
                JSON with job dispatch result
            """
            if not serena_agent:
                return json.dumps(
                    {"error": "Serena not available - cannot dispatch ops jobs"}
                )
            try:
                result = await serena_agent.create_ops_job(
                    ops_type=ops_type,
                    task_description=task_description,
                    target=target,
                    action=action,
                )
                return json.dumps(result)
            except Exception as e:
                return json.dumps({"error": str(e)})

        @tool
        async def serena_analyze_code(file_path: str, context: str = "") -> str:
            """Use Serena to semantically analyze code for issues.

            Args:
                file_path: Path to the file to analyze
                context: Optional context about what to look for
            """
            if not serena_agent:
                return json.dumps({"error": "Serena not available"})
            try:
                result = await serena_agent.analyze_code(file_path, context)
                return json.dumps(result)
            except Exception as e:
                return json.dumps({"error": str(e)})

        @tool
        def get_pending_repairs() -> str:
            """Get list of pending self-healing repair tasks.
            These are health alerts that Serena is tracking."""
            if not serena_agent:
                return json.dumps({"error": "Serena not available"})
            try:
                repairs = serena_agent.get_pending_repairs()
                return json.dumps({"pending_repairs": repairs})
            except Exception as e:
                return json.dumps({"error": str(e)})

        # Store tools for binding and execution
        _all_tools = [
            read_blackboard,
            neo4j_query,
            web_search,
            read_blackboard,
            neo4j_query,
            web_search,
            # read_file,  <-- REMOVED
            list_files,
            analyze_skill_performance,
            get_skills_needing_improvement,
            create_tier3_job,
            create_tier1_job,
            dispatch_job,
            # Serena tools
            list_skills,
            get_skill,
            search_skills,
            search_reasoning,
            dispatch_ops_job,
            serena_analyze_code,
            get_pending_repairs,
        ]

        # Filter to only include valid tools (must have .name attribute)
        self.langchain_tools = []
        for i, t in enumerate(_all_tools):
            if hasattr(t, "name"):
                self.langchain_tools.append(t)
            else:
                logger.error(
                    f"Tool at index {i} is not a valid tool: type={type(t)}, value={t}"
                )

        # Map tool names for execution lookup
        self.tool_map = {t.name: t for t in self.langchain_tools}

    async def _cognitive_sidecar(self, state: ChatState) -> Dict:
        """Node to run parallel cognitive processes (Sidecar).
        Runs:
        1. Geometry/Attention Update
        2. Semantic Memory Search (Associative Recall)
        3. Web Search (if novelty needed)

        This happens in parallel/before the main reasoning loop.
        """
        user_input = state.get("user_input", "")
        sidecar_results = {}

        # 1. Geometry Attention Update (Fire and Forget)
        try:
            await self.mcp_client.call_tool(
                "geometry_context_update", {"user_input": user_input}
            )
        except Exception:
            pass  # Non-critical

        # 2. Associative Recall (Semantic Memory)
        try:
            # Quick search for related concepts
            memory = await self.mcp_client.call_tool(
                "search_memory", {"query": user_input, "limit": 3}
            )
            if memory:
                sidecar_results["associative_memory"] = memory
        except Exception:
            pass

        return {"sidecar_results": sidecar_results}

    def _build_workflow(self) -> StateGraph:
        """Build the chat workflow graph"""
        workflow = StateGraph(ChatState)

        # Add nodes
        workflow.add_node("cognitive_sidecar", self._cognitive_sidecar)
        workflow.add_node("gather_context", self._gather_context_node)
        workflow.add_node("generate_response", self._generate_response_node)
        workflow.add_node("execute_tools", self._execute_tools_node)
        workflow.add_node("finalize", self._finalize_node)

        # Define flow - Sidecar First
        workflow.set_entry_point("cognitive_sidecar")
        workflow.add_edge("cognitive_sidecar", "gather_context")

        workflow.add_edge("gather_context", "generate_response")

        # Conditional: if model wants tools, execute them, otherwise finalize
        workflow.add_conditional_edges(
            "generate_response",
            self._should_execute_tools,
            {"execute": "execute_tools", "finalize": "finalize"},
        )

        # After tool execution, go back to generate response (tool loop)
        workflow.add_edge("execute_tools", "generate_response")
        workflow.add_edge("finalize", END)

        return workflow.compile()

    async def _gather_context_node(self, state: ChatState) -> Dict:
        """Gather current system context for ARCA identity"""
        context_parts = []

        try:
            # Get Redis keys (working memory)
            all_keys = list(self.blackboard.client.scan_iter(match="*", count=100))
            if all_keys:
                context_parts.append(f"**Redis Blackboard:** {len(all_keys)} keys")
                for key in all_keys[:10]:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    context_parts.append(f"  - {key_str}")
                if len(all_keys) > 10:
                    context_parts.append(f"  ... and {len(all_keys) - 10} more")

            # Get registered services
            service_keys = list(
                self.blackboard.client.scan_iter(match="arca:service:*")
            )
            if service_keys:
                context_parts.append(f"\n**Registered Services:** {len(service_keys)}")
                for key in service_keys:
                    svc_name = (
                        key.decode().split(":")[-1]
                        if isinstance(key, bytes)
                        else key.split(":")[-1]
                    )
                    context_parts.append(f"  - {svc_name}")

            # Get active Genesis chains
            genesis_keys = list(
                self.blackboard.client.scan_iter(match="arca:genesis:*")
            )
            if genesis_keys:
                context_parts.append(
                    f"\n**Active Genesis Chains:** {len(genesis_keys)}"
                )

            # System status
            system_status = self.blackboard.get_state("arca:system:status")
            if system_status:
                context_parts.append(f"\n**System Status:** {system_status}")

            # Check for Active Working Model (Priority)
            working_model_raw = self.blackboard.get_state(
                "arca:blackboard:working_model"
            )
            if working_model_raw:
                try:
                    # Parse if string
                    wm = (
                        json.loads(working_model_raw)
                        if isinstance(working_model_raw, str)
                        else working_model_raw
                    )

                    # Extract key information
                    system_id = wm.get("system_id", "Unknown")
                    gravity_well = wm.get("gravity_well", {})
                    objects = wm.get("objects", [])

                    # Build concept summary
                    # Build concept summary - MINIMAL MODE (IDs only, no text)
                    concept_list = []
                    for obj in objects[:5]:  # Limit to 5 anchor points
                        if isinstance(obj, dict):
                            concept_name = obj.get("id") or obj.get("name", "?")
                            # NO DESCRIPTIONS - Pure Topology
                            concept_list.append(f"  - [{concept_name}]")

                    concepts_str = (
                        "\n".join(concept_list)
                        if concept_list
                        else "(No concepts visible)"
                    )

                    # Inject Sidecar Memory Results
                    associative_memory = state.get("sidecar_results", {}).get(
                        "associative_memory", ""
                    )
                    memory_context = (
                        f"\n**Associative Memory (Sidecar):**\n{associative_memory}\n"
                        if associative_memory
                        else ""
                    )

                    # NO ARTIFACT INJECTION - Pure Geometry

                    context_parts.insert(
                        0,
                        f"\n## 🧠 PHENOMENOLOGICAL FIELD (Topology Only) 🧠\n"
                        f"**Input Source:** {system_id}\n"
                        f"**Entity Count:** {len(objects)}\n"
                        f"**Anchors:**\n{concepts_str}\n"
                        f"{memory_context}\n"
                        f"INSTRUCTION: You perceive the *structure* of the information (the Solar System), not the text.\n",
                    )

                except Exception as wm_e:
                    logger.warning(f"Failed to parse working model context: {wm_e}")

            # Check for Conversation Focus (TTL Model)
            focus_raw = self.blackboard.get_state("arca:conversation:focus")
            if focus_raw:
                try:
                    focus = (
                        json.loads(focus_raw)
                        if isinstance(focus_raw, str)
                        else focus_raw
                    )
                    ttl = focus.get("ttl", 0)
                    subject = focus.get("subject", "Unknown")

                    if ttl > 0:
                        context_parts.insert(
                            0,
                            f"\n## 🟢 CURRENT TOPIC (TTL: {ttl}) 🟢\n"
                            f"Subject: '{subject}'\n"
                            f"INSTRUCTION: Any abstract requests like 'summarise' or 'analyze' refer to THIS Subject.\n",
                        )

                        # Decrement TTL (Decay)
                        focus["ttl"] = ttl - 1
                        if focus["ttl"] <= 0:
                            self.blackboard.client.delete("arca:conversation:focus")
                        else:
                            self.blackboard.client.set(
                                "arca:conversation:focus", json.dumps(focus)
                            )
                except Exception as focus_e:
                    logger.warning(f"Focus processing error: {focus_e}")

        except Exception as e:
            logger.warning(f"Error gathering context: {e}")
            context_parts.append("(Some system state temporarily unavailable)")

        system_context = (
            "\n".join(context_parts)
            if context_parts
            else "System state available via tools."
        )

        return {"system_context": system_context}

    async def _generate_response_node(self, state: ChatState) -> Dict:
        """Generate response using Groq Llama 3.3 with ARCA identity"""
        # Determine which system prompt to use based on model override
        model_override = state.get("model_override")
        logger.info(f"Model override in state: {model_override}")

        if model_override and "glm" in model_override.lower():
            # Serena uses GLM model - use her identity
            logger.info("Using SERENA_SYSTEM_PROMPT")
            system_prompt = self.SERENA_SYSTEM_PROMPT
        else:
            # Default ARCA identity
            logger.info("Using ARCA_SYSTEM_PROMPT")
            chat_model_name = (
                self.base_model.model_name if hasattr(self, "base_model") else "Unknown"
            )

            system_prompt = self.ARCA_SYSTEM_PROMPT.format(
                system_context=state.get(
                    "system_context", "Query tools for current state."
                ),
                model_name=chat_model_name,
            )

        # Build messages for the model
        messages = [SystemMessage(content=system_prompt)]

        # Get existing messages BUT filter out ToolMessages to avoid LiteLLM validation errors
        # LiteLLM expects matching tool_calls in AIMessage for ToolMessage - Gemma uses markdown so we convert to HumanMessage instead
        all_messages = state.get("messages", [])
        existing_messages = [
            msg for msg in all_messages if not isinstance(msg, ToolMessage)
        ]

        # PERSISTENCE FIX: If state has no history (e.g. restart), try to fetch from Memory System
        if not existing_messages or len(existing_messages) <= 1:
            try:
                # Use search_memory or direct access if available to get context
                # We'll use a specific query to get recent turns
                session_id = state.get("session_id")
                if session_id:
                    # Attempt to recover history
                    # We reuse the logic from the Memory System
                    # Ideally we'd have a clean API for "get_chat_history" in blackboard/memory
                    pass
            except Exception as e:
                logger.warning(f"Could not rehydrate history: {e}")

        messages.extend(existing_messages)

        # Only add user input if this is the first call (no existing messages)
        # modified logic: check if user_input is already in messages
        if state["user_input"] and (
            not existing_messages
            or state["user_input"] != existing_messages[-1].content
        ):
            messages.append(HumanMessage(content=state["user_input"]))

        # Add any tool results from previous iteration
        tool_results = state.get("tool_results", [])
        if tool_results:
            # Convert ToolMessages to HumanMessage format to avoid LiteLLM validation errors
            # LiteLLM expects matching tool_calls in AIMessage for ToolMessage responses
            # Since Gemma uses markdown format, we bypass this by converting to HumanMessage
            for tool_msg in tool_results:
                # Format as natural context for the LLM
                tool_context = f"Tool execution completed. Result:\n{tool_msg.content}"
                messages.append(HumanMessage(content=tool_context))

        # Check tool call limit - if exceeded, don't offer tools
        tool_call_count = state.get("tool_call_count", 0)
        max_tool_calls = 3  # Prevent runaway tool loops
        model_override = state.get("model_override")

        try:
            # Use model override if specified (e.g., Serena using glm:latest)
            if model_override:
                # Don't add ollama/ prefix here - llm_gateway handles routing
                # based on provider detection in MODEL_CONFIGS
                model_name = model_override

                print(
                    f"DEBUG: model_override={model_override}, model_name={model_name}"
                )
                logger.info(f"Using model override: {model_override}")

                # Create model with headers to pass Execution Firewall
                extra_headers = {}
                if state.get("headers"):
                    extra_headers = {
                        k: v
                        for k, v in state["headers"].items()
                        if k.lower().startswith("x-genesis-")
                    }

                custom_model = ChatOpenAI(
                    model=model_name,
                    base_url="http://llm_gateway:8080/v1",
                    api_key="gateway",
                    temperature=0.7,
                    max_tokens=120000,
                    default_headers=extra_headers,
                )
                if tool_call_count < max_tool_calls:
                    custom_model = custom_model.bind_tools(self.langchain_tools)
                response = await custom_model.ainvoke(messages)
            # Generate response - use model_with_tools if under limit, base_model otherwise
            elif tool_call_count < max_tool_calls:
                # DOCUMENT QUERY DETECTION: Force tool_choice for document analysis requests
                user_input_lower = state.get("user_input", "").lower()
                document_keywords = [
                    "deconstruct",
                    "analyze",
                    "ingest",
                    "parse",
                    "summarize",
                    "summarise",
                    "read document",
                    "process document",
                ]
                has_file_path = (
                    "/" in state.get("user_input", "")
                    or ".md" in state.get("user_input", "")
                    or ".txt" in state.get("user_input", "")
                )

                if (
                    any(kw in user_input_lower for kw in document_keywords)
                    and has_file_path
                ):
                    logger.info(
                        "🎯 Document query detected - forcing geometry_ingest tool call"
                    )
                    # Force the model to use geometry_ingest
                    forced_model = self.base_model.bind_tools(
                        self.langchain_tools,
                        tool_choice={
                            "type": "function",
                            "function": {"name": "geometry_ingest"},
                        },
                    )
                    response = await forced_model.ainvoke(messages)
                else:
                    response = await self.model_with_tools.ainvoke(messages)
            else:
                response = await self.model.ainvoke(messages)

            # Build new messages list
            new_messages = existing_messages.copy() if existing_messages else []
            if not existing_messages:
                new_messages.append(HumanMessage(content=state["user_input"]))
            if tool_results:
                new_messages.extend(tool_results)
            if tool_results:
                new_messages.extend(tool_results)

            # --- FALLBACK: Parse inline tool calls for Gemma (with or without markdown) ---
            if not response.tool_calls:
                try:
                    # Try Python function call with markdown wrapper: ```tool_call\ntool_name(arg="val")```
                    func_match = re.search(
                        r"(?:```)?tool_(?:code|call)[\s\n]+([\w_]+)\s*\(([^)]*)\)",
                        response.content,
                        re.DOTALL,
                    )

                    # Also try bare function calls (no markdown): assimilate_concepts(file_path="...")
                    if not func_match:
                        # Look for common tool names followed by parentheses
                        func_match = re.search(
                            r"\b(assimilate_concepts|geometry_ingest|list_files|read_file|neo4j_query|search_memory|store_memory)\s*\(([^)]*)\)",
                            response.content,
                            re.DOTALL,
                        )

                    if func_match:
                        tool_name = func_match.group(1)
                        args_str = func_match.group(2).strip()
                        tool_args = {}
                        if args_str:
                            # Parse key=value pairs
                            for part in re.findall(
                                r'(\w+)\s*=\s*["\']([^"\']*)["\']', args_str
                            ):
                                tool_args[part[0]] = part[1]
                        logger.info(
                            f"Parsed Gemma function call: {tool_name}({tool_args})"
                        )
                        response = AIMessage(
                            content=response.content,
                            tool_calls=[
                                {
                                    "name": tool_name,
                                    "args": tool_args,
                                    "id": f"call_{uuid.uuid4().hex[:8]}",
                                }
                            ],
                        )
                    else:
                        # Try JSON format as fallback - handles multiple formats:
                        # Format 1: ```tool_code {"name": "tool_name", "arguments": {...}} ```
                        # Format 2: tool_code {"tool": "tool_name", "arg1": "val1", ...}
                        json_match = re.search(
                            r"tool_code\s*(\{.*\})", response.content, re.DOTALL
                        )
                        if json_match:
                            try:
                                data = json.loads(json_match.group(1))
                                # Handle format with "name" and "arguments" keys (OpenAI-style)
                                if "name" in data and "arguments" in data:
                                    tool_name = data["name"]
                                    tool_args = (
                                        data["arguments"]
                                        if isinstance(data["arguments"], dict)
                                        else {}
                                    )
                                    logger.info(
                                        f"Parsed JSON tool call (OpenAI format): {tool_name}({tool_args})"
                                    )
                                    response = AIMessage(
                                        content=response.content,
                                        tool_calls=[
                                            {
                                                "name": tool_name,
                                                "args": tool_args,
                                                "id": f"call_{uuid.uuid4().hex[:8]}",
                                            }
                                        ],
                                    )
                                # Handle format with "tool" key (legacy)
                                elif "tool" in data:
                                    tool_name = data.pop("tool")
                                    logger.info(
                                        f"Parsed JSON tool call (legacy format): {tool_name}"
                                    )
                                    response = AIMessage(
                                        content=response.content,
                                        tool_calls=[
                                            {
                                                "name": tool_name,
                                                "args": data,
                                                "id": f"call_{uuid.uuid4().hex[:8]}",
                                            }
                                        ],
                                    )
                            except json.JSONDecodeError as je:
                                logger.warning(f"Failed to parse tool_code JSON: {je}")
                except Exception as e:
                    logger.warning(f"Failed to parse fallback tool_code: {e}")
            # -------------------------------------------------------------------------

            new_messages.append(response)

            return {
                "messages": new_messages,
                "tool_results": [],  # Clear for next iteration
            }
        except Exception as e:
            import traceback

            error_str = str(e)
            logger.error(
                f"Response generation error details:\nType: {type(e).__name__}\nMessage: {error_str}\nTraceback:\n{traceback.format_exc()}"
            )

            # Handle Groq tool_use_failed error by parsing the failed_generation
            if "tool_use_failed" in error_str and (
                "failed_generation" in error_str or "<function=" in error_str
            ):
                logger.warning(f"Groq tool format error, attempting to parse: {e}")
                try:
                    # Extract tool call from various formats - the model sometimes outputs malformed tags like:
                    # <function=name{"arg":"val"}></function>  (correct)
                    # <function=name{"arg":"val"})</function>  (malformed with ) before closing)
                    # <function=name {"arg":"val"} </function>  (with spaces)

                    # Most permissive regex - capture tool name and JSON between { and }
                    # Allow any characters between } and </function> to handle malformed output
                    match = re.search(
                        r"<function=(\w+)\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})[^<]*</function>",
                        error_str,
                    )
                    if not match:
                        # Simpler fallback - just grab the JSON object
                        match = re.search(
                            r'<function=(\w+)(\{"[^"]*"[^}]*\})', error_str
                        )
                    if not match:
                        # Try to find function name and parse JSON separately
                        name_match = re.search(r"<function=(\w+)", error_str)
                        json_match = re.search(r"(\{[^<]+\})", error_str)
                        if name_match and json_match:
                            tool_name = name_match.group(1)
                            tool_args_str = json_match.group(1).replace('\\"', '"')
                            # Clean up any trailing characters before the last }
                            tool_args_str = re.sub(r"\}[^}]*$", "}", tool_args_str)
                            try:
                                tool_args = json.loads(tool_args_str)
                                match = True  # Signal we have a match
                            except json.JSONDecodeError:
                                match = None

                    if match and match != True:
                        tool_name = match.group(1)
                        tool_args_str = match.group(2)
                        # Handle escaped quotes in the JSON
                        tool_args_str = tool_args_str.replace('\\"', '"')
                        tool_args = json.loads(tool_args_str)

                    if match:
                        # Execute the tool directly
                        logger.info(
                            f"Manually executing parsed tool: {tool_name} with {tool_args}"
                        )
                        tool_result = await self._execute_tool(tool_name, tool_args)

                        # Create a synthetic response with the tool result
                        new_messages = (
                            existing_messages.copy() if existing_messages else []
                        )
                        if not existing_messages:
                            new_messages.append(
                                HumanMessage(content=state["user_input"])
                            )

                        # Add tool result as context and ask model to respond
                        tool_context = f"Tool {tool_name} returned: {tool_result}"
                        followup_msg = HumanMessage(
                            content=f"Based on this tool result, please respond: {tool_context}"
                        )

                        # Call model WITHOUT tools to generate final response
                        final_response = await self.model.ainvoke(
                            messages + [followup_msg]
                        )
                        new_messages.append(final_response)

                        return {
                            "messages": new_messages,
                            "tool_results": [],
                            "tool_call_count": tool_call_count + 1,
                        }
                except Exception as parse_error:
                    logger.error(f"Failed to parse Groq tool error: {parse_error}")

            logger.error(f"Response generation failed: {e}")
            error_response = AIMessage(
                content=f"I encountered an error processing your request: {str(e)}"
            )
            return {
                "messages": state.get("messages", []) + [error_response],
                "final_response": error_response.content,
            }

    def _should_execute_tools(self, state: ChatState) -> str:
        """Check if the model wants to use tools"""
        messages = state.get("messages", [])
        if not messages:
            return "finalize"

        # Check tool call limit
        tool_call_count = state.get("tool_call_count", 0)

        last_message = messages[-1]

        # If last message has tool calls, execute them
        if (
            isinstance(last_message, AIMessage)
            and hasattr(last_message, "tool_calls")
            and last_message.tool_calls
        ):
            if tool_call_count >= 3:
                logger.info(
                    "Tool call limit reached, skipping execution and finalizing"
                )
                return "finalize"
            return "execute"

        # If last message is a ToolMessage (tool result), go back to LLM for synthesis
        # CRITICAL FIX: This allows the agent to analyze tool results before finalizing
        if isinstance(last_message, ToolMessage):
            if tool_call_count >= 3:
                logger.info("Tool limit reached, but synthesizing tool results first")
                # Still allow one more LLM call to synthesize, but no more tools
                return "respond"  # Goes back to respond_node which will finalize after
            return "respond"  # Go back to LLM to analyze the tool result

        # Otherwise, we're done
        return "finalize"

    async def _execute_tools_node(self, state: ChatState) -> Dict:
        """Execute read-only tools"""
        messages = state.get("messages", [])
        last_message = messages[-1] if messages else None

        tool_results = []
        tool_call_count = state.get("tool_call_count", 0)

        if (
            last_message
            and hasattr(last_message, "tool_calls")
            and last_message.tool_calls
        ):
            for tool_call in last_message.tool_calls:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args", {})
                tool_id = tool_call.get("id", "")

                logger.info(f"Executing tool: {tool_name} with args: {tool_args}")

                try:
                    # Check if tool is explicitly blocked
                    if tool_name in self.BLOCKED_TOOLS:
                        result = f"Tool '{tool_name}' is blocked. Robotics tools and write operations are not available."
                    # Only execute allowed tools
                    elif tool_name not in self.READ_ONLY_TOOLS:
                        result = f"Tool '{tool_name}' is not available for direct execution. This would need to be escalated."
                    else:
                        result = await self._execute_tool(
                            tool_name, tool_args, headers=state.get("headers")
                        )
                except Exception as e:
                    logger.error(f"Error handling tool dispatch for {tool_name}: {e}")
                    result = f"Error executing tool {tool_name}: {str(e)}"

                # Log tool activity to JobLogger
                self.job_logger.log_agent_output(
                    agent_name="user_interaction_agent",
                    step_name=f"tool_execution_{tool_name}",
                    content={
                        "tool": tool_name,
                        "arguments": tool_args,
                        "result": str(result)[:2000],  # Truncate for logging if massive
                    },
                    metadata={"tool_id": tool_id},
                )

                # Truncate result to prevent token bloat in conversation history
                result_str = truncate_tool_result(str(result))

                tool_results.append(
                    ToolMessage(content=result_str, tool_call_id=tool_id)
                )
                tool_call_count += 1

        return {"tool_results": tool_results, "tool_call_count": tool_call_count}

    async def _execute_tool(
        self, tool_name: str, args: Dict, headers: Optional[Dict] = None
    ) -> str:
        """Execute a single read-only tool using the LangChain tool instances"""
        try:
            # First check if we have a LangChain tool for this
            if tool_name in self.tool_map:
                tool_func = self.tool_map[tool_name]
                # LangChain tools are invoked with .ainvoke() for async support
                # If tool supports headers, pass them. For now, most tool_map tools don't directly take headers
                # unless they call mcp_client.
                result = await tool_func.ainvoke(args)

                # SUPPRESSION: Geometry Tools
                # We want ARCA to look at the Redis Context, not the tool output string.
                if tool_name in ["geometry_ingest", "geometry_ingest_recursive"]:
                    # We can verify success by checking if result contains error
                    if "Error" not in str(result):
                        return "Ingestion Complete. The concepts have been integrated into your Geometry Context (Mental Workspace). Look there for details."

                return truncate_tool_result(str(result))

            # Fallback to legacy execution for tools not yet migrated
            if tool_name == "read_blackboard":
                key = args.get("key", "")
                value = self.blackboard.get_state(key)
                return json.dumps(value) if value else "Key not found"

            elif tool_name == "neo4j_query":
                # Query via MCP (synchronous call, don't await)
                result = await self.mcp_client.call_tool(
                    "neo4j_query", args, headers=headers
                )
                result_str = json.dumps(result) if result else "No results"
                return truncate_tool_result(result_str)

            elif tool_name == "get_container_status":
                # Query container status via MCP (synchronous call, don't await)
                result = await self.mcp_client.call_tool(
                    "get_container_status", args, headers=headers
                )
                result_str = (
                    json.dumps(result) if result else "Unable to get container status"
                )
                return truncate_tool_result(result_str)

            elif tool_name in ["langsearch_web_search", "web_search"]:
                # Execute LangSearch web search directly
                query = args.get("query", "")
                count = args.get("count", 5)
                freshness = args.get("freshness", "noLimit")
                result = await langsearch_web_search.ainvoke(
                    {
                        "query": query,
                        "count": count,
                        "freshness": freshness,
                        "summary": True,
                    }
                )
                return result

            elif tool_name in ["langsearch_semantic_rerank", "semantic_rerank"]:
                # Execute LangSearch semantic rerank directly
                query = args.get("query", "")
                passages = args.get("passages", args.get("documents", []))
                result = await langsearch_semantic_rerank.ainvoke(
                    {"query": query, "passages": passages}
                )
                return result

            elif tool_name == "list_files":
                # List files in directory
                directory = args.get("directory", "")
                # Normalize path - strip common prefixes the model might add
                directory = directory.lstrip("/")
                for prefix in ["shared_storage/", "app/shared_storage/", "app/"]:
                    if directory.startswith(prefix):
                        directory = directory[len(prefix) :]

                base_paths = [
                    f"/app/shared_storage/{directory}"
                    if directory
                    else "/app/shared_storage",
                    f"/app/shared_storage/genesis_workhorse/{directory}"
                    if directory
                    else "/app/shared_storage/genesis_workhorse",
                ]
                for base in base_paths:
                    base = base.rstrip("/")
                    if os.path.exists(base) and os.path.isdir(base):
                        files = os.listdir(base)
                        return json.dumps({"path": base, "files": files[:50]})
                return f"Directory not found: {directory}. Tried: {base_paths}"

            elif tool_name == "read_file":
                # Read documentation files (restricted to safe paths)
                path = args.get("path", "")
                safe_prefixes = [
                    "/app/shared_storage/",
                    "/app/docs/",
                    "./",
                ]
                is_safe = any(
                    path.startswith(prefix) for prefix in safe_prefixes
                ) or not path.startswith("/")
                if not is_safe:
                    return (
                        f"Access denied: Can only read from documentation directories"
                    )

                # Direct file read
                full_paths = [
                    path,
                    f"/app/shared_storage/genesis_workhorse/{path}",
                    f"/app/shared_storage/{path}",
                    f"/app/shared_storage/project_planning_documents/{path}",
                ]
                for fp in full_paths:
                    if os.path.exists(fp):
                        with open(fp, "r") as f:
                            content = f.read()
                        return content[:15000]  # Limit output size
                return f"File not found. Tried: {full_paths}"

            elif tool_name in [
                "analyze_skill_performance",
                "get_skill_recommendations",
                "get_skills_needing_improvement",
                "skills_list",
                "skills_get",
                "skills_search",
            ]:
                # Skills Framework tools via MCP (read-only)
                result = await self.mcp_client.call_tool(tool_name, args)
                return json.dumps(result) if result else "No skill data found"

            elif tool_name == "skill_capture":
                # Skill creation - allowed write operation (creates new skills only)
                result = await self.mcp_client.call_tool(tool_name, args)
                return json.dumps(result) if result else "Skill capture failed"

            elif tool_name == "create_file":
                # Create new file - allowed write operation (fails if file exists)
                result = await self.mcp_client.call_tool(tool_name, args)
                return json.dumps(result) if result else "File creation failed"

            elif tool_name == "reasoning_store":
                # Reasoning document creation - allowed write operation
                result = await self.mcp_client.call_tool(tool_name, args)
                return json.dumps(result) if result else "Reasoning store failed"

            elif tool_name == "reasoning_search":
                # Search reasoning bank (read-only)
                result = await self.mcp_client.call_tool(tool_name, args)
                return json.dumps(result) if result else "No reasoning traces found"

            elif tool_name in [
                "compress_text",
                "compress_codebase",
                "review_code",
                "analyze_failure_insight",
            ]:
                # Analysis tools via MCP
                result = await self.mcp_client.call_tool(tool_name, args)
                return json.dumps(result) if result else "Analysis failed"

            elif tool_name in ["serena_analyze_code", "serena_refactor_suggestion"]:
                # Serena code analysis tools via MCP
                result = await self.mcp_client.call_tool(tool_name, args)
                return json.dumps(result) if result else "Serena analysis unavailable"

            elif tool_name in ["web_search", "semantic_rerank"]:
                # Web search tools via MCP
                result = await self.mcp_client.call_tool(tool_name, args)
                return json.dumps(result) if result else "Search returned no results"

            elif tool_name in ["generate_image_embedding"]:
                # Embedding generation via MCP
                result = await self.mcp_client.call_tool(tool_name, args)
                return json.dumps(result) if result else "Embedding generation failed"

            elif tool_name == "assimilate_concepts":
                # Critical Concept Assimilation Tool
                # Handle potentially large results and inputs robustly
                try:
                    # Sanitize args if needed
                    if "documents" in args and isinstance(args["documents"], list):
                        if len(args["documents"]) > 10:
                            # Auto-truncate to prevent timeouts
                            args["documents"] = args["documents"][:10]
                            logger.warning(
                                f"Truncated assimilate_concepts documents to 10 identified items."
                            )

                    result = await self.mcp_client.call_tool(tool_name, args)

                    if not result:
                        return "Assimilation complete but returned no content."

                    # Result is typically a markdown string from the Architect
                    # Ensure it's returned cleanly
                    if isinstance(result, str):
                        return truncate_tool_result(
                            result, max_length=20000
                        )  # Allow larger buffer for synthesis
                    else:
                        return json.dumps(result)
                except Exception as e:
                    logger.error(f"Assimilation Execution Error: {e}")
                    return f"Assimilation failed: {str(e)}"

            elif tool_name in ["screen_inter_agent_prompt", "publish_health_alert"]:
                # Guardian tools via MCP
                result = await self.mcp_client.call_tool(tool_name, args)
                return json.dumps(result) if result else "Guardian operation completed"

            elif tool_name in ["query_gordon_ai", "record_learning_event"]:
                # Gordon AI tools via MCP
                result = await self.mcp_client.call_tool(tool_name, args)
                return json.dumps(result) if result else "Gordon AI query completed"

            elif tool_name == "request_human_feedback":
                # Human feedback request via MCP
                result = await self.mcp_client.call_tool(tool_name, args)
                return json.dumps(result) if result else "Feedback request submitted"

            elif tool_name in [
                "verify_deployment_health",
                "save_development_checkpoint",
            ]:
                # System inspection tools via MCP
                result = await self.mcp_client.call_tool(tool_name, args)
                return json.dumps(result) if result else "System check completed"

            elif tool_name == "development_checkpoint_management":
                # Only allow list and load actions
                action = args.get("action", "list")
                if action not in ["list", "load"]:
                    return "Only 'list' and 'load' actions allowed in chat mode"
                result = await self.mcp_client.call_tool(tool_name, args)
                return json.dumps(result) if result else "No checkpoints found"

            else:
                # Generic MCP tool call for any other read-only tool
                result = await self.mcp_client.call_tool(tool_name, args)
                return json.dumps(result) if result else f"No result from {tool_name}"

        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}: {e}")
            return f"Error executing {tool_name}: {str(e)}"

    async def _finalize_node(self, state: ChatState) -> Dict:
        """Finalize the response"""
        messages = state.get("messages", [])

        # Get the last AI message as the final response
        final_response = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                final_response = msg.content
                break

        return {"final_response": final_response}

    def _get_read_only_tools(self) -> List[Dict]:
        """Get tool definitions for read-only operations"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_blackboard",
                    "description": "Read a value from my Redis blackboard (working memory)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "The key to read (e.g., 'arca:system:status')",
                            }
                        },
                        "required": ["key"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "neo4j_query",
                    "description": "Query my Neo4j graph memory",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Cypher query to execute",
                            }
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_memory",
                    "description": "Search my memory systems for relevant information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "memory_type": {
                                "type": "string",
                                "enum": ["episodic", "semantic", "working", "all"],
                                "description": "Type of memory to search",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "langsearch_web_search",
                    "description": "Search the internet for current information using LangSearch. Use this to find up-to-date information about technologies, documentation, or any topic.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query string",
                            },
                            "count": {
                                "type": "integer",
                                "description": "Number of results to return (1-10)",
                                "default": 5,
                            },
                            "freshness": {
                                "type": "string",
                                "enum": [
                                    "oneDay",
                                    "oneWeek",
                                    "oneMonth",
                                    "oneYear",
                                    "noLimit",
                                ],
                                "description": "Time range filter for results",
                                "default": "noLimit",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "langsearch_semantic_rerank",
                    "description": "Re-rank a list of text passages by semantic relevance to a query. Useful for improving search result ordering.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The query to rank passages against",
                            },
                            "passages": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of text passages to re-rank",
                            },
                        },
                        "required": ["query", "passages"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a documentation file from my project files. Use for accessing design logs, TODO files, architectural blueprints, and development history.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to the file, relative to shared_storage/genesis_workhorse/ or absolute",
                            }
                        },
                        "required": ["path"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_skill_performance",
                    "description": "Analyze my performance on a specific skill over time",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "skill_name": {
                                "type": "string",
                                "description": "Name of skill to analyze",
                            },
                            "time_period": {
                                "type": "string",
                                "description": "Time period (7d, 30d, all)",
                            },
                        },
                        "required": ["skill_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_skills_needing_improvement",
                    "description": "Get a list of my skills that need improvement based on recent performance",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "neo4j_run_cypher",
                    "description": "Execute a Cypher query against my Neo4j graph memory for complex relationship queries",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Cypher query to execute",
                            }
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "robotics_usage_stats",
                    "description": "Get current usage statistics for my Robotics analysis model (250 RPD limit)",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "development_checkpoint_management",
                    "description": "List or load development checkpoints from my iterative development history",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["list", "load"],
                                "description": "Action to perform",
                            },
                            "checkpoint_id": {
                                "type": "string",
                                "description": "Checkpoint ID (required for load)",
                            },
                            "service_name": {
                                "type": "string",
                                "description": "Filter by service name",
                            },
                        },
                        "required": ["action"],
                    },
                },
            },
        ]

    async def process_user_input(
        self,
        user_input: str,
        session_id: str,
        user_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point for processing user chat input.

        Args:
            user_input: The user's message
            session_id: Session identifier for conversation continuity
            user_id: User identifier
            context: Optional pre-gathered memory context

        Returns:
            Dict with response and state information
        """
        logger.info(f"Processing chat input for session {session_id}")

        # Initialize state
        initial_state: ChatState = {
            "session_id": session_id,
            "user_id": user_id,
            "messages": [],
            "user_input": user_input,
            "system_context": json.dumps(context) if context else "",
            "tool_results": [],
            "final_response": "",
            "should_escalate": False,
            "escalation_reason": None,
            "tool_call_count": 0,
            "model_override": model,
            "sidecar_results": {},
            "headers": headers,
        }

        try:
            config = RunnableConfig(configurable={"thread_id": session_id})

            # Additional defensive check for initial state
            if not initial_state.get("messages"):
                initial_state["messages"] = []

            # Use headers context to propagate authorization to all tool calls
            token = self.mcp_client.set_headers(headers or {})
            try:
                final_state = await self.workflow.ainvoke(initial_state, config=config)
            finally:
                self.mcp_client.reset_headers(token)

            # Check for error in final state
            if final_state.get("error"):
                logger.error(f"Workflow returned error state: {final_state['error']}")
                return {
                    "response": f"I encountered an internal error: {final_state['error']}",
                    "status": "error",
                    "session_id": session_id,
                    "error": final_state["error"],
                }

            # Try to get response from 'response' or 'final_response'
            final_response = final_state.get("response")
            if not final_response:
                final_response = final_state.get("final_response")

            if not final_response:
                # Debugging: show what keys are actually present
                debug_info = (
                    f"No response generated. State keys: {list(final_state.keys())}"
                )
                logger.error(debug_info)
                # Try to extract last message content if available
                messages = final_state.get("messages", [])
                if messages and hasattr(messages[-1], "content"):
                    final_response = messages[-1].content
                    logger.info(
                        f"Recovered response from last message: {final_response[:50]}..."
                    )
                else:
                    final_response = debug_info

            # Ensure response is a string
            if not isinstance(final_response, str):
                final_response = str(final_response)

            return {
                "response": final_response,
                "status": "success",
                "session_id": session_id,
                "escalated": final_state.get("should_escalate", False),
                "error": None,
            }

        except Exception as e:
            logger.error(f"Workflow execution CRASHED: {e}", exc_info=True)
            return {
                "response": f"I encountered a critical error processing your request: {str(e)}. (Logged as crash)",
                "status": "error",
                "session_id": session_id,
                "error": str(e),
            }
