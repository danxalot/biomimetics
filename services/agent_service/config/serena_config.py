"""
Serena Agent Configuration
==========================

Noetic Code Agent - Read-only system analyzer and repair orchestrator.

- Monitors all system services via Redis pub/sub
- Analyzes issues using MCP skills and reasoning bank
- Dispatches repair jobs to ops agents via RabbitMQ
- Cannot execute write operations directly
- Models: Google AI Studio (primary) → GLM (fallback) → Granite (fallback)
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
    from shared.model_config import serena_model, local_ops_model, maintainer_model

    MODEL_CONFIG_AVAILABLE = True
    print("✅ Serena: Successfully imported centralized model configuration")
except ImportError as e:
    MODEL_CONFIG_AVAILABLE = False
    print(f"⚠️ Serena: Could not import centralized model_config, using fallbacks: {e}")

    # Fallback functions
    def serena_model():
        return "glm-4.6v-flash"

    def local_ops_model():
        return "granite-guardian-3.1-2b"

    def maintainer_model():
        return "granite-guardian-3.1-2b"

# ============================================================================
# Model Configuration
# ============================================================================


class ModelProvider(Enum):
    GOOGLE_AI_STUDIO = "google_ai_studio"
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"


@dataclass
class ModelConfig:
    """Model configuration with fallback chain."""

    provider: ModelProvider
    model: str
    temperature: float = 0.7
    max_tokens: int = 8192
    tools_enabled: bool = True
    endpoint: Optional[str] = None
    api_key: Optional[str] = None

    @classmethod
    def from_env(cls, prefix: str) -> "ModelConfig":
        """Load from environment variables."""
        provider_str = os.getenv(f"{prefix}_PROVIDER", "google_ai_studio").upper()
        provider = (
            ModelProvider[provider_str]
            if provider_str in ModelProvider.__members__
            else ModelProvider.GOOGLE_AI_STUDIO
        )

        # Import centralized model configuration
        try:
            from shared.model_config import serena_model

            default_model = serena_model()
        except ImportError:
            # Fallback to gemini model with system message support
            default_model = "gemini-2.5-flash-lite"

        return cls(
            provider=provider,
            model=os.getenv(f"{prefix}_MODEL", default_model),
            temperature=float(os.getenv(f"{prefix}_TEMPERATURE", "0.7")),
            max_tokens=int(os.getenv(f"{prefix}_MAX_TOKENS", "8192")),
            tools_enabled=os.getenv(f"{prefix}_TOOLS_ENABLED", "true").lower()
            == "true",
            endpoint=os.getenv(f"{prefix}_ENDPOINT"),
            api_key=os.getenv(f"{prefix}_API_KEY"),
        )


@dataclass
class ModelChain:
    """Fallback chain for model selection."""

    primary: ModelConfig
    fallback_1: ModelConfig
    fallback_2: ModelConfig

    def get_available_model(self) -> ModelConfig:
        """Get first available model in chain."""
        for model in [self.primary, self.fallback_1, self.fallback_2]:
            if model.provider == ModelProvider.OLLAMA or model.api_key:
                return model
        return self.fallback_2  # Default to Granite


# ============================================================================
# Permissions & Tools Configuration
# ============================================================================


class PermissionLevel(Enum):
    READ_ONLY = "read-only"
    WRITE = "write"


@dataclass
class ToolPermission:
    """Tool access control."""

    tool_name: str
    category: str
    allowed: bool = True
    read_only: bool = True
    requires_confirmation: bool = False


@dataclass
class SerenaToolkit:
    """Serena's allowed tools - all read-only."""

    # Service Monitoring Tools
    list_services: ToolPermission = field(
        default_factory=lambda: ToolPermission(
            "list_services", "monitoring", True, True
        )
    )
    get_service_health: ToolPermission = field(
        default_factory=lambda: ToolPermission(
            "get_service_health", "monitoring", True, True
        )
    )
    get_service_logs: ToolPermission = field(
        default_factory=lambda: ToolPermission(
            "get_service_logs", "monitoring", True, True
        )
    )
    trace_service_dependencies: ToolPermission = field(
        default_factory=lambda: ToolPermission(
            "trace_service_dependencies", "monitoring", True, True
        )
    )

    # Knowledge Access Tools
    get_skill: ToolPermission = field(
        default_factory=lambda: ToolPermission("get_skill", "knowledge", True, True)
    )
    search_skills: ToolPermission = field(
        default_factory=lambda: ToolPermission("search_skills", "knowledge", True, True)
    )
    search_reasoning: ToolPermission = field(
        default_factory=lambda: ToolPermission(
            "search_reasoning", "knowledge", True, True
        )
    )
    query_blackboard: ToolPermission = field(
        default_factory=lambda: ToolPermission(
            "query_blackboard", "knowledge", True, True
        )
    )

    # Analysis Tools
    serena_analyze_code: ToolPermission = field(
        default_factory=lambda: ToolPermission(
            "serena_analyze_code", "analysis", True, True
        )
    )
    analyze_error_pattern: ToolPermission = field(
        default_factory=lambda: ToolPermission(
            "analyze_error_pattern", "analysis", True, True
        )
    )
    check_repair_feasibility: ToolPermission = field(
        default_factory=lambda: ToolPermission(
            "check_repair_feasibility", "analysis", True, True
        )
    )

    # Job Dispatch Tools (dispatch, but no direct execution)
    dispatch_ops_job: ToolPermission = field(
        default_factory=lambda: ToolPermission(
            "dispatch_ops_job", "dispatch", True, True
        )
    )
    get_pending_repairs: ToolPermission = field(
        default_factory=lambda: ToolPermission(
            "get_pending_repairs", "dispatch", True, True
        )
    )
    get_job_status: ToolPermission = field(
        default_factory=lambda: ToolPermission("get_job_status", "dispatch", True, True)
    )

    # Redis/Messaging Tools (read only)
    subscribe_to_alerts: ToolPermission = field(
        default_factory=lambda: ToolPermission(
            "subscribe_to_alerts", "messaging", True, True
        )
    )
    query_health_status: ToolPermission = field(
        default_factory=lambda: ToolPermission(
            "query_health_status", "messaging", True, True
        )
    )

    def get_allowed_tools(self) -> List[str]:
        """Get list of allowed tool names."""
        return [
            getattr(self, attr).tool_name
            for attr in dir(self)
            if not attr.startswith("_")
            and isinstance(getattr(self, attr), ToolPermission)
            and getattr(self, attr).allowed
        ]


