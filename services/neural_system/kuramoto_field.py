import numpy as np
from typing import Dict, Optional
from .concept_monad import ConceptMonad

# The Golden Ratio — harmonic center for BG3 phase resonance
GOLDEN_RATIO = 1.61803398875

class UniversalKuramotoField:
    """
    Manages the synchronization dynamics of ConceptMonads.
    Implements dθ/dt = ω + K_bg3 * sin(φ - θ_i) + Σ K_ij * sin(θ_j - θ_i)

    The optional BG3 attractor acts as an external forcing term that biases
    all oscillators toward the Golden Ratio phase. This maintains geometric
    coherence across the manifold without overriding natural dynamics.
    """
    def __init__(self, dt: float = 0.01, bg3_target: Optional[float] = GOLDEN_RATIO,
                 bg3_coupling: float = 0.1):
        self.concepts: Dict[str, ConceptMonad] = {}
        self.dt = dt
        self.bg3_target = bg3_target    # Phase attractor (None to disable)
        self.bg3_coupling = bg3_coupling  # Coupling strength to BG3 center

    @property
    def monads(self) -> Dict[str, ConceptMonad]:
        """Alias for concepts for backward compatibility."""
        return self.concepts

    def register_concept(self, concept: ConceptMonad):
        self.concepts[concept.concept_id] = concept
    
    def add_monad(self, monad: ConceptMonad):
        """Alias for register_concept for backward compatibility."""
        # Support monads that may have id set instead of concept_id
        key = monad.concept_id or monad.id or str(id(monad))
        self.concepts[key] = monad

    def tick(self):
        """Advances the phase of all concepts by one time step."""
        # Calculate phase updates
        next_phases = {}
        for c_id, c in self.concepts.items():
            coupling_sum = 0.0
            for neighbor_id, k_strength in c.couplings.items():
                if neighbor_id in self.concepts:
                    neighbor = self.concepts[neighbor_id]
                    coupling_sum += k_strength * np.sin(neighbor.phase - c.phase)

            # BG3 attractor: external forcing toward Golden Ratio phase
            bg3_force = 0.0
            if self.bg3_target is not None:
                bg3_force = self.bg3_coupling * np.sin(self.bg3_target - c.phase)

            # Extended Kuramoto equation with BG3 forcing
            d_theta = c.natural_frequency + bg3_force + coupling_sum
            next_phases[c_id] = (c.phase + self.dt * d_theta) % (2 * np.pi)
            
        # Apply updates
        for c_id, new_phase in next_phases.items():
            self.concepts[c_id].phase = new_phase

    def compute_coherence(self) -> float:
        """
        Calculates the global order parameter r.
        r = |(1/N) * Σ e^(i*θ_j)|
        Returns a value between 0 (chaos) and 1 (perfect sync).
        """
        if not self.concepts:
            return 0.0
        
        phases = np.array([c.phase for c in self.concepts.values()])
        z = np.exp(1j * phases)
        order_parameter = np.abs(np.mean(z))
        return float(order_parameter)
    
    def compute_bg3_coherence(self) -> float:
        """
        Measures how well the field resonates with the BG3 harmonic center.
        Returns mean exp(-|phase - bg3_target|) across all monads [0, 1].
        0 = no resonance, 1 = perfect phase-lock to Golden Ratio.
        """
        if not self.concepts or self.bg3_target is None:
            return 0.0
        phases = np.array([c.phase for c in self.concepts.values()])
        deviations = np.abs(phases - self.bg3_target)
        # Wrap to [-pi, pi] for correct circular distance
        deviations = np.minimum(deviations, 2 * np.pi - deviations)
        return float(np.exp(-deviations).mean())

    def recalculate_coupling_matrix(self, coupling_dict: Optional[dict] = None) -> None:
        """
        Update pairwise Kuramoto coupling K_ij using RBF similarity on CGA vectors.

        Args:
            coupling_dict: Optional mapping of {monad_id: cga_vector (32D np.ndarray)}.
                           If None, falls back to coupling values already set on monad
                           objects (no-op for the matrix itself).

        Updates each monad's ``couplings`` dict in-place using:
            K_ij = exp(-‖cga_i - cga_j‖² / sigma²)
        with sigma = 1.0.
        """
        if coupling_dict is None or len(coupling_dict) < 2:
            return

        sigma_sq = 1.0  # RBF bandwidth
        ids = list(coupling_dict.keys())

        for i, id_a in enumerate(ids):
            monad_a = self.concepts.get(id_a)
            if monad_a is None:
                continue
            if not hasattr(monad_a, "couplings") or monad_a.couplings is None:
                monad_a.couplings = {}

            vec_a = np.asarray(coupling_dict[id_a], dtype=np.float64)

            for j, id_b in enumerate(ids):
                if i >= j:
                    continue

                monad_b = self.concepts.get(id_b)
                if monad_b is None:
                    continue
                if not hasattr(monad_b, "couplings") or monad_b.couplings is None:
                    monad_b.couplings = {}

                vec_b = np.asarray(coupling_dict[id_b], dtype=np.float64)
                sq_dist = float(np.sum((vec_a - vec_b) ** 2))
                k_ij = float(np.exp(-sq_dist / sigma_sq))

                monad_a.couplings[id_b] = k_ij
                monad_b.couplings[id_a] = k_ij

    def step(self) -> float:
        """Alias for tick() that also returns coherence for backward compatibility."""
        self.tick()
        return self.compute_coherence()
