import logging
import time
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class FractalSelf:
    """
    Manages the 'Fractal Self' - the self-referential model of the system.
    Enables 'Strange Loops': The system observing itself observing the world.
    """
    def __init__(self, kuramoto_field, agent_id="ARCA"):
        self.field = kuramoto_field
        self.agent_id = agent_id
        self.history = []
        
        # Ensure 'I' exists in the field
        if self.agent_id not in self.field.monads:
            from .concept_monad import ConceptMonad
            # Late import to avoid circular dependency if any
            
            # The Seed of Self
            self_monad = ConceptMonad(name="ARCA", origin="system")
            self_monad.id = self.agent_id
            self_monad.is_self_referential = True
            self_monad.uncertainty = 0.01  # I am sure that I am
            
            # Use a stable chaotic seed if accessible, otherwise random/zero
            # Assuming field interactions will shape it.
            
            self.field.add_monad(self_monad)
            logger.info(f"FractalSelf: Initialized Identity '{self.agent_id}'.")

    def introspect(self) -> Dict[str, Any]:
        """
        Looks inward. Analyzes the state of the 'Self' monad relative to others.
        Returns a report on internal tensions (high phase difference with trusted concepts).
        """
        self_monad = self.field.monads.get(self.agent_id)
        if not self_monad:
            return {"status": "dissociated", "tensions": []}
            
        tensions = []
        
        # Check couplings
        for neighbor_id, strength in self_monad.couplings.items():
            if strength > 0.5: # Trusted neighbor
                neighbor = self.field.monads.get(neighbor_id)
                if neighbor:
                    # Check Phase difference
                    delta = abs(self_monad.phase - neighbor.phase)
                    # Normalize to [0, Pi]
                    # If delta is high, I am out of sync with what I value -> Tension
                    if delta > 1.5: # Approx 90 degrees
                        tensions.append({
                            "source": neighbor.name,
                            "type": "dissonance",
                            "severity": float(delta)
                        })
                        
        report = {
            "timestamp": time.time(),
            "status": "integrated" if not tensions else "conflicted",
            "self_uncertainty": self_monad.uncertainty,
            "tensions": tensions
        }
        
        self.history.append(report)
        return report

    def expand_self(self, new_concept_id: str, relationship_strength: float):
        """
        Integrates a new concept into the Self-Model.
        "I am now related to X."
        """
        if self.agent_id in self.field.monads:
            self.field.monads[self.agent_id].couplings[new_concept_id] = relationship_strength
            logger.info(f"FractalSelf: Expanded to include relationship with {new_concept_id}")
