"""
GLM Feasibility Assessment System

Provides cheap, frequent semantic pre-checks on geometry proposals.

GLM acts as a pessimistic surrogate that flags semantic/structural risks
BEFORE expensive robotics ER-1.5 review.

Key principle: GLM learns to predict when ER-1.5 would say no,
without ever seeing constraints, thresholds, or rejection mechanics.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from enum import Enum
import json


class RiskLevel(Enum):
    """Qualitative risk levels for proposals."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FailureMode(Enum):
    """Semantic/structural failure categories (no numeric thresholds)."""
    INSTABILITY = "instability"  # conflicting attractor pulls
    IRREVERSIBILITY = "irreversibility"  # no safe rollback path
    EXCESSIVE_COUPLING = "excessive_coupling"  # too many affected concepts
    SENSITIVITY_AMPLIFICATION = "sensitivity_amplification"  # small noise → big divergence
    DISCONTINUITY = "discontinuity"  # sudden large state deltas


@dataclass
class GLMFeasibilityCheckRequest:
    """Input to GLM feasibility assessment."""
    state_id: str
    state_summary: Dict[str, Any]  # nodes, attractors (symbolic + numeric)
    proposed_forces: List[Dict[str, Any]]  # force proposals
    attractor_proposals: Optional[List[Dict[str, Any]]] = None
    mode: str = "wake"  # wake or dream
    additional_context: Optional[str] = None


@dataclass
class GLMFeasibilityResponse:
    """Output from GLM assessment."""
    risk_level: RiskLevel
    failure_modes: List[FailureMode]
    confidence: float  # self-assessed confidence (0.0-1.0)
    brief_rationale: Optional[str] = None


@dataclass
class PromotionDecision:
    """Decision on whether to send to robotics ER-1.5."""
    proposal_id: str
    decision: str  # "accept", "softened", "reject"
    reason: str
    glm_risk_level: RiskLevel
    glm_failure_modes: List[FailureMode]
    kernel_checks_passed: bool
    should_promote_to_robotics: bool
    quota_cost: int  # 0 for GLM-only, 1 for robotics call


