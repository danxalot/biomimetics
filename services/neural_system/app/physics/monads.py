
# services/neural_system/app/physics/monads.py
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import time

@dataclass
class ConceptMonad:
    """
    A Monad representing the 'Relational Existence' of a concept or agent.
    
    Based on the 'Universal Relational Substrate' (Design Doc Part 1).
    A Monad is an entity that 'mirrors' the universe from its perspective.
    
    It encapsulates:
    - Identity (Who am I)
    - State (How am I)
    - Relation (How do I couple with others)
    """
    
    id: str  # Unique Identity
    
    # Internal State (Proprioception)
    phase: float = 0.0  # Current phase in the specific cycle (0-2pi)
    frequency: float = 1.0  # Intrinsic frequency (Speed of thought/processing)
    energy: float = 1.0     # Vitality/Resource level
    
    # Relational Field (Coupling)
    # Map of OtherID -> CouplingStrength (0.0 - 1.0)
    coupling_matrix: Dict[str, float] = None
    
    # The 'Mirror'
    # A simplified representation of the external world as seen by this monad
    mirror_state: Dict[str, Any] = None

    def __post_init__(self):
        if self.coupling_matrix is None:
            self.coupling_matrix = {}
        if self.mirror_state is None:
            self.mirror_state = {}
            
    def tick(self, dt: float = 0.1):
        """
        Evolve the monad's internal clock using Kuramoto dynamics.
        dtheta/dt = omega + sum(K * sin(theta_j - theta_i))
        """
        # Basic intrinsic evolution
        self.phase += self.frequency * dt
        # Wrap to 0-2pi? Usually we keep continuous phase for tracking cycles
        
        # Note: Full Kuramoto interaction requires access to the full field of monads
        # which would be handled by the 'UniversalKuramotoField' engine.

    def resonate(self, other_phase: float, coupling: float) -> float:
        """
        Calculate resonance (phase coherence) with an external signal.
        Returns: Coherence [0, 1] (1 = perfectly in sync)
        """
        # Phase difference
        diff = abs(self.phase - other_phase)
        # Normalize to 0-1 coherence
        import math
        coherence = 0.5 * (1.0 + math.cos(diff))
        
        # Update internal frequency to synchronize (Entrainment)
        # d_omega = K * sin(diff)
        entrainment = coupling * math.sin(other_phase - self.phase)
        self.frequency += entrainment * 0.1 # Learning rate
        
        return coherence
