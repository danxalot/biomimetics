"""
Skill Selection Agent - Intelligent Skill Routing and Recommendation

This agent:
1. Analyzes incoming task descriptions
2. Recommends appropriate skills based on effectiveness
3. Routes tasks to selected skills
4. Records outcomes and updates skill effectiveness ratings
5. Learns from failures to improve recommendations

Separate from ReasoningBank:
- SkillSelector: "What tool should I use for this task?"
- ReasoningBank: "Why did this fail and what should I try differently?"
"""

import logging
import json
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class SelectionStrategy(Enum):
    """Strategy for selecting skills"""
    BEST_MATCH = "best_match"              # Highest effectiveness for category
    HIGHEST_EFFECTIVENESS = "highest_effectiveness"  # Ranked by effectiveness alone
    BALANCED = "balanced"                  # Balance effectiveness with diversity
    LEARNING = "learning"                  # Prefer skills that need practice


@dataclass
class SkillSelection:
    """Result of skill selection"""
    selected_skill_id: str
    skill_name: str
    effectiveness: float
    confidence: float                      # 0.0-1.0, how confident is this selection
    reasoning: str                         # Why this skill was selected
    alternatives: List[Tuple[str, str, float]] = field(default_factory=list)  # (id, name, score)
    required_parameters: Dict[str, str] = field(default_factory=dict)
    estimated_success_rate: float = 0.7
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'selected_skill_id': self.selected_skill_id,
            'skill_name': self.skill_name,
            'effectiveness': self.effectiveness,
            'confidence': self.confidence,
            'reasoning': self.reasoning,
            'alternatives': self.alternatives,
            'required_parameters': self.required_parameters,
            'estimated_success_rate': self.estimated_success_rate,
            'timestamp': datetime.now().isoformat()
        }


@dataclass
class ExecutionRecord:
    """Record of skill execution"""
    selection: SkillSelection
    start_time: datetime
    end_time: Optional[datetime] = None
    success: bool = False
    result: Optional[str] = None
    error: Optional[str] = None
    feedback: Optional[str] = None
    confidence_justified: bool = False    # Was confidence estimate accurate?
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'skill_id': self.selection.selected_skill_id,
            'skill_name': self.selection.skill_name,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'success': self.success,
            'result': self.result,
            'error': self.error,
            'feedback': self.feedback,
            'confidence_justified': self.confidence_justified,
            'execution_time_ms': (self.end_time - self.start_time).total_seconds() * 1000 if self.end_time else None
        }


