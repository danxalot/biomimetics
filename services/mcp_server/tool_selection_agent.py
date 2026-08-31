"""
Tool Selection Agent - Intelligent Tool Routing and Recommendation

This agent:
1. Analyzes incoming task descriptions
2. Recommends appropriate tools based on effectiveness
3. Routes tasks to selected tools
4. Records outcomes and updates tool effectiveness ratings
5. Learns from failures to improve recommendations

Mirrors SkillSelectionAgent but for tools instead of skills.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SelectionStrategy(Enum):
    """Strategy for tool selection"""

    BEST_MATCH = "best_match"  # Highest effectiveness for category
    HIGHEST_EFFECTIVENESS = "highest_effectiveness"  # Ranked by effectiveness alone
    BALANCED = "balanced"  # Balance effectiveness with diversity
    LEARNING = "learning"  # Prefer tools that need practice
    FASTEST = "fastest"  # Prefer tools with lowest latency


@dataclass
class ToolSelection:
    """Result of tool selection"""

    selected_tool_id: str
    tool_name: str
    effectiveness: float
    confidence: float  # 0.0-1.0, how confident is this selection
    reasoning: str  # Why this tool was selected
    alternatives: List[Tuple[str, str, float]] = field(
        default_factory=list
    )  # (id, name, score)
    required_parameters: Dict[str, str] = field(default_factory=dict)
    estimated_success_rate: float = 0.7
    estimated_latency_ms: float = 100.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "selected_tool_id": self.selected_tool_id,
            "tool_name": self.tool_name,
            "effectiveness": self.effectiveness,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "alternatives": self.alternatives,
            "required_parameters": self.required_parameters,
            "estimated_success_rate": self.estimated_success_rate,
            "estimated_latency_ms": self.estimated_latency_ms,
            "timestamp": datetime.now().isoformat(),
        }


@dataclass
class ExecutionRecord:
    """Record of tool execution"""

    selection: ToolSelection
    start_time: datetime
    end_time: Optional[datetime] = None
    success: bool = False
    result: Optional[Any] = None
    error: Optional[str] = None
    feedback: Optional[str] = None
    confidence_justified: bool = False  # Was confidence estimate accurate?
    actual_latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "tool_id": self.selection.selected_tool_id,
            "tool_name": self.selection.tool_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "success": self.success,
            "result": str(self.result) if self.result else None,
            "error": self.error,
            "feedback": self.feedback,
            "confidence_justified": self.confidence_justified,
            "actual_latency_ms": self.actual_latency_ms,
            "execution_time_ms": (self.end_time - self.start_time).total_seconds()
            * 1000
            if self.end_time
            else None,
        }


class ToolSelectionAgent:
    """
    Agent for intelligent tool selection and execution routing

    Features:
    - Analyzes task descriptions
    - Ranks available tools by effectiveness
    - Selects best tool for task
    - Executes tool (delegates to actual implementation)
    - Records outcomes and updates effectiveness
    - Learns from failures to improve recommendations
    """

    def __init__(self, tool_registry):
        """
        Initialize Tool Selection Agent

        Args:
            tool_registry: ToolRegistry instance
        """
        self.tool_registry = tool_registry
        self.execution_history: List[ExecutionRecord] = []
        self.selection_strategy = SelectionStrategy.BALANCED

        self.stats = {
            "total_selections": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "confidence_justified_rate": 0.0,
            "avg_confidence": 0.0,
            "avg_latency_ms": 0.0,
        }

    def select_tool(
        self,
        task_description: str,
        category: Optional[str] = None,
        required_parameters: Optional[List[str]] = None,
        strategy: Optional[SelectionStrategy] = None,
        max_latency_ms: Optional[float] = None,
    ) -> Optional[ToolSelection]:
        """
        Select best tool for a task

        Args:
            task_description: Description of what needs to be done
            category: Optional category filter (infrastructure, intelligence, memory, geometry, security, agent_ops, persistence, self_model)
            required_parameters: Optional list of required parameter names
            strategy: Strategy to use (defaults to agent's preferred strategy)
            max_latency_ms: Maximum acceptable latency in milliseconds

        Returns:
            ToolSelection with selected tool and alternatives
        """
        strategy = strategy or self.selection_strategy

        logger.info(f"🔧 Selecting tool for task: {task_description[:50]}...")

        # Get recommendations from tool registry
        recommendations = self.tool_registry.recommend_tools(
            task_description,
            category=None,  # We'll filter manually if needed
            top_k=10,
        )

        if not recommendations:
            logger.warning("❌ No tools available for task")
            return None

        # Filter by category if specified
        if category:
            try:
                from tool_registry import ToolCategory

                category_enum = ToolCategory(category)
                recommendations = [
                    r for r in recommendations if r.get("category") == category
                ]
            except ValueError:
                logger.warning(f"Unknown category: {category}")

        # Filter by max latency if specified
        if max_latency_ms:
            recommendations = [
                r
                for r in recommendations
                if self.tool_registry._tools.get(r["tool_id"], {}).latency_p50
                < max_latency_ms
            ]

        if not recommendations:
            logger.warning("❌ No tools match filters")
            return None

        # Score and rank tools based on strategy
        scored_tools = self._score_tools(recommendations, strategy, task_description)

        if not scored_tools:
            return None

        # Select top tool
        top_tool = scored_tools[0]

        # Get full metadata
        tool_metadata = self.tool_registry._tools.get(top_tool["tool_id"])

        # Build selection result
        selection = ToolSelection(
            selected_tool_id=top_tool["tool_id"],
            tool_name=top_tool["name"],
            effectiveness=top_tool["effectiveness"],
            confidence=top_tool["confidence"],
            reasoning=self._generate_reasoning(top_tool, task_description, strategy),
            alternatives=[
                (t["tool_id"], t["name"], t["confidence"])
                for t in scored_tools[1:5]  # Top 4 alternatives
            ],
            required_parameters=tool_metadata.parameters if tool_metadata else {},
            estimated_success_rate=top_tool.get("estimated_success_rate", 0.7),
            estimated_latency_ms=top_tool.get("latency_p50", 100.0),
        )

        # Update stats
        self.stats["total_selections"] += 1
        self.stats["avg_confidence"] = (
            self.stats["avg_confidence"] * (self.stats["total_selections"] - 1)
            + selection.confidence
        ) / self.stats["total_selections"]

        logger.info(
            f"✅ Selected tool: {selection.tool_name} (confidence: {selection.confidence:.2f})"
        )

        return selection

    def _score_tools(
        self,
        recommendations: List[Dict[str, Any]],
        strategy: SelectionStrategy,
        task_description: str,
    ) -> List[Dict[str, Any]]:
        """Score and rank tools based on strategy"""
        scored = []

        for tool_rec in recommendations:
            tool_id = tool_rec["tool_id"]
            metadata = self.tool_registry._tools.get(tool_id)

            # Base scores
            effectiveness = tool_rec.get("effectiveness", 0.5)
            confidence = tool_rec.get("confidence", 0.5)

            # Get actual metrics
            latency_p50 = metadata.latency_p50 if metadata else 100.0
            success_rate = metadata.success_rate if metadata else 0.7

            # Strategy-specific scoring
            if strategy == SelectionStrategy.BEST_MATCH:
                # Weight by keyword match confidence and effectiveness
                score = (confidence * 0.6) + (effectiveness * 0.4)

            elif strategy == SelectionStrategy.HIGHEST_EFFECTIVENESS:
                # Pure effectiveness ranking
                score = effectiveness

            elif strategy == SelectionStrategy.BALANCED:
                # Balanced score: effectiveness + confidence + latency
                latency_score = max(0.0, 1.0 - (latency_p50 / 5000.0))
                score = (
                    (effectiveness * 0.4) + (confidence * 0.3) + (latency_score * 0.3)
                )

            elif strategy == SelectionStrategy.LEARNING:
                # Prefer tools that need practice (lower usage but decent effectiveness)
                usage_factor = 1.0 - min(
                    1.0, metadata.invocation_count / 100 if metadata else 0.0
                )
                score = (effectiveness * 0.5) + (usage_factor * 0.5)

            elif strategy == SelectionStrategy.FASTEST:
                # Prefer low latency
                latency_score = max(0.0, 1.0 - (latency_p50 / 5000.0))
                score = (latency_score * 0.7) + (effectiveness * 0.3)

            else:
                score = confidence

            # Add derived fields
            tool_rec["score"] = score
            tool_rec["estimated_success_rate"] = success_rate
            tool_rec["latency_p50"] = latency_p50

            scored.append(tool_rec)

        # Sort by score descending
        scored.sort(key=lambda x: x["score"], reverse=True)

        return scored

    def _generate_reasoning(
        self, tool: Dict[str, Any], task_description: str, strategy: SelectionStrategy
    ) -> str:
        """Generate human-readable reasoning for tool selection"""
        tool_name = tool["name"]
        effectiveness = tool.get("effectiveness", 0.0)
        confidence = tool.get("confidence", 0.0)

        if strategy == SelectionStrategy.BEST_MATCH:
            return f"Selected {tool_name} as best match for task with {effectiveness:.0%} effectiveness and {confidence:.0%} confidence"

        elif strategy == SelectionStrategy.HIGHEST_EFFECTIVENESS:
            return f"Selected {tool_name} with highest effectiveness score of {effectiveness:.0%}"

        elif strategy == SelectionStrategy.BALANCED:
            return f"Selected {tool_name} balancing effectiveness ({effectiveness:.0%}), confidence ({confidence:.0%}), and performance"

        elif strategy == SelectionStrategy.LEARNING:
            return f"Selected {tool_name} to build experience (current effectiveness: {effectiveness:.0%})"

        elif strategy == SelectionStrategy.FASTEST:
            latency = tool.get("latency_p50", 0)
            return (
                f"Selected {tool_name} for fastest response time ({latency:.0f}ms p50)"
            )

        else:
            return f"Selected {tool_name} based on configured selection criteria"

    async def execute_task(
        self,
        task_description: str,
        parameters: Optional[Dict[str, Any]] = None,
        strategy: Optional[SelectionStrategy] = None,
    ) -> ExecutionRecord:
        """
        Select and execute a tool for a task

        Args:
            task_description: Description of what needs to be done
            parameters: Optional parameters to pass to tool
            strategy: Selection strategy to use

        Returns:
            ExecutionRecord with results
        """
        # Select tool
        selection = self.select_tool(task_description, strategy=strategy)

        if not selection:
            # No suitable tool found
            record = ExecutionRecord(
                selection=ToolSelection(
                    selected_tool_id="none",
                    tool_name="None",
                    effectiveness=0.0,
                    confidence=0.0,
                    reasoning="No suitable tool found for task",
                ),
                start_time=datetime.now(),
                success=False,
                error="No suitable tool found",
            )
            self.execution_history.append(record)
            self.stats["failed_executions"] += 1
            return record

        # Execute tool
        start_time = datetime.now()
        success = False
        result = None
        error = None

        try:
            # Use registry to execute
            result = await self.tool_registry.execute_tool(
                selection.selected_tool_id, arguments=parameters or {}
            )
            success = not (isinstance(result, dict) and "error" in result)

        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            error = str(e)
            success = False

        end_time = datetime.now()
        actual_latency_ms = (end_time - start_time).total_seconds() * 1000

        # Create execution record
        record = ExecutionRecord(
            selection=selection,
            start_time=start_time,
            end_time=end_time,
            success=success,
            result=result,
            error=error,
            actual_latency_ms=actual_latency_ms,
        )

        # Update confidence justification
        expected_success = selection.estimated_success_rate > 0.5
        record.confidence_justified = success == expected_success

        # Store in history
        self.execution_history.append(record)

        # Update stats
        if success:
            self.stats["successful_executions"] += 1
        else:
            self.stats["failed_executions"] += 1

        # Update average latency
        total_executions = len(self.execution_history)
        self.stats["avg_latency_ms"] = (
            self.stats["avg_latency_ms"] * (total_executions - 1) + actual_latency_ms
        ) / total_executions

        # Update confidence justified rate
        justified_count = sum(
            1 for r in self.execution_history if r.confidence_justified
        )
        self.stats["confidence_justified_rate"] = justified_count / total_executions

        logger.info(
            f"{'✅' if success else '❌'} Tool execution completed in {actual_latency_ms:.0f}ms"
        )

        return record

    def get_execution_history(
        self,
        tool_id: Optional[str] = None,
        success_only: bool = False,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get execution history with optional filtering

        Args:
            tool_id: Filter by specific tool
            success_only: Only return successful executions
            limit: Maximum number of records to return

        Returns:
            List of execution records
        """
        history = self.execution_history

        if tool_id:
            history = [r for r in history if r.selection.selected_tool_id == tool_id]

        if success_only:
            history = [r for r in history if r.success]

        # Convert to dicts and sort by start time descending
        history_dicts = [r.to_dict() for r in history]
        history_dicts.sort(key=lambda x: x["start_time"], reverse=True)

        return history_dicts[:limit]

    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics"""
        total = self.stats["total_selections"]
        return {
            **self.stats,
            "success_rate": (
                self.stats["successful_executions"] / total if total > 0 else 0.0
            ),
            "total_executions": len(self.execution_history),
        }


# ============================================================================
# Global Instance
# ============================================================================

_global_instance: Optional[ToolSelectionAgent] = None


def get_tool_selection_agent(tool_registry=None):
    """
    Get or create the global ToolSelectionAgent instance

    Args:
        tool_registry: ToolRegistry instance (required if creating new instance)

    Returns:
        ToolSelectionAgent instance
    """
    global _global_instance

    if _global_instance is None:
        if tool_registry is None:
            from tool_registry import get_tool_registry

            tool_registry = get_tool_registry()

        _global_instance = ToolSelectionAgent(tool_registry)
        logger.info("✅ Created global ToolSelectionAgent instance")

    return _global_instance
