"""
Ops Agents Configuration
========================

Configuration for Docker, Git, Security, and File maintenance agents.

- All use models from centralized model_config.py
- Have WRITE permissions within their domains
- Receive jobs from Serena via RabbitMQ
- Execute repairs using MCP skills
- Cannot touch critical services (mcp_server, redis, rabbitmq)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from enum import Enum
import os
import sys

# Add shared module to path for model_config import
sys.path.insert(0, "/shared")
sys.path.insert(0, "/app/shared")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../shared"))
try:
    from shared.model_config import (
        docker_ops_model,
        git_ops_model,
        security_ops_model,
        file_ops_model,
    )

    MODEL_CONFIG_AVAILABLE = True
    print("✅ Ops Agents: Successfully imported centralized model configuration")
except ImportError as e:
    MODEL_CONFIG_AVAILABLE = False
    print(
        f"⚠️ Ops Agents: Could not import centralized model_config, using fallbacks: {e}"
    )

    # Fallback functions
    def docker_ops_model():
        return "granite-guardian-3.1-2b"

    def git_ops_model():
        return "granite-guardian-3.1-2b"

    def security_ops_model():
        return "granite-guardian-3.1-2b"

    def file_ops_model():
        return "granite-guardian-3.1-2b"


# ============================================================================
# OTEL Configuration
# ============================================================================


@dataclass
class OTELConfig:
    """OTEL instrumentation configuration for all agents."""

    enabled: bool = True
    endpoint: str = "otel_collector:4317"  # gRPC endpoint
    service_name: str = ""  # Set by agent type
    trace_sample_rate: float = 1.0  # 100% tracing (for ops agents, we trace everything)
    metrics_enabled: bool = True
    logs_enabled: bool = True

    @classmethod
    def from_env(cls, agent_type: str) -> "OTELConfig":
        """Load OTEL config from environment."""
        return cls(
            enabled=os.getenv("OTEL_ENABLED", "true").lower() == "true",
            endpoint=os.getenv("OTEL_ENDPOINT", "otel_collector:4317"),
            service_name=f"arca_{agent_type}",
            trace_sample_rate=float(os.getenv("OTEL_TRACE_SAMPLE_RATE", "1.0")),
        )


# ============================================================================
# Agent Types
# ============================================================================


class AgentType(Enum):
    DOCKER = "docker"
    GIT = "git"
    SECURITY = "security"
    FILE = "file"


# ============================================================================
# Docker Ops Agent Configuration
# ============================================================================


@dataclass
class DockerOpsConfig:
    """Docker maintainer agent configuration."""

    # Identity
    name: str = "Docker Maintainer"
    agent_type: AgentType = AgentType.DOCKER
    description: str = "Container and Docker Compose operations for system repair"
    permissions: str = "write"

    # Model Configuration
    primary_model: str = field(default_factory=docker_ops_model)  # From model_config
    fallback_model: str = "glm:latest"
    temperature: float = 0.3  # Lower for deterministic ops
    max_tokens: int = 4096
    llm_endpoint: str = "http://llm_gateway:8080/v1/chat/completions"

    # RabbitMQ Configuration
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "arca"
    rabbitmq_vhost: str = "arca_vhost"
    rabbitmq_queue: str = "arca:ops:docker"
    rabbitmq_routing_key: str = "ops.docker.*"

    # OTEL Instrumentation
    otel: OTELConfig = field(default_factory=lambda: OTELConfig.from_env("docker"))

    # Operations Allowed
    container_operations: List[str] = field(
        default_factory=lambda: [
            "restart",
            "stop",
            "start",
            "remove",
            "rebuild",
            "logs",
            "inspect",
            "exec",
        ]
    )
    image_operations: List[str] = field(
        default_factory=lambda: ["build", "pull", "push", "tag", "remove", "inspect"]
    )
    compose_operations: List[str] = field(
        default_factory=lambda: ["up", "down", "restart", "logs", "ps"]
    )
    network_operations: List[str] = field(
        default_factory=lambda: ["list", "inspect", "create", "remove"]
    )
    volume_operations: List[str] = field(
        default_factory=lambda: ["list", "inspect", "create", "remove", "prune"]
    )

    # Security Constraints
    max_restart_attempts: int = 3
    max_build_timeout: int = 600  # seconds
    prevent_rm_running: bool = True
    require_confirmation: bool = False

    # Protected Services (Cannot Stop)
    cannot_touch: Set[str] = field(
        default_factory=lambda: {
            "mcp_server",  # Critical - needed for all repairs
            "redis",  # Health messaging
            "rabbitmq",  # Job dispatch
        }
    )

    # MCP Skills
    repair_skills: List[str] = field(
        default_factory=lambda: [
            "ARCA_DOCKER_HELPER.md",
            "CONTAINER_HOTFIX_WITHOUT_REBUILD.md",
            "ARCA_DEPLOYMENT_HEALTHCHECK.md",
        ]
    )

    @classmethod
    def from_env(cls) -> "DockerOpsConfig":
        """Load from environment."""
        return cls(
            primary_model=os.getenv("DOCKER_OPS_MODEL", "granite:latest"),
            rabbitmq_host=os.getenv("RABBITMQ_HOST", "rabbitmq"),
            rabbitmq_user=os.getenv("RABBITMQ_USER", "arca"),
        )


# ============================================================================
# Git Ops Agent Configuration
# ============================================================================


@dataclass
class GitOpsConfig:
    """Git maintainer agent configuration."""

    # Identity
    name: str = "Git Maintainer"
    agent_type: AgentType = AgentType.GIT
    description: str = "Git operations for code and configuration management"
    permissions: str = "write"

    # Model Configuration
    primary_model: str = field(default_factory=git_ops_model)  # From model_config
    fallback_model: str = "glm:latest"
    temperature: float = 0.2  # Very low for deterministic ops
    max_tokens: int = 4096
    llm_endpoint: str = "http://llm_gateway:8080/v1/chat/completions"

    # RabbitMQ Configuration
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "arca"
    rabbitmq_vhost: str = "arca_vhost"
    rabbitmq_queue: str = "arca:ops:git"
    rabbitmq_routing_key: str = "ops.git.*"

    # OTEL Instrumentation
    otel: OTELConfig = field(default_factory=lambda: OTELConfig.from_env("git"))

    # Git Configuration
    user_name: str = "ARCA-Maintainer"
    user_email: str = "arca@system.local"
    default_branch: str = "main"
    safe_mode: bool = True

    # Operations Allowed
    repository_operations: List[str] = field(
        default_factory=lambda: ["clone", "init", "status", "config"]
    )
    branch_operations: List[str] = field(
        default_factory=lambda: ["list", "create", "delete", "switch", "merge"]
    )
    commit_operations: List[str] = field(
        default_factory=lambda: ["commit", "push", "pull", "rebase", "reset"]
    )
    file_operations: List[str] = field(
        default_factory=lambda: ["add", "remove", "restore", "diff"]
    )
    log_operations: List[str] = field(
        default_factory=lambda: ["log", "show", "blame", "diff"]
    )

    # Security Constraints
    require_commit_message: bool = True
    min_commit_message_length: int = 20
    prevent_force_push_main: bool = True
    require_branch_protection: bool = True

    # Protected Paths (Cannot Modify)
    cannot_touch: Set[str] = field(
        default_factory=lambda: {
            ".github/workflows",  # Critical workflows
            "docker-compose.local.yml",  # Deployment config
        }
    )

    # Requires Confirmation
    requires_confirmation: Set[str] = field(
        default_factory=lambda: {
            "push_to_main",
            "force_operations",
            "delete_operations",
        }
    )

    # MCP Skills
    repair_skills: List[str] = field(
        default_factory=lambda: [
            "ARCA_DEPLOYMENT_HEALTHCHECK.md",
            "GITOPS_DEPLOYMENT.md",
        ]
    )

    @classmethod
    def from_env(cls) -> "GitOpsConfig":
        """Load from environment."""
        return cls(
            primary_model=os.getenv(
                "GIT_OPS_MODEL", git_ops_model()
            ),  # Use model_config default
            user_name=os.getenv("GIT_OPS_USER_NAME", "ARCA-Maintainer"),
            safe_mode=os.getenv("GIT_OPS_SAFE_MODE", "true").lower() == "true",
        )


# ============================================================================
# Security Ops Agent Configuration
# ============================================================================


@dataclass
class SecurityOpsConfig:
    """Security maintainer agent configuration."""

    # Identity
    name: str = "Security Maintainer"
    agent_type: AgentType = AgentType.SECURITY
    description: str = "Security scanning, validation, and remediation"
    permissions: str = "write"

    # Model Configuration
    primary_model: str = field(default_factory=file_ops_model)  # From model_config
    fallback_model: str = "glm:latest"
    temperature: float = 0.1  # Minimal for security ops
    max_tokens: int = 4096
    llm_endpoint: str = "http://llm_gateway:8080/v1/chat/completions"

    # RabbitMQ Configuration
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "arca"
    rabbitmq_vhost: str = "arca_vhost"
    rabbitmq_queue: str = "arca:ops:security"
    rabbitmq_routing_key: str = "ops.security.*"

    # OTEL Instrumentation
    otel: OTELConfig = field(default_factory=lambda: OTELConfig.from_env("security"))

    # Operations Allowed
    scanning_operations: List[str] = field(
        default_factory=lambda: [
            "vulnerability_scan",
            "secret_scan",
            "dependency_check",
            "policy_audit",
            "compliance_check",
        ]
    )
    remediation_operations: List[str] = field(
        default_factory=lambda: [
            "patch_vulnerability",
            "rotate_secret",
            "update_dependency",
            "apply_policy",
        ]
    )
    validation_operations: List[str] = field(
        default_factory=lambda: [
            "validate_cert",
            "validate_secret",
            "validate_config",
            "health_check",
        ]
    )
    reporting_operations: List[str] = field(
        default_factory=lambda: ["generate_report", "audit_trail", "compliance_report"]
    )

    # Security Constraints
    cannot_write_secrets_delete: bool = False  # Can update, but verify deletion
    cannot_delete_audit_logs: bool = True

    # Requires Approval
    requires_approval: Set[str] = field(
        default_factory=lambda: {
            "secret_deletion",
            "policy_override",
            "major_patches",
        }
    )

    # Container Isolation
    runs_in_secure_container: bool = True
    network_restricted: bool = True
    filesystem_restricted: bool = True

    # MCP Skills
    repair_skills: List[str] = field(
        default_factory=lambda: [
            "ARCA_AUDIT_LOG_COMPLIANCE.md",
            "ARCA_SELF_HEALING_SYSTEM.md",
        ]
    )

    @classmethod
    def from_env(cls) -> "SecurityOpsConfig":
        """Load from environment."""
        return cls(
            primary_model=os.getenv("SEC_OPS_MODEL", "granite:latest"),
        )


# ============================================================================
# File Ops Agent Configuration
# ============================================================================


@dataclass
class FileOpsConfig:
    """File maintainer agent configuration."""

    # Identity
    name: str = "File Maintainer"
    agent_type: AgentType = AgentType.FILE
    description: str = "File and filesystem operations for system maintenance"
    permissions: str = "write"

    # Model Configuration
    primary_model: str = field(default_factory=security_ops_model)  # From model_config
    fallback_model: str = "glm:latest"
    temperature: float = 0.3
    max_tokens: int = 4096
    llm_endpoint: str = "http://llm_gateway:8080/v1/chat/completions"

    # RabbitMQ Configuration
    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "arca"
    rabbitmq_vhost: str = "arca_vhost"
    rabbitmq_queue: str = "arca:ops:file"
    rabbitmq_routing_key: str = "ops.file.*"

    # OTEL Instrumentation
    otel: OTELConfig = field(default_factory=lambda: OTELConfig.from_env("file"))

    # Allowed Root Paths
    allowed_paths: Set[str] = field(
        default_factory=lambda: {
            "/app",
            "/data",
            "./databases",
            "./cache",
            "./logs",
            "./mcp_storage",
        }
    )

    # Protected Paths (Cannot Modify)
    protected_paths: Set[str] = field(
        default_factory=lambda: {
            "/etc",
            "/sys",
            "/var/run",
            "docker-compose.local.yml",
            ".env",
            ".secrets/*",
        }
    )

    # Operations Allowed
    file_operations: List[str] = field(
        default_factory=lambda: ["read", "write", "create", "delete", "move", "copy"]
    )
    directory_operations: List[str] = field(
        default_factory=lambda: ["list", "create", "delete", "copy"]
    )
    permission_operations: List[str] = field(default_factory=lambda: ["chmod", "chown"])
    analysis_operations: List[str] = field(
        default_factory=lambda: ["stat", "find", "grep", "du", "df"]
    )

    # Security Constraints
    cannot_delete: Set[str] = field(
        default_factory=lambda: {
            "docker-compose.local.yml",
            ".env",
            ".secrets/*",
        }
    )
    cannot_modify: Set[str] = field(
        default_factory=lambda: {
            ".gitignore",
            ".github/*",
        }
    )

    allow_symlinks: bool = True
    allow_hardlinks: bool = False

    # MCP Skills
    repair_skills: List[str] = field(
        default_factory=lambda: [
            "ARCA_DEPLOYMENT_HEALTHCHECK.md",
            "ARCA_SYSTEM_MAINTENANCE.md",
        ]
    )

    @classmethod
    def from_env(cls) -> "FileOpsConfig":
        """Load from environment."""
        return cls(
            primary_model=os.getenv("FILE_OPS_MODEL", "granite:latest"),
        )


# ============================================================================
# Ops Agent Factory
# ============================================================================


class OpsAgentConfigFactory:
    """Factory for creating ops agent configurations."""

    _configs = {
        AgentType.DOCKER: DockerOpsConfig,
        AgentType.GIT: GitOpsConfig,
        AgentType.SECURITY: SecurityOpsConfig,
        AgentType.FILE: FileOpsConfig,
    }

    @classmethod
    def create(cls, agent_type: AgentType):
        """Create configuration for agent type."""
        config_class = cls._configs.get(agent_type)
        if not config_class:
            raise ValueError(f"Unknown agent type: {agent_type}")
        return config_class.from_env()

    @classmethod
    def create_all(cls) -> Dict[AgentType, object]:
        """Create all ops agent configurations."""
        return {agent_type: cls.create(agent_type) for agent_type in AgentType}


# ============================================================================
# RabbitMQ Job Format
# ============================================================================


@dataclass
class OpsJob:
    """Job dispatched to ops agents."""

    job_id: str
    timestamp: str
    dispatch_agent: str  # Usually "serena"
    target_agent: str  # docker, git, security, or file
    operation: str
    description: str
    skill_reference: str
    parameters: Dict
    urgency: str = "normal"  # normal, high, critical
    repair_chain: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dict for RabbitMQ."""
        return {
            "job_id": self.job_id,
            "timestamp": self.timestamp,
            "dispatch_agent": self.dispatch_agent,
            "target_agent": self.target_agent,
            "operation": self.operation,
            "description": self.description,
            "skill_reference": self.skill_reference,
            "parameters": self.parameters,
            "urgency": self.urgency,
            "repair_chain": self.repair_chain,
        }


