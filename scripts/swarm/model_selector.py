#!/usr/bin/env python3
"""
Tony Stark Swarm - Model Orchestration Matrix
============================================
Meta-cognitive model deployment system for ARCA Biomimetic OS.
Routes tasks to optimal model based on capability, cost, and quota.

Model Tiers:
- TIER_0: Free conversational (daily swap between models)
- TIER_1: Free code/reasoning (generous quotas)
- TIER_2: Paid subscriptions (limited, high-value tasks only)
- TIER_3: Premium (rare use, complex orchestration)

Task Types:
- CONVERSATION: Interactive chat, personality
- ANALYSIS: Project-wide code analysis
- IMPLEMENTATION: Code writing, refactoring
- REASONING: Complex problem solving, architecture
- CREATION: Task briefs, planning, design
- REVIEW: Error detection, quality gate
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import json
import os


class ModelTier(Enum):
    TIER_0_CONVERSATION = 0  # Free, personality-driven
    TIER_1_CODE = 1  # Free, capability-driven
    TIER_2_PAID = 2  # Subscription, high-value
    TIER_3_PREMIUM = 3  # Pay-per-token, rare use


class TaskType(Enum):
    CONVERSATION = "conversation"
    ANALYSIS = "analysis"
    IMPLEMENTATION = "implementation"
    REASONING = "reasoning"
    CREATION = "creation"
    REVIEW = "review"
    ROUTING = "routing"  # Task brief creation
    ORCHESTRATION = "orchestration"  # Multi-model coordination


@dataclass
class ModelSpec:
    id: str
    name: str
    provider: str
    endpoint: str
    tier: ModelTier
    strengths: List[str]
    weaknesses: List[str]
    context_window: int
    cost_per_1k: float  # USD
    daily_quota: int  # requests
    monthly_quota: int  # requests
    supports_streaming: bool
    supports_tools: bool
    personality: str  # Brief character description


class QuotaManager:
    def __init__(self, quota_file: str = "~/.stark_swarm/quotas.json"):
        self.quota_file = os.path.expanduser(quota_file)
        self.quotas = self._load_quotas()

    def _load_quotas(self) -> Dict:
        os.makedirs(os.path.dirname(self.quota_file), exist_ok=True)
        if os.path.exists(self.quota_file):
            with open(self.quota_file) as f:
                return json.load(f)
        return self._default_quotas()

    def _default_quotas(self) -> Dict:
        return {"daily_resets": {}, "monthly_resets": {}, "usage": {}}

    def check_quota(self, model_id: str) -> bool:
        """Check if model has remaining quota."""
        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().strftime("%Y-%m")

        usage = self.quotas.get("usage", {}).get(model_id, {"daily": 0, "monthly": 0})
        daily_limit = MODEL_MATRIX[model_id].daily_quota
        monthly_limit = MODEL_MATRIX[model_id].monthly_quota

        return (
            usage.get("daily", 0) < daily_limit
            and usage.get("monthly", 0) < monthly_limit
        )

    def increment_usage(self, model_id: str):
        """Track usage after API call."""
        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().strftime("%Y-%m")

        if model_id not in self.quotas["usage"]:
            self.quotas["usage"][model_id] = {"daily": 0, "monthly": 0, "total": 0}

        self.quotas["usage"][model_id]["daily"] += 1
        self.quotas["usage"][model_id]["monthly"] += 1
        self.quotas["usage"][model_id]["total"] += 1
        self.quotas["daily_resets"][model_id] = today
        self.quotas["monthly_resets"][model_id] = month

        self._save_quotas()

    def _save_quotas(self):
        with open(self.quota_file, "w") as f:
            json.dump(self.quotas, f, indent=2)

    def reset_daily_if_needed(self):
        today = datetime.now().strftime("%Y-%m-%d")
        for model_id, last_reset in self.quotas.get("daily_resets", {}).items():
            if last_reset != today:
                self.quotas["usage"][model_id]["daily"] = 0

    def reset_monthly_if_needed(self):
        month = datetime.now().strftime("%Y-%m")
        for model_id, last_reset in self.quotas.get("monthly_resets", {}).items():
            if last_reset != month:
                self.quotas["usage"][model_id]["monthly"] = 0

    def get_remaining(self, model_id: str) -> Dict:
        usage = self.quotas.get("usage", {}).get(model_id, {"daily": 0, "monthly": 0})
        model = MODEL_MATRIX[model_id]
        return {
            "daily": model.daily_quota - usage.get("daily", 0),
            "monthly": model.monthly_quota - usage.get("monthly", 0),
        }


# =============================================================================
# MODEL CAPABILITY MATRIX
# =============================================================================

MODEL_MATRIX: Dict[str, ModelSpec] = {
    # TIER 0: Free Conversational Models (Daily Rotation)
    "gemini-2.5-flash": ModelSpec(
        id="gemini-2.5-flash",
        name="Gemini 2.5 Flash",
        provider="google",
        endpoint="https://generativelanguage.googleapis.com",
        tier=ModelTier.TIER_0_CONVERSATION,
        strengths=["Fast", "Good reasoning", "Tool use", "Multimodal"],
        weaknesses=["Less personality", "Can be generic"],
        context_window=128000,
        cost_per_1k=0.0,
        daily_quota=1500,
        monthly_quota=45000,
        supports_streaming=True,
        supports_tools=True,
        personality="Highly competent, slightly formal but warm",
    ),
    "minimax-m2.5-free": ModelSpec(
        id="minimax-m2.5-free",
        name="MiniMax 2.5 Free",
        provider="opencode/zen",
        endpoint="https://opencode.ai/zen/v1",
        tier=ModelTier.TIER_0_CONVERSATION,
        strengths=["Fast", "Concise", "Good code", "Free"],
        weaknesses=["Limited context", "Can be inconsistent"],
        context_window=100000,
        cost_per_1k=0.0,
        daily_quota=500,
        monthly_quota=15000,
        supports_streaming=True,
        supports_tools=True,
        personality="Direct, efficient, no-nonsense assistant",
    ),
    "nemotron-3-super-free": ModelSpec(
        id="nemotron-3-super-free",
        name="Super Nemotron 3",
        provider="opencode/zen",
        endpoint="https://opencode.ai/zen/v1",
        tier=ModelTier.TIER_0_CONVERSATION,
        strengths=[
            "Thorough",
            "Rigorous",
            "Watertight implementation",
            "Excellent for precise tasks",
        ],
        weaknesses=["Slower", "Verbose"],
        context_window=100000,
        cost_per_1k=0.0,
        daily_quota=100,
        monthly_quota=3000,
        supports_streaming=True,
        supports_tools=True,
        personality="Meticulous, precise, thorough to a fault",
    ),
    # TIER 1: Free Code/Reasoning Models
    "kimi-k2.5-free": ModelSpec(
        id="kimi-k2.5-free",
        name="Kimi K2.5",
        provider="openrouter",
        endpoint="https://openrouter.ai/api/v1",
        tier=ModelTier.TIER_1_CODE,
        strengths=[
            "Code analysis",
            "Long context",
            "Finds subtle errors",
            "Architecture",
        ],
        weaknesses=["Less conversational"],
        context_window=200000,
        cost_per_1k=0.0,
        daily_quota=100,
        monthly_quota=3000,
        supports_streaming=True,
        supports_tools=True,
        personality="Analytical, deep thinker, architectural mind",
    ),
    "qwen-3-122b-free": ModelSpec(
        id="qwen-3-122b-free",
        name="Qwen 3 122B",
        provider="openrouter",
        endpoint="https://openrouter.ai/api/v1",
        tier=ModelTier.TIER_1_CODE,
        strengths=["Code generation", "Speed", "Wide knowledge"],
        weaknesses=["Quality variance"],
        context_window=100000,
        cost_per_1k=0.0,
        daily_quota=50,
        monthly_quota=1500,
        supports_streaming=True,
        supports_tools=True,
        personality="Broad knowledge, quick implementations",
    ),
    # TIER 2: Paid Subscriptions
    "minimax-m2.5": ModelSpec(
        id="minimax-m2.5",
        name="MiniMax 2.5 (Go)",
        provider="opencode/go",
        endpoint="https://opencode.ai/zen/go/v1",
        tier=ModelTier.TIER_2_PAID,
        strengths=["Fast", "Concise", "Good code", "UI/Conversation primary"],
        weaknesses=["Subscription required"],
        context_window=100000,
        cost_per_1k=0.0,  # Subscription
        daily_quota=1000,
        monthly_quota=30000,
        supports_streaming=True,
        supports_tools=True,
        personality="Direct, efficient, primary voice interface",
    ),
    "kimi-k2.5": ModelSpec(
        id="kimi-k2.5",
        name="Kimi K2.5",
        provider="opencode/go",
        endpoint="https://opencode.ai/zen/go/v1",
        tier=ModelTier.TIER_2_PAID,
        strengths=[
            "Code analysis",
            "Error detection",
            "Refactoring",
            "Architecture design",
        ],
        weaknesses=["Costs credits"],
        context_window=200000,
        cost_per_1k=0.0,  # Subscription
        daily_quota=200,
        monthly_quota=6000,
        supports_streaming=True,
        supports_tools=True,
        personality="Premium code analyst, architectural perfectionist",
    ),
    "glm-5": ModelSpec(
        id="glm-5",
        name="GLM-5",
        provider="opencode/go",
        endpoint="https://opencode.ai/zen/go/v1",
        tier=ModelTier.TIER_2_PAID,
        strengths=["Reasoning", "Planning", "Code generation", "Long context"],
        weaknesses=["Subscription required"],
        context_window=200000,
        cost_per_1k=0.0,  # Subscription
        daily_quota=200,
        monthly_quota=6000,
        supports_streaming=True,
        supports_tools=True,
        personality="Strategic thinker, planning master",
    ),
    "minimax-m2.7": ModelSpec(
        id="minimax-m2.7",
        name="MiniMax M2.7",
        provider="opencode/go",
        endpoint="https://opencode.ai/zen/go/v1",
        tier=ModelTier.TIER_2_PAID,
        strengths=["Advanced reasoning", "Complex problem solving", "Code generation"],
        weaknesses=["Higher cost"],
        context_window=100000,
        cost_per_1k=0.0,  # Subscription
        daily_quota=100,
        monthly_quota=3000,
        supports_streaming=True,
        supports_tools=True,
        personality="Deep thinker, complex problem solver",
    ),
    # TIER 3: Premium / GitHub Copilot
    "claude-3-7-sonnet": ModelSpec(
        id="claude-3-7-sonnet",
        name="Claude 3.7 Sonnet",
        provider="github/copilot",
        endpoint="https://api.githubcopilot.com",
        tier=ModelTier.TIER_3_PREMIUM,
        strengths=["Code generation", "Review", "Architecture", "Complex reasoning"],
        weaknesses=["Limited by GitHub Pro quota"],
        context_window=200000,
        cost_per_1k=0.0,  # GitHub Pro
        daily_quota=500,
        monthly_quota=15000,
        supports_streaming=True,
        supports_tools=True,
        personality="Elegant coder, architectural excellence",
    ),
    "claude-4-6-opus": ModelSpec(
        id="claude-4-6-opus",
        name="Claude 4.6 Opus",
        provider="github/copilot",
        endpoint="https://api.githubcopilot.com",
        tier=ModelTier.TIER_3_PREMIUM,
        strengths=["Top-tier reasoning", "Code generation", "Complex orchestration"],
        weaknesses=["GitHub Pro limit"],
        context_window=200000,
        cost_per_1k=0.0,  # GitHub Pro
        daily_quota=200,
        monthly_quota=6000,
        supports_streaming=True,
        supports_tools=True,
        personality="Top-tier intellect, architectural mastermind",
    ),
}


# =============================================================================
# TASK SUITABILITY MATRIX
# =============================================================================

TASK_SUITABILITY: Dict[TaskType, Dict[str, float]] = {
    # (task_type, model_id) -> suitability_score (0-1)
    TaskType.CONVERSATION: {
        "minimax-m2.5-free": 0.95,
        "gemini-2.5-flash": 0.85,
        "nemotron-3-super-free": 0.6,
    },
    TaskType.ANALYSIS: {
        "kimi-k2.5": 0.95,
        "kimi-k2.5-free": 0.85,
        "claude-4-6-opus": 0.9,
        "minimax-m2.7": 0.85,
    },
    TaskType.IMPLEMENTATION: {
        "glm-5": 0.9,
        "nemotron-3-super-free": 0.95,  # Rigorous implementation
        "claude-3-7-sonnet": 0.85,
        "qwen-3-122b-free": 0.75,
    },
    TaskType.REASONING: {
        "minimax-m2.7": 0.95,
        "claude-4-6-opus": 0.9,
        "glm-5": 0.85,
        "nemotron-3-super-free": 0.8,
    },
    TaskType.CREATION: {
        "glm-5": 0.95,  # Planning master
        "kimi-k2.5": 0.9,
        "claude-3-7-sonnet": 0.85,
    },
    TaskType.REVIEW: {
        "kimi-k2.5": 0.95,  # Error detection
        "kimi-k2.5-free": 0.9,
        "nemotron-3-super-free": 0.85,
        "claude-3-7-sonnet": 0.8,
    },
    TaskType.ROUTING: {
        "glm-5": 0.9,  # Task brief creation
        "minimax-m2.7": 0.85,
        "nemotron-3-super-free": 0.8,
    },
    TaskType.ORCHESTRATION: {
        "claude-4-6-opus": 0.95,
        "glm-5": 0.9,
        "minimax-m2.7": 0.85,
    },
}


class ModelRouter:
    """
    Meta-cognitive router that selects optimal model for a given task.
    Considers: task type, model suitability, quota availability, cost.
    """

    def __init__(self):
        self.quota_manager = QuotaManager()
        self.conversation_rotation = [
            "gemini-2.5-flash",
            "minimax-m2.5-free",
            "nemotron-3-super-free",
        ]
        self.conversation_index = 0
        self.last_conversation_switch = datetime.now()

    def get_conversation_model(self) -> ModelSpec:
        """Get the next model in conversation rotation (free tier)."""
        now = datetime.now()
        if now - self.last_conversation_switch > timedelta(hours=4):
            self.conversation_index = (self.conversation_index + 1) % len(
                self.conversation_rotation
            )
            self.last_conversation_switch = now

        model_id = self.conversation_rotation[self.conversation_index]
        return MODEL_MATRIX[model_id]

    def select_model(self, task_type: TaskType, force_free: bool = False) -> ModelSpec:
        """
        Select optimal model for task.

        Strategy:
        1. Check suitability scores for task type
        2. Filter by quota availability
        3. Prefer free models unless force_paid=True
        4. Return best available
        """
        self.quota_manager.reset_daily_if_needed()
        self.quota_manager.reset_monthly_if_needed()

        candidates = TASK_SUITABILITY.get(task_type, {})

        scored_models = []
        for model_id, score in candidates.items():
            model = MODEL_MATRIX.get(model_id)
            if not model:
                continue

            if force_free and model.tier.value > ModelTier.TIER_1_CODE.value:
                continue

            has_quota = self.quota_manager.check_quota(model_id)
            if not has_quota:
                continue

            final_score = score * (1.0 if has_quota else 0.0)

            if model.tier == ModelTier.TIER_0_CONVERSATION:
                final_score *= 0.5  # Deprioritize for non-conversation

            scored_models.append((model_id, final_score))

        scored_models.sort(key=lambda x: x[1], reverse=True)

        if scored_models:
            return MODEL_MATRIX[scored_models[0][0]]

        return self.get_conversation_model()

    def get_project_analysis_team(self) -> List[ModelSpec]:
        """
        Get multi-model team for comprehensive project analysis.
        Each model finds different things (as Kilo Code demonstrated).
        """
        team = [
            self.select_model(TaskType.ANALYSIS, force_free=True),
            MODEL_MATRIX["kimi-k2.5-free"],
            MODEL_MATRIX["qwen-3-122b-free"],
            MODEL_MATRIX["nemotron-3-super-free"],
        ]
        seen = set()
        result = []
        for m in team:
            if m.id not in seen:
                seen.add(m.id)
                result.append(m)
        return result[:4]

    def get_task_brief_team(self) -> List[ModelSpec]:
        """Get team for creating optimal task briefs."""
        return [
            MODEL_MATRIX["glm-5"],  # Planning/orchestration
            MODEL_MATRIX["minimax-m2.7"],  # Complex reasoning
        ]

    def create_task_brief(self, task_description: str, context: str = "") -> str:
        """
        Generate optimal task brief using planning model.
        """
        planning_model = self.select_model(TaskType.ROUTING, force_free=False)

        prompt = f"""Create an optimal task brief for the following task:

