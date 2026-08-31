import numpy as np
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

@dataclass
class RelationalDimension:
    id: str
    name: str
    description: str
    weight: float = 1.0  # How much this dimension contributes to scalar K
    positive_pole: str = "high"
    negative_pole: str = "low"

class RelationalTensor:
    """
    Manages the multi-dimensional couplings between ConceptMonads.
    Replaces simple scalar weights with a Tensor K_ij^d.
    
    Dimensions (d) might include:
    - Trust (Reliability)
    - Valence (Good/Bad)
    - Temporality (Urgency)
    - Agency (Passive/Active)
    
    Provides:
    - Storage of tensor values.
    - Projection to scalar 'Effective Coupling' (k_eff) for Kuramoto.
    - Discovery of new dimensions (placeholder for 'DimensionDiscoverer').
    """

    def __init__(self):
        # The Schema: Registered dimensions
        self.dimensions: Dict[str, RelationalDimension] = {
            "resonance": RelationalDimension("resonance", "Resonance", "General compatibility", 1.0),
            "trust": RelationalDimension("trust", "Trust", "Predicted reliability", 0.8),
            "valence": RelationalDimension("valence", "Valence", "Emotional/Goal alignment", 0.5),
            "causality": RelationalDimension("causality", "Causality", "Predictive power A->B", 0.9)
        }
        
        # The Data: Sparse storage
        # {source_id: {target_id: {dim_id: value}}}
        # Values are typically [-1.0, 1.0]
        self._tensor: Dict[str, Dict[str, Dict[str, float]]] = {}
        
    def set_relation(self, source_id: str, target_id: str, dim_id: str, value: float):
        if source_id not in self._tensor:
            self._tensor[source_id] = {}
        if target_id not in self._tensor[source_id]:
            self._tensor[source_id][target_id] = {}
            
        # Clamp value
        value = max(-1.0, min(1.0, value))
        self._tensor[source_id][target_id][dim_id] = value

    def get_relation(self, source_id: str, target_id: str) -> Dict[str, float]:
        return self._tensor.get(source_id, {}).get(target_id, {})

    def get_scalar_coupling(self, source_id: str, target_id: str) -> float:
        """
        Projects the multi-dimensional tensor K_ij^d down to a single
        scalar k_eff for the Kuramoto Physics Engine.
        
        k_eff = Sum(w_d * v_d) / Sum(w_d)
        """
        relations = self.get_relation(source_id, target_id)
        if not relations:
            return 0.0
            
        weighted_sum = 0.0
        total_weight = 0.0
        
        for dim_id, val in relations.items():
            if dim_id in self.dimensions:
                w = self.dimensions[dim_id].weight
                weighted_sum += val * w
                total_weight += w
        
        if total_weight == 0:
            return 0.0
            
        return weighted_sum / total_weight

    def add_dimension(self, dim: RelationalDimension):
        self.dimensions[dim.id] = dim


class RelationalDimensionDiscoverer:
    """
    Discovers new ways of relating by analyzing relational failures.
    Based on 'Vision: Infinitely Expandable Relational Axes'.
    """
    def __init__(self, tensor: 'RelationalTensor'):
        self.tensor = tensor
        self.failure_log: List[dict] = []

    def log_failure(self, source: str, target: str, expected: str, actual: str):
        """Log when a relation doesn't behave as expected."""
        self.failure_log.append({
            'source': source,
            'target': target,
            'relation': self.tensor.get_relation(source, target),
            'expected': expected,
            'actual': actual,
            'timestamp': time.time()
        })

    def analyze_failures(self) -> Optional[RelationalDimension]:
        """
        Analyze failure patterns to discover missing dimensions.
        """
        if len(self.failure_log) < 5: 
            return None

        # Gather profiles
        profiles = []
        for f in self.failure_log:
            # Vectorize current relation
            p = []
            for d in self.tensor.dimensions:
                p.append(f['relation'].get(d, 0.0))
            profiles.append(p)
            
        profiles = np.array(profiles)
        
        # Simple Logic for now: If high variance in failures implies uncaptured factor
        # In a real impl, we use KMeans/PCA as per vision doc
        try:
            from sklearn.decomposition import PCA
            pca = PCA(n_components=min(len(profiles), 2))
            pca.fit(profiles)
            unexplained = 1.0 - sum(pca.explained_variance_ratio_)
            
            if unexplained > 0.1: # Significant unexplained variance
                return RelationalDimension(
                    id=f"discovered_{int(time.time())}",
                    name=f"Discovered Dim {len(self.tensor.dimensions)}",
                    description="Auto-discovered from failure patterns.",
                    weight=0.5
                )
        except ImportError:
            pass
            
        return None

# Attach discovery to Tensor
RelationalTensor.discoverer = property(lambda self: RelationalDimensionDiscoverer(self))
