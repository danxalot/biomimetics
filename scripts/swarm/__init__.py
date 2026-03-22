"""
Tony Stark Swarm - Model Orchestration System
============================================
Meta-cognitive model deployment for ARCA Biomimetic OS.
"""

from .model_selector import (
    ModelTier,
    TaskType,
    ModelSpec,
    QuotaManager,
    ModelRouter,
    MODEL_MATRIX,
    run_swarm_diagnostic,
)

from .project_analyzer import MultiModelAnalyzer
from .task_brief_generator import TaskBriefGenerator, TaskBrief, generate_task_brief_cli

__all__ = [
    "ModelTier",
    "TaskType",
    "ModelSpec",
    "QuotaManager",
    "ModelRouter",
    "MODEL_MATRIX",
    "run_swarm_diagnostic",
    "MultiModelAnalyzer",
    "TaskBriefGenerator",
    "TaskBrief",
    "generate_task_brief_cli",
]
