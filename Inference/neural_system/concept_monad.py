from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import numpy as np


class ConceptMonad:
    """
    The fundamental unit of the Phenomenological Core.
    A concept is a living oscillator with geometric and energetic properties.
    
    Accepts both `concept_id` and `name` as the primary identifier for backward compatibility.
    """
    
    def __init__(
        self,
        concept_id: str = "",
        name: str = "",  # Alias for concept_id
        lineage: Optional[List[str]] = None,
        birth_tick: int = 0,
        hv_signature: Optional[np.ndarray] = None,
        hv_velocity: Optional[np.ndarray] = None,
        phase: float = 0.0,
        natural_frequency: float = 1.0,
        amplitude: float = 1.0,
        energy: float = 0.0,
        uncertainty: float = 0.0,
        couplings: Optional[Dict[str, float]] = None,
        is_self_referential: bool = False,
        mirror_of: Optional[str] = None,
        origin: str = "",
        vector: Any = None,
        id: str = "",
        frequency: float = 1.0,
    ):
        # Identity - support both concept_id and name (name takes precedence if provided)
        self.concept_id = name if name else concept_id
        self.lineage = lineage if lineage is not None else []
        self.birth_tick = birth_tick
        
        # Geometric (HDC) - 10,000-bit encoding
        self.hv_signature = hv_signature if hv_signature is not None else np.zeros(10000, dtype=np.int8)
        self.hv_velocity = hv_velocity if hv_velocity is not None else np.zeros(10000, dtype=np.int8)
        
        # Oscillatory (Kuramoto)
        self.phase = phase
        self.natural_frequency = natural_frequency
        self.amplitude = amplitude
        
        # Energy (from Jeepas)
        self.energy = energy
        
        # Curiosity/Empathy metrics
        self.uncertainty = uncertainty
        self.couplings = couplings if couplings is not None else {}
        
        # Fractal Self properties
        self.is_self_referential = is_self_referential
        self.mirror_of = mirror_of
        
        # Optional properties for compatibility
        self.origin = origin
        self.vector = vector
        self.id = id
        self.frequency = frequency
        
        # Sync natural_frequency with frequency if frequency was explicitly set
        if frequency != 1.0 and natural_frequency == 1.0:
            self.natural_frequency = frequency
    
    @property
    def name(self) -> str:
        """Alias for concept_id for backward compatibility."""
        return self.concept_id
    
    @name.setter
    def name(self, value: str):
        """Set concept_id via name alias."""
        self.concept_id = value
    
    def set_vector(self, vector: Any):
        """Set the HDC vector for this concept."""
        self.vector = vector
    
    # Factory method for compatibility
    @classmethod
    def create(cls, name: str = "", origin: str = "", **kwargs) -> "ConceptMonad":
        """Create ConceptMonad with name parameter for backward compatibility."""
        return cls(name=name, origin=origin, **kwargs)
    
    def __repr__(self):
        return f"ConceptMonad(concept_id='{self.concept_id}', phase={self.phase:.3f}, energy={self.energy:.3f})"


def ConceptMonadFactory(name: str = "", origin: str = "", **kwargs) -> ConceptMonad:
    """Factory function for backward compatibility with name/origin parameters."""
    return ConceptMonad(name=name, origin=origin, **kwargs)
