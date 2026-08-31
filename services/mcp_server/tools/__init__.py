"""
ARCA MCP Tools Package
Provides MCP-compatible tools for the ARCA agent system
"""

# Import and re-export all tools and modules for accessibility

# Core tool managers
try:
    from .queue_manager_tool import QueueManager
except ImportError:
    QueueManager = None

try:
    from .langsearch_tools import LangSearchClient
except ImportError:
    LangSearchClient = None

# MCP tool modules - import each individually to ensure they're available
try:
    from . import mcp_robotics
except ImportError as e:
    mcp_robotics = None

try:
    from . import mcp_compressor
except ImportError as e:
    mcp_compressor = None

try:
    from . import mcp_reviewer
except ImportError as e:
    mcp_reviewer = None

try:
    from . import mcp_insight_synthesis
except ImportError as e:
    mcp_insight_synthesis = None

try:
    from . import mcp_skill_forge
except ImportError as e:
    mcp_skill_forge = None

try:
    from . import mcp_otel_autopsy
except ImportError as e:
    mcp_otel_autopsy = None

try:
    from . import mcp_knowledge_crystallizer
except ImportError as e:
    mcp_knowledge_crystallizer = None

try:
    from . import mcp_human_feedback
except ImportError as e:
    mcp_human_feedback = None

try:
    from . import mcp_git_ops
except ImportError as e:
    mcp_git_ops = None

try:
    from . import mcp_docker_ops
except ImportError as e:
    mcp_docker_ops = None

try:
    from . import mcp_file_ops
except ImportError as e:
    mcp_file_ops = None

try:
    from . import mcp_secrets_ops
except ImportError as e:
    mcp_secrets_ops = None

try:
    from . import mcp_vision_encoder
except ImportError as e:
    mcp_vision_encoder = None

try:
    from . import mcp_neo4j_admin
except ImportError as e:
    mcp_neo4j_admin = None

try:
    from . import mcp_blackboard_redis
except ImportError as e:
    mcp_blackboard_redis = None

try:
    from . import mcp_guardian
except ImportError as e:
    mcp_guardian = None

__all__ = [
    'QueueManager',
    'LangSearchClient',
    'mcp_robotics',
    'mcp_compressor',
    'mcp_reviewer',
    'mcp_insight_synthesis',
    'mcp_skill_forge',
    'mcp_otel_autopsy',
    'mcp_knowledge_crystallizer',
    'mcp_human_feedback',
    'mcp_git_ops',
    'mcp_docker_ops',
    'mcp_file_ops',
    'mcp_secrets_ops',
    'mcp_vision_encoder',
    'mcp_neo4j_admin',
    'mcp_blackboard_redis',
    'mcp_guardian'
]

try:
    from .mcp_geouni import geouni_visualize_geometry, geouni_solve_problem
except ImportError:
    pass
