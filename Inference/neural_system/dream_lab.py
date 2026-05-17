import copy
import numpy as np
from typing import Dict, List, Any
from .kuramoto_field import UniversalKuramotoField
from .energy_service import EnergyService

class DreamLaboratory:
    """
    The Simulation Sandbox.
    
    Allows ARCA to:
    1. Clone the current state of a sub-graph (Concept Cluster).
    2. Apply mutations (Hypothetical Relations: "What if I trusted X?").
    3. Run the physics engine forward in time (Simulate outcome).
    4. Measure result (Does Energy drop? Does Coherence rise?).
    
    Used for:
    - Planning (Pre-computation of social dynamics).
    - Creativity (Random mutation of concepts).
    - Self-Reflection (Analyzing past failures).
    """

    def __init__(self):
        pass

    def run_simulation(self, 
                       base_field: UniversalKuramotoField, 
                       target_ids: List[str], 
                       mutations: List[Dict[str, Any]],
                       steps: int = 100) -> Dict[str, Any]:
        """
        Run a 'Dream' simulation.
        
        Args:
            base_field: The source of truth (Reality).
            target_ids: IDs of concepts to include in the dream (Scope).
            mutations: List of changes (e.g. {'type': 'coupling', 'source': A, 'target': B, 'value': 0.9}).
            steps: How many ticks to simulate.
            
        Returns:
            Outcome report (Energy delta, Coherence delta).
        """
        # 1. Clone the Sub-Graph
        dream_field = UniversalKuramotoField(dt=base_field.dt)
        
        for mid in target_ids:
            original = base_field.get_monad(mid)
            if original:
                # Deep copy to allow mutation without affecting reality
                clone = copy.deepcopy(original)
                dream_field.add_monad(clone)
                
        # 2. Apply Mutations (The "Hypothesis")
        for mut in mutations:
            m_type = mut.get("type")
            if m_type == "coupling":
                src = mut["source"]
                tgt = mut["target"]
                val = mut["value"]
                if src in dream_field.monads:
                    dream_field.monads[src].couplings[tgt] = val
                    
            elif m_type == "frequency_shift":
                mid = mut["id"]
                shift = mut["value"]
                if mid in dream_field.monads:
                    dream_field.monads[mid].frequency += shift

        # 3. Initialize Energy Service for the dream
        dream_energy = EnergyService(dream_field)
        
        initial_energy = dream_energy.compute_total_energy()["total"]
        initial_coherence = dream_field.global_coherence
        
        # 4. Run Physics (The "Evolution")
        for _ in range(steps):
            dream_field.step()
            
        # 5. Measure Outcome
        final_energy = dream_energy.compute_total_energy()["total"]
        final_coherence = dream_field.global_coherence
        
        return {
            "energy_delta": final_energy - initial_energy,
            "coherence_delta": final_coherence - initial_coherence,
            "is_stable": final_coherence > 0.3, # Arbitrary stability threshold
            "final_state": {mid: m.phase for mid, m in dream_field.monads.items()}
        }
