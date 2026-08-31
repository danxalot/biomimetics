"""
Tool Registry - Unified Tool Discovery and Registration Framework

Mirrors the EnhancedSkillsManager approach to provide:
1. Automatic tool discovery from tools/ directory
2. Tool categorisation (8 categories)
3. EMA-based effectiveness tracking
4. MCP endpoints for tool management
5. Retirement signalling for low-performing tools

Author: ARCA System
Date: March 2026
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Redis for metrics storage (Pythia Redis)
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("redis not available - metrics will be in-memory only")

logger = logging.getLogger(__name__)


# ============================================================================
# Enums and Constants
# ============================================================================


class ToolCategory(Enum):
    """Tool categories for organisation and discovery"""

    INFRASTRUCTURE = "infrastructure"  # Docker, service management, infra discovery
    INTELLIGENCE = "intelligence"  # LLM, reasoning, analysis tools
    MEMORY = "memory"  # Neo4j, Redis, vector storage
    GEOMETRY = "geometry"  # Pythia, geometric algebra, embeddings
    SECURITY = "security"  # Guardian, secrets, security ops
    AGENT_OPS = "agent_ops"  # Agent dispatch, workflow, director
    PERSISTENCE = "persistence"  # File ops, blackboard, storage
    SELF_MODEL = "self_model"  # Self-awareness, telemetry, context


class ToolSource(Enum):
    """Source of tool definition"""

    CORE = "core"  # Built-in MCP server tools
    MODULE = "module"  # From tools/ directory modules
    DYNAMIC = "dynamic"  # Dynamically registered at runtime


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class ToolMetadata:
    """Extended tool metadata"""

    tool_id: str  # Unique identifier (function name)
    name: str  # Display name
    description: str  # What the tool does
    category: ToolCategory  # Tool category
    source: ToolSource  # Where tool came from

    # Function reference
    func: Optional[Callable] = None

    # Effectiveness tracking (EMA-based)
    invocation_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    last_used: Optional[str] = None
    effectiveness_score: float = 1.0  # 0.0-1.0

    # Performance metrics
    latency_p50: float = 0.0  # milliseconds
    latency_p95: float = 0.0  # milliseconds
    latency_samples: List[float] = field(default_factory=list)

    # Documentation
    parameters: Dict[str, Any] = field(default_factory=dict)
    returns: str = ""

    # Learning
    weaknesses: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)

    # Relationships
    related_tools: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)

    # Module source
    module_name: Optional[str] = None
    module_path: Optional[str] = None

    # Metadata for MCP
    mcp_tool_def: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if isinstance(self.category, str):
            self.category = ToolCategory(self.category)
        if isinstance(self.source, str):
            self.source = ToolSource(self.source)

    @property
    def success_rate(self) -> float:
        """Calculate success rate"""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 1.0

    @property
    def needs_improvement(self) -> bool:
        """Whether tool needs improvement"""
        return self.success_rate < 0.7 or len(self.weaknesses) >= 3

    @property
    def should_retire(self) -> bool:
        """Check if tool should be flagged for retirement"""
        # Retire if: < 30% success rate AND used > 10 times
        # OR: not used in 30 days (we'll track this externally)
        if self.invocation_count < 10:
            return False
        return self.success_rate < 0.3

    @property
    def recommended(self) -> bool:
        """Whether tool is recommended based on effectiveness"""
        return self.effectiveness_score >= 0.7 and self.invocation_count > 0

    def update_effectiveness(self, success: bool, latency_ms: float):
        """
        Update effectiveness metrics using EMA (Exponential Moving Average)

        EMA formula: new_ema = alpha * current_value + (1 - alpha) * old_ema
        Alpha = 0.3 gives more weight to recent values
        """
        alpha = 0.3  # EMA smoothing factor

        # Update counts
        self.invocation_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

        # Update timestamp
        self.last_used = datetime.now().isoformat()

        # Update latency samples (keep last 100 for percentile calculation)
        self.latency_samples.append(latency_ms)
        if len(self.latency_samples) > 100:
            self.latency_samples = self.latency_samples[-100:]

        # Calculate latency percentiles
        if self.latency_samples:
            sorted_samples = sorted(self.latency_samples)
            p50_idx = int(len(sorted_samples) * 0.5)
            p95_idx = int(len(sorted_samples) * 0.95)
            self.latency_p50 = sorted_samples[p50_idx]
            self.latency_p95 = sorted_samples[min(p95_idx, len(sorted_samples) - 1)]

        # Update effectiveness score using EMA
        # Effectiveness = weighted combination of success rate and latency score
        success_component = self.success_rate

        # Latency score: 1.0 for <100ms, decaying to 0.0 for >5000ms
        latency_score = max(0.0, 1.0 - (self.latency_p50 / 5000.0))

        # Combined target: 70% success rate, 30% latency
        target_effectiveness = (0.7 * success_component) + (0.3 * latency_score)

        # Apply EMA smoothing
        self.effectiveness_score = (alpha * target_effectiveness) + (
            (1 - alpha) * self.effectiveness_score
        )

    def to_mcp_tool(self) -> Dict[str, Any]:
        """Convert to MCP tool definition"""
        if self.mcp_tool_def:
            return self.mcp_tool_def

        # Build input schema from parameters
        properties = {}
        required = []
        for param_name, param_def in self.parameters.items():
            if isinstance(param_def, dict):
                properties[param_name] = param_def
                if not param_def.get("optional", False):
                    required.append(param_name)
            else:
                properties[param_name] = {
                    "type": "string",
                    "description": str(param_def),
                }

        return {
            "name": self.tool_id,
            "description": f"{self.description} (Effectiveness: {self.effectiveness_score:.0%}, Used: {self.invocation_count}x)",
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
            "metadata": {
                "category": self.category.value,
                "source": self.source.value,
                "effectiveness": self.effectiveness_score,
                "invocation_count": self.invocation_count,
                "success_rate": self.success_rate,
                "latency_p50": self.latency_p50,
                "latency_p95": self.latency_p95,
                "related_tools": self.related_tools,
                "prerequisites": self.prerequisites,
            },
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data["category"] = self.category.value
        data["source"] = self.source.value
        data["func"] = None  # Don't serialize function reference
        return data


# ============================================================================
# Tool Registry
# ============================================================================


class ToolRegistry:
    """
    Unified tool registry with automatic discovery and effectiveness tracking

    Usage:
        registry = ToolRegistry()
        registry.scan_tools()  # Auto-discover from tools/ directory
        tools = registry.list_tools()
        result = registry.execute_tool('tool_name', args)
    """

    # Redis key pattern for metrics storage
    REDIS_KEY_PATTERN = "tool:metrics:{tool_name}"

    def __init__(
        self,
        tools_dir: Optional[Path] = None,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        auto_scan: bool = True,
    ):
        """
        Initialize Tool Registry

        Args:
            tools_dir: Path to tools/ directory (defaults to ./tools)
            redis_host: Redis hostname for metrics storage
            redis_port: Redis port
            auto_scan: Whether to automatically scan tools directory on init
        """
        self.tools_dir = tools_dir or Path(__file__).parent / "tools"
        self.redis_host = redis_host
        self.redis_port = redis_port

        # Tool storage
        self._tools: Dict[str, ToolMetadata] = {}
        self._tools_by_category: Dict[ToolCategory, List[str]] = {
            cat: [] for cat in ToolCategory
        }

        # Initialize Redis connection
        self._redis_client = None
        if REDIS_AVAILABLE:
            try:
                self._redis_client = redis.Redis(
                    host=redis_host, port=redis_port, decode_responses=True
                )
                logger.info(
                    f"✅ ToolRegistry connected to Redis at {redis_host}:{redis_port}"
                )
            except Exception as e:
                logger.warning(
                    f"⚠️  ToolRegistry Redis connection failed: {e} - using in-memory metrics"
                )

        # Auto-scan tools directory
        if auto_scan:
            self.scan_tools()

    def _register_tool_decorator(
        self,
        category: ToolCategory,
        description: str,
        parameters: Optional[Dict[str, Any]] = None,
        returns: str = "",
        related_tools: Optional[List[str]] = None,
        prerequisites: Optional[List[str]] = None,
    ) -> Callable:
        """
        Decorator factory for registering tools

        Usage:
            @registry.register_tool(
                category=ToolCategory.INFRASTRUCTURE,
                description="List Docker containers",
                parameters={"all": {"type": "boolean", "description": "List all containers"}},
                returns="List of container dicts"
            )
            def list_containers(all: bool = False) -> List[Dict]:
                ...
        """

        def decorator(func: Callable) -> Callable:
            tool_id = func.__name__

            # Extract parameters from function signature if not provided
            if parameters is None:
                import inspect

                sig = inspect.signature(func)
                parameters = {}
                for param_name, param in sig.parameters.items():
                    param_type = (
                        param.annotation
                        if param.annotation != inspect.Parameter.empty
                        else str
                    )
                    param_default = (
                        param.default
                        if param.default != inspect.Parameter.empty
                        else None
                    )
                    parameters[param_name] = {
                        "type": self._python_type_to_json(param_type),
                        "description": f"Parameter {param_name}",
                        "optional": param_default is not None,
                    }

            # Create metadata
            metadata = ToolMetadata(
                tool_id=tool_id,
                name=tool_id.replace("_", " ").title(),
                description=description,
                category=category,
                source=ToolSource.DYNAMIC,
                func=func,
                parameters=parameters or {},
                returns=returns,
                related_tools=related_tools or [],
                prerequisites=prerequisites or [],
            )

            # Register
            self._register_tool_metadata(metadata)

            # Return original function (wrapper not needed - registry stores reference)
            return func

        return decorator

    def _python_type_to_json(self, python_type) -> str:
        """Convert Python type to JSON schema type"""
        if python_type == int:
            return "integer"
        elif python_type == float:
            return "number"
        elif python_type == bool:
            return "boolean"
        elif python_type == list or (
            hasattr(python_type, "__origin__") and python_type.__origin__ == list
        ):
            return "array"
        elif python_type == dict or (
            hasattr(python_type, "__origin__") and python_type.__origin__ == dict
        ):
            return "object"
        else:
            return "string"

    def _register_tool_metadata(self, metadata: ToolMetadata):
        """Register tool metadata in internal structures"""
        tool_id = metadata.tool_id

        # Store in main registry
        self._tools[tool_id] = metadata

        # Store in category index
        if tool_id not in self._tools_by_category[metadata.category]:
            self._tools_by_category[metadata.category].append(tool_id)

        logger.info(
            f"✅ Registered tool: {tool_id} (category: {metadata.category.value})"
        )

    def scan_tools(self) -> int:
        """
        Automatically scan tools/ directory and register all tool modules

        Returns:
            Number of tools registered
        """
        logger.info(f"🔍 Scanning tools directory: {self.tools_dir}")

        if not self.tools_dir.exists():
            logger.warning(f"Tools directory not found: {self.tools_dir}")
            return 0

        tools_registered = 0

        # Scan all Python files in tools/ directory
        for tool_file in self.tools_dir.glob("mcp_*.py"):
            if tool_file.name.endswith(".bak"):
                continue  # Skip backup files

            try:
                count = self._scan_tool_module(tool_file)
                tools_registered += count
            except Exception as e:
                logger.error(f"Failed to scan {tool_file.name}: {e}")

        logger.info(f"✅ Scanned {tools_registered} tools from {self.tools_dir}")
        return tools_registered

    def _scan_tool_module(self, file_path: Path) -> int:
        """
        Scan a single tool module and extract tool definitions

        Looks for:
        1. @mcp.tool() decorated functions
        2. Functions with tool-like signatures and docstrings
        """
        tools_registered = 0
        module_name = file_path.stem

        try:
            # Read module source
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()

            # Parse for @mcp.tool() decorated functions
            # Pattern: @mcp.tool() or @mcp.tool followed by def
            tool_pattern = r'@mcp\.tool\(\)?\s*\n(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*([^\n:]+))?\s*:\s*\n\s*"""([^"]+)"""'

            matches = re.finditer(tool_pattern, source, re.MULTILINE | re.DOTALL)

            for match in matches:
                func_name = match.group(1)
                func_params = match.group(2)
                func_return = match.group(3) or ""
                func_doc = match.group(4).strip()

                # Infer category from module name
                category = self._infer_category_from_module(module_name)

                # Parse parameters
                parameters = self._parse_params_string(func_params)

                # Create metadata
                metadata = ToolMetadata(
                    tool_id=func_name,
                    name=func_name.replace("_", " ").title(),
                    description=func_doc[:200],  # Truncate long descriptions
                    category=category,
                    source=ToolSource.MODULE,
                    module_name=module_name,
                    module_path=str(file_path),
                    parameters=parameters,
                    returns=func_return.strip() if func_return else "",
                )

                # Try to import and get function reference
                try:
                    import importlib.util

                    spec = importlib.util.spec_from_file_location(
                        module_name, file_path
                    )
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    if hasattr(module, func_name):
                        metadata.func = getattr(module, func_name)
                except Exception as e:
                    logger.debug(
                        f"Could not load function {func_name} from {module_name}: {e}"
                    )

                # Register
                self._register_tool_metadata(metadata)
                tools_registered += 1

            # If no @mcp.tool patterns found, check for module-level mcp attribute
            # and register the module itself as a tool provider
            if tools_registered == 0 and "mcp" in source:
                # Module uses FastMCP but we couldn't parse individual tools
                # Register a meta-tool for this module
                category = self._infer_category_from_module(module_name)
                metadata = ToolMetadata(
                    tool_id=module_name,
                    name=module_name.replace("_", " ").title(),
                    description=f"Tool module: {module_name}",
                    category=category,
                    source=ToolSource.MODULE,
                    module_name=module_name,
                    module_path=str(file_path),
                )
                self._register_tool_metadata(metadata)
                tools_registered = 1

        except Exception as e:
            logger.error(f"Error scanning module {file_path}: {e}")

        return tools_registered

    def _infer_category_from_module(self, module_name: str) -> ToolCategory:
        """Infer tool category from module name"""
        name_lower = module_name.lower()

        # Infrastructure
        if any(x in name_lower for x in ["docker", "infra", "service", "proxy"]):
            return ToolCategory.INFRASTRUCTURE

        # Intelligence
        if any(
            x in name_lower
            for x in [
                "intelligence",
                "deepthink",
                "insight",
                "analysis",
                "reviewer",
                "compressor",
            ]
        ):
            return ToolCategory.INTELLIGENCE

        # Memory
        if any(
            x in name_lower for x in ["neo4j", "redis", "blackboard", "vector", "graph"]
        ):
            return ToolCategory.MEMORY

        # Geometry
        if any(
            x in name_lower
            for x in ["geometry", "geouni", "transgeo", "pythia", "geometric"]
        ):
            return ToolCategory.GEOMETRY

        # Security
        if any(x in name_lower for x in ["security", "guardian", "secrets"]):
            return ToolCategory.SECURITY

        # Agent Ops
        if any(x in name_lower for x in ["agent", "director", "workflow", "dispatch"]):
            return ToolCategory.AGENT_OPS

        # Persistence
        if any(x in name_lower for x in ["file", "persistence", "storage"]):
            return ToolCategory.PERSISTENCE

        # Self Model
        if any(x in name_lower for x in ["self", "telemetry", "context", "universal"]):
            return ToolCategory.SELF_MODEL

        # Default to intelligence
        return ToolCategory.INTELLIGENCE

    def _parse_params_string(self, params_str: str) -> Dict[str, Any]:
        """Parse function parameter string into parameter dict"""
        if not params_str.strip():
            return {}

        parameters = {}
        params = [p.strip() for p in params_str.split(",")]

        for param in params:
            # Handle type annotations: name: type = default
            if ":" in param:
                parts = param.split(":")
                param_name = parts[0].strip()
                type_and_default = ":".join(parts[1:])

                param_def = {"type": "string", "description": f"Parameter {param_name}"}

                # Check for default value
                if "=" in type_and_default:
                    param_def["optional"] = True
                else:
                    param_def["optional"] = False

                parameters[param_name] = param_def
            else:
                # Simple parameter: name
                param_name = param.split("=")[0].strip()
                if param_name and param_name != "self":
                    parameters[param_name] = {
                        "type": "string",
                        "description": f"Parameter {param_name}",
                        "optional": "=" in param,
                    }

        return parameters

    # ========================================================================
    # Tool Discovery APIs
    # ========================================================================

    def list_tools(
        self,
        category: Optional[ToolCategory] = None,
        min_effectiveness: float = 0.0,
        include_metadata: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        List all registered tools with optional filtering

        Args:
            category: Filter by category
            min_effectiveness: Minimum effectiveness score (0.0-1.0)
            include_metadata: Include full metadata or just summary

        Returns:
            List of tool definitions
        """
        tools = []

        # Get tool IDs to include
        if category:
            tool_ids = self._tools_by_category.get(category, [])
        else:
            tool_ids = list(self._tools.keys())

        for tool_id in tool_ids:
            metadata = self._tools.get(tool_id)
            if not metadata:
                continue

            # Filter by effectiveness
            if metadata.effectiveness_score < min_effectiveness:
                continue

            if include_metadata:
                tools.append(metadata.to_mcp_tool())
            else:
                tools.append(
                    {
                        "name": metadata.tool_id,
                        "description": metadata.description,
                        "category": metadata.category.value,
                        "effectiveness": metadata.effectiveness_score,
                    }
                )

        return tools

    def get_tool_details(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific tool"""
        metadata = self._tools.get(tool_id)
        if not metadata:
            return None
        return metadata.to_dict()

    def recommend_tools(
        self,
        task_description: str,
        category: Optional[ToolCategory] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Recommend tools for a given task

        Uses simple keyword matching against tool descriptions.
        Can be enhanced with semantic search or LLM-based recommendation.

        Args:
            task_description: Description of the task
            category: Optional category filter
            top_k: Number of recommendations to return

        Returns:
            List of recommended tools with confidence scores
        """
        # Simple keyword-based recommendation
        task_keywords = set(task_description.lower().split())

        recommendations = []

        for tool_id, metadata in self._tools.items():
            # Skip if wrong category
            if category and metadata.category != category:
                continue

            # Calculate keyword overlap
            tool_keywords = set(metadata.description.lower().split())
            overlap = len(task_keywords & tool_keywords)

            # Boost by effectiveness
            score = (overlap * 0.6) + (metadata.effectiveness_score * 0.4)

            if score > 0.1:  # Minimum threshold
                recommendations.append(
                    {
                        "tool_id": tool_id,
                        "name": metadata.name,
                        "description": metadata.description,
                        "category": metadata.category.value,
                        "confidence": min(1.0, score),
                        "effectiveness": metadata.effectiveness_score,
                    }
                )

        # Sort by confidence and return top_k
        recommendations.sort(key=lambda x: x["confidence"], reverse=True)
        return recommendations[:top_k]

    # ========================================================================
    # Tool Execution APIs
    # ========================================================================

    async def execute_tool(
        self,
        tool_id: str,
        arguments: Optional[Dict[str, Any]] = None,
        track_metrics: bool = True,
    ) -> Any:
        """
        Execute a tool with metrics tracking

        Args:
            tool_id: Tool identifier
            arguments: Tool arguments
            track_metrics: Whether to track execution metrics

        Returns:
            Tool execution result
        """
        metadata = self._tools.get(tool_id)
        if not metadata:
            raise ValueError(f"Unknown tool: {tool_id}")

        if not metadata.func:
            raise ValueError(f"Tool {tool_id} has no executable function")

        # Execute with timing
        start_time = time.time()
        success = False
        result = None

        try:
            arguments = arguments or {}

            # Call function
            if asyncio.iscoroutinefunction(metadata.func):
                result = await metadata.func(**arguments)
            else:
                result = metadata.func(**arguments)

            success = True

        except Exception as e:
            logger.error(f"Tool {tool_id} execution failed: {e}")
            result = {"error": str(e)}
            success = False

        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000

        # Update metrics
        if track_metrics:
            metadata.update_effectiveness(success, latency_ms)
            await self._save_metrics_to_redis(tool_id, metadata)

        return result

    def execute_tool_sync(
        self,
        tool_id: str,
        arguments: Optional[Dict[str, Any]] = None,
        track_metrics: bool = True,
    ) -> Any:
        """Synchronous wrapper for execute_tool"""
        import asyncio

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(
            self.execute_tool(tool_id, arguments, track_metrics)
        )

    async def rate_tool_execution(
        self,
        tool_id: str,
        success: bool,
        latency_ms: float,
        feedback: Optional[str] = None,
    ):
        """
        Manually rate a tool execution

        Args:
            tool_id: Tool identifier
            success: Whether execution was successful
            latency_ms: Execution latency in milliseconds
            feedback: Optional human feedback
        """
        metadata = self._tools.get(tool_id)
        if not metadata:
            logger.warning(f"Cannot rate unknown tool: {tool_id}")
            return

        metadata.update_effectiveness(success, latency_ms)

        if feedback:
            if success:
                metadata.improvements.append(f"Feedback: {feedback}")
            else:
                metadata.weaknesses.append(f"Feedback: {feedback}")

        await self._save_metrics_to_redis(tool_id, metadata)

    # ========================================================================
    # Metrics Persistence
    # ========================================================================

    async def _save_metrics_to_redis(self, tool_id: str, metadata: ToolMetadata):
        """Save tool metrics to Redis"""
        if not self._redis_client:
            return  # Redis not available

        try:
            key = self.REDIS_KEY_PATTERN.format(tool_name=tool_id)
            metrics_data = {
                "invocation_count": metadata.invocation_count,
                "success_count": metadata.success_count,
                "failure_count": metadata.failure_count,
                "effectiveness_score": metadata.effectiveness_score,
                "latency_p50": metadata.latency_p50,
                "latency_p95": metadata.latency_p95,
                "last_used": metadata.last_used,
            }

            # Store as JSON
            self._redis_client.set(key, json.dumps(metrics_data))

            # Set expiry (keep metrics for 30 days)
            self._redis_client.expire(key, 30 * 24 * 60 * 60)

        except Exception as e:
            logger.debug(f"Failed to save metrics for {tool_id}: {e}")

    async def _load_metrics_from_redis(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """Load tool metrics from Redis"""
        if not self._redis_client:
            return None

        try:
            key = self.REDIS_KEY_PATTERN.format(tool_name=tool_id)
            data = self._redis_client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.debug(f"Failed to load metrics for {tool_id}: {e}")

        return None

    # ========================================================================
    # Retirement Signalling
    # ========================================================================

    def get_retirement_candidates(self) -> List[Dict[str, Any]]:
        """
        Get list of tools that should be considered for retirement

        Returns:
            List of tool metadata for tools below effectiveness threshold
        """
        candidates = []

        for tool_id, metadata in self._tools.items():
            if metadata.should_retire:
                candidates.append(
                    {
                        "tool_id": tool_id,
                        "name": metadata.name,
                        "category": metadata.category.value,
                        "success_rate": metadata.success_rate,
                        "invocation_count": metadata.invocation_count,
                        "effectiveness_score": metadata.effectiveness_score,
                        "reason": "low_success_rate"
                        if metadata.success_rate < 0.3
                        else "not_used",
                    }
                )

        return candidates

    # ========================================================================
    # Global Instance
    # ========================================================================

    _global_instance: Optional["ToolRegistry"] = None


def get_tool_registry(
    tools_dir: Optional[Path] = None,
    redis_host: str = "localhost",
    redis_port: int = 6379,
) -> ToolRegistry:
    """
    Get or create the global ToolRegistry instance

    Args:
        tools_dir: Path to tools directory
        redis_host: Redis hostname
        redis_port: Redis port

    Returns:
        ToolRegistry instance
    """
    if ToolRegistry._global_instance is None:
        ToolRegistry._global_instance = ToolRegistry(
            tools_dir=tools_dir,
            redis_host=redis_host,
            redis_port=redis_port,
            auto_scan=True,
        )

    return ToolRegistry._global_instance


# ============================================================================
# Decorator for module-level tool registration
# ============================================================================


def register_tool(
    category: str,
    description: str,
    parameters: Optional[Dict[str, Any]] = None,
    returns: str = "",
    related_tools: Optional[List[str]] = None,
    prerequisites: Optional[List[str]] = None,
) -> Callable:
    """
    Decorator for registering tools to the global registry

    Usage in tool modules:
        @register_tool(
            category="infrastructure",
            description="List Docker containers",
            parameters={"all": {"type": "boolean", "description": "Include stopped containers"}}
        )
        def list_containers(all: bool = False) -> List[Dict]:
            ...
    """

    def decorator(func: Callable) -> Callable:
        # Get or create registry
        registry = get_tool_registry()

        # Create category enum from string
        try:
            category_enum = ToolCategory(category)
        except ValueError:
            category_enum = ToolCategory.INTELLIGENCE
            logger.warning(f"Unknown category '{category}', defaulting to INTELLIGENCE")

        # Create metadata
        tool_id = func.__name__
        metadata = ToolMetadata(
            tool_id=tool_id,
            name=tool_id.replace("_", " ").title(),
            description=description,
            category=category_enum,
            source=ToolSource.DYNAMIC,
            func=func,
            parameters=parameters or {},
            returns=returns,
            related_tools=related_tools or [],
            prerequisites=prerequisites or [],
        )

        # Register
        registry._register_tool_metadata(metadata)

        return func

    return decorator
