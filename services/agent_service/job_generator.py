"""
ARCA Job Generator
Utility for creating standardized Tier 1 and Tier 3 job JSON files.

Used by:
- user_interaction_agent: Generate prompt files for Granite Router
- Development Maintainer: Create deployment/operation jobs
- Any agent needing to dispatch work to the tiered system

The generated JSON files are saved to /app/shared_storage/jobs/ and
referenced by the Granite Router for RabbitMQ dispatch.
"""

import os
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Literal
from dataclasses import dataclass, asdict
from pathlib import Path

import logging
logger = logging.getLogger(__name__)

# Base paths
SHARED_STORAGE = os.environ.get("SHARED_STORAGE_PATH", "/app/shared_storage")
JOBS_DIR = os.path.join(SHARED_STORAGE, "jobs")
PROMPTS_DIR = os.path.join(SHARED_STORAGE, "prompts")

# Ensure directories exist
os.makedirs(JOBS_DIR, exist_ok=True)
os.makedirs(PROMPTS_DIR, exist_ok=True)


@dataclass
class Tier3Job:
    """
    Tier 3 Job (High Council) - For complex analysis and architecture tasks.
    
    Target Agents:
    - Architect (Gemini 2.5 Pro)
    - Structural Analyst (Gemini Robotics)
    - Context Compressor (Gemini Flash)
    """
    objective: str
    task_category: Literal[
        "genesis_initialization",
        "system_architecture", 
        "infrastructure_design",
        "security_architecture",
        "integration_design",
        "migration_planning",
        "disaster_recovery"
    ]
    routing_key: Literal[
        "tier3.architect.genesis",
        "tier3.architect.design",
        "tier3.architect.analysis",
        "tier3.structural_analyst.verify"
    ] = "tier3.architect.design"
    
    # Context
    current_state: str = ""
    dependencies: List[str] = None
    related_systems: List[str] = None
    
    # Constraints and criteria
    constraints: List[str] = None
    success_criteria: List[str] = None
    output_format: Literal["cypher_schema", "architecture_doc", "design_spec", "migration_plan", "json_response"] = "json_response"
    
    # Metadata
    priority: Literal["critical", "high", "normal", "low"] = "normal"
    timeout_seconds: int = 300
    user_note: str = ""
    session_id: str = ""
    
    # Cascade settings
    auto_cascade: bool = True
    
    # Content (optional - for inline text jobs)
    inline_content: str = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []
        if self.related_systems is None:
            self.related_systems = []
        if self.constraints is None:
            self.constraints = []
        if self.success_criteria is None:
            self.success_criteria = []


@dataclass
class Tier1Job:
    """
    Tier 1 Job (Body) - For tool execution and implementation tasks.
    
    Target Agents:
    - Engineer (Cohere)
    - Reviewer (Gemma 27B)
    - Ops Controller (Local Granite)
    - Local Executor (Granite 1B)
    """
    action: Literal[
        "create_file",
        "modify_file",
        "delete_file",
        "read_file",
        "execute_cypher",
        "execute_script",
        "docker_build",
        "docker_deploy",
        "docker_restart",
        "git_commit",
        "git_push",
        "git_pull",
        "set_secret",
        "verify_health",
        "run_tests",
        "execute_mcp_tool"
    ]
    target: str  # File path, container name, etc.
    task_category: Literal[
        "code_implementation",
        "code_review",
        "docker_operation",
        "git_operation",
        "file_operation",
        "database_operation",
        "security_operation",
        "deployment",
        "tool_execution",
        "genesis_execution"
    ]
    routing_key: Literal[
        "tier1.engineer.implement",
        "tier1.engineer.genesis",
        "tier1.reviewer.validate",
        "tier1.ops.deploy",
        "tier1.ops.docker",
        "tier1.ops.git",
        "tier1.ops.security",
        "tier1.executor.run"
    ] = "tier1.engineer.implement"
    
    # Action parameters
    parameters: Dict[str, Any] = None
    
    # MCP tools to use
    mcp_tools: List[Dict[str, Any]] = None
    
    # Validation
    validation_method: Literal["health_check", "file_exists", "command_output", "api_response"] = None
    validation_expected: str = None
    
    # Rollback
    rollback_action: str = None
    rollback_target: str = None
    
    # Metadata
    priority: Literal["critical", "high", "normal", "low"] = "normal"
    timeout_seconds: int = 120
    user_note: str = ""
    session_id: str = ""
    parent_job_id: str = None
    requires_approval: bool = False
    
    # Execution control
    dry_run: bool = False
    stop_on_error: bool = True
    retry_count: int = 0
    
    # Content (optional - for inline text jobs)
    inline_content: str = None
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}
        if self.mcp_tools is None:
            self.mcp_tools = []