class SkillSelectionAgent:
    """
    Agent for intelligent skill selection and execution routing
    
    Features:
    - Analyzes task descriptions
    - Ranks available skills by effectiveness
    - Selects best skill for task
    - Executes skill (delegates to actual implementation)
    - Records outcomes and updates effectiveness
    - Learns from failures to improve recommendations
    """
    
    def __init__(self, skills_manager):
        """
        Initialize Skill Selection Agent
        
        Args:
            skills_manager: EnhancedSkillsManager instance
        """
        self.skills_manager = skills_manager
        self.execution_history: List[ExecutionRecord] = []
        self.selection_strategy = SelectionStrategy.BALANCED
        
        self.stats = {
            'total_selections': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'confidence_justified_rate': 0.0,
            'avg_confidence': 0.0,
        }
    
    def select_skill(self, task_description: str, category: Optional[str] = None,
                    required_parameters: Optional[List[str]] = None,
                    strategy: Optional[SelectionStrategy] = None) -> Optional[SkillSelection]:
        """
        Select best skill for a task
        
        Args:
            task_description: Description of what needs to be done
            category: Optional category restriction (reasoning, technical, creative, meta, communication)
            required_parameters: Optional list of required parameter names
            strategy: Strategy to use (defaults to agent's preferred strategy)
        
        Returns:
            SkillSelection with selected skill and alternatives
        """
        strategy = strategy or self.selection_strategy
        
        logger.info(f"🎯 Selecting skill for task: {task_description[:50]}...")
        
        # Get recommendations from skills manager
        recommendations = self.skills_manager.recommend_skill(
            task_description,
            category=category,
            top_k=5
        )
        
        if not recommendations:
            logger.warning("❌ No skills available for task")
            return None
        
        # Score each recommendation based on strategy
        scored_skills = self._score_recommendations(
            recommendations,
            strategy,
            required_parameters
        )
        
        if not scored_skills:
            logger.warning("❌ No skills passed filtering criteria")
            return None
        
        # Get best skill
        best_skill, best_score = scored_skills[0]
        
        # Build alternatives list
        alternatives = []
        for skill, score in scored_skills[1:4]:  # Top 3 alternatives
            alternatives.append((skill.skill_id, skill.name, score))
        
        # Calculate confidence based on score gap
        confidence = self._calculate_confidence(best_score, scored_skills)
        
        # Create selection
        selection = SkillSelection(
            selected_skill_id=best_skill.skill_id,
            skill_name=best_skill.name,
            effectiveness=best_skill.effectiveness_score,
            confidence=confidence,
            reasoning=self._generate_reasoning(
                best_skill,
                best_score,
                strategy,
                task_description
            ),
            alternatives=alternatives,
            required_parameters=self._extract_parameters(best_skill),
            estimated_success_rate=best_skill.success_rate
        )
        
        self.stats['total_selections'] += 1
        self.stats['avg_confidence'] = (
            (self.stats['avg_confidence'] * (self.stats['total_selections'] - 1) + confidence) /
            self.stats['total_selections']
        )
        
        logger.info(f"✅ Selected skill: {selection.skill_name} (confidence: {confidence:.2%})")
        logger.info(f"   Alternatives: {', '.join([alt[1] for alt in alternatives])}")
        
        return selection
    
    def _score_recommendations(self, recommendations: List[Tuple[Any, float]],
                              strategy: SelectionStrategy,
                              required_parameters: Optional[List[str]] = None) -> List[Tuple[Any, float]]:
        """Score recommendations based on strategy"""
        scored = list(recommendations)
        
        # Filter by required parameters if specified
        if required_parameters:
            def has_required_params(skill):
                skill_params = set(skill.parameters.keys())
                return all(param in skill_params or param + "(optional)" in skill_params 
                          for param in required_parameters)
            
            scored = [(s, score) for s, score in scored if has_required_params(s)]
        
        # Apply strategy-specific scoring
        if strategy == SelectionStrategy.BEST_MATCH:
            # Already scored by category match in recommend_skill
            pass
        
        elif strategy == SelectionStrategy.HIGHEST_EFFECTIVENESS:
            # Re-rank by effectiveness alone
            scored = sorted(scored, key=lambda x: -x[0].effectiveness_score)
            scored = [(s, s.effectiveness_score) for s, _ in scored]
        
        elif strategy == SelectionStrategy.BALANCED:
            # Balance effectiveness with diversity
            for i, (skill, old_score) in enumerate(scored):
                diversity_bonus = (1.0 - (i / max(len(scored), 1))) * 0.1  # Bonus for variety
                adjusted_score = old_score + diversity_bonus
                scored[i] = (skill, adjusted_score)
        
        elif strategy == SelectionStrategy.LEARNING:
            # Prefer skills with improvement potential
            for i, (skill, old_score) in enumerate(scored):
                if skill.success_rate < 0.7:
                    # Low success rate = needs practice = boost it
                    learning_bonus = (0.7 - skill.success_rate) * 0.3
                    scored[i] = (skill, old_score + learning_bonus)
        
        return sorted(scored, key=lambda x: -x[1])
    
    def _calculate_confidence(self, best_score: float,
                             scored_skills: List[Tuple[Any, float]]) -> float:
        """
        Calculate confidence in selection based on score gap
        
        High confidence if best is clearly ahead of alternatives
        Low confidence if alternatives are close
        """
        if len(scored_skills) < 2:
            return 0.8  # High confidence if only one option
        
        best_score = scored_skills[0][1]
        second_score = scored_skills[1][1]
        
        gap = best_score - second_score
        gap_percentage = gap / (best_score + 0.001)  # Avoid division by zero
        
        # Gap > 0.2 = high confidence, Gap < 0.05 = low confidence
        confidence = min(0.95, max(0.5, 0.5 + (gap_percentage * 2)))
        
        return confidence
    
    def _generate_reasoning(self, skill: Any, score: float,
                           strategy: SelectionStrategy,
                           task_description: str) -> str:
        """Generate human-readable reasoning for the selection"""
        reasons = []
        
        # Add strategy-specific reasoning
        if strategy == SelectionStrategy.BEST_MATCH:
            reasons.append(f"Best match for '{task_description[:30]}...'")
        elif strategy == SelectionStrategy.HIGHEST_EFFECTIVENESS:
            reasons.append(f"Highest effectiveness score ({skill.effectiveness_score:.2%})")
        elif strategy == SelectionStrategy.BALANCED:
            reasons.append(f"Good effectiveness ({skill.effectiveness_score:.2%}) with category match")
        elif strategy == SelectionStrategy.LEARNING:
            if skill.success_rate < 0.7:
                reasons.append(f"Needs practice ({skill.success_rate:.2%} success rate)")
            else:
                reasons.append(f"Effective ({skill.effectiveness_score:.2%}) and proven")
        
        # Add category reasoning
        reasons.append(f"Category: {skill.category}")
        
        # Add usage history
        if skill.usage_count > 0:
            reasons.append(f"Used {skill.usage_count}x with {skill.success_rate:.0%} success")
        else:
            reasons.append(f"New skill (level: {skill.level})")
        
        return " | ".join(reasons)
    
    def _extract_parameters(self, skill: Any) -> Dict[str, str]:
        """Extract required parameters from skill"""
        required = {}
        for param_name, param_info in skill.parameters.items():
            if not param_info.get('optional', False):
                required[param_name] = param_info.get('description', param_name)
        return required
    
    def execute_skill(self, selection: SkillSelection,
                     parameters: Optional[Dict[str, Any]] = None) -> ExecutionRecord:
        """
        Execute selected skill (placeholder - actual implementation delegates to skill executor)
        
        Args:
            selection: SkillSelection from select_skill()
            parameters: Parameter values for skill execution
        
        Returns:
            ExecutionRecord with results
        """
        record = ExecutionRecord(
            selection=selection,
            start_time=datetime.now()
        )
        
        logger.info(f"▶️  Executing skill: {selection.skill_name}")
        logger.info(f"    Parameters: {parameters}")
        
        # TODO: Actual skill execution
        # This would delegate to the actual skill executor
        # For now, simulate execution
        
        record.end_time = datetime.now()
        record.success = True  # Placeholder
        record.result = "Skill execution completed"
        
        return record
    
    def record_execution(self, record: ExecutionRecord) -> None:
        """
        Record skill execution and update skill effectiveness
        
        Args:
            record: ExecutionRecord with execution results
        """
        self.execution_history.append(record)
        
        # Update skill manager
        self.skills_manager.record_skill_usage(
            record.selection.selected_skill_id,
            success=record.success,
            context=f"Executed via SkillSelectionAgent",
            details=record.to_dict()
        )
        
        # Update stats
        if record.success:
            self.stats['successful_executions'] += 1
        else:
            self.stats['failed_executions'] += 1
        
        # Track confidence justification
        if record.success and record.selection.confidence > 0.7:
            record.confidence_justified = True
        elif not record.success and record.selection.confidence < 0.7:
            record.confidence_justified = True
        
        justified_count = sum(1 for r in self.execution_history if r.confidence_justified)
        self.stats['confidence_justified_rate'] = (
            justified_count / max(len(self.execution_history), 1)
        )
        
        logger.info(f"📊 Execution recorded: {'✅' if record.success else '❌'}")
        logger.info(f"    Execution time: {(record.end_time - record.start_time).total_seconds():.2f}s")
        logger.info(f"    Confidence justified: {record.confidence_justified}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics"""
        return {
            'total_selections': self.stats['total_selections'],
            'successful_executions': self.stats['successful_executions'],
            'failed_executions': self.stats['failed_executions'],
            'success_rate': (
                self.stats['successful_executions'] /
                max(self.stats['successful_executions'] + self.stats['failed_executions'], 1)
            ),
            'avg_confidence': self.stats['avg_confidence'],
            'confidence_justified_rate': self.stats['confidence_justified_rate'],
            'execution_history_size': len(self.execution_history),
        }
    
    def get_execution_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent execution history"""
        recent = self.execution_history[-limit:]
        return [record.to_dict() for record in recent]
    
    def analyze_failures(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Analyze recent failures to identify patterns"""
        failures = [r for r in self.execution_history if not r.success][-limit:]
        
        analysis = []
        for record in failures:
            skill = self.skills_manager.get_skill(record.selection.selected_skill_id)
            analysis.append({
                'skill_name': record.selection.skill_name,
                'timestamp': record.start_time.isoformat(),
                'reason': record.error,
                'feedback': record.feedback,
                'current_effectiveness': skill.effectiveness_score if skill else 0,
                'recommendation': self._generate_failure_recommendation(record)
            })
        
        return analysis
    
    def _generate_failure_recommendation(self, record: ExecutionRecord) -> str:
        """Generate recommendation after failure"""
        skill = self.skills_manager.get_skill(record.selection.selected_skill_id)
        
        if skill.success_rate < 0.5:
            return "Consider retiring this skill - too many failures"
        elif skill.success_rate < 0.7:
            return "Skill needs improvement or better selection criteria"
        else:
            return "Skill is generally effective - this was an edge case"
    
    def batch_select_and_execute(self, tasks: List[Tuple[str, Optional[Dict[str, Any]]]]) -> List[ExecutionRecord]:
        """
        Select and execute skills for multiple tasks
        
        Args:
            tasks: List of (task_description, parameters) tuples
        
        Returns:
            List of ExecutionRecords
        """
        records = []
        
        logger.info(f"⚙️  Batch processing {len(tasks)} tasks...")
        
        for i, (task_desc, params) in enumerate(tasks, 1):
            logger.info(f"[{i}/{len(tasks)}] Processing: {task_desc[:40]}...")
            
            selection = self.select_skill(task_desc)
            if selection:
                record = self.execute_skill(selection, params)
                self.record_execution(record)
                records.append(record)
        
        logger.info(f"✅ Batch processing complete: {len(records)}/{len(tasks)} completed")
        
        return records


def get_skill_selection_agent(skills_manager=None):
    """Factory function to get or create Skill Selection Agent"""
    if skills_manager is None:
        from enhanced_skills_manager import get_enhanced_skills_manager
        skills_manager = get_enhanced_skills_manager()
    
    return SkillSelectionAgent(skills_manager)


if __name__ == "__main__":
    # Test the agent
    logging.basicConfig(level=logging.INFO)
    
    from enhanced_skills_manager import get_enhanced_skills_manager
    
    print("\n🤖 Skill Selection Agent - Test")
    print("=" * 70)
    
    # Initialize
    skills_manager = get_enhanced_skills_manager()
    agent = get_skill_selection_agent(skills_manager)
    
    # Test selection
    tasks = [
        "Debug an API connection error in Python",
        "Generate innovative solution for distributed caching",
        "Explain complex system architecture to stakeholders",
    ]
    
    print("\n📋 Testing Skill Selection:")
    for task in tasks:
        print(f"\n📝 Task: {task}")
        selection = agent.select_skill(task)
        
        if selection:
            print(f"   ✅ Selected: {selection.skill_name}")
            print(f"      Confidence: {selection.confidence:.2%}")
            print(f"      Effectiveness: {selection.effectiveness:.2%}")
            print(f"      Reasoning: {selection.reasoning}")
            
            if selection.alternatives:
                print(f"      Alternatives:")
                for alt_id, alt_name, alt_score in selection.alternatives:
                    print(f"         - {alt_name} ({alt_score:.2%})")
    
    # Show stats
    print(f"\n📊 Agent Statistics:")
    stats = agent.get_stats()
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"   {key}: {value:.2%}")
        else:
            print(f"   {key}: {value}")
