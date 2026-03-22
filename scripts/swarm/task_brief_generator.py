#!/usr/bin/env python3
"""
Task Brief Generator
====================
Creates optimal task briefs for the agent PM and routes tasks
to the most suitable model based on task complexity, type, and quota.

This is the meta-cognitive layer that:
1. Analyzes incoming tasks
2. Creates structured briefs
3. Selects optimal model
4. Tracks task outcomes for learning
"""

import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from model_selector import MODEL_MATRIX, ModelRouter, TaskType, ModelTier, QuotaManager


class TaskPriority(Enum):
    CRITICAL = 1  # Blockers, security issues
    HIGH = 2  # Core features
    MEDIUM = 3  # Improvements
    LOW = 4  # Nice to have


class TaskComplexity(Enum):
    TRIVIAL = 1  # Quick fixes, one-liners
    SIMPLE = 2  # Single file, clear scope
    MODERATE = 3  # Multi-file, some ambiguity
    COMPLEX = 4  # Architecture, significant changes
    CRITICAL = 5  # System-level, high risk


@dataclass
class TaskBrief:
    task_id: str
    description: str
    priority: TaskPriority
    complexity: TaskComplexity
    task_type: TaskType

    primary_model: str
    primary_model_reasoning: str

    review_model: Optional[str] = None
    review_model_reasoning: Optional[str] = None

    implementation_steps: List[str] = None
    success_criteria: List[str] = None
    estimated_tokens: int = 0

    created_at: str = None
    completed_at: Optional[str] = None
    outcome: Optional[str] = None

    def __post_init__(self):
        if self.implementation_steps is None:
            self.implementation_steps = []
        if self.success_criteria is None:
            self.success_criteria = []
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


