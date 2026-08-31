"""
Kuramoto Field: Phase-locking dynamics for empathic resonance.

Every ConceptMonad is an oscillator coupled to every other.
Understanding = phase-locking (order parameter near 1)
Dissonance = high energy (oscillators out of phase)
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from concept_monad import ConceptMonad


class UniversalKuramotoField:
    """
    Universal field of coupled oscillators.
    
    Implements the Kuramoto model where each concept is an oscillator
    with a natural frequency and couplings to other oscillators.
    
    The order parameter r measures global synchronization:
    - |r| ≈ 1: Perfect sync (global understanding)
    - |r| ≈ 0: Incoherent (no shared understanding)
    """
    
    def __init__(self, dt: float = 0.01, default_coupling: float = 0.5):
        """
        Initialize Kuramoto field.
        
        Args:
            dt: Time step for evolution
            default_coupling: Default coupling strength between concepts
        """
        self.concepts: Dict[str, ConceptMonad] = {}
        self.dt = dt
        self.default_coupling = default_coupling
        self.tick_count = 0
    
    def add_concept(self, concept: ConceptMonad, auto_couple: bool = True):
        """
        Add a concept to the field.
        
        Args:
            concept: ConceptMonad to add
            auto_couple: Automatically couple to existing concepts
        """
        self.concepts[concept.concept_id] = concept
        
        if auto_couple:
            # Couple to all existing concepts with default strength
            for other_id in self.concepts:
                if other_id != concept.concept_id:
                    if other_id not in concept.couplings:
                        concept.couplings[other_id] = self.default_coupling
                    other = self.concepts[other_id]
                    if concept.concept_id not in other.couplings:
                        other.couplings[concept.concept_id] = self.default_coupling
    
    def remove_concept(self, concept_id: str):
        """Remove a concept from the field."""
        if concept_id in self.concepts:
            # Remove couplings from other concepts
            for other in self.concepts.values():
                if concept_id in other.couplings:
                    del other.couplings[concept_id]
            del self.concepts[concept_id]
    
    def set_coupling(self, id_a: str, id_b: str, strength: float):
        """Set coupling strength between two concepts (symmetric)."""
        if id_a in self.concepts and id_b in self.concepts:
            self.concepts[id_a].couplings[id_b] = strength
            self.concepts[id_b].couplings[id_a] = strength
    
    def tick(self):
        """
        Evolve all oscillator phases one timestep.
        
        Implements: dθ_i/dt = ω_i + Σ_j K_ij * sin(θ_j - θ_i)
        """
        # Store new phases (to avoid order-dependent updates)
        new_phases = {}
        
        for concept_id, concept in self.concepts.items():
            # Kuramoto equation: phase contribution from couplings
            phase_contribution = 0.0
            
            for other_id, coupling in concept.couplings.items():
                if other_id in self.concepts:
                    other = self.concepts[other_id]
                    phase_diff = other.phase - concept.phase
                    phase_contribution += coupling * np.sin(phase_diff)
            
            # Update phase
            new_phase = concept.phase + self.dt * (
                concept.natural_frequency + phase_contribution
            )
            new_phases[concept_id] = new_phase % (2 * np.pi)
        
        # Apply new phases
        for concept_id, new_phase in new_phases.items():
            self.concepts[concept_id].phase = new_phase
        
        self.tick_count += 1
    
    def compute_order_parameter(self) -> complex:
        """
        Compute global synchronization measure.
        
        Returns:
            Complex number where |r| = sync strength, arg(r) = mean phase
            |r| = 1 means perfect synchronization
            |r| = 0 means complete incoherence
        """
        if not self.concepts:
            return 0.0 + 0.0j
        
        phases = np.array([c.phase for c in self.concepts.values()])
        return np.mean(np.exp(1j * phases))
    
    def sync_strength(self) -> float:
        """Return |r|, the sync strength (0 to 1)."""
        return abs(self.compute_order_parameter())
    
    def mean_phase(self) -> float:
        """Return the mean phase of all oscillators."""
        r = self.compute_order_parameter()
        return np.angle(r)
    
    def compute_local_sync(self, concept_id: str) -> float:
        """
        Compute local synchronization for a specific concept.
        
        Returns how well this concept is phase-locked with its neighbors.
        """
        if concept_id not in self.concepts:
            return 0.0
        
        concept = self.concepts[concept_id]
        if not concept.couplings:
            return 0.0
        
        coupled_phases = []
        for other_id in concept.couplings:
            if other_id in self.concepts:
                coupled_phases.append(self.concepts[other_id].phase)
        
        if not coupled_phases:
            return 0.0
        
        # Local order parameter
        local_r = np.mean(np.exp(1j * (np.array(coupled_phases) - concept.phase)))
        return abs(local_r)
    
    def find_phase_locked_clusters(self, threshold: float = 0.9) -> List[List[str]]:
        """
        Find clusters of phase-locked concepts.
        
        Args:
            threshold: Phase difference threshold for considering locked
            
        Returns:
            List of clusters (lists of concept IDs)
        """
        if not self.concepts:
            return []
        
        visited = set()
        clusters = []
        
        for start_id in self.concepts:
            if start_id in visited:
                continue
            
            # BFS to find phase-locked cluster
            cluster = []
            queue = [start_id]
            
            while queue:
                current_id = queue.pop(0)
                if current_id in visited:
                    continue
                
                visited.add(current_id)
                cluster.append(current_id)
                current = self.concepts[current_id]
                
                for other_id in current.couplings:
                    if other_id in visited or other_id not in self.concepts:
                        continue
                    
                    other = self.concepts[other_id]
                    phase_diff = abs(current.phase - other.phase)
                    # Normalize to [0, π]
                    phase_diff = min(phase_diff, 2 * np.pi - phase_diff)
                    
                    if phase_diff < (1 - threshold) * np.pi:
                        queue.append(other_id)
            
            if len(cluster) > 1:
                clusters.append(cluster)
        
        return clusters
    
    def compute_empathy_score(self, id_a: str, id_b: str) -> float:
        """
        Compute empathy (phase-locking) between two concepts.
        
        Returns:
            1.0 = perfect sync, 0.0 = opposite phase, 0.5 = orthogonal
        """
        if id_a not in self.concepts or id_b not in self.concepts:
            return 0.0
        
        phase_diff = abs(self.concepts[id_a].phase - self.concepts[id_b].phase)
        phase_diff = min(phase_diff, 2 * np.pi - phase_diff)
        
        # Convert to empathy score (0 diff = 1.0, π diff = 0.0)
        return 1.0 - (phase_diff / np.pi)
    
    def get_state_summary(self) -> dict:
        """Get summary of field state."""
        r = self.compute_order_parameter()
        return {
            "tick": self.tick_count,
            "concept_count": len(self.concepts),
            "sync_strength": abs(r),
            "mean_phase": np.angle(r),
            "clusters": len(self.find_phase_locked_clusters()),
        }
