"""
Curiosity Engine + Koopman Operator

Part of Stage 3: Phenomenological Mind
Linearizes dynamics to hunt for topological voids and dream new concepts
"""

import numpy as np
from typing import List, Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class KoopmanOperator:
    """
    Koopman Operator for linearizing nonlinear dynamics

    Lifts state space to observable space where dynamics become linear
    Allows prediction and void detection in linearized space
    """

    def __init__(self, observables_dim: int = 128):
        self.observables_dim = observables_dim

        # Dictionary of observables (polynomial features)
        self.observables = []

        logger.info(
            f"Koopman Operator initialized: {observables_dim}-dim observable space"
        )

    def lift(self, state: np.ndarray) -> np.ndarray:
        """
        Lift state to observable space

        Args:
            state: 32-dim multivector state

        Returns:
            Observable space representation
        """
        lifted = []

        # Add original state
        lifted.extend(state)

        # Add polynomial features
        for i in range(len(state)):
            for j in range(i, len(state)):
                lifted.append(state[i] * state[j])

        # Add trigonometric features
        for i in range(min(4, len(state))):
            lifted.append(np.sin(state[i]))
            lifted.append(np.cos(state[i]))

        # Pad or truncate to target dimension
        lifted = np.array(lifted[: self.observables_dim], dtype=np.float32)

        if len(lifted) < self.observables_dim:
            lifted = np.pad(lifted, (0, self.observables_dim - len(lifted)))

        return lifted


class CuriosityEngine:
    """
    Curiosity Engine for discovering topological voids

    Uses Koopman operator to linearize dynamics and hunt for:
    - Topological voids (empty regions in state space)
    - Novel concepts (regions with high prediction error)
    """

    def __init__(self):
        self.koopman = KoopmanOperator(observables_dim=128)
        self.state_history = []
        self.prediction_errors = []

        # Void detection parameters
        self.void_threshold = 0.5
        self.novelty_threshold = 0.3

        logger.info("CuriosityEngine initialized")

    def hunt_voids(self, state_space: np.ndarray) -> Dict[str, Any]:
        """
        Hunt for topological voids in state space

        Args:
            state_space: Array of 32-dim states

        Returns:
            Void locations and characteristics
        """
        if len(state_space) < 2:
            return {"voids": [], "prediction_error": 0.0}

        # Lift all states to observable space
        lifted_states = np.array([self.koopman.lift(s) for s in state_space])

        # Compute distances between lifted states
        distances = []
        for i in range(len(lifted_states)):
            for j in range(i + 1, len(lifted_states)):
                dist = np.linalg.norm(lifted_states[i] - lifted_states[j])
                distances.append(dist)

        distances = np.array(distances)

        # Detect voids (large gaps in state space)
        voids = []
        void_threshold = np.percentile(distances, 75)  # Top 25% gaps

        for i in range(len(lifted_states)):
            for j in range(i + 1, len(lifted_states)):
                dist = np.linalg.norm(lifted_states[i] - lifted_states[j])
                if dist > void_threshold:
                    # Midpoint of void
                    midpoint = 0.5 * (state_space[i] + state_space[j])
                    voids.append(
                        {
                            "location": midpoint.tolist(),
                            "size": float(dist),
                            "indices": [i, j],
                        }
                    )

        # Compute prediction error (curiosity signal)
        prediction_error = float(np.mean(distances)) if len(distances) > 0 else 0.0

        return {
            "voids": voids,
            "prediction_error": prediction_error,
            "num_voids": len(voids),
            "avg_void_size": float(np.mean([v["size"] for v in voids]))
            if voids
            else 0.0,
        }

    def dream_concepts(self, voids: List[Dict[str, Any]]) -> List[str]:
        """
        Generate new concepts from discovered voids

        Args:
            voids: List of void locations

        Returns:
            List of concept names
        """
        concepts = []

        for i, void in enumerate(voids):
            # Generate concept name based on void characteristics
            location = void["location"]
            size = void["size"]

            # Create descriptive concept name
            concept = f"void_{i}_loc_{'_'.join(f'{x:.2f}' for x in location[:3])}_size_{size:.2f}"
            concepts.append(concept)

        return concepts

    def compute_curiosity_score(self, state: np.ndarray) -> float:
        """
        Compute curiosity score for a state

        High curiosity = state is novel or in a void region
        """
        if len(self.state_history) < 10:
            return 0.5

        # Compare to history
        lifted_state = self.koopman.lift(state)

        distances = []
        for hist_state in self.state_history[-100:]:  # Last 100 states
            lifted_hist = self.koopman.lift(hist_state)
            dist = np.linalg.norm(lifted_state - lifted_hist)
            distances.append(dist)

        # High distance = high curiosity
        curiosity = float(np.mean(distances)) if distances else 0.5

        return min(curiosity, 1.0)


# Singleton instance
_curiosity_engine: Optional[CuriosityEngine] = None


def get_curiosity_engine() -> CuriosityEngine:
    """Get or create Curiosity engine singleton"""
    global _curiosity_engine
    if _curiosity_engine is None:
        _curiosity_engine = CuriosityEngine()
    return _curiosity_engine


def hunt_for_voids(state_space: List[List[float]]) -> Dict[str, Any]:
    """Convenience function to hunt for voids"""
    engine = get_curiosity_engine()
    state_array = np.array(state_space)
    return engine.hunt_voids(state_array)


def dream_new_concepts(voids: List[Dict[str, Any]]) -> List[str]:
    """Convenience function to dream new concepts"""
    engine = get_curiosity_engine()
    return engine.dream_concepts(voids)


def compute_curiosity(state: List[float]) -> float:
    """Convenience function to compute curiosity score"""
    engine = get_curiosity_engine()
    return engine.compute_curiosity_score(np.array(state))
