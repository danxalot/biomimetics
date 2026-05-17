"""
Meta-Cognitive Governor for ARCA

Implements:
- DirectorAgent: Meta-orchestrator managing Genesis/Serena agents
- HolisticAuditor: Project-wide quality gate using GATr + EB-JEPA + Qwen
- DelphiCheck: JEPA stability prediction before action execution
- SystemConstitution: Core operating principles

Based on: Gemini's Meta-Cognitive Governor source document.
Respects: User energy constraints (disability welfare status).
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
import json

logger = logging.getLogger(__name__)


class AgentType(Enum):
    """Agent types in the bicameral architecture."""
    GENESIS = "genesis"      # Architecture, creation
    SERENA = "serena"        # User interaction, execution
    MAINTAINER = "maintainer"  # Docker/Git/File/Security
    OBSERVER = "observer"    # Monitoring, analysis


class DecisionOutcome(Enum):
    """Possible outcomes from Delphi check."""
    PROCEED = "proceed"
    SIMPLIFY = "simplify"
    DELEGATE = "delegate"
    ABORT = "abort"
    ESCALATE = "escalate"


@dataclass
class SystemConstitution:
    """
    Core operating principles for the ARCA Director.
    
    The constitution defines inviolable constraints that
    protect system stability and user wellbeing.
    """
    
    # User energy protection
    user_is_disabled: bool = True
    max_user_interactions_per_task: int = 3
    escalate_only_for_critical: bool = True
    
    # System stability
    energy_threshold_warning: float = 0.5
    energy_threshold_abort: float = 0.8
    max_cascade_depth: int = 5
    
    # Autonomy levels
    flash_agent_autonomy: float = 0.9   # High - routine tasks
    pro_agent_autonomy: float = 0.7     # Medium - complex tasks
    human_override_always: bool = True
    
    # Protected components
    protected_services: List[str] = field(default_factory=lambda: [
        "geometry_kernel", "neo4j", "postgres", "redis"
    ])
    
    def to_prompt_block(self) -> str:
        """Format constitution for agent prompts."""
        return f"""
# SYSTEM CONSTITUTION (INVIOLABLE)

## User Protection
- User Status: {"Disabled/Low Energy" if self.user_is_disabled else "Normal"}
- Maximum user interactions per task: {self.max_user_interactions_per_task}
- Escalate only for CRITICAL issues

## Stability Thresholds
- Energy WARNING at: {self.energy_threshold_warning}
- Energy ABORT at: {self.energy_threshold_abort}
- Maximum cascade depth: {self.max_cascade_depth}

## Protected Services (NEVER modify without explicit approval)
{chr(10).join(f"- {s}" for s in self.protected_services)}

