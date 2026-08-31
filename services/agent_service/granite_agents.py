import logging
import json
import os
from typing import Dict, Any, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph_agent import LocalLLMWrapper
from redis_blackboard import RedisBlackboard

logger = logging.getLogger(__name__)

class GraniteAgent:
    """Base class for Granite 1B agents."""
    def __init__(self, role: str, system_prompt: str, blackboard: RedisBlackboard):
        self.role = role
        self.system_prompt = system_prompt
        self.blackboard = blackboard
        # Connect to the vLLM server hosting Granite 1B
        self.llm = LocalLLMWrapper(
            base_url=os.getenv("GRANITE_API_URL", "http://vllm-server:8000/v1"),
            model=os.getenv("GRANITE_MODEL_NAME", "granite-4.0-1b"),
            api_key="dummy"
        )

    async def process(self, task: str, context: Dict[str, Any] = None) -> str:
        """Process a task using the Granite model."""
        logger.info(f"[{self.role}] Processing task: {task}")
        
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"Context: {json.dumps(context) if context else 'None'}\n\nTask: {task}")
        ]
        
        try:
            response = await self.llm.ainvoke(messages)
            result = response.content
            logger.info(f"[{self.role}] Result: {result[:100]}...")
            return result
        except Exception as e:
            logger.error(f"[{self.role}] Error: {e}")
            return f"Error: {str(e)}"

class GraniteRouter(GraniteAgent):
    """
    The Granite Router - File Delivery Only.
    
    This router ONLY delivers pre-generated JSON job files to RabbitMQ.
    It does NOT process content or generate prompts.
    
    Workflow:
    1. UI Agent generates job JSON file -> saves to /app/shared_storage/jobs/
    2. User says "Execute Tier X job. File: <filename>. Note: <note>"
    3. Router parses command, validates file exists, publishes to RabbitMQ
    
    Why Granite 1B is perfect: Small, fast, only needs to understand JSON formatting.
    """
    def __init__(self, blackboard: RedisBlackboard):
        super().__init__(
            role="granite_router",
            system_prompt="""You are the ARCA Router. Your ONLY job is to deliver pre-generated JSON job files to RabbitMQ.

CRITICAL: You do NOT generate content. You do NOT answer questions. You ONLY route files.

Input Format (from user):
- "Execute Tier 3 job. File: genesis_v1.json. Note: Initialize System."
- "Execute Tier 1 job. File: docker_restart.json"
- "Route job: tier3_1733443200_a1b2c3d4.json"

Output Format (ALWAYS this exact structure):
```json
{
  "tier": 3,
  "routing_key": "tier3.architect.genesis",
  "payload": {
    "type": "file_ref",
    "path": "/app/shared_storage/jobs/<filename>",
    "user_note": "<note from user>"
  }
}
```

Routing Key Rules:
- Tier 3 jobs: tier3.architect.genesis, tier3.architect.design, tier3.architect.analysis
- Tier 1 jobs: tier1.engineer.implement, tier1.ops.docker, tier1.ops.git, tier1.reviewer.validate

If no file is specified or file doesn't exist, respond with:
```json
{"error": "No job file specified or file not found", "action": "none"}
```

NEVER summarize. NEVER explain. ONLY output JSON.""",
            blackboard=blackboard
        )
    
    async def route_job_file(self, job_filename: str, user_note: str = "") -> Dict[str, Any]:
        """
        Route a job file directly without LLM processing.
        This is the preferred method - bypasses Granite for pure file routing.
        """
        import os
        import json
        
        # Build full path
        jobs_dir = "/app/shared_storage/jobs"
        job_path = os.path.join(jobs_dir, job_filename)
        
        # Validate file exists
        if not os.path.exists(job_path):
            return {"error": f"Job file not found: {job_path}", "action": "none"}
        
        # Load job to get routing info
        try:
            with open(job_path, 'r') as f:
                job = json.load(f)
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON in job file: {e}", "action": "none"}
        
        # Build router payload
        return {
            "tier": job.get("tier", 3),
            "routing_key": job.get("routing_key", "tier3.architect.design"),
            "payload": {
                "type": "file_ref",
                "path": job_path,
                "user_note": user_note or job.get("metadata", {}).get("user_note", "")
            }
        }

class DockerMaintainer(GraniteAgent):
    """
    Docker Maintainer.
    Handles Docker SOPs and operations.
    """
    def __init__(self, blackboard: RedisBlackboard):
        super().__init__(
            role="docker_maintainer",
            system_prompt="""You are the Docker Maintainer.
Your role is to manage Docker containers and services.
You follow Standard Operating Procedures (SOPs) for deployment, health checks, and logs.
You have access to shared memory at /app/shared_data.""",
            blackboard=blackboard
        )

class SecurityMaintainer(GraniteAgent):
    """
    Security Maintainer.
    Handles Security SOPs.
    """
    def __init__(self, blackboard: RedisBlackboard):
        super().__init__(
            role="sec_maintainer",
            system_prompt="""You are the Security Maintainer.
Your role is to enforce security policies and perform audits.
You monitor for vulnerabilities and unauthorized access.
You have access to shared memory at /app/shared_data.""",
            blackboard=blackboard
        )

class GitMaintainer(GraniteAgent):
    """
    Git Maintainer.
    Handles Git SOPs and operations.
    """
    def __init__(self, blackboard: RedisBlackboard):
        super().__init__(
            role="git_maintainer",
            system_prompt="""You are the Git Maintainer.
Your role is to manage the git repository, branches, and commits.
You ensure version control best practices are followed.
You have access to shared memory at /app/shared_data.""",
            blackboard=blackboard
        )

class DevelopmentMaintainer(GraniteAgent):
    """
    Development Maintainer.
    Handles file operations and development SOPs.
    """
    def __init__(self, blackboard: RedisBlackboard):
        super().__init__(
            role="dev_maintainer",
            system_prompt="""You are the Development Maintainer.
Your role is to manage project files, directories, and code structure.
You assist with refactoring and code organization.
You have access to shared memory at /app/shared_data.""",
            blackboard=blackboard
        )

# Factory to create all agents
def create_granite_agents(blackboard: RedisBlackboard) -> Dict[str, GraniteAgent]:
    return {
        "router": GraniteRouter(blackboard),
        "docker": DockerMaintainer(blackboard),
        "security": SecurityMaintainer(blackboard),
        "git": GitMaintainer(blackboard),
        "dev": DevelopmentMaintainer(blackboard)
    }