class JobGenerator:
    """
    Generates standardized job JSON files for the ARCA tiered agent system.
    
    Usage:
        generator = JobGenerator()
        
        # Create a Tier 3 job
        job_path = generator.create_tier3_job(
            objective="Initialize ARCA system",
            task_category="genesis_initialization",
            routing_key="tier3.architect.genesis",
            priority="critical",
            user_note="Run Genesis Protocol"
        )
        
        # Create a Tier 1 job  
        job_path = generator.create_tier1_job(
            action="docker_restart",
            target="agent_service",
            task_category="docker_operation",
            priority="high"
        )
    """
    
    def __init__(self, jobs_dir: str = JOBS_DIR, prompts_dir: str = PROMPTS_DIR):
        self.jobs_dir = jobs_dir
        self.prompts_dir = prompts_dir
        os.makedirs(self.jobs_dir, exist_ok=True)
        os.makedirs(self.prompts_dir, exist_ok=True)
    
    def _generate_job_id(self, tier: int) -> str:
        """Generate unique job ID"""
        timestamp = int(datetime.now().timestamp())
        short_uuid = uuid.uuid4().hex[:8]
        return f"tier{tier}_{timestamp}_{short_uuid}"
    
    def _get_timestamp(self) -> str:
        """Get ISO 8601 timestamp"""
        return datetime.utcnow().isoformat() + "Z"
    
    def create_tier3_job(
        self,
        objective: str,
        task_category: str,
        routing_key: str = "tier3.architect.design",
        current_state: str = "",
        dependencies: List[str] = None,
        related_systems: List[str] = None,
        constraints: List[str] = None,
        success_criteria: List[str] = None,
        output_format: str = "json_response",
        priority: str = "normal",
        timeout_seconds: int = 300,
        user_note: str = "",
        session_id: str = None,
        auto_cascade: bool = True,
        inline_content: str = None,
        prompt_file_content: str = None
    ) -> str:
        """
        Create a Tier 3 job JSON file.
        
        Args:
            objective: Primary goal of the task
            task_category: Category of Tier 3 task
            routing_key: RabbitMQ routing key
            prompt_file_content: If provided, saves to prompts/ and references the file
            
        Returns:
            Path to the created job JSON file
        """
        job_id = self._generate_job_id(3)
        session_id = session_id or f"session_{uuid.uuid4().hex[:12]}"
        
        # Determine payload type
        if prompt_file_content:
            # Save prompt content to file
            prompt_filename = f"{job_id}_prompt.md"
            prompt_path = os.path.join(self.prompts_dir, prompt_filename)
            with open(prompt_path, 'w') as f:
                f.write(prompt_file_content)
            
            payload_type = "file_ref"
            payload_path = f"/app/shared_storage/prompts/{prompt_filename}"
            payload_content = None
        elif inline_content:
            payload_type = "text"
            payload_path = None
            payload_content = inline_content
        else:
            payload_type = "text"
            payload_path = None
            payload_content = objective
        
        job = {
            "job_id": job_id,
            "tier": 3,
            "routing_key": routing_key,
            "payload": {
                "type": payload_type,
                "task_category": task_category,
                "instructions": {
                    "objective": objective,
                    "context": {
                        "current_state": current_state,
                        "dependencies": dependencies or [],
                        "related_systems": related_systems or []
                    },
                    "constraints": constraints or [],
                    "success_criteria": success_criteria or [],
                    "output_format": output_format
                }
            },
            "metadata": {
                "created_at": self._get_timestamp(),
                "created_by": "user_interaction_agent",
                "session_id": session_id,
                "priority": priority,
                "timeout_seconds": timeout_seconds,
                "user_note": user_note
            },
            "cascade": {
                "auto_cascade": auto_cascade,
                "tier2_routing_key": "tier2.planner.execute",
                "tier1_routing_key": "tier1.engineer.implement"
            }
        }
        
        # Add path or content based on type
        if payload_path:
            job["payload"]["path"] = payload_path
        if payload_content:
            job["payload"]["content"] = payload_content
        
        # Save job file
        job_filename = f"{job_id}.json"
        job_path = os.path.join(self.jobs_dir, job_filename)
        with open(job_path, 'w') as f:
            json.dump(job, f, indent=2)
        
        logger.info(f"Created Tier 3 job: {job_path}")
        return job_path
    
    def create_tier1_job(
        self,
        action: str,
        target: str,
        task_category: str,
        routing_key: str = "tier1.engineer.implement",
        parameters: Dict[str, Any] = None,
        mcp_tools: List[Dict[str, Any]] = None,
        validation_method: str = None,
        validation_expected: str = None,
        rollback_action: str = None,
        rollback_target: str = None,
        priority: str = "normal",
        timeout_seconds: int = 120,
        user_note: str = "",
        session_id: str = None,
        parent_job_id: str = None,
        requires_approval: bool = False,
        dry_run: bool = False,
        stop_on_error: bool = True,
        retry_count: int = 0,
        inline_content: str = None,
        instruction_file_content: str = None
    ) -> str:
        """
        Create a Tier 1 job JSON file.
        
        Args:
            action: Specific action to perform
            target: Target resource
            task_category: Category of Tier 1 task
            instruction_file_content: If provided, saves to prompts/ and references
            
        Returns:
            Path to the created job JSON file
        """
        job_id = self._generate_job_id(1)
        session_id = session_id or f"session_{uuid.uuid4().hex[:12]}"
        
        # Determine payload type
        if instruction_file_content:
            prompt_filename = f"{job_id}_instructions.md"
            prompt_path = os.path.join(self.prompts_dir, prompt_filename)
            with open(prompt_path, 'w') as f:
                f.write(instruction_file_content)
            
            payload_type = "file_ref"
            payload_path = f"/app/shared_storage/prompts/{prompt_filename}"
            payload_content = None
        elif inline_content:
            payload_type = "text"
            payload_path = None
            payload_content = inline_content
        else:
            payload_type = "text"
            payload_path = None
            payload_content = None
        
        # Build instructions
        instructions = {
            "action": action,
            "target": target,
            "parameters": parameters or {}
        }
        
        if validation_method:
            instructions["validation"] = {
                "method": validation_method,
                "expected": validation_expected or ""
            }
        
        if rollback_action:
            instructions["rollback"] = {
                "action": rollback_action,
                "target": rollback_target or target
            }
        
        job = {
            "job_id": job_id,
            "tier": 1,
            "routing_key": routing_key,
            "payload": {
                "type": payload_type,
                "task_category": task_category,
                "instructions": instructions,
                "mcp_tools": mcp_tools or []
            },
            "metadata": {
                "created_at": self._get_timestamp(),
                "created_by": "user_interaction_agent",
                "session_id": session_id,
                "priority": priority,
                "timeout_seconds": timeout_seconds,
                "user_note": user_note,
                "requires_approval": requires_approval
            },
            "execution": {
                "dry_run": dry_run,
                "sequential": True,
                "stop_on_error": stop_on_error,
                "retry_count": retry_count
            }
        }
        
        # Add optional fields
        if payload_path:
            job["payload"]["path"] = payload_path
        if payload_content:
            job["payload"]["content"] = payload_content
        if parent_job_id:
            job["metadata"]["parent_job_id"] = parent_job_id
        
        # Save job file
        job_filename = f"{job_id}.json"
        job_path = os.path.join(self.jobs_dir, job_filename)
        with open(job_path, 'w') as f:
            json.dump(job, f, indent=2)
        
        logger.info(f"Created Tier 1 job: {job_path}")
        return job_path
    
    def create_router_payload(self, job_path: str, user_note: str = "") -> Dict[str, Any]:
        """
        Create a router payload for the Granite Router.
        
        This is the minimal JSON that the UI agent passes to the Granite Router,
        which then publishes to RabbitMQ.
        
        Args:
            job_path: Path to the job JSON file
            user_note: Human-readable note
            
        Returns:
            Router payload dict
        """
        # Load job to get tier and routing key
        with open(job_path, 'r') as f:
            job = json.load(f)
        
        # Convert local path to container path
        container_path = job_path.replace(JOBS_DIR, "/app/shared_storage/jobs")
        
        return {
            "tier": job["tier"],
            "routing_key": job["routing_key"],
            "payload": {
                "type": "file_ref",
                "path": container_path,
                "user_note": user_note or job["metadata"].get("user_note", "")
            }
        }
    
    def list_pending_jobs(self, tier: int = None) -> List[Dict[str, Any]]:
        """List pending job files"""
        jobs = []
        for filename in os.listdir(self.jobs_dir):
            if filename.endswith('.json'):
                job_path = os.path.join(self.jobs_dir, filename)
                with open(job_path, 'r') as f:
                    job = json.load(f)
                    if tier is None or job.get("tier") == tier:
                        jobs.append({
                            "job_id": job["job_id"],
                            "tier": job["tier"],
                            "routing_key": job["routing_key"],
                            "priority": job["metadata"]["priority"],
                            "created_at": job["metadata"]["created_at"],
                            "user_note": job["metadata"].get("user_note", ""),
                            "path": job_path
                        })
        return sorted(jobs, key=lambda x: x["created_at"], reverse=True)