@dataclass
class OpsJobResult:
    """Result from ops agent execution."""

    job_id: str
    status: str  # completed, failed, timeout
    agent: str
    timestamp: str
    result: Dict
    learned: Optional[Dict] = None

    def to_dict(self) -> Dict:
        """Convert to dict for RabbitMQ."""
        return {
            "job_id": self.job_id,
            "status": self.status,
            "agent": self.agent,
            "timestamp": self.timestamp,
            "result": self.result,
            "learned": self.learned,
        }


# ============================================================================
# Initialization
# ============================================================================


def get_docker_ops_config() -> DockerOpsConfig:
    """Get Docker ops configuration."""
    return DockerOpsConfig.from_env()


def get_git_ops_config() -> GitOpsConfig:
    """Get Git ops configuration."""
    return GitOpsConfig.from_env()


def get_security_ops_config() -> SecurityOpsConfig:
    """Get Security ops configuration."""
    return SecurityOpsConfig.from_env()


def get_file_ops_config() -> FileOpsConfig:
    """Get File ops configuration."""
    return FileOpsConfig.from_env()


if __name__ == "__main__":
    # Example usage
    configs = OpsAgentConfigFactory.create_all()
    for agent_type, config in configs.items():
        print(f"\n{agent_type.value.upper()} OPS AGENT")
        print(f"  Name: {config.name}")
        print(f"  Model: {config.primary_model}")
        print(f"  Queue: {config.rabbitmq_queue}")
        print(
            f"  Protected: {config.cannot_touch if hasattr(config, 'cannot_touch') else 'N/A'}"
        )