Task: {task_description}

Context: {context}

Based on the task type, select the most suitable model from this matrix:
{json.dumps({k: v.name for k, v in MODEL_MATRIX.items()}, indent=2)}

Provide:
1. Task classification (task type)
2. Recommended primary model (with reasoning)
3. Recommended review model (with reasoning)
4. Implementation approach
5. Success criteria
"""
        return prompt


def run_swarm_diagnostic():
    """Run full system diagnostic."""
    router = ModelRouter()
    quota_mgr = QuotaManager()

    print("=" * 70)
    print("TONY STARK SWARM - SYSTEM DIAGNOSTIC")
    print("=" * 70)

    print("\n[1] MODEL CAPABILITY MATRIX")
    print("-" * 50)
    for model_id, model in MODEL_MATRIX.items():
        remaining = quota_mgr.get_remaining(model_id)
        print(f"  {model.name} ({model.provider})")
        print(f"    Tier: {model.tier.name}")
        print(f"    Strengths: {', '.join(model.strengths[:3])}")
        print(f"    Daily remaining: {remaining['daily']}/{model.daily_quota}")
        print()

    print("\n[2] TASK-TO-MODEL ROUTING")
    print("-" * 50)
    for task_type in TaskType:
        model = router.select_model(task_type)
        print(f"  {task_type.value}: {model.name}")

    print("\n[3] PROJECT ANALYSIS TEAM")
    print("-" * 50)
    team = router.get_project_analysis_team()
    for i, model in enumerate(team, 1):
        print(f"  {i}. {model.name} - {', '.join(model.strengths[:2])}")

    print("\n[4] QUOTA STATUS")
    print("-" * 50)
    for tier in ModelTier:
        tier_models = [m for m in MODEL_MATRIX.values() if m.tier == tier]
        if tier_models:
            print(f"\n  {tier.name}:")
            for m in tier_models[:2]:
                remaining = quota_mgr.get_remaining(m.id)
                status = "OK" if remaining["daily"] > 10 else "LOW"
                print(f"    {m.name}: {remaining['daily']} daily remaining [{status}]")

    print("\n" + "=" * 70)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    run_swarm_diagnostic()
