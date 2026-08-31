"""
Hyperbolic Kuramoto Field

Part of Stage 3: Phenomenological Mind
Phase-locking of concept monads toward golden ratio (1.618) target
"""

import numpy as np
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class HyperbolicKuramoto:
    """
    Hyperbolic Kuramoto Model for concept phase-locking

    Simulates 2,000 concept monads phase-locking toward golden ratio target
    Regulated by Poincaré Kernel pushing unused concepts to 32-dim edge
    """

    def __init__(self, num_concepts: int = 2000, target_frequency: float = 1.618):
        self.num_concepts = num_concepts
        self.target_frequency = target_frequency  # Golden ratio (BG3)

        # Concept monads: each has phase and frequency
        self.phases = np.random.uniform(0, 2 * np.pi, num_concepts)
        self.frequencies = np.random.uniform(0.5, 2.0, num_concepts)

        # Coupling matrix (all-to-all with random strengths)
        self.coupling = np.random.randn(num_concepts, num_concepts) * 0.1

        # Poincaré kernel parameters
        self.poincaré_strength = 0.5
        self.edge_threshold = 0.32  # 32-dim edge

        logger.info(f"Hyperbolic Kuramoto initialized: {num_concepts} concept monads")

    def phase_locking(
        self, concept_activations: List[float], steps: int = 10
    ) -> Dict[str, Any]:
        """
        Simulate phase-locking of concept monads

        Args:
            concept_activations: Activation strengths of concepts
            steps: Number of simulation steps

        Returns:
            Phase-locking statistics and final state
        """
        activations = np.array(concept_activations)

        if len(activations) != self.num_concepts:
            raise ValueError(
                f"Expected {self.num_concepts} activations, got {len(activations)}"
            )

        # Update phases over time
        phase_history = []

        for step in range(steps):
            # Kuramoto update rule
            for i in range(self.num_concepts):
                # Coupling from other concepts
                coupling_sum = np.sum(
                    self.coupling[i] * np.sin(self.phases - self.phases[i])
                )

                # Update frequency toward target
                freq_error = self.target_frequency - self.frequencies[i]
                self.frequencies[i] += 0.01 * freq_error

                # Update phase
                self.phases[i] += self.frequencies[i] + 0.1 * coupling_sum

                # Apply Poincaré kernel (push inactive concepts to edge)
                if activations[i] < self.edge_threshold:
                    # Push toward edge of phase space
                    self.phases[i] += self.poincaré_strength * (
                        np.pi - np.abs(self.phases[i] - np.pi)
                    )

            # Normalize phases
            self.phases = np.mod(self.phases, 2 * np.pi)

            phase_history.append(self.phases.copy())

        # Compute phase-locking statistics
        phase_array = np.array(phase_history)

        # Order parameter (degree of synchronization)
        order_parameter = np.abs(np.mean(np.exp(1j * self.phases)))

        # Cluster analysis
        clusters = self._detect_clusters()

        # Frequency distribution
        freq_std = np.std(self.frequencies)

        result = {
            "order_parameter": float(order_parameter),
            "phase_coherence": float(1 - freq_std),
            "num_clusters": len(clusters),
            "cluster_sizes": [len(c) for c in clusters],
            "final_phases": self.phases.tolist(),
            "final_frequencies": self.frequencies.tolist(),
            "phase_history": phase_array.tolist(),
        }

        return result

    def _detect_clusters(self) -> List[List[int]]:
        """Detect phase clusters in the system"""
        # Simple clustering based on phase proximity
        clusters = []
        visited = set()

        for i in range(self.num_concepts):
            if i in visited:
                continue

            # Find nearby phases
            cluster = [i]
            visited.add(i)

            for j in range(i + 1, self.num_concepts):
                if j in visited:
                    continue

                phase_diff = np.abs(self.phases[i] - self.phases[j])
                if phase_diff < 0.5:  # Within 0.5 radians
                    cluster.append(j)
                    visited.add(j)

            clusters.append(cluster)

        return clusters

    def get_dominant_concepts(self, top_k: int = 10) -> List[int]:
        """Get concepts with highest activation or phase coherence"""
        # Compute coherence with target frequency
        coherence = np.cos(self.phases - self.target_frequency)

        # Sort by coherence
        sorted_indices = np.argsort(coherence)[::-1]

        return sorted_indices[:top_k].tolist()


# Singleton instance
_kuramoto_field: Optional[HyperbolicKuramoto] = None


def get_kuramoto_field() -> HyperbolicKuramoto:
    """Get or create Kuramoto field singleton"""
    global _kuramoto_field
    if _kuramoto_field is None:
        _kuramoto_field = HyperbolicKuramoto(num_concepts=2000, target_frequency=1.618)
    return _kuramoto_field


def simulate_phase_locking(
    concept_activations: List[float], steps: int = 10
) -> Dict[str, Any]:
    """Convenience function to simulate phase-locking"""
    field = get_kuramoto_field()
    return field.phase_locking(concept_activations, steps)


def get_dominant_concepts(top_k: int = 10) -> List[int]:
    """Convenience function to get dominant concepts"""
    field = get_kuramoto_field()
    return field.get_dominant_concepts(top_k)
