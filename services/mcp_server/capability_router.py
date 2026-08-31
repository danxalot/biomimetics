"""
Capability Router - Unified Skill/Tool Routing

Combines SkillSelectionAgent + ToolSelectionAgent outputs to answer:
"Given this task, should I use a skill, a tool, or both?"

Returns ranked capability list with confidence scores and logs routing
decisions to Neo4j for pattern analysis.

Author: ARCA System
Date: March 2026
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class CapabilityType(Enum):
    """Type of capability"""

    SKILL = "skill"
    TOOL = "tool"
    HYBRID = "hybrid"  # Both skill and tool needed


class RoutingStrategy(Enum):
    """Strategy for routing decisions"""

    BEST_MATCH = "best_match"  # Route to highest confidence option
    SKILL_FIRST = "skill_first"  # Prefer skills, fall back to tools
    TOOL_FIRST = "tool_first"  # Prefer tools, fall back to skills
    HYBRID_AWARE = "hybrid_aware"  # Consider skill-tool combinations


@dataclass
class CapabilityMatch:
    """A matched capability for a task"""

    capability_type: CapabilityType
    capability_id: str
    name: str
    description: str
    category: str
    confidence: float
    effectiveness: float
    reasoning: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "capability_type": self.capability_type.value,
            "capability_id": self.capability_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "confidence": self.confidence,
            "effectiveness": self.effectiveness,
            "reasoning": self.reasoning,
            "metadata": self.metadata,
        }


@dataclass
class RoutingDecision:
    """Result of capability routing"""

    task_description: str
    primary_capability: Optional[CapabilityMatch]
    alternative_capabilities: List[CapabilityMatch]
    routing_strategy: RoutingStrategy
    confidence: float
    reasoning: str
    should_log_to_neo4j: bool = True
    neo4j_node_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "task_description": self.task_description,
            "primary_capability": self.primary_capability.to_dict()
            if self.primary_capability
            else None,
            "alternative_capabilities": [
                c.to_dict() for c in self.alternative_capabilities
            ],
            "routing_strategy": self.routing_strategy.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "timestamp": datetime.now().isoformat(),
            "neo4j_node_id": self.neo4j_node_id,
        }


class CapabilityRouter:
    """
    Unified router for skills and tools

    Features:
    - Analyzes task descriptions
    - Queries both SkillSelectionAgent and ToolSelectionAgent
    - Ranks and combines results
    - Returns best capability recommendation
    - Logs decisions to Neo4j for pattern analysis
    """

    def __init__(
        self,
        skills_manager=None,
        tool_registry=None,
        neo4j_uri: Optional[str] = None,
        neo4j_user: Optional[str] = None,
        neo4j_password: Optional[str] = None,
    ):
        """
        Initialize Capability Router

        Args:
            skills_manager: EnhancedSkillsManager instance
            tool_registry: ToolRegistry instance
            neo4j_uri: Neo4j connection URI (e.g., bolt://neo4j-hub:7687)
            neo4j_user: Neo4j username
            neo4j_password: Neo4j password
        """
        self.skills_manager = skills_manager
        self.tool_registry = tool_registry

        # Initialize selection agents
        self._skill_agent = None
        self._tool_agent = None

        # Neo4j configuration
        self.neo4j_uri = neo4j_uri
        self.neo4j_user = neo4j_user
        self.neo4j_password = neo4j_password
        self._neo4j_driver = None

        # Routing strategy
        self.routing_strategy = RoutingStrategy.HYBRID_AWARE

        # Statistics
        self.stats = {
            "total_routings": 0,
            "skill_routings": 0,
            "tool_routings": 0,
            "hybrid_routings": 0,
            "avg_confidence": 0.0,
            "neo4j_logs": 0,
        }

        # Initialize Neo4j driver if configured
        if neo4j_uri:
            self._init_neo4j_driver()

    def _init_skill_agent(self):
        """Lazy initialization of skill selection agent"""
        if self._skill_agent is None and self.skills_manager:
            try:
                from skill_selection_agent import SkillSelectionAgent

                self._skill_agent = SkillSelectionAgent(self.skills_manager)
                logger.info("✅ Initialized SkillSelectionAgent")
            except ImportError as e:
                logger.warning(f"Could not initialize SkillSelectionAgent: {e}")

        return self._skill_agent

    def _init_tool_agent(self):
        """Lazy initialization of tool selection agent"""
        if self._tool_agent is None and self.tool_registry:
            try:
                from tool_selection_agent import ToolSelectionAgent

                self._tool_agent = ToolSelectionAgent(self.tool_registry)
                logger.info("✅ Initialized ToolSelectionAgent")
            except ImportError as e:
                logger.warning(f"Could not initialize ToolSelectionAgent: {e}")

        return self._tool_agent

    def _init_neo4j_driver(self):
        """Initialize Neo4j driver for logging"""
        try:
            from neo4j import GraphDatabase

            self._neo4j_driver = GraphDatabase.driver(
                self.neo4j_uri, auth=(self.neo4j_user, self.neo4j_password)
            )

            # Test connection
            with self._neo4j_driver.session() as session:
                session.run("RETURN 1")

            logger.info(f"✅ Connected to Neo4j at {self.neo4j_uri}")

        except ImportError:
            logger.warning(
                "Neo4j driver not available - routing logs will be in-memory only"
            )
        except Exception as e:
            logger.warning(f"Could not connect to Neo4j: {e}")

    def route_task(
        self,
        task_description: str,
        strategy: Optional[RoutingStrategy] = None,
        category_filter: Optional[str] = None,
        log_to_neo4j: bool = True,
    ) -> RoutingDecision:
        """
        Route a task to the best capability (skill or tool)

        Args:
            task_description: Description of the task
            strategy: Routing strategy to use
            category_filter: Optional category filter
            log_to_neo4j: Whether to log decision to Neo4j

        Returns:
            RoutingDecision with primary capability and alternatives
        """
        strategy = strategy or self.routing_strategy

        logger.info(f"🧭 Routing task: {task_description[:50]}...")

        # Initialize agents if needed
        skill_agent = self._init_skill_agent()
        tool_agent = self._init_tool_agent()

        # Get skill recommendations
        skill_matches = []
        if skill_agent:
            try:
                skill_selection = skill_agent.select_skill(
                    task_description,
                    category=category_filter,
                    strategy=skill_agent.selection_strategy,
                )

                if skill_selection:
                    skill_matches.append(
                        CapabilityMatch(
                            capability_type=CapabilityType.SKILL,
                            capability_id=skill_selection.selected_skill_id,
                            name=skill_selection.skill_name,
                            description=f"Skill: {skill_selection.skill_name}",
                            category=category_filter or "unknown",
                            confidence=skill_selection.confidence,
                            effectiveness=skill_selection.effectiveness,
                            reasoning=skill_selection.reasoning,
                            metadata={
                                "estimated_success_rate": skill_selection.estimated_success_rate,
                                "alternatives": skill_selection.alternatives,
                            },
                        )
                    )
            except Exception as e:
                logger.error(f"Error getting skill recommendations: {e}")

        # Get tool recommendations
        tool_matches = []
        if tool_agent:
            try:
                tool_selection = tool_agent.select_tool(
                    task_description,
                    category=category_filter,
                    strategy=tool_agent.selection_strategy,
                )

                if tool_selection:
                    tool_matches.append(
                        CapabilityMatch(
                            capability_type=CapabilityType.TOOL,
                            capability_id=tool_selection.selected_tool_id,
                            name=tool_selection.tool_name,
                            description=f"Tool: {tool_selection.tool_name}",
                            category=category_filter or "unknown",
                            confidence=tool_selection.confidence,
                            effectiveness=tool_selection.effectiveness,
                            reasoning=tool_selection.reasoning,
                            metadata={
                                "estimated_success_rate": tool_selection.estimated_success_rate,
                                "estimated_latency_ms": tool_selection.estimated_latency_ms,
                                "alternatives": tool_selection.alternatives,
                            },
                        )
                    )
            except Exception as e:
                logger.error(f"Error getting tool recommendations: {e}")

        # Combine and rank matches
        all_matches = skill_matches + tool_matches

        if not all_matches:
            logger.warning("❌ No capabilities available for task")
            decision = RoutingDecision(
                task_description=task_description,
                primary_capability=None,
                alternative_capabilities=[],
                routing_strategy=strategy,
                confidence=0.0,
                reasoning="No suitable skills or tools found for this task",
            )
            return decision

        # Apply routing strategy
        primary = self._select_primary_capability(all_matches, strategy)
        alternatives = self._rank_alternatives(all_matches, primary, strategy)

        # Determine if hybrid approach is needed
        capability_type = (
            CapabilityType.SKILL
            if primary.capability_type == CapabilityType.SKILL
            else CapabilityType.TOOL
        )

        # Check if complementary capability exists
        if strategy == RoutingStrategy.HYBRID_AWARE:
            has_skill = any(
                m.capability_type == CapabilityType.SKILL for m in all_matches
            )
            has_tool = any(
                m.capability_type == CapabilityType.TOOL for m in all_matches
            )

            if has_skill and has_tool:
                # Consider hybrid if both types have good confidence
                skill_conf = max((m.confidence for m in skill_matches), default=0.0)
                tool_conf = max((m.confidence for m in tool_matches), default=0.0)

                if skill_conf > 0.5 and tool_conf > 0.5:
                    capability_type = CapabilityType.HYBRID

        # Build reasoning
        reasoning = self._generate_routing_reasoning(
            primary, alternatives, strategy, capability_type
        )

        # Create decision
        decision = RoutingDecision(
            task_description=task_description,
            primary_capability=primary,
            alternative_capabilities=alternatives,
            routing_strategy=strategy,
            confidence=primary.confidence,
            reasoning=reasoning,
            should_log_to_neo4j=log_to_neo4j,
        )

        # Update stats
        self.stats["total_routings"] += 1
        if capability_type == CapabilityType.HYBRID:
            self.stats["hybrid_routings"] += 1
        elif primary.capability_type == CapabilityType.SKILL:
            self.stats["skill_routings"] += 1
        else:
            self.stats["tool_routings"] += 1

        self.stats["avg_confidence"] = (
            self.stats["avg_confidence"] * (self.stats["total_routings"] - 1)
            + decision.confidence
        ) / self.stats["total_routings"]

        # Log to Neo4j
        if log_to_neo4j and self._neo4j_driver:
            self._log_routing_to_neo4j(decision)

        logger.info(
            f"✅ Routed to {primary.name} ({primary.capability_type.value}) with {decision.confidence:.0%} confidence"
        )

        return decision

    def _select_primary_capability(
        self, matches: List[CapabilityMatch], strategy: RoutingStrategy
    ) -> CapabilityMatch:
        """Select primary capability based on strategy"""

        if strategy == RoutingStrategy.SKILL_FIRST:
            # Prefer skills
            skill_matches = [
                m for m in matches if m.capability_type == CapabilityType.SKILL
            ]
            if skill_matches:
                return max(skill_matches, key=lambda m: m.confidence)
            # Fall back to tools
            tool_matches = [
                m for m in matches if m.capability_type == CapabilityType.TOOL
            ]
            if tool_matches:
                return max(tool_matches, key=lambda m: m.confidence)

        elif strategy == RoutingStrategy.TOOL_FIRST:
            # Prefer tools
            tool_matches = [
                m for m in matches if m.capability_type == CapabilityType.TOOL
            ]
            if tool_matches:
                return max(tool_matches, key=lambda m: m.confidence)
            # Fall back to skills
            skill_matches = [
                m for m in matches if m.capability_type == CapabilityType.SKILL
            ]
            if skill_matches:
                return max(skill_matches, key=lambda m: m.confidence)

        # Default: best match by confidence
        return max(matches, key=lambda m: m.confidence)

    def _rank_alternatives(
        self,
        all_matches: List[CapabilityMatch],
        primary: CapabilityMatch,
        strategy: RoutingStrategy,
    ) -> List[CapabilityMatch]:
        """Rank alternative capabilities"""
        # Exclude primary
        alternatives = [
            m for m in all_matches if m.capability_id != primary.capability_id
        ]

        # Sort by confidence
        alternatives.sort(key=lambda m: m.confidence, reverse=True)

        # Return top 5
        return alternatives[:5]

    def _generate_routing_reasoning(
        self,
        primary: CapabilityMatch,
        alternatives: List[CapabilityMatch],
        strategy: RoutingStrategy,
        capability_type: CapabilityType,
    ) -> str:
        """Generate human-readable routing reasoning"""

        reasoning_parts = []

        # Primary selection reasoning
        reasoning_parts.append(
            f"Selected {primary.name} ({primary.capability_type.value}) "
            f"with {primary.confidence:.0%} confidence and {primary.effectiveness:.0%} effectiveness"
        )

        # Strategy influence
        if strategy == RoutingStrategy.SKILL_FIRST:
            reasoning_parts.append("preferring skills over tools")
        elif strategy == RoutingStrategy.TOOL_FIRST:
            reasoning_parts.append("preferring tools over skills")
        elif strategy == RoutingStrategy.HYBRID_AWARE:
            if capability_type == CapabilityType.HYBRID:
                reasoning_parts.append("both skill and tool approaches recommended")

        # Alternative mention
        if alternatives:
            alt_names = [f"{a.name} ({a.confidence:.0%})" for a in alternatives[:3]]
            reasoning_parts.append(f"Alternatives: {', '.join(alt_names)}")

        return ". ".join(reasoning_parts) + "."

    def _log_routing_to_neo4j(self, decision: RoutingDecision):
        """Log routing decision to Neo4j for pattern analysis"""
        if not self._neo4j_driver:
            return

        try:
            with self._neo4j_driver.session() as session:
                # Create Routing node
                query = """
                CREATE (r:RoutingDecision {
                    task_description: $task_description,
                    capability_type: $capability_type,
                    capability_id: $capability_id,
                    capability_name: $capability_name,
                    confidence: $confidence,
                    effectiveness: $effectiveness,
                    reasoning: $reasoning,
                    strategy: $strategy,
                    timestamp: $timestamp,
                    alternatives_count: $alternatives_count
                })
                RETURN id(r) as node_id
                """

                result = session.run(
                    query,
                    task_description=decision.task_description,
                    capability_type=decision.primary_capability.capability_type.value
                    if decision.primary_capability
                    else None,
                    capability_id=decision.primary_capability.capability_id
                    if decision.primary_capability
                    else None,
                    capability_name=decision.primary_capability.name
                    if decision.primary_capability
                    else None,
                    confidence=decision.confidence,
                    effectiveness=decision.primary_capability.effectiveness
                    if decision.primary_capability
                    else None,
                    reasoning=decision.reasoning,
                    strategy=decision.routing_strategy.value,
                    timestamp=datetime.now().isoformat(),
                    alternatives_count=len(decision.alternative_capabilities),
                )

                record = result.single()
                if record:
                    decision.neo4j_node_id = record["node_id"]
                    self.stats["neo4j_logs"] += 1
                    logger.debug(
                        f"Logged routing decision to Neo4j (node id: {decision.neo4j_node_id})"
                    )

        except Exception as e:
            logger.error(f"Failed to log routing to Neo4j: {e}")

    def get_routing_history(
        self, capability_type: Optional[CapabilityType] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get routing history from Neo4j

        Args:
            capability_type: Filter by capability type
            limit: Maximum number of records

        Returns:
            List of routing decision records
        """
        if not self._neo4j_driver:
            logger.warning("Neo4j not connected - no routing history available")
            return []

        try:
            with self._neo4j_driver.session() as session:
                if capability_type:
                    query = """
                    MATCH (r:RoutingDecision)
                    WHERE r.capability_type = $capability_type
                    RETURN r ORDER BY r.timestamp DESC LIMIT $limit
                    """
                    result = session.run(
                        query, capability_type=capability_type.value, limit=limit
                    )
                else:
                    query = """
                    MATCH (r:RoutingDecision)
                    RETURN r ORDER BY r.timestamp DESC LIMIT $limit
                    """
                    result = session.run(query, limit=limit)

                history = []
                for record in result:
                    node = record["r"]
                    history.append(
                        {
                            "task_description": node["task_description"],
                            "capability_type": node["capability_type"],
                            "capability_name": node["capability_name"],
                            "confidence": node["confidence"],
                            "effectiveness": node["effectiveness"],
                            "timestamp": node["timestamp"],
                        }
                    )

                return history

        except Exception as e:
            logger.error(f"Failed to fetch routing history: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Get router statistics"""
        total = self.stats["total_routings"]
        return {
            **self.stats,
            "skill_percentage": (self.stats["skill_routings"] / total * 100)
            if total > 0
            else 0,
            "tool_percentage": (self.stats["tool_routings"] / total * 100)
            if total > 0
            else 0,
            "hybrid_percentage": (self.stats["hybrid_routings"] / total * 100)
            if total > 0
            else 0,
        }


# ============================================================================
# Global Instance
# ============================================================================

_global_instance: Optional[CapabilityRouter] = None


def get_capability_router(
    skills_manager=None,
    tool_registry=None,
    neo4j_uri: Optional[str] = None,
    neo4j_user: Optional[str] = None,
    neo4j_password: Optional[str] = None,
) -> CapabilityRouter:
    """
    Get or create the global CapabilityRouter instance

    Args:
        skills_manager: EnhancedSkillsManager instance
        tool_registry: ToolRegistry instance
        neo4j_uri: Neo4j connection URI
        neo4j_user: Neo4j username
        neo4j_password: Neo4j password

    Returns:
        CapabilityRouter instance
    """
    global _global_instance

    if _global_instance is None:
        _global_instance = CapabilityRouter(
            skills_manager=skills_manager,
            tool_registry=tool_registry,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )
        logger.info("✅ Created global CapabilityRouter instance")

    return _global_instance
