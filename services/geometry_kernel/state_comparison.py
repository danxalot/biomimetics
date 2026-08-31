"""
State Comparison Module
=======================
Compares a document's geometric model against the current system state.

This enables ARCA to:
1. Identify what's NEW in the document (not in current state)
2. Identify what's MISSING from the document (in current state only)
3. Map out TRANSITIONS required to align with the document's vision

The system state is maintained by the Cognitive Tick in:
    arca:blackboard:working_model
"""

import json
import logging
import numpy as np
from typing import Dict, List, Any, Set, Tuple, Optional
from dataclasses import dataclass, asdict
import redis

logger = logging.getLogger(__name__)

# Redis key for current system state (from Cognitive Tick)
SYSTEM_STATE_KEY = "arca:blackboard:working_model"


@dataclass
class ConceptDelta:
    """Represents a difference between document and system state."""
    concept_id: str
    delta_type: str  # "new", "missing", "modified", "aligned"
    document_value: Optional[Dict]  # Value in document (if any)
    system_value: Optional[Dict]  # Value in system state (if any)
    transition_action: str  # Required action to align


@dataclass
class TransitionPlan:
    """Plan for transitioning system state to align with document."""
    priority: int  # 1 = highest
    action: str    # "add", "remove", "modify", "reposition"
    concept_id: str
    description: str
    effort_estimate: str  # "low", "medium", "high"


@dataclass
class StateComparisonResult:
    """Full comparison result between document and system state."""
    document_id: str
    system_state_id: str
    
    # Concept sets
    new_concepts: List[str]      # In document, not in system
    missing_concepts: List[str]  # In system, not in document
    shared_concepts: List[str]   # In both
    modified_concepts: List[str] # In both, but different
    
    # Detailed deltas
    deltas: List[ConceptDelta]
    
    # Transition plan
    transitions: List[TransitionPlan]
    
    # Overall alignment score
    alignment_score: float  # 0-1, how aligned is document with current state
    
    # Summary for ARCA
    summary: str
    
    def to_dict(self) -> Dict:
        return {
            "document_id": self.document_id,
            "system_state_id": self.system_state_id,
            "new_concepts": self.new_concepts,
            "missing_concepts": self.missing_concepts,
            "shared_concepts": self.shared_concepts,
            "modified_concepts": self.modified_concepts,
            "deltas": [asdict(d) for d in self.deltas],
            "transitions": [asdict(t) for t in self.transitions],
            "alignment_score": self.alignment_score,
            "summary": self.summary
        }


