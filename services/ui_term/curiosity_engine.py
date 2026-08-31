"""
Curiosity Engine: Fisher Information gradient for intrinsic motivation.

System is "pulled" toward high-uncertainty regions of the knowledge manifold.
Where the model is confident → flat manifold (low energy)
Where uncertain → steep gradient → curiosity pull
"""

import numpy as np
from typing import Optional, List, Tuple
from concept_monad import ConceptMonad


class CuriosityEngine:
    """
    Fisher Information Curiosity Engine.
    
    Computes curiosity gradients based on prediction uncertainty.
    High prediction error = high curiosity = system should explore.
    
    Energy model:
    - Low energy (confident) = flat manifold = no curiosity pull
    - High energy (uncertain) = steep gradient = strong curiosity pull
    """
    
    def __init__(
        self,
        predictor=None,
        curiosity_threshold: float = 0.4,
        high_curiosity_threshold: float = 0.7,
    ):
        """
        Initialize curiosity engine.
        
        Args:
            predictor: Optional JEPA or embedding predictor
            curiosity_threshold: Minimum gradient for generating inquiry
            high_curiosity_threshold: Threshold for high-curiosity questions
        """
        self.predictor = predictor
        self.curiosity_threshold = curiosity_threshold
        self.high_curiosity_threshold = high_curiosity_threshold
    
    def compute_curiosity_gradient(self, concept: ConceptMonad) -> float:
        """
        Compute gradient of entropy (∇H) for this concept.
        
        High gradient = system should explore this concept.
        
        Args:
            concept: ConceptMonad to analyze
            
        Returns:
            Curiosity gradient in [0, 1]
        """
        if self.predictor is None:
            # Fallback: use concept's intrinsic uncertainty
            return concept.uncertainty
        
        # JEPA prediction uncertainty
        try:
            predicted = self.predictor.predict(concept.hv_signature)
            prediction_error = np.linalg.norm(predicted - concept.hv_velocity)
            # Normalize to [0, 1]
            return min(1.0, prediction_error / 10.0)
        except Exception:
            return concept.uncertainty
    
    def should_explore(self, concept: ConceptMonad) -> bool:
        """Check if this concept warrants exploration."""
        return self.compute_curiosity_gradient(concept) >= self.curiosity_threshold
    
    def rank_by_curiosity(
        self,
        concepts: List[ConceptMonad],
    ) -> List[Tuple[ConceptMonad, float]]:
        """
        Rank concepts by curiosity gradient.
        
        Args:
            concepts: List of concepts to rank
            
        Returns:
            List of (concept, gradient) tuples sorted by gradient descending
        """
        ranked = [
            (c, self.compute_curiosity_gradient(c))
            for c in concepts
        ]
        return sorted(ranked, key=lambda x: x[1], reverse=True)
    
    def generate_inquiry(
        self,
        concept: ConceptMonad,
        context: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generate a curiosity-driven question about this concept.
        
        This is the "Inquire" mode for document processing.
        
        Args:
            concept: ConceptMonad to inquire about
            context: Optional context for more specific questions
            
        Returns:
            Question string, or None if curiosity is too low
        """
        gradient = self.compute_curiosity_gradient(concept)
        
        if gradient < self.curiosity_threshold:
            return None  # Low curiosity, no question needed
        
        concept_name = concept.concept_id
        
        if gradient >= self.high_curiosity_threshold:
            # High curiosity - deep exploration questions
            templates = [
                f"What is the relationship between {concept_name} and the broader system?",
                f"What assumptions underlie {concept_name} that we haven't examined?",
                f"How might {concept_name} behave under conditions we haven't considered?",
                f"What would falsify our understanding of {concept_name}?",
            ]
        else:
            # Medium curiosity - clarification questions
            templates = [
                f"How does {concept_name} connect to what we discussed before?",
                f"Can you elaborate on the mechanism behind {concept_name}?",
                f"What are the edge cases for {concept_name}?",
            ]
        
        # Select based on hash for consistency
        idx = hash(concept_name) % len(templates)
        return templates[idx]
    
    def generate_exploration_plan(
        self,
        concepts: List[ConceptMonad],
        max_questions: int = 5,
    ) -> List[dict]:
        """
        Generate an exploration plan for multiple concepts.
        
        Args:
            concepts: List of concepts to explore
            max_questions: Maximum questions to generate
            
        Returns:
            List of exploration items with concept, gradient, and question
        """
        ranked = self.rank_by_curiosity(concepts)
        plan = []
        
        for concept, gradient in ranked[:max_questions]:
            question = self.generate_inquiry(concept)
            if question:
                plan.append({
                    "concept_id": concept.concept_id,
                    "curiosity_gradient": gradient,
                    "question": question,
                    "uncertainty": concept.uncertainty,
                    "energy": concept.energy,
                })
        
        return plan
    
    def compute_field_curiosity(
        self,
        concepts: List[ConceptMonad],
    ) -> dict:
        """
        Compute aggregate curiosity metrics for a field of concepts.
        
        Returns:
            Dictionary with mean, max, distribution stats
        """
        if not concepts:
            return {"mean": 0.0, "max": 0.0, "count": 0}
        
        gradients = [self.compute_curiosity_gradient(c) for c in concepts]
        
        return {
            "mean": np.mean(gradients),
            "max": np.max(gradients),
            "min": np.min(gradients),
            "std": np.std(gradients),
            "count": len(concepts),
            "explorable_count": sum(1 for g in gradients if g >= self.curiosity_threshold),
            "high_curiosity_count": sum(1 for g in gradients if g >= self.high_curiosity_threshold),
        }
    
    def update_concept_curiosity(self, concept: ConceptMonad):
        """Update a concept's curiosity_pull based on current gradient."""
        concept.curiosity_pull = self.compute_curiosity_gradient(concept)


class EmpathyEngine:
    """
    Empathy Engine: Phase-locking detection for resonant understanding.
    
    Works with KuramotoField to detect when concepts achieve
    synchronization (understanding/empathy).
    """
    
    def __init__(self, sync_threshold: float = 0.8):
        """
        Initialize empathy engine.
        
        Args:
            sync_threshold: Threshold for considering concepts "in sync"
        """
        self.sync_threshold = sync_threshold
    
    def compute_empathy_depth(
        self,
        concept: ConceptMonad,
        neighbors: List[ConceptMonad],
    ) -> float:
        """
        Compute how well we can "mirror" this concept.
        
        Based on phase alignment with coupled concepts.
        """
        if not neighbors:
            return 0.0
        
        phase_diffs = []
        for other in neighbors:
            diff = abs(concept.phase - other.phase)
            diff = min(diff, 2 * np.pi - diff)  # Normalize to [0, π]
            phase_diffs.append(diff)
        
        # Convert to empathy (0 diff = 1.0, π diff = 0.0)
        mean_diff = np.mean(phase_diffs)
        return 1.0 - (mean_diff / np.pi)
    
    def find_resonant_pairs(
        self,
        concepts: List[ConceptMonad],
    ) -> List[Tuple[str, str, float]]:
        """
        Find pairs of concepts that are resonating (phase-locked).
        
        Returns:
            List of (id_a, id_b, empathy_score) tuples
        """
        pairs = []
        
        for i, a in enumerate(concepts):
            for b in concepts[i + 1:]:
                phase_diff = abs(a.phase - b.phase)
                phase_diff = min(phase_diff, 2 * np.pi - phase_diff)
                empathy = 1.0 - (phase_diff / np.pi)
                
                if empathy >= self.sync_threshold:
                    pairs.append((a.concept_id, b.concept_id, empathy))
        
        return sorted(pairs, key=lambda x: x[2], reverse=True)