# Convenience functions for quick job creation
def create_genesis_job(prompt_content: str, user_note: str = "Run Genesis Protocol") -> str:
    """Quick helper to create a Genesis initialization job"""
    generator = JobGenerator()
    return generator.create_tier3_job(
        objective="Initialize ARCA system with complete knowledge graph and state",
        task_category="genesis_initialization",
        routing_key="tier3.architect.genesis",
        priority="critical",
        timeout_seconds=600,
        user_note=user_note,
        auto_cascade=True,
        prompt_file_content=prompt_content,
        dependencies=["neo4j", "redis", "oracle"],
        related_systems=["mcp_server", "embedding_service"],
        constraints=[
            "Must create all required Neo4j constraints and indexes",
            "Must initialize Redis blackboard state",
            "Must not overwrite existing data if present"
        ],
        success_criteria=[
            "Neo4j schema validated",
            "arca:state:global set in Redis",
            "All services report healthy"
        ],
        output_format="cypher_schema"
    )


# Simple helper functions for UI agent tools
def create_tier3_job(
    job_type: str,
    task_description: str,
    context: str = "",
    priority: str = "normal"
) -> Dict[str, Any]:
    """
    Simple helper for UI agent to create Tier 3 jobs.
    
    Args:
        job_type: 'genesis' or 'gnosis'
        task_description: What the task should accomplish
        context: Additional context
        priority: Job priority
        
    Returns:
        Dict with job details including job_id, routing_key, file_path
    """
    generator = JobGenerator()
    
    if job_type == "genesis":
        routing_key = "tier3.architect.genesis"
        task_category = "genesis_initialization"
    elif job_type == "gnosis":
        routing_key = "tier3.architect.gnosis"
        task_category = "system_architecture"
    else:
        routing_key = f"tier3.architect.{job_type}"
        task_category = job_type
    
    # Generate job ID for return value
    job_id = generator._generate_job_id(3)
    
    # Create the job using inline content
    file_path = generator.create_tier3_job(
        objective=task_description,
        task_category=task_category,
        routing_key=routing_key,
        priority=priority,
        current_state=context,
        inline_content=task_description
    )
    
    # Load the job to get the actual job_id
    with open(file_path, 'r') as f:
        job_data = json.load(f)
    
    return {
        "job_id": job_data["job_id"],
        "tier": 3,
        "routing_key": routing_key,
        "file_path": file_path,
        "created_at": job_data["metadata"]["created_at"]
    }


