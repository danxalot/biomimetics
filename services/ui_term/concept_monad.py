"""
ConceptMonad: Universal representation of any relatable concept.

Every concept (document, user, service) is a living oscillator with:
- Geometric properties (HDC hypervector)
- Oscillatory dynamics (Kuramoto phase)
- Energy state (distance from attractors)
- Curiosity/Empathy metrics
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np
from datetime import datetime


@dataclass
class ConceptMonad:
    """
    Universal representation of any relatable concept.
    
    A ConceptMonad exists as a "living oscillator" that can:
    - Phase-lock with other concepts (empathy/understanding)
    - Attract curiosity (high uncertainty = high pull)
    - Evolve over time (velocity in HDC space)
    """
    
    # Identity
    concept_id: str
    lineage: List[str] = field(default_factory=list)  # Ancestral concepts
    birth_tick: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    # Geometric (HDC) - 10,000-bit encoding
    hv_signature: Optional[np.ndarray] = None  # Binary hypervector
    hv_velocity: Optional[np.ndarray] = None   # Rate of change (delta)
    
    # Oscillatory (Kuramoto)
    phase: float = 0.0              # θ ∈ [0, 2π]
    natural_frequency: float = 1.0  # ω - intrinsic rhythm
    amplitude: float = 1.0          # Salience/importance
    
    # Energy (Geometric Tension)
    energy: float = 0.5             # Distance from attractor = system health
    
    # Curiosity metrics
    uncertainty: float = 0.5        # Fisher Information (how unknown)
    curiosity_pull: float = 0.0     # Gradient strength toward this concept
    
    # Empathy metrics  
    couplings: Dict[str, float] = field(default_factory=dict)  # concept_id → K
    empathy_depth: float = 0.0      # How well we can "mirror" this
    
    # Metadata
    source_type: str = "unknown"    # document, user, service, abstract
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Initialize hypervectors if not provided."""
        if self.hv_signature is None:
            # Random initialization (will be replaced by encoder)
            self.hv_signature = np.random.choice([-1, 1], size=10000).astype(np.int8)
        if self.hv_velocity is None:
            self.hv_velocity = np.zeros(10000, dtype=np.float32)
    
    def bind(self, other: 'ConceptMonad') -> np.ndarray:
        """HDC Binding: XOR for binary, element-wise multiply for bipolar."""
        return self.hv_signature * other.hv_signature
    
    def bundle(self, others: List['ConceptMonad']) -> np.ndarray:
        """HDC Bundling: Superposition (majority vote for binary)."""
        all_vectors = [self.hv_signature] + [o.hv_signature for o in others]
        summed = np.sum(all_vectors, axis=0)
        return np.sign(summed).astype(np.int8)
    
    def similarity(self, other: 'ConceptMonad') -> float:
        """Cosine similarity in HDC space (or Hamming for binary)."""
        dot = np.dot(self.hv_signature.astype(float), other.hv_signature.astype(float))
        norm = np.linalg.norm(self.hv_signature) * np.linalg.norm(other.hv_signature)
        return dot / (norm + 1e-8)
    
    def hamming_distance(self, other: 'ConceptMonad') -> int:
        """Hamming distance for binary vectors."""
        return np.sum(self.hv_signature != other.hv_signature)
    
    def compute_energy(self, attractor: 'ConceptMonad') -> float:
        """Energy = normalized Hamming distance from attractor."""
        dist = self.hamming_distance(attractor)
        self.energy = dist / len(self.hv_signature)
        return self.energy
    
    def to_dict(self) -> dict:
        """Serialize for storage (excluding large arrays)."""
        return {
            "concept_id": self.concept_id,
            "lineage": self.lineage,
            "birth_tick": self.birth_tick,
            "phase": self.phase,
            "natural_frequency": self.natural_frequency,
            "amplitude": self.amplitude,
            "energy": self.energy,
            "uncertainty": self.uncertainty,
            "curiosity_pull": self.curiosity_pull,
            "couplings": self.couplings,
            "empathy_depth": self.empathy_depth,
            "source_type": self.source_type,
            "tags": self.tags,
        }
    
    @classmethod
    def from_dict(cls, data: dict, hv_signature: Optional[np.ndarray] = None) -> 'ConceptMonad':
        """Deserialize from storage."""
        return cls(
            concept_id=data["concept_id"],
            lineage=data.get("lineage", []),
            birth_tick=data.get("birth_tick", 0),
            phase=data.get("phase", 0.0),
            natural_frequency=data.get("natural_frequency", 1.0),
            amplitude=data.get("amplitude", 1.0),
            energy=data.get("energy", 0.5),
            uncertainty=data.get("uncertainty", 0.5),
            curiosity_pull=data.get("curiosity_pull", 0.0),
            couplings=data.get("couplings", {}),
            empathy_depth=data.get("empathy_depth", 0.0),
            source_type=data.get("source_type", "unknown"),
            tags=data.get("tags", []),
            hv_signature=hv_signature,
        )