class TaskBriefGenerator:
    """
    Meta-cognitive task brief generator.
    Analyzes tasks and creates optimal briefs with model routing.
    """

    def __init__(self, briefs_dir: str = "~/.stark_swarm/briefs"):
        self.briefs_dir = Path(os.path.expanduser(briefs_dir))
        self.briefs_dir.mkdir(parents=True, exist_ok=True)
        self.router = ModelRouter()
        self.quota_manager = QuotaManager()
        self._load_brief_history()

    def _load_brief_history(self):
        history_file = self.briefs_dir / "brief_history.json"
        if history_file.exists():
            with open(history_file) as f:
                self.history = json.load(f)
        else:
            self.history = {"briefs": [], "outcomes": {}}

    def _save_history(self):
        history_file = self.briefs_dir / "brief_history.json"
        with open(history_file, "w") as f:
            json.dump(self.history, f, indent=2)

    def analyze_task(self, description: str, context: str = "") -> Dict:
        """
        Analyze task to determine priority, complexity, and optimal routing.
        """
        description_lower = description.lower()
        context_lower = context.lower()

        priority = TaskPriority.MEDIUM
        if any(
            kw in description_lower
            for kw in ["critical", "blocker", "security", "urgent", "asap"]
        ):
            priority = TaskPriority.CRITICAL
        elif any(kw in description_lower for kw in ["important", "core", "must-have"]):
            priority = TaskPriority.HIGH
        elif any(
            kw in description_lower for kw in ["nice-to-have", "cleanup", "refactor"]
        ):
            priority = TaskPriority.LOW

        complexity = TaskComplexity.MODERATE
        if any(kw in description_lower for kw in ["simple", "fix", "typo", "one-line"]):
            complexity = TaskComplexity.TRIVIAL
        if any(
            kw in description_lower
            for kw in ["architecture", "system", "redesign", "core"]
        ):
            complexity = TaskComplexity.CRITICAL
        elif any(
            kw in description_lower for kw in ["multi-file", "refactor", "complex"]
        ):
            complexity = TaskComplexity.COMPLEX

        task_type = TaskType.IMPLEMENTATION
        if any(kw in description_lower for kw in ["analyze", "review", "check"]):
            task_type = TaskType.ANALYSIS
        elif any(
            kw in description_lower
            for kw in ["plan", "design", "propose", "create brief"]
        ):
            task_type = TaskType.CREATION
        elif any(
            kw in description_lower
            for kw in ["reason", "solve", "debug", "investigate"]
        ):
            task_type = TaskType.REASONING
        elif any(
            kw in description_lower
            for kw in ["implement", "build", "create", "write", "add"]
        ):
            task_type = TaskType.IMPLEMENTATION

        return {"priority": priority, "complexity": complexity, "task_type": task_type}

    def select_models(self, task_type: TaskType, complexity: TaskComplexity) -> tuple:
        """
        Select primary and review models based on task characteristics.
        """
        use_paid = complexity.value >= TaskComplexity.COMPLEX.value

        primary = self.router.select_model(task_type, force_free=not use_paid)

        review_task = TaskType.REVIEW
        review = self.router.select_model(review_task, force_free=True)

        return primary, review

    def generate_brief(
        self, description: str, context: str = "", github_issue: Dict = None
    ) -> TaskBrief:
        """
        Generate comprehensive task brief with optimal model routing.
        """
        analysis = self.analyze_task(description, context)

        primary_model, review_model = self.select_models(
            analysis["task_type"], analysis["complexity"]
        )

        task_id = f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        brief = TaskBrief(
            task_id=task_id,
            description=description,
            priority=analysis["priority"],
            complexity=analysis["complexity"],
            task_type=analysis["task_type"],
            primary_model=primary_model.id,
            primary_model_reasoning=f"Selected for {analysis['task_type'].value} at {analysis['complexity'].name} complexity",
            review_model=review_model.id,
            review_model_reasoning=f"Review model for error detection and quality gate",
            implementation_steps=self._generate_steps(description, analysis),
            success_criteria=self._generate_criteria(description, analysis),
        )

        if github_issue:
            brief.task_id = f"github-{github_issue.get('number', 'unknown')}"

        self._save_brief(brief)
        return brief

    def _generate_steps(self, description: str, analysis: Dict) -> List[str]:
        """Generate implementation steps based on task type."""
        steps = []

        if analysis["task_type"] == TaskType.IMPLEMENTATION:
            steps = [
                "Read existing code to understand context",
                "Identify files requiring changes",
                "Implement changes incrementally",
                "Test locally before commit",
                "Run linting and type checks",
                "Submit for review",
            ]
        elif analysis["task_type"] == TaskType.ANALYSIS:
            steps = [
                "Scan project structure",
                "Analyze targeted components",
                "Identify patterns and anomalies",
                "Document findings",
                "Suggest remediation",
            ]
        elif analysis["task_type"] == TaskType.REASONING:
            steps = [
                "Break down problem into components",
                "Analyze dependencies and constraints",
                "Develop solution hypothesis",
                "Validate with evidence",
                "Document reasoning chain",
            ]

        return steps

    def _generate_criteria(self, description: str, analysis: Dict) -> List[str]:
        """Generate success criteria."""
        criteria = [
            f"Task type: {analysis['task_type'].value}",
            f"Priority: {analysis['priority'].name}",
            f"Complexity: {analysis['complexity'].name}",
        ]

        if "error" in description.lower():
            criteria.append("Error is resolved")
        if "test" in description.lower():
            criteria.append("Tests pass")
        if "security" in description.lower():
            criteria.append("Security review passed")

        return criteria

    def _save_brief(self, brief: TaskBrief):
        """Save brief to history."""
        brief_dict = asdict(brief)
        brief_dict["priority"] = brief.priority.name
        brief_dict["complexity"] = brief.complexity.name
        brief_dict["task_type"] = brief.task_type.value
        self.history["briefs"].append(brief_dict)
        self._save_history()

    def get_brief(self, task_id: str) -> Optional[TaskBrief]:
        """Retrieve a specific brief."""
        for brief_dict in self.history["briefs"]:
            if brief_dict["task_id"] == task_id:
                return TaskBrief(**brief_dict)
        return None

    def complete_task(self, task_id: str, outcome: str):
        """Mark task as completed and track outcome."""
        for brief_dict in self.history["briefs"]:
            if brief_dict["task_id"] == task_id:
                brief_dict["outcome"] = outcome
                brief_dict["completed_at"] = datetime.now().isoformat()

                if task_id not in self.history["outcomes"]:
                    self.history["outcomes"][task_id] = []
                self.history["outcomes"][task_id].append(outcome)

                self._save_history()
                return True
        return False

    def generate_routing_report(self) -> str:
        """Generate report on task routing effectiveness."""
        report = []
        report.append("=" * 70)
        report.append("TASK ROUTING EFFECTIVENESS REPORT")
        report.append("=" * 70)

        model_usage = {}
        task_type_distribution = {}

        for brief_dict in self.history["briefs"]:
            primary = brief_dict["primary_model"]
            model_usage[primary] = model_usage.get(primary, 0) + 1

            task_type = brief_dict["task_type"]
            task_type_distribution[task_type] = (
                task_type_distribution.get(task_type, 0) + 1
            )

        report.append("\nModel Usage:")
        for model_id, count in sorted(model_usage.items(), key=lambda x: -x[1]):
            model = MODEL_MATRIX.get(model_id)
            name = model.name if model else model_id
            report.append(f"  {name}: {count} tasks")

        report.append("\nTask Type Distribution:")
        for task_type, count in task_type_distribution.items():
            report.append(f"  {task_type}: {count}")

        report.append("\n" + "=" * 70)
        return "\n".join(report)


def generate_task_brief_cli():
    """CLI for generating task briefs."""
    import argparse

    parser = argparse.ArgumentParser(description="Task Brief Generator")
    parser.add_argument("description", help="Task description")
    parser.add_argument("--context", "-c", help="Additional context")
    parser.add_argument(
        "--priority",
        "-p",
        choices=["critical", "high", "medium", "low"],
        help="Override priority",
    )
    parser.add_argument("--model", "-m", help="Force specific model")
    parser.add_argument("--output", "-o", help="Output file")
    args = parser.parse_args()

    generator = TaskBriefGenerator()
    brief = generator.generate_brief(args.description, args.context or "")

    print("=" * 70)
    print("TASK BRIEF GENERATED")
    print("=" * 70)
    print(f"\nTask ID: {brief.task_id}")
    print(f"Priority: {brief.priority.name}")
    print(f"Complexity: {brief.complexity.name}")
    print(f"Task Type: {brief.task_type.value}")
    print(f"\nPrimary Model: {brief.primary_model}")
    print(f"  Reasoning: {brief.primary_model_reasoning}")
    print(f"\nReview Model: {brief.review_model}")
    print(f"  Reasoning: {brief.review_model_reasoning}")
    print(f"\nImplementation Steps:")
    for i, step in enumerate(brief.implementation_steps, 1):
        print(f"  {i}. {step}")
    print(f"\nSuccess Criteria:")
    for criterion in brief.success_criteria:
        print(f"  - {criterion}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(asdict(brief), f, indent=2)
        print(f"\n[+] Brief saved to: {args.output}")

    return brief


if __name__ == "__main__":
    generate_task_brief_cli()