def create_tier1_job(
    maintainer_type: str,
    task_description: str,
    target_path: str = "",
    action: str = "",
    priority: str = "normal"
) -> Dict[str, Any]:
    """
    Simple helper for UI agent to create Tier 1 maintainer jobs.
    
    Args:
        maintainer_type: 'docker', 'git', 'security', 'dev'
        task_description: What the task should accomplish
        target_path: Target file or directory
        action: Specific action to perform
        priority: Job priority
        
    Returns:
        Dict with job details including job_id, routing_key, maintainer, file_path
    """
    generator = JobGenerator()
    
    # Map maintainer type to routing key and category
    maintainer_map = {
        "docker": ("tier1.maintainer.docker", "docker_operation", "docker_maintainer"),
        "git": ("tier1.maintainer.git", "git_operation", "git_maintainer"),
        "security": ("tier1.maintainer.security", "security_scan", "security_maintainer"),
        "dev": ("tier1.maintainer.dev", "development_task", "dev_maintainer")
    }
    
    if maintainer_type not in maintainer_map:
        raise ValueError(f"Unknown maintainer type: {maintainer_type}. Must be: docker, git, security, dev")
    
    routing_key, task_category, maintainer = maintainer_map[maintainer_type]
    
    file_path = generator.create_tier1_job(
        action=action or maintainer_type,
        target=target_path or "/app",
        task_category=task_category,
        routing_key=routing_key,
        priority=priority,
        inline_content=task_description,
        user_note=task_description
    )
    
    # Load the job to get the actual job_id and add maintainer field
    with open(file_path, 'r') as f:
        job_data = json.load(f)
    
    # Add maintainer field to the job file
    job_data["maintainer"] = maintainer
    job_data["payload"]["task_description"] = task_description
    job_data["payload"]["target_path"] = target_path
    job_data["payload"]["action"] = action
    
    with open(file_path, 'w') as f:
        json.dump(job_data, f, indent=2)
    
    return {
        "job_id": job_data["job_id"],
        "tier": 1,
        "routing_key": routing_key,
        "maintainer": maintainer,
        "file_path": file_path,
        "created_at": job_data["metadata"]["created_at"]
    }