class StateComparisonEngine:
    """
    Compares geometric models to detect deltas and plan transitions.
    """
    
    def __init__(self, redis_client: redis.Redis = None):
        if redis_client:
            self.redis = redis_client
        else:
            try:
                self.redis = redis.Redis(host="redis", port=6379, decode_responses=True)
                self.redis.ping()
            except Exception as e:
                logger.warning(f"Redis unavailable for StateComparison: {e}")
                self.redis = None
    
    def compare_to_system_state(self, document_model: Dict[str, Any]) -> StateComparisonResult:
        """
        Compare a document's geometric model to the current system state.
        
        Args:
            document_model: Geometric model from recursive ingestion
            
        Returns:
            StateComparisonResult with deltas and transition plan
        """
        document_id = document_model.get("system_id", "unknown")
        
        # Get current system state
        system_state = self._get_system_state()
        system_state_id = system_state.get("system_id", "current_state") if system_state else "none"
        
        if not system_state:
            return StateComparisonResult(
                document_id=document_id,
                system_state_id="none",
                new_concepts=[obj.get("id", "unknown") for obj in document_model.get("objects", [])],
                missing_concepts=[],
                shared_concepts=[],
                modified_concepts=[],
                deltas=[],
                transitions=[],
                alignment_score=0.0,
                summary="No system state to compare against. All document concepts are new."
            )
        
        # Extract concept sets
        doc_objects = {obj.get("id"): obj for obj in document_model.get("objects", [])}
        sys_objects = {obj.get("id"): obj for obj in system_state.get("objects", [])}
        
        doc_ids = set(doc_objects.keys())
        sys_ids = set(sys_objects.keys())
        
        new_concepts = list(doc_ids - sys_ids)
        missing_concepts = list(sys_ids - doc_ids)
        shared_concepts = list(doc_ids & sys_ids)
        
        # Check for modifications in shared concepts
        modified_concepts = []
        for concept_id in shared_concepts:
            if self._is_modified(doc_objects[concept_id], sys_objects[concept_id]):
                modified_concepts.append(concept_id)
        
        # Build detailed deltas
        deltas = []
        
        for concept_id in new_concepts:
            deltas.append(ConceptDelta(
                concept_id=concept_id,
                delta_type="new",
                document_value=doc_objects[concept_id],
                system_value=None,
                transition_action="Add to system state"
            ))
        
        for concept_id in missing_concepts:
            deltas.append(ConceptDelta(
                concept_id=concept_id,
                delta_type="missing",
                document_value=None,
                system_value=sys_objects[concept_id],
                transition_action="Remove from system state or add to document"
            ))
        
        for concept_id in modified_concepts:
            deltas.append(ConceptDelta(
                concept_id=concept_id,
                delta_type="modified",
                document_value=doc_objects[concept_id],
                system_value=sys_objects[concept_id],
                transition_action="Update system state to match document"
            ))
        
        # Build transition plan
        transitions = self._build_transition_plan(deltas, doc_objects, sys_objects)
        
        # Calculate alignment score
        total = len(doc_ids | sys_ids)
        aligned = len(shared_concepts) - len(modified_concepts)
        alignment_score = aligned / total if total > 0 else 1.0
        
        # Generate summary
        summary = self._generate_summary(
            new_concepts, missing_concepts, shared_concepts, 
            modified_concepts, alignment_score
        )
        
        return StateComparisonResult(
            document_id=document_id,
            system_state_id=system_state_id,
            new_concepts=new_concepts,
            missing_concepts=missing_concepts,
            shared_concepts=shared_concepts,
            modified_concepts=modified_concepts,
            deltas=deltas,
            transitions=transitions,
            alignment_score=alignment_score,
            summary=summary
        )
    
    def _get_system_state(self) -> Optional[Dict]:
        """Get the current system state from Redis Cognitive Tick."""
        if not self.redis:
            return None
        
        try:
            data = self.redis.get(SYSTEM_STATE_KEY)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning(f"Failed to get system state: {e}")
        
        return None
    
    def _is_modified(self, doc_obj: Dict, sys_obj: Dict) -> bool:
        """Check if a concept has been modified between document and system."""
        # Compare key properties
        
        # Position difference
        doc_pos = np.array(doc_obj.get("position", [0, 0, 0]))
        sys_pos = np.array(sys_obj.get("position", [0, 0, 0]))
        position_diff = float(np.linalg.norm(doc_pos - sys_pos))
        
        # Mass difference
        doc_mass = doc_obj.get("mass", 0.5)
        sys_mass = sys_obj.get("mass", 0.5)
        mass_diff = abs(doc_mass - sys_mass)
        
        # Description difference (if present)
        doc_desc = doc_obj.get("desc", "")
        sys_desc = sys_obj.get("desc", "")
        desc_changed = doc_desc != sys_desc
        
        # Thresholds for "modified"
        return position_diff > 0.5 or mass_diff > 0.2 or desc_changed
    
    def _build_transition_plan(self, deltas: List[ConceptDelta], 
                                doc_objects: Dict, sys_objects: Dict) -> List[TransitionPlan]:
        """Build a prioritized transition plan from deltas."""
        transitions = []
        priority = 1
        
        # High priority: New concepts with high mass (important additions)
        high_mass_new = [d for d in deltas if d.delta_type == "new" 
                         and d.document_value.get("mass", 0) >= 0.7]
        for delta in high_mass_new:
            transitions.append(TransitionPlan(
                priority=priority,
                action="add",
                concept_id=delta.concept_id,
                description=f"Add high-priority concept: {delta.concept_id}",
                effort_estimate="medium"
            ))
            priority += 1
        
        # Medium priority: Modified concepts
        for delta in [d for d in deltas if d.delta_type == "modified"]:
            transitions.append(TransitionPlan(
                priority=priority,
                action="modify",
                concept_id=delta.concept_id,
                description=f"Update concept to match document: {delta.concept_id}",
                effort_estimate="low"
            ))
            priority += 1
        
        # Lower priority: Other new concepts
        other_new = [d for d in deltas if d.delta_type == "new" 
                     and d.document_value.get("mass", 0) < 0.7]
        for delta in other_new:
            transitions.append(TransitionPlan(
                priority=priority,
                action="add",
                concept_id=delta.concept_id,
                description=f"Add concept: {delta.concept_id}",
                effort_estimate="low"
            ))
            priority += 1
        
        # Lowest priority: Missing concepts (need decision)
        for delta in [d for d in deltas if d.delta_type == "missing"]:
            transitions.append(TransitionPlan(
                priority=priority,
                action="review",
                concept_id=delta.concept_id,
                description=f"Review: '{delta.concept_id}' is in system but not in document",
                effort_estimate="low"
            ))
            priority += 1
        
        return transitions
    
    def _generate_summary(self, new: List, missing: List, shared: List,
                          modified: List, alignment: float) -> str:
        """Generate a human-readable summary for ARCA."""
        parts = []
        
        # Alignment overview
        if alignment >= 0.8:
            parts.append(f"Document is well-aligned with current state ({alignment:.0%} alignment).")
        elif alignment >= 0.5:
            parts.append(f"Document has moderate alignment with current state ({alignment:.0%}).")
        else:
            parts.append(f"Document diverges significantly from current state ({alignment:.0%} alignment).")
        
        # Key changes
        if new:
            parts.append(f"{len(new)} new concepts to add: {', '.join(new[:3])}{'...' if len(new) > 3 else ''}.")
        
        if modified:
            parts.append(f"{len(modified)} concepts need updating: {', '.join(modified[:3])}{'...' if len(modified) > 3 else ''}.")
        
        if missing:
            parts.append(f"{len(missing)} concepts in system not covered by document.")
        
        if shared and not modified:
            parts.append(f"{len(shared)} concepts are already aligned.")
        
        return " ".join(parts)
    
    def format_for_context(self, result: StateComparisonResult) -> str:
        """Format comparison result for injection into ARCA's context."""
        lines = [
            f"## Comparison with Current System State",
            f"**Alignment**: {result.alignment_score:.0%}",
            "",
            result.summary,
            ""
        ]
        
        if result.transitions:
            lines.append("### Transition Plan:")
            for t in result.transitions[:5]:  # Top 5
                lines.append(f"{t.priority}. [{t.action.upper()}] {t.concept_id} ({t.effort_estimate})")
        
        if result.new_concepts:
            lines.append(f"\n### New Concepts ({len(result.new_concepts)}):")
            for c in result.new_concepts[:5]:
                lines.append(f"- {c}")
        
        return "\n".join(lines)


# Convenience function
def compare_document_to_system(document_model: Dict, redis_client=None) -> Dict:
    """
    Compare a document's geometric model to the current system state.
    
    Returns dict with deltas, transitions, alignment score, and context for ARCA.
    """
    engine = StateComparisonEngine(redis_client)
    result = engine.compare_to_system_state(document_model)
    
    return {
        **result.to_dict(),
        "context_injection": engine.format_for_context(result)
    }