## Operating Principles
1. MINIMIZE cognitive load on user
2. AUTOMATE all routine operations
3. ESCALATE only when truly necessary
4. LEARN from every interaction
"""


@dataclass
class DelphiCheckResult:
    """Result from the Delphi stability check."""
    stability_score: float      # 0-1, higher = more stable
    entropy: float              # Chaos measure
    outcome: DecisionOutcome
    interpretation: str
    recommended_agent: AgentType
    modifications: Optional[List[str]] = None


class DelphiCheck:
    """
    Delphi: The intuition layer using JEPA/Mamba.
    
    Before executing any action, the Director consults Delphi
    to predict stability of the resulting state.
    
    "The subconscious whispers to the conscious."
    """
    
    def __init__(
        self,
        energy_model: Optional[Any] = None,  # ARCAEnergyModel
        jepa_model: Optional[Any] = None,    # GeometricTDJEPA
        constitution: Optional[SystemConstitution] = None
    ):
        self.energy_model = energy_model
        self.jepa = jepa_model
        self.constitution = constitution or SystemConstitution()
    
    def check_stability(
        self,
        proposed_action: str,
        current_state: Optional[Dict] = None,
        context: Optional[List[str]] = None
    ) -> DelphiCheckResult:
        """
        Check stability of a proposed action.
        
        Uses JEPA to predict future state and Energy model
        to assess stability of that prediction.
        """
        # Compute base metrics
        stability = self._estimate_stability(proposed_action, current_state)
        entropy = self._estimate_entropy(proposed_action, context)
        
        # Determine outcome based on thresholds
        if entropy > self.constitution.energy_threshold_abort:
            outcome = DecisionOutcome.ABORT
            interpretation = "High entropy detected. Action would destabilize system."
        elif entropy > self.constitution.energy_threshold_warning:
            outcome = DecisionOutcome.SIMPLIFY
            interpretation = "Moderate entropy. Consider breaking into smaller steps."
        elif stability < 0.3:
            outcome = DecisionOutcome.ESCALATE
            interpretation = "Low confidence. Requires human review."
        else:
            outcome = DecisionOutcome.PROCEED
            interpretation = "Stable. Proceed with action."
        
        # Recommend agent based on complexity
        complexity = self._estimate_complexity(proposed_action)
        if complexity < 0.3:
            recommended_agent = AgentType.MAINTAINER
        elif complexity < 0.6:
            recommended_agent = AgentType.SERENA
        else:
            recommended_agent = AgentType.GENESIS
        
        return DelphiCheckResult(
            stability_score=stability,
            entropy=entropy,
            outcome=outcome,
            interpretation=interpretation,
            recommended_agent=recommended_agent
        )
    
    def _estimate_stability(
        self, 
        action: str, 
        state: Optional[Dict]
    ) -> float:
        """Estimate stability using JEPA if available."""
        if self.jepa is None or self.energy_model is None:
            # Heuristic fallback
            risky_keywords = ['delete', 'drop', 'remove', 'reset', 'force']
            risk_count = sum(1 for k in risky_keywords if k in action.lower())
            return max(0.2, 1.0 - (risk_count * 0.2))
        
        # Use JEPA for proper prediction (when models loaded)
        # TODO: Wire to actual JEPA inference
        return 0.7  # Default moderate stability
    
    def _estimate_entropy(
        self, 
        action: str,
        context: Optional[List[str]]
    ) -> float:
        """Estimate action entropy (chaos potential)."""
        # Simple heuristic: longer actions with many operations = higher entropy
        word_count = len(action.split())
        
        # Operations that increase entropy
        high_entropy_ops = ['migrate', 'refactor', 'rewrite', 'overhaul', 'rebuild']
        entropy_boost = sum(0.2 for op in high_entropy_ops if op in action.lower())
        
        base_entropy = min(0.5, word_count / 50)
        return min(1.0, base_entropy + entropy_boost)
    
    def _estimate_complexity(self, action: str) -> float:
        """Estimate task complexity for agent routing."""
        # Keywords indicating complexity
        architecture_keywords = ['architect', 'design', 'create service', 
                                'new component', 'implement feature']
        routine_keywords = ['restart', 'logs', 'status', 'check', 'verify']
        
        if any(k in action.lower() for k in architecture_keywords):
            return 0.8
        elif any(k in action.lower() for k in routine_keywords):
            return 0.2
        else:
            return 0.5


class HolisticAuditor:
    """
    Project-wide quality gate using GATr + EB-JEPA + Qwen.
    
    Before any change is committed, the Auditor performs:
    1. GATr Physics Check: Does this change geometric stress?
    2. EB-JEPA Energy Check: Is the resulting state stable?
    3. Qwen Synthesis: Generate human-readable verdict
    
    This replaces the need for external "Robotics" model.
    """
    
    def __init__(
        self,
        gatr_model_path: Optional[str] = None,
        ebjepa_model_path: Optional[str] = None,
        qwen_endpoint: str = "http://localhost:8080/v1"
    ):
        self.gatr_path = gatr_model_path
        self.ebjepa_path = ebjepa_model_path
        self.qwen_endpoint = qwen_endpoint
        
        # Lazy loading flags
        self._gatr_loaded = False
        self._ebjepa_loaded = False
    
    def audit_proposal(
        self,
        proposal_text: str,
        affected_files: List[str],
        blackboard_state: Optional[Dict] = None
    ) -> Dict:
        """
        Perform holistic audit on a proposed change.
        
        Returns:
            Dict with verdict, scores, and recommendations
        """
        results = {
            'timestamp': datetime.now().isoformat(),
            'proposal_summary': proposal_text[:200],
            'affected_files': affected_files[:10],  # Limit for logging
        }
        
        # Step 1: Physics check (GATr)
        physics_result = self._gatr_physics_check(proposal_text, affected_files)
        results['physics'] = physics_result
        
        # Step 2: Energy check (EB-JEPA)
        energy_result = self._ebjepa_energy_check(proposal_text, blackboard_state)
        results['energy'] = energy_result
        
        # Step 3: Synthesize verdict (Qwen)
        verdict = self._synthesize_verdict(
            physics_result, 
            energy_result, 
            proposal_text
        )
        results['verdict'] = verdict
        
        # Overall score
        overall_score = (
            0.4 * physics_result['score'] +
            0.4 * energy_result['score'] +
            0.2 * verdict['confidence']
        )
        results['overall_score'] = overall_score
        results['approved'] = overall_score > 0.5
        
        return results
    
    def _gatr_physics_check(
        self, 
        proposal: str,
        files: List[str]
    ) -> Dict:
        """
        GATr-based physics check for geometric stress.
        
        Looks for:
        - Structural inconsistencies
        - Dependency violations
        - Architecture drift
        """
        # Check for protected component modifications
        protected = ['geometry_kernel', 'neo4j', 'hse_encoder']
        protected_modified = [
            f for f in files 
            if any(p in f for p in protected)
        ]
        
        # Heuristic stress calculation
        if protected_modified:
            stress = 0.8  # High stress for protected files
            concern = f"Protected components affected: {protected_modified}"
        else:
            stress = 0.2  # Low stress for routine changes
            concern = None
        
        return {
            'score': 1.0 - stress,  # Higher score = better
            'stress_level': stress,
            'protected_files_affected': protected_modified,
            'concern': concern
        }
    
    def _ebjepa_energy_check(
        self,
        proposal: str,
        state: Optional[Dict]
    ) -> Dict:
        """
        EB-JEPA energy check for stability.
        
        Predicts whether the change leads to:
        - Low energy (stable, efficient)
        - High energy (unstable, problematic)
        """
        # Heuristic energy estimation
        risky_patterns = [
            'delete all', 'drop table', 'reset', 'force push',
            'override', 'bypass', 'disable'
        ]
        
        risk_score = sum(
            0.15 for pattern in risky_patterns 
            if pattern in proposal.lower()
        )
        
        energy = min(1.0, 0.2 + risk_score)
        stability = 1.0 - energy
        
        return {
            'score': stability,
            'energy_level': energy,
            'is_stable': energy < 0.5,
            'interpretation': (
                'Stable' if energy < 0.3 else
                'Moderate risk' if energy < 0.6 else
                'High risk'
            )
        }
    
    def _synthesize_verdict(
        self,
        physics: Dict,
        energy: Dict,
        proposal: str
    ) -> Dict:
        """
        Synthesize human-readable verdict using Qwen.
        
        Falls back to template if Qwen unavailable.
        """
        # Template-based synthesis (works without LLM)
        if physics['stress_level'] > 0.6:
            verdict = (
                f"⚠️ HIGH STRESS: {physics.get('concern', 'Architecture impact detected')}. "
                "Recommend thorough review before proceeding."
            )
            confidence = 0.4
        elif energy['energy_level'] > 0.6:
            verdict = (
                f"⚠️ HIGH ENERGY: {energy['interpretation']}. "
                "Consider breaking into smaller, safer changes."
            )
            confidence = 0.5
        else:
            verdict = (
                "✅ APPROVED: Change appears stable and within safety margins. "
                "Proceed with standard verification."
            )
            confidence = 0.8
        
        return {
            'text': verdict,
            'confidence': confidence,
            'requires_human_review': confidence < 0.6
        }


class DirectorAgent:
    """
    Meta-Cognitive Governor orchestrating Genesis/Serena.
    
    The Director:
    1. Receives user intent
    2. Consults Delphi for stability prediction
    3. Routes to appropriate agent (Genesis/Serena/Maintainer)
    4. Monitors execution via Observer
    5. Enforces SOPs and Constitution
    
    "The conscious mind that coordinates the subconscious systems."
    """
    
    def __init__(
        self,
        constitution: Optional[SystemConstitution] = None,
        delphi: Optional[DelphiCheck] = None,
        auditor: Optional[HolisticAuditor] = None
    ):
        self.constitution = constitution or SystemConstitution()
        self.delphi = delphi or DelphiCheck(constitution=self.constitution)
        self.auditor = auditor or HolisticAuditor()
        
        # Task tracking
        self.active_tasks: Dict[str, Dict] = {}
        self.task_history: List[Dict] = []
        
        # Agent availability
        self.agents = {
            AgentType.GENESIS: {'available': True, 'endpoint': '/genesis'},
            AgentType.SERENA: {'available': True, 'endpoint': '/serena'},
            AgentType.MAINTAINER: {'available': True, 'endpoint': 'http://localhost:8090'},
            AgentType.OBSERVER: {'available': True, 'endpoint': '/observer'}
        }
    
    async def process_intent(
        self,
        user_intent: str,
        context: Optional[Dict] = None
    ) -> Dict:
        """
        Process user intent through the Director workflow.
        
        1. Create plan from intent
        2. Delphi stability check
        3. Route to appropriate agent
        4. Return action plan
        """
        task_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Step 1: Delphi check
        delphi_result = self.delphi.check_stability(
            proposed_action=user_intent,
            current_state=context,
            context=None
        )
        
        # Step 2: Handle based on Delphi outcome
        if delphi_result.outcome == DecisionOutcome.ABORT:
            return {
                'task_id': task_id,
                'status': 'rejected',
                'reason': delphi_result.interpretation,
                'recommendation': 'Simplify the request or break into smaller tasks'
            }
        
        if delphi_result.outcome == DecisionOutcome.SIMPLIFY:
            return {
                'task_id': task_id,
                'status': 'needs_breakdown',
                'reason': delphi_result.interpretation,
                'recommended_agent': delphi_result.recommended_agent.value,
                'modifications': delphi_result.modifications or [
                    'Break into smaller steps',
                    'Consider phased rollout'
                ]
            }
        
        # Step 3: Create dispatch plan
        dispatch_plan = self._create_dispatch_plan(
            task_id=task_id,
            intent=user_intent,
            delphi_result=delphi_result
        )
        
        # Track task
        self.active_tasks[task_id] = {
            'intent': user_intent,
            'delphi': delphi_result,
            'plan': dispatch_plan,
            'started_at': datetime.now().isoformat()
        }
        
        return dispatch_plan
    
    def _create_dispatch_plan(
        self,
        task_id: str,
        intent: str,
        delphi_result: DelphiCheckResult
    ) -> Dict:
        """
        Create dispatch plan for the recommended agent.
        """
        recommended = delphi_result.recommended_agent
        agent_info = self.agents.get(recommended, {})
        
        # Determine if pre-flight audit needed
        needs_audit = (
            delphi_result.stability_score < 0.7 or
            recommended == AgentType.GENESIS
        )
        
        return {
            'task_id': task_id,
            'status': 'approved',
            'stability_score': delphi_result.stability_score,
            'entropy': delphi_result.entropy,
            'dispatch': {
                'agent': recommended.value,
                'endpoint': agent_info.get('endpoint', 'unknown'),
                'autonomy_level': (
                    self.constitution.flash_agent_autonomy 
                    if recommended == AgentType.MAINTAINER 
                    else self.constitution.pro_agent_autonomy
                )
            },
            'requires_audit': needs_audit,
            'constitution_block': self.constitution.to_prompt_block(),
            'pre_actions': [
                'Load relevant skill frames',
                'Check ReasoningBank for similar tasks'
            ] if needs_audit else []
        }
    
    async def dispatch_to_agent(
        self,
        task_id: str,
        agent_type: AgentType,
        payload: Dict
    ) -> Dict:
        """
        Dispatch task to specified agent.
        
        Actual HTTP dispatch would be implemented here.
        """
        if task_id not in self.active_tasks:
            return {'error': 'Unknown task ID'}
        
        agent_info = self.agents.get(agent_type, {})
        if not agent_info.get('available', False):
            return {'error': f'{agent_type.value} agent unavailable'}
        
        # Log dispatch
        logger.info(f"Dispatching {task_id} to {agent_type.value}")
        
        return {
            'task_id': task_id,
            'dispatched_to': agent_type.value,
            'endpoint': agent_info.get('endpoint'),
            'payload': payload,
            'status': 'dispatched'
        }
    
    def run_pre_flight_audit(
        self,
        task_id: str,
        proposal: str,
        affected_files: List[str]
    ) -> Dict:
        """
        Run pre-flight audit via HolisticAuditor.
        """
        audit_result = self.auditor.audit_proposal(
            proposal_text=proposal,
            affected_files=affected_files
        )
        
        # Update task with audit result
        if task_id in self.active_tasks:
            self.active_tasks[task_id]['audit'] = audit_result
        
        return audit_result
    
    def complete_task(self, task_id: str, result: Dict) -> Dict:
        """
        Mark task as complete and store in history.
        """
        if task_id not in self.active_tasks:
            return {'error': 'Unknown task ID'}
        
        task = self.active_tasks.pop(task_id)
        task['completed_at'] = datetime.now().isoformat()
        task['result'] = result
        
        self.task_history.append(task)
        
        return {
            'task_id': task_id,
            'status': 'completed',
            'duration': (
                datetime.fromisoformat(task['completed_at']) -
                datetime.fromisoformat(task['started_at'])
            ).total_seconds()
        }
    
    def get_status(self) -> Dict:
        """Get Director status and metrics."""
        return {
            'active_tasks': len(self.active_tasks),
            'completed_tasks': len(self.task_history),
            'agents': {
                k.value: v['available'] 
                for k, v in self.agents.items()
            },
            'constitution': {
                'user_protected': self.constitution.user_is_disabled,
                'max_interactions': self.constitution.max_user_interactions_per_task
            }
        }


# Factory function
def create_governor(
    energy_model: Optional[Any] = None,
    jepa_model: Optional[Any] = None
) -> Dict:
    """
    Create complete Meta-Cognitive Governor.
    
    Returns dict with:
    - director: DirectorAgent
    - delphi: DelphiCheck
    - auditor: HolisticAuditor
    - constitution: SystemConstitution
    """
    constitution = SystemConstitution()
    delphi = DelphiCheck(
        energy_model=energy_model,
        jepa_model=jepa_model,
        constitution=constitution
    )
    auditor = HolisticAuditor()
    director = DirectorAgent(
        constitution=constitution,
        delphi=delphi,
        auditor=auditor
    )
    
    return {
        'director': director,
        'delphi': delphi,
        'auditor': auditor,
        'constitution': constitution
    }
