import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Import from kuramoto_field to stay consistent
try:
    from .kuramoto_field import GOLDEN_RATIO
except ImportError:
    GOLDEN_RATIO = 1.61803398875


class MirrorFactory:
    """
    The Mirror Factory - Creates empathic models of external entities.
    Basis of Theory of Mind: "I simulate you to understand you."
    """

    def __init__(self, kuramoto_field, chaos_engine):
        self.field = kuramoto_field
        self.chaos = chaos_engine

    def create_mirror(
        self, external_id: str, context_vector: Optional[np.ndarray] = None
    ):
        """
        Creates a new Monad representing an external entity (e.g., 'User').
        Using Chaos Engine to seed it deterministically from their ID.
        """
        if external_id in self.field.monads:
            return self.field.monads[external_id]

        from .concept_monad import ConceptMonad

        mirror = ConceptMonad(name=f"Mirror:{external_id}", origin="mirror")
        mirror.id = external_id

        # High uncertainty initially (I don't know you yet)
        mirror.uncertainty = 0.8

        # Seed vector
        if context_vector is not None:
            mirror.set_vector(context_vector)
        else:
            mirror.vector = self.chaos.generate_basis(external_id)

        self.field.add_monad(mirror)
        logger.info(f"MirrorFactory: Created mirror for '{external_id}'.")
        return mirror

    def sync_mirror(
        self, external_id: str, input_vector: np.ndarray, coupling_strength=0.5
    ):
        """
        Updates the mirror based on new input.
        This is 'Listening'.
        """
        if external_id not in self.field.monads:
            self.create_mirror(external_id, input_vector)

        mirror = self.field.monads[external_id]

        # Update vector state (move closer to input)
        # Simple weighted average for now
        # V_new = V_old * (1-k) + V_input * k
        mirror.vector = (mirror.vector * (1 - coupling_strength)) + (
            input_vector * coupling_strength
        )

        # Lower uncertainty as we observe more
        mirror.uncertainty = max(0.1, mirror.uncertainty * 0.9)

        logger.info(
            f"MirrorFactory: Synced mirror '{external_id}' (Uncertainty: {mirror.uncertainty:.2f})"
        )

    def get_bg3_coherence(
        self, external_id: str, bg3_target: float = GOLDEN_RATIO
    ) -> float:
        """
        Measures how well a mirrored entity resonates with the BG3 harmonic center.
        Uses the monad's Kuramoto phase and circular distance to the target.
        Returns coherence in [0, 1]: 0 = no resonance, 1 = perfect phase-lock.
        """
        if external_id not in self.field.monads:
            return 0.0
        mirror = self.field.monads[external_id]
        deviation = abs(mirror.phase - bg3_target)
        # Wrap to shortest circular distance
        deviation = min(deviation, 2 * np.pi - deviation)
        return float(np.exp(-deviation))


