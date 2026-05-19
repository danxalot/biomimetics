"""
Versor Sequence Engine

Part of Stage 2: Physical Engine
Learns temporal flow of geometric sequences from kinematic datasets
"""

import numpy as np
from typing import List, Dict, Any, Optional
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class KinematicDataset:
    name: str
    description: str
    sequence_length: int
    features: int


class VersorSequenceEngine:
    """
    Learns temporal dynamics of geometric sequences using versor algebra

    Processes sequences of 32-dim multivectors and learns:
    - Temporal evolution patterns
    - Geometric constraints
    - Kinematic relationships
    """

    def __init__(self):
        # Define kinematic datasets
        self.datasets = {
            "pendulums": KinematicDataset(
                name="pendulums",
                description="Oscillatory motion patterns",
                sequence_length=100,
                features=32,
            ),
            "shockwaves": KinematicDataset(
                name="shockwaves",
                description="Wave propagation patterns",
                sequence_length=50,
                features=32,
            ),
            "emf": KinematicDataset(
                name="emf",
                description="Electromagnetic field patterns",
                sequence_length=75,
                features=32,
            ),
            "gravitational": KinematicDataset(
                name="gravitational",
                description="Gravitational field patterns",
                sequence_length=60,
                features=32,
            ),
            "fluid_dynamics": KinematicDataset(
                name="fluid_dynamics",
                description="Fluid flow patterns",
                sequence_length=80,
                features=32,
            ),
            "thermal": KinematicDataset(
                name="thermal",
                description="Heat diffusion patterns",
                sequence_length=70,
                features=32,
            ),
        }

        # Temporal models for each dataset
        self.temporal_models = {}

        # Initialize simple temporal models (LSTM-like behavior)
        for name in self.datasets:
            self.temporal_models[name] = {
                "weights": np.random.randn(32, 32) * 0.01,
                "hidden_state": np.zeros(32),
                "memory": [],
            }

        logger.info(
            f"Versor Sequence Engine initialized with {len(self.datasets)} kinematic datasets"
        )

    def process_sequence(
        self, multivector_sequence: List[List[float]], dataset_name: str = "pendulums"
    ) -> Dict[str, Any]:
        """
        Process a sequence of 32-dim multivectors

        Args:
            multivector_sequence: List of 32-dim multivectors
            dataset_name: Which kinematic dataset to use

        Returns:
            Dictionary with temporal features and predictions
        """
        if dataset_name not in self.datasets:
            raise ValueError(f"Unknown dataset: {dataset_name}")

        sequence_array = np.array(multivector_sequence)

        # Validate sequence
        if sequence_array.shape[1] != 32:
            raise ValueError(
                f"Expected 32-dim multivectors, got {sequence_array.shape[1]}"
            )

        # Get temporal model
        model = self.temporal_models[dataset_name]

        # Process sequence through temporal model
        temporal_features = []
        hidden_states = []

        for multivector in sequence_array:
            # Update hidden state (simple RNN-like update)
            hidden = model["hidden_state"]
            update = multivector @ model["weights"]
            new_hidden = 0.9 * hidden + 0.1 * update

            # Store features
            temporal_features.append(new_hidden.copy())
            hidden_states.append(new_hidden)

            # Update model state
            model["hidden_state"] = new_hidden
            model["memory"].append(new_hidden.copy())

            # Keep memory bounded
            if len(model["memory"]) > 1000:
                model["memory"] = model["memory"][-1000:]

        # Compute temporal statistics
        features_array = np.array(temporal_features)

        result = {
            "dataset": dataset_name,
            "sequence_length": len(multivector_sequence),
            "temporal_features": features_array.tolist(),
            "final_state": hidden_states[-1].tolist(),
            "velocity": self._compute_velocity(features_array),
            "acceleration": self._compute_acceleration(features_array),
            "stability": self._compute_stability(features_array),
        }

        return result

    def _compute_velocity(self, features: np.ndarray) -> float:
        """Compute velocity from temporal features"""
        if len(features) < 2:
            return 0.0
        return float(np.mean(np.linalg.norm(np.diff(features, axis=0), axis=1)))

    def _compute_acceleration(self, features: np.ndarray) -> float:
        """Compute acceleration from temporal features"""
        if len(features) < 3:
            return 0.0
        velocity = np.linalg.norm(np.diff(features, axis=0), axis=1)
        acceleration = np.diff(velocity)
        return float(np.mean(np.abs(acceleration)))

    def _compute_stability(self, features: np.ndarray) -> float:
        """Compute stability metric (lower is more stable)"""
        return float(np.std(features))

    def predict_next(
        self, recent_sequence: List[List[float]], dataset_name: str, steps: int = 1
    ) -> List[List[float]]:
        """Predict future states in the sequence"""
        if dataset_name not in self.datasets:
            raise ValueError(f"Unknown dataset: {dataset_name}")

        model = self.temporal_models[dataset_name]
        predictions = []

        # Start from last known state
        current_state = np.array(recent_sequence[-1])

        for _ in range(steps):
            # Predict next state
            update = current_state @ model["weights"]
            next_state = 0.9 * current_state + 0.1 * update

            predictions.append(next_state.tolist())
            current_state = next_state

        return predictions


# Singleton instance
_versor_engine: Optional[VersorSequenceEngine] = None


def get_versor_engine() -> VersorSequenceEngine:
    """Get or create Versor engine singleton"""
    global _versor_engine
    if _versor_engine is None:
        _versor_engine = VersorSequenceEngine()
    return _versor_engine


def process_multivector_sequence(
    sequence: List[List[float]], dataset_name: str = "pendulums"
) -> Dict[str, Any]:
    """Convenience function to process a multivector sequence"""
    engine = get_versor_engine()
    return engine.process_sequence(sequence, dataset_name)


def predict_sequence_future(
    recent_sequence: List[List[float]], dataset_name: str, steps: int = 1
) -> List[List[float]]:
    """Convenience function to predict future states"""
    engine = get_versor_engine()
    return engine.predict_next(recent_sequence, dataset_name, steps)