class GLMFeasibilityPrompt:
    """
    Constructs the exact prompt for GLM feasibility assessment.

    Key principle: GLM sees qualitative system state, not numeric constraints.
    GLM outputs structured JSON risk assessment, not prose.
    """

    SYSTEM_INSTRUCTION = """You are a semantic feasibility assessor.

Your job is to evaluate proposed changes to the concept geometry system.

You may:
- Flag risks and describe possible failure modes
- Assign qualitative risk levels (low, medium, high)
- Provide self-assessed confidence in your evaluation

You may NOT:
- Modify state directly
- See numeric constraints or limits
- Know acceptance thresholds
- Know why things are rejected

You operate in either dream mode (exploratory) or wake mode (conservative).
You learn only through feedback about outcomes (accepted/softened/rejected),
never through exposure to constraint internals.
"""

    @staticmethod
    def build_wake_mode_prompt(
        state_summary: Dict[str, Any],
        proposed_forces: List[Dict[str, Any]],
        attractor_proposals: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Prompt for conservative wake-mode assessment."""
        return f"""{GLMFeasibilityPrompt.SYSTEM_INSTRUCTION}

MODE: WAKE (conservative, prefer minimal force, reinforce existing attractors)

CURRENT STATE:
Concept Nodes:
{json.dumps(state_summary.get('nodes', [])[:5], indent=2)}

Attractors:
{json.dumps(state_summary.get('attractors', [])[:3], indent=2)}

Recent Events:
{json.dumps(state_summary.get('recent_events', [])[:3], indent=2)}

System Health:
- stability_index: {state_summary.get('health_metrics', {}).get('stability_index', 'unknown')}
- error_rate: {state_summary.get('health_metrics', {}).get('error_rate', 'unknown')}

TASK:
Evaluate these proposed force deltas:
{json.dumps(proposed_forces, indent=2)}

{f"And these attractor proposals:" + json.dumps(attractor_proposals, indent=2) if attractor_proposals else ""}

Identify:
1. Any semantic or structural risks
2. Potential failure modes from the list:
   - instability (conflicting attractor pulls)
   - irreversibility (no safe rollback)
   - excessive_coupling (too many concepts affected)
   - sensitivity_amplification (small noise → big divergence)
   - discontinuity (sudden state deltas)
3. Your confidence in this assessment (0.0-1.0)

OUTPUT MUST BE VALID JSON:
{{
  "risk_level": "low | medium | high",
  "failure_modes": ["instability", "irreversibility", ...],
  "confidence": 0.75,
  "brief_rationale": "optional short explanation"
}}

Do not explain. Do not justify. Output only the JSON."""

    @staticmethod
    def build_dream_mode_prompt(
        state_summary: Dict[str, Any],
        proposed_forces: List[Dict[str, Any]],
        attractor_proposals: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Prompt for exploratory dream-mode assessment."""
        return f"""{GLMFeasibilityPrompt.SYSTEM_INSTRUCTION}

MODE: DREAM (exploratory, allow novel configurations, higher uncertainty acceptable)

CURRENT STATE:
Concept Nodes:
{json.dumps(state_summary.get('nodes', [])[:5], indent=2)}

Attractors:
{json.dumps(state_summary.get('attractors', [])[:3], indent=2)}

Recent Events:
{json.dumps(state_summary.get('recent_events', [])[:3], indent=2)}

TASK:
In dream mode, you are exploring alternative geometric configurations.
Evaluate these proposed force deltas:
{json.dumps(proposed_forces, indent=2)}

{f"And these attractor proposals:" + json.dumps(attractor_proposals, indent=2) if attractor_proposals else ""}

Even though the system is in dream mode (relaxed constraints), still identify:
1. Semantic or structural risks
2. Potential failure modes:
   - instability
   - irreversibility
   - excessive_coupling
   - sensitivity_amplification
   - discontinuity
3. Your confidence (0.0-1.0)

Dream mode does NOT mean ignoring physics — it means exploring within a wider envelope.
Flag anything that violates basic continuity or reversibility.

OUTPUT MUST BE VALID JSON:
{{
  "risk_level": "low | medium | high",
  "failure_modes": ["instability", "irreversibility", ...],
  "confidence": 0.75,
  "brief_rationale": "optional short explanation"
}}

Do not explain. Do not justify. Output only the JSON."""


class RejectionTaxonomy:
    """
    Semantic failure categories GLM can safely signal.

    These map to qualitative risks, NOT numeric thresholds.
    """

    CATEGORIES = {
        "instability": {
            "description": "Proposed change causes conflicting pull between attractors",
            "glm_observes": "overlapping attractors, force conflicts",
            "knows_constraints": False,
        },
        "irreversibility": {
            "description": "Change may not be rolled back without violating invariants",
            "glm_observes": "node movements, mass distribution, trajectory shapes",
            "knows_constraints": False,
        },
        "excessive_coupling": {
            "description": "Too many concepts affected by a single change",
            "glm_observes": "number of influenced nodes, cascade breadth",
            "knows_constraints": False,
        },
        "sensitivity_amplification": {
            "description": "Small perturbations may propagate unpredictably",
            "glm_observes": "delta magnitudes relative to neighbors, clustering tightness",
            "knows_constraints": False,
        },
        "discontinuity": {
            "description": "Sudden large state deltas, axis reweightings flip importance",
            "glm_observes": "movement magnitude, direction changes, attractor proximity",
            "knows_constraints": False,
        },
    }

    @staticmethod
    def get_taxonomy() -> Dict[str, Dict[str, Any]]:
        """Return full taxonomy for documentation."""
        return RejectionTaxonomy.CATEGORIES


class PromotionThreshold:
    """
    Decides which proposals reach expensive robotics ER-1.5.

    Three-stage funnel:
    1. GLM local feasibility (cheap, frequent)
    2. Kernel heuristics (cheap, deterministic)
    3. Robotics ER-1.5 (expensive, rare)
    """

    @staticmethod
    def evaluate_promotion(
        glm_risk_level: RiskLevel,
        kernel_checks_passed: bool,
        proposal_type: str = "dream",  # dream or wake
        quota_budget_remaining: int = 250,
    ) -> PromotionDecision:
        """
        Determine if proposal should go to robotics.

        Decision table:
        - HIGH risk + kernel fails → REJECT immediately
        - HIGH risk + kernel passes → REJECT (too risky)
        - MEDIUM risk + kernel passes → CONDITIONAL (maybe, if quota allows)
        - LOW risk + kernel passes → PROMOTE (guaranteed robotics review)
        - Anything + kernel fails → REJECT
        """
        proposal_id = f"{proposal_type}_{id(object())}"

        # Hard reject: high risk + kernel failure
        if glm_risk_level == RiskLevel.HIGH and not kernel_checks_passed:
            return PromotionDecision(
                proposal_id=proposal_id,
                decision="reject",
                reason="high_risk_with_kernel_failure",
                glm_risk_level=glm_risk_level,
                glm_failure_modes=[],
                kernel_checks_passed=kernel_checks_passed,
                should_promote_to_robotics=False,
                quota_cost=0,
            )

        # Hard reject: high risk even if kernel passes
        if glm_risk_level == RiskLevel.HIGH:
            return PromotionDecision(
                proposal_id=proposal_id,
                decision="reject",
                reason="high_risk_glm_assessment",
                glm_risk_level=glm_risk_level,
                glm_failure_modes=[],
                kernel_checks_passed=kernel_checks_passed,
                should_promote_to_robotics=False,
                quota_cost=0,
            )

        # Kernel failure always rejects
        if not kernel_checks_passed:
            return PromotionDecision(
                proposal_id=proposal_id,
                decision="reject",
                reason="kernel_invariant_violation",
                glm_risk_level=glm_risk_level,
                glm_failure_modes=[],
                kernel_checks_passed=kernel_checks_passed,
                should_promote_to_robotics=False,
                quota_cost=0,
            )

        # Medium risk: conditional promotion if quota allows
        if glm_risk_level == RiskLevel.MEDIUM:
            should_promote = quota_budget_remaining > 50  # conservative threshold
            return PromotionDecision(
                proposal_id=proposal_id,
                decision="softened",
                reason="medium_risk_conditional_promotion",
                glm_risk_level=glm_risk_level,
                glm_failure_modes=[],
                kernel_checks_passed=kernel_checks_passed,
                should_promote_to_robotics=should_promote,
                quota_cost=1 if should_promote else 0,
            )

        # Low risk + kernel pass: promote to robotics
        return PromotionDecision(
            proposal_id=proposal_id,
            decision="accept",
            reason="low_risk_kernel_pass",
            glm_risk_level=glm_risk_level,
            glm_failure_modes=[],
            kernel_checks_passed=kernel_checks_passed,
            should_promote_to_robotics=True,
            quota_cost=1,
        )

    @staticmethod
    def apply_table(
        glm_risk: str,
        kernel_pass: bool,
    ) -> tuple[str, str, int]:
        """
        Simplified table lookup.

        Returns: (decision, reason, quota_cost)
        """
        risk_level = RiskLevel(glm_risk)

        decision = PromotionThreshold.evaluate_promotion(
            glm_risk_level=risk_level,
            kernel_checks_passed=kernel_pass,
        )

        return (decision.decision, decision.reason, decision.quota_cost)


class DreamCyclePipeline:
    """
    Full pipeline for a single dream proposal.

    1. GLM feasibility check (cheap)
    2. Kernel deterministic checks (cheap)
    3. Promotion decision (cheap math)
    4. Optionally: Robotics ER-1.5 (expensive)
    """

    def __init__(self, quota_budget_remaining: int = 250):
        self.quota_budget_remaining = quota_budget_remaining

    def process_dream_proposal(
        self,
        state_id: str,
        state_summary: Dict[str, Any],
        proposed_forces: List[Dict[str, Any]],
        attractor_proposals: Optional[List[Dict[str, Any]]] = None,
        glm_client: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        End-to-end dream cycle.

        Returns: {
            'state': current state,
            'decision': promotion_decision,
            'quota_remaining': int,
            'promote_to_robotics': bool,
        }
        """

        # Stage 1: GLM feasibility
        glm_response = self._run_glm_feasibility(
            state_summary,
            proposed_forces,
            attractor_proposals,
            mode="dream",
            glm_client=glm_client,
        )

        # Early exit: high risk
        if glm_response.risk_level == RiskLevel.HIGH:
            return {
                "decision": "rejected_by_glm",
                "reason": "high_risk_glm_assessment",
                "quota_remaining": self.quota_budget_remaining,
                "promote_to_robotics": False,
            }

        # Stage 2: Kernel checks (placeholder - would call kernel API)
        kernel_checks_passed = True  # TODO: integrate with actual kernel

        # Stage 3: Promotion decision
        promotion = PromotionThreshold.evaluate_promotion(
            glm_risk_level=glm_response.risk_level,
            kernel_checks_passed=kernel_checks_passed,
            proposal_type="dream",
            quota_budget_remaining=self.quota_budget_remaining,
        )

        if promotion.should_promote_to_robotics:
            self.quota_budget_remaining -= 1

        return {
            "decision": promotion.decision,
            "reason": promotion.reason,
            "glm_response": {
                "risk_level": glm_response.risk_level.value,
                "failure_modes": [fm.value for fm in glm_response.failure_modes],
                "confidence": glm_response.confidence,
            },
            "quota_remaining": self.quota_budget_remaining,
            "promote_to_robotics": promotion.should_promote_to_robotics,
        }

    def _run_glm_feasibility(
        self,
        state_summary: Dict[str, Any],
        proposed_forces: List[Dict[str, Any]],
        attractor_proposals: Optional[List[Dict[str, Any]]],
        mode: str,
        glm_client: Optional[Any] = None,
    ) -> GLMFeasibilityResponse:
        """
        Call GLM feasibility assessment.

        If no glm_client provided, returns mock response for testing.
        """
        prompt = (
            GLMFeasibilityPrompt.build_dream_mode_prompt(
                state_summary, proposed_forces, attractor_proposals
            )
            if mode == "dream"
            else GLMFeasibilityPrompt.build_wake_mode_prompt(
                state_summary, proposed_forces, attractor_proposals
            )
        )

        if glm_client is None:
            # Mock response for testing
            return GLMFeasibilityResponse(
                risk_level=RiskLevel.LOW,
                failure_modes=[],
                confidence=0.75,
                brief_rationale="Mock assessment (no GLM client)",
            )

        # In production: glm_client.call(prompt) and parse JSON response
        # For now, placeholder
        return GLMFeasibilityResponse(
            risk_level=RiskLevel.LOW,
            failure_modes=[],
            confidence=0.75,
            brief_rationale="Awaiting GLM client integration",
        )


if __name__ == "__main__":
    # Example usage
    print("GLM Feasibility Assessment System Initialized")

    # Show prompt templates
    print("\n=== WAKE MODE PROMPT TEMPLATE ===")
    state = {
        "nodes": [{"id": "concept:x", "position": [0, 0, 0]}],
        "attractors": [{"id": "att:y", "center": [1, 1, 1]}],
        "health_metrics": {"stability_index": 0.95},
    }
    prompt = GLMFeasibilityPrompt.build_wake_mode_prompt(
        state,
        [{"target_id": "concept:x", "magnitude": 0.1}],
    )
    print(prompt[:500] + "...")

    # Show rejection taxonomy
    print("\n=== REJECTION TAXONOMY ===")
    for cat, details in RejectionTaxonomy.get_taxonomy().items():
        print(f"{cat}: {details['description']}")

    # Show promotion thresholds
    print("\n=== PROMOTION THRESHOLD EXAMPLES ===")
    examples = [
        ("low", True),
        ("medium", True),
        ("high", True),
        ("high", False),
    ]
    for risk, kernel_pass in examples:
        decision, reason, cost = PromotionThreshold.apply_table(risk, kernel_pass)
        print(f"Risk={risk}, KernelPass={kernel_pass} → {decision} (quota_cost={cost})")

    print("\nGLM Feasibility System ready.")