# ============================================================================
# Escalation Configuration
# ============================================================================


@dataclass
class EscalationConfig:
    """Escalation settings when Serena cannot fix automatically."""

    enabled: bool = True
    redis_queue: str = "arca:escalations:pending"
    user_alert_channel: str = "arca:user:alerts"
    alert_timeout: int = 300  # seconds (give ops 5 min before escalating)

    # Require manual review for these operations
    require_manual_for: Set[str] = field(
        default_factory=lambda: {
            "git_operations",  # User must review code changes
            "major_patches",  # Security patches need approval
            "secret_changes",  # Never auto-change secrets
            "multi_service_repair",  # Complex repairs need oversight
        }
    )

    # Escalation methods
    log_to_loki: bool = True
    publish_to_redis: bool = True
    create_grafana_alert: bool = True
    send_email: bool = False  # Optional: configure SMTP
    send_slack: bool = False  # Optional: configure webhook


# ============================================================================
# Health Monitoring Configuration
# ============================================================================


@dataclass
class HealthMonitorConfig:
    """Health monitoring and auto-repair settings."""

    enabled: bool = True

    # Alert-driven (NOT polling)
    alert_subscription: bool = True  # Active subscription to health alerts
    alert_subscription_channel: str = "arca:health:alerts"

    # Auto-repair settings
    auto_repair: bool = True
    learning_enabled: bool = True

    # Alert channels (Redis pub/sub)
    repair_dispatch_channel: str = "arca:repair:dispatch"
    repair_status_channel: str = "arca:repair:status"

    # Service status keys (Redis)
    service_status_pattern: str = "arca:service:status:*"
    job_pending_pattern: str = "arca:job:pending:*"
    repair_active_pattern: str = "arca:repair:active:*"

    # Repair parameters
    max_repair_attempts: int = 3
    repair_timeout: int = 300  # seconds
    alert_to_analysis_delay: int = 2  # seconds before analyzing

    # Escalation
    escalation: EscalationConfig = field(default_factory=EscalationConfig)