def save_job(job: Dict[str, Any]) -> str:
    """
    Save a job dictionary to a file.
    
    This is a passthrough for jobs already saved by create_tier*_job functions.
    Returns the file_path from the job dict.
    
    Args:
        job: Job dictionary (must contain 'file_path' from create_tier*_job)
        
    Returns:
        Path to the job file
    """
    if "file_path" in job:
        return job["file_path"]
    
    # If job doesn't have file_path, save it now
    jobs_dir = os.path.join(SHARED_STORAGE, "jobs")
    os.makedirs(jobs_dir, exist_ok=True)
    
    job_id = job.get("job_id", f"tier{job.get('tier', 0)}_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}")
    file_path = os.path.join(jobs_dir, f"{job_id}.json")
    
    with open(file_path, 'w') as f:
        json.dump(job, f, indent=2)
    
    return file_path


def create_docker_restart_job(
    container_name: str,
    image: str = None,
    volumes: List[str] = None,
    environment: Dict[str, str] = None,
    user_note: str = ""
) -> str:
    """Quick helper to create a Docker restart job"""
    generator = JobGenerator()
    return generator.create_tier1_job(
        action="docker_restart",
        target=container_name,
        task_category="docker_operation",
        routing_key="tier1.ops.docker",
        priority="high",
        parameters={
            "image": image,
            "volumes": volumes or [],
            "environment": environment or {}
        },
        mcp_tools=[
            {"tool_name": "docker_maintainer_operation", "arguments": {"operation": "stop", "service_name": container_name}},
            {"tool_name": "docker_maintainer_operation", "arguments": {"operation": "run", "service_name": container_name}}
        ],
        validation_method="health_check",
        validation_expected="healthy",
        user_note=user_note or f"Restart {container_name}"
    )


def create_git_commit_job(
    message: str,
    files: List[str] = None,
    push: bool = True,
    user_note: str = ""
) -> str:
    """Quick helper to create a Git commit job"""
    generator = JobGenerator()
    return generator.create_tier1_job(
        action="git_commit",
        target="/home/ubuntu/ARCA",
        task_category="git_operation",
        routing_key="tier1.ops.git",
        priority="normal",
        parameters={
            "message": message,
            "files": files or ["."],
            "push": push
        },
        mcp_tools=[
            {"tool_name": "git_maintainer_operation", "arguments": {"operation": "add", "files": files or ["."]}},
            {"tool_name": "git_maintainer_operation", "arguments": {"operation": "commit", "message": message}}
        ] + ([{"tool_name": "git_maintainer_operation", "arguments": {"operation": "push"}}] if push else []),
        user_note=user_note or f"Commit: {message}"
    )