@dataclass
class RedisConfig:
    """Redis connection configuration."""

    host: str = "redis"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    ssl: bool = False

    @classmethod
    def from_env(cls) -> "RedisConfig":
        """Load from environment."""
        return cls(
            host=os.getenv("REDIS_HOST", "redis"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            password=os.getenv("REDIS_PASSWORD"),
            ssl=os.getenv("REDIS_SSL", "false").lower() == "true",
        )


# ============================================================================
# MCP Integration Configuration
# ============================================================================


@dataclass
class MCPIntegrationConfig:
    """MCP Server integration settings."""

    server_url: str = "http://mcp_server:8086"
    tools_enabled: bool = True
    skills_read_only: bool = True
    dispatch_capability: bool = True
    timeout: int = 30  # seconds
    max_retries: int = 3

    # Skills that Serena can read
    skill_categories: List[str] = field(
        default_factory=lambda: [
            "system_health",
            "repair_procedures",
            "analysis",
            "deployment",
        ]
    )

    # Skills to NOT load (security restriction)
    forbidden_skills: Set[str] = field(default_factory=lambda: set())

    @classmethod
    def from_env(cls) -> "MCPIntegrationConfig":
        """Load from environment."""
        return cls(
            server_url=os.getenv("MCP_SERVER_URL", "http://mcp_server:8086"),
            tools_enabled=os.getenv("MCP_TOOLS_ENABLED", "true").lower() == "true",
        )


# ============================================================================
# Main Serena Configuration
# ============================================================================


@dataclass
class SerenaConfig:
    """Complete Serena agent configuration."""

    # Agent Identity
    name: str = "Serena"
    agent_type: str = "analyzer"
    description: str = "Noetic Code Agent - Alert-driven system health monitoring and repair orchestration"
    permissions: PermissionLevel = PermissionLevel.READ_ONLY

    # Model Configuration
    model_chain: ModelChain = field(
        default_factory=lambda: ModelChain(
            primary=ModelConfig(
                provider=ModelProvider.GOOGLE_AI_STUDIO,
                model="gemma-3-27b-it",  # Learning model (was LearnLM)
                temperature=0.7,
                max_tokens=8192,
            ),
            fallback_1=ModelConfig(
                provider=ModelProvider.OLLAMA,
                model="glm:latest",
                temperature=0.7,
                max_tokens=8192,
                endpoint="http://llm_gateway:8080/v1/chat/completions",
            ),
            fallback_2=ModelConfig(
                provider=ModelProvider.OLLAMA,
                model="granite:latest",
                temperature=0.7,
                max_tokens=8192,
                endpoint="http://llm_gateway:8080/v1/chat/completions",
            ),
        )
    )

    # Memory Configuration
    episodic_memory_enabled: bool = True
    knowledge_graph_enabled: bool = True
    reasoning_bank_enabled: bool = True
    blackboard_enabled: bool = True

    # Tools
    toolkit: SerenaToolkit = field(default_factory=SerenaToolkit)

    # Health Monitoring (ALERT-DRIVEN, NOT POLLING)
    health_monitor: HealthMonitorConfig = field(default_factory=HealthMonitorConfig)

    # Redis
    redis: RedisConfig = field(default_factory=RedisConfig.from_env)

    # MCP Integration
    mcp: MCPIntegrationConfig = field(default_factory=MCPIntegrationConfig.from_env)

    # Learning Configuration
    learning_enabled: bool = True
    pattern_discovery_enabled: bool = True
    repair_effectiveness_tracking: bool = True

    # OTEL Observability
    otel_enabled: bool = True
    otel_endpoint: str = "otel_collector:4317"
    otel_trace_sample_rate: float = 1.0  # 100% tracing

    # Execution Firewall
    can_execute_write: bool = False  # Always false - cannot execute directly
    can_dispatch_jobs: bool = True  # True - dispatch to ops agents
    can_escalate: bool = True  # True - escalate to users if needed

    # Constraints
    cannot_execute_write: bool = True
    can_dispatch_jobs: bool = True
    can_query_memory: bool = True
    can_access_reasoning: bool = True

    @classmethod
    def from_env(cls) -> "SerenaConfig":
        """Load configuration from environment variables."""
        return cls(
            name=os.getenv("SERENA_NAME", "Serena"),
            description=os.getenv(
                "SERENA_DESCRIPTION",
                "Noetic Code Agent - System health monitoring and repair orchestration",
            ),
            learning_enabled=os.getenv("SERENA_LEARNING_ENABLED", "true").lower()
            == "true",
            health_monitor=HealthMonitorConfig(
                enabled=os.getenv("SERENA_HEALTH_MONITORING", "true").lower() == "true",
                auto_repair=os.getenv("SERENA_AUTO_REPAIR", "true").lower() == "true",
            ),
            redis=RedisConfig.from_env(),
            mcp=MCPIntegrationConfig.from_env(),
        )


# ============================================================================
# Initialization
# ============================================================================


def get_serena_config() -> SerenaConfig:
    """Get Serena configuration from environment or defaults."""
    return SerenaConfig.from_env()


if __name__ == "__main__":
    # Example usage
    config = get_serena_config()
    print(f"Agent: {config.name}")
    print(f"Permissions: {config.permissions.value}")
    print(f"Model Primary: {config.model_chain.primary.model}")
    print(f"Allowed Tools: {config.toolkit.get_allowed_tools()}")
    print(f"Redis: {config.redis.host}:{config.redis.port}")
    print(f"MCP Server: {config.mcp.server_url}")
    print(f"Learning Enabled: {config.learning_enabled}")
