"""
Production Curiosity Engine — Koopman-Based Manifold Discovery
==============================================================

This module replaces the deprecated prediction-error curiosity engine with a
Koopman-based curiosity system elevated from `pythia_mind`.

Design goals:
- Pure NumPy runtime path.
- No PyTorch dependency.
- Uses `neural_system.koopman_operator.KoopmanOperator` for manifold lifting,
  EDMD fitting, residual energy, and novelty scoring.
- Integrates gracefully with `UniversalKuramotoField` without requiring it.
- Never hard-fails the inference server on singular/unstable Koopman dynamics.
- Preserves backward-compatible methods used by older neural-system code:
  `CuriosityEngine(use_mock=False)`, `.predictor`, `compute_gradient()`,
  and `rank_curiosity()`.

Safety policy:
- If Koopman fitting or prediction becomes numerically unstable, log an explicit
  warning and return a safe baseline curiosity score of 1.0.
- If history is insufficient, return a neutral curiosity score of 0.5.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

try:
    from .koopman_operator import (
        BASELINE_CURIOSITY_SCORE,
        INSUFFICIENT_HISTORY_CURIOSITY_SCORE,
        KoopmanOperator,
    )
except ImportError:  # pragma: no cover - supports direct script execution
    from koopman_operator import (  # type: ignore
        BASELINE_CURIOSITY_SCORE,
        INSUFFICIENT_HISTORY_CURIOSITY_SCORE,
        KoopmanOperator,
    )

logger = logging.getLogger(__name__)


class CuriosityEngine:
    """
    Koopman-based curiosity engine for topological void discovery and novelty.

    The engine learns/uses a linearized observable manifold and treats high
    Koopman residuals, high distance from known manifold history, and large
    topological gaps as curiosity signals.

    Parameters
    ----------
    state_dim:
        Raw state dimensionality expected by the Koopman operator. Defaults to
        32 for CGA / multivector states.
    observables_dim:
        Lifted observable dimension. Defaults to 128, matching the elevated
        `pythia_mind` engine.
    lifting_type:
        Koopman observable lift type. `polynomial` is the production default
        because it is deterministic and pure NumPy/Numba accelerated in
        `koopman_operator.py`.
    baseline_curiosity:
        Score returned on manifold instability or numerical failure.
    history_limit:
        Maximum number of historical states retained in memory.
    kuramoto_field:
        Optional `UniversalKuramotoField`-like object. If provided, curiosity
        can rank monads directly from the field.
    use_mock:
        Deprecated compatibility parameter from the old prediction-error
        engine. It is intentionally ignored; no predictor is required.
    predictor:
        Deprecated compatibility slot. Preserved so older code can assign
        `engine.predictor = self.predictor` without breaking startup.
    """

    def __init__(
        self,
        state_dim: int = 32,
        observables_dim: int = 128,
        lifting_type: str = "polynomial",
        baseline_curiosity: float = BASELINE_CURIOSITY_SCORE,
        history_limit: int = 512,
        kuramoto_field: Optional[Any] = None,
        use_mock: Optional[bool] = None,
        predictor: Optional[Any] = None,
        **_: Any,
    ) -> None:
        # [F] Track calls to get_high_void_states for pipeline activation logging
        self._void_check_count: int = 0
        self._pipeline_activated: bool = False
        self.state_dim = int(state_dim)
        self.observables_dim = int(observables_dim)
        self.baseline_curiosity = float(baseline_curiosity)
        self.history_limit = int(history_limit)

        self.koopman = KoopmanOperator(
            state_dim=self.state_dim,
            lifted_dim=self.observables_dim,
            lifting_type=lifting_type,
            baseline_curiosity=self.baseline_curiosity,
        )

        self.kuramoto_field = kuramoto_field

        # Backward-compatible field expected by older neural-system startup.
        # The Koopman engine does not require or call this predictor.
        self.predictor = predictor

        self.state_history: List[np.ndarray] = []
        self.prediction_errors: List[float] = []

        # Tunables retained from the pythia_mind implementation.
        self.void_threshold = 0.5
        self.novelty_threshold = 0.3

        if use_mock is not None:
            logger.info(
                "CuriosityEngine(use_mock=%s) compatibility parameter ignored; "
                "Koopman production engine is active.",
                use_mock,
            )

        logger.info(
            "Koopman CuriosityEngine initialized: state_dim=%s, observables_dim=%s",
            self.state_dim,
            self.observables_dim,
        )

    # ------------------------------------------------------------------
    # Integration with UniversalKuramotoField
    # ------------------------------------------------------------------

    def bind_kuramoto_field(self, field: Any) -> None:
        """Attach a UniversalKuramotoField-like object for monad ranking."""
        self.kuramoto_field = field

    def _field_monads(self) -> Dict[str, Any]:
        """Return monads from a compatible field, or an empty dict."""
        field = self.kuramoto_field
        if field is None:
            return {}

        monads = getattr(field, "monads", None)
        if isinstance(monads, dict):
            return monads

        concepts = getattr(field, "concepts", None)
        if isinstance(concepts, dict):
            return concepts

        return {}

    def _extract_monad_vector(self, monad: Any) -> Optional[np.ndarray]:
        """
        Extract a vector/state from a ConceptMonad-like object.

        Preference order:
        1. `vector`
        2. `hv_signature`
        3. first `state_dim` scalar features from phase/frequency/energy/etc.
        """
        vector = getattr(monad, "vector", None)
        if vector is not None:
            return self._coerce_state(vector)

        hv_signature = getattr(monad, "hv_signature", None)
        if hv_signature is not None:
            return self._coerce_state(hv_signature)

        phase = float(getattr(monad, "phase", 0.0))
        frequency = float(
            getattr(monad, "natural_frequency", getattr(monad, "frequency", 1.0))
        )
        amplitude = float(getattr(monad, "amplitude", 1.0))
        energy = float(getattr(monad, "energy", 0.0))
        uncertainty = float(getattr(monad, "uncertainty", 0.0))

        state = np.zeros(self.state_dim, dtype=np.float64)
        base = np.array(
            [
                phase,
                np.sin(phase),
                np.cos(phase),
                frequency,
                amplitude,
                energy,
                uncertainty,
            ],
            dtype=np.float64,
        )
        state[: min(self.state_dim, base.size)] = base[: self.state_dim]
        return state

    def ingest_kuramoto_field(self) -> int:
        """
        Pull current monad vectors from the attached field into state history.

        Returns the number of states ingested.
        """
        monads = self._field_monads()
        count = 0

        for monad in monads.values():
            state = self._extract_monad_vector(monad)
            if state is None:
                continue
            self._append_history(state)
            count += 1

        return count

    # ------------------------------------------------------------------
    # State handling
    # ------------------------------------------------------------------

    def _coerce_state(self, state: Any) -> np.ndarray:
        """Convert arbitrary vector-like input into a finite `state_dim` vector."""
        try:
            arr = np.asarray(state, dtype=np.float64).reshape(-1)
        except Exception as exc:
            logger.warning(
                "Koopman manifold instability detected: state conversion failed: %s",
                exc,
            )
            return np.zeros(self.state_dim, dtype=np.float64)

        if arr.size >= self.state_dim:
            out = arr[: self.state_dim].copy()
        else:
            out = np.zeros(self.state_dim, dtype=np.float64)
            out[: arr.size] = arr

        if not np.all(np.isfinite(out)):
            logger.warning(
                "Koopman manifold instability detected: non-finite state values"
            )
            out = np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)

        return out

    def _coerce_state_space(self, state_space: Any) -> np.ndarray:
        """Convert list/array state space to shape `(T, state_dim)` safely."""
        try:
            arr = np.asarray(state_space, dtype=np.float64)
        except Exception as exc:
            logger.warning(
                "Koopman manifold instability detected: state-space conversion failed: %s",
                exc,
            )
            return np.zeros((0, self.state_dim), dtype=np.float64)

        if arr.ndim == 1:
            arr = arr.reshape(1, -1)

        if arr.ndim != 2:
            logger.warning(
                "Koopman manifold instability detected: invalid state-space shape %s",
                arr.shape,
            )
            return np.zeros((0, self.state_dim), dtype=np.float64)

        if arr.shape[1] > self.state_dim:
            arr = arr[:, : self.state_dim]
        elif arr.shape[1] < self.state_dim:
            padded = np.zeros((arr.shape[0], self.state_dim), dtype=np.float64)
            padded[:, : arr.shape[1]] = arr
            arr = padded

        if not np.all(np.isfinite(arr)):
            logger.warning(
                "Koopman manifold instability detected: non-finite state-space values"
            )
            arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)

        return arr

    def _append_history(self, state: Any) -> None:
        self.state_history.append(self._coerce_state(state))
        if len(self.state_history) > self.history_limit:
            del self.state_history[: len(self.state_history) - self.history_limit]

    def _history_matrix(self, limit: Optional[int] = None) -> np.ndarray:
        if not self.state_history:
            return np.zeros((0, self.state_dim), dtype=np.float64)

        hist = self.state_history[-limit:] if limit else self.state_history
        return np.asarray(hist, dtype=np.float64)

    def observe(self, state: Any, fit: bool = True) -> float:
        """
        Observe a state, append it to history, and return its curiosity score.
        """
        state_vec = self._coerce_state(state)
        score = self.compute_curiosity_score(state_vec, update_history=False)
        self._append_history(state_vec)

        if fit and len(self.state_history) >= 3:
            self._fit_safely(self._history_matrix())

        return score

    # ------------------------------------------------------------------
    # Koopman fitting and fallback handling
    # ------------------------------------------------------------------

    def _fit_safely(self, trajectory: np.ndarray) -> float:
        """
        Fit Koopman operator with explicit warning/fallback behavior.
        """
        if trajectory.shape[0] < 2:
            return INSUFFICIENT_HISTORY_CURIOSITY_SCORE

        try:
            return float(self.koopman.fit(trajectory))
        except Exception as exc:
            # KoopmanOperator itself should already be safe, but this extra
            # guard ensures the inference server never hard-fails here.
            logger.warning(
                "Koopman manifold instability detected: fit failed in curiosity engine: %s",
                exc,
            )
            return self.baseline_curiosity

    # ------------------------------------------------------------------
    # Void discovery and dream generation
    # ------------------------------------------------------------------

    def hunt_voids(self, state_space: Any) -> Dict[str, Any]:
        """
        Hunt for topological voids in a state-space sample.

        A void is represented as a large gap in lifted Koopman observable space.
        The method returns an empty result for insufficient data and never
        raises on singular/unstable manifolds.
        """
        states = self._coerce_state_space(state_space)

        if states.shape[0] < 2:
            return {
                "voids": [],
                "prediction_error": 0.0,
                "num_voids": 0,
                "avg_void_size": 0.0,
                "stability_score": float(self.koopman.stability_score()),
            }

        for state in states:
            self._append_history(state)

        if states.shape[0] >= 3:
            self._fit_safely(states)

        try:
            lifted = np.asarray(self.koopman.lift(states), dtype=np.float64)
            distances = self.koopman.pairwise_lifted_distances(states)

            if distances.size == 0:
                return {
                    "voids": [],
                    "prediction_error": 0.0,
                    "num_voids": 0,
                    "avg_void_size": 0.0,
                    "stability_score": float(self.koopman.stability_score()),
                }

            if not np.all(np.isfinite(distances)):
                raise FloatingPointError("non-finite lifted distances")

            threshold = float(np.percentile(distances, 75))
            voids: List[Dict[str, Any]] = []

            for i in range(states.shape[0]):
                for j in range(i + 1, states.shape[0]):
                    dist = float(np.linalg.norm(lifted[i] - lifted[j]))
                    if dist > threshold:
                        midpoint = 0.5 * (states[i] + states[j])
                        voids.append(
                            {
                                "location": midpoint.tolist(),
                                "size": dist,
                                "indices": [int(i), int(j)],
                            }
                        )

            prediction_error = float(np.mean(distances)) if distances.size else 0.0
            avg_void_size = (
                float(np.mean([void["size"] for void in voids])) if voids else 0.0
            )

            return {
                "voids": voids,
                "prediction_error": prediction_error,
                "num_voids": len(voids),
                "avg_void_size": avg_void_size,
                "stability_score": float(self.koopman.stability_score()),
            }

        except Exception as exc:
            logger.warning(
                "Koopman manifold instability detected during void hunt: %s",
                exc,
            )
            return {
                "voids": [],
                "prediction_error": self.baseline_curiosity,
                "num_voids": 0,
                "avg_void_size": 0.0,
                "stability_score": 0.0,
                "warning": "manifold_instability",
            }

    def dream_concepts(self, voids: Sequence[Dict[str, Any]]) -> List[str]:
        """
        Generate concept names from discovered topological voids.
        """
        concepts: List[str] = []

        for i, void in enumerate(voids):
            location = void.get("location", [])
            size = float(void.get("size", 0.0))

            try:
                prefix = "_".join(f"{float(x):.2f}" for x in location[:3])
            except Exception:
                prefix = "unknown"

            concepts.append(f"void_{i}_loc_{prefix}_size_{size:.2f}")

        return concepts

    # ------------------------------------------------------------------
    # Curiosity scoring
    # ------------------------------------------------------------------

    def compute_curiosity_score(
        self,
        state: Any,
        update_history: bool = False,
        fit_if_possible: bool = True,
    ) -> float:
        """
        Compute curiosity score for a state.

        High score means the state is novel, poorly predicted by the Koopman
        flow, or located near an unstable/empty region of the manifold.
        """
        state_vec = self._coerce_state(state)
        history = self._history_matrix(limit=100)

        if history.shape[0] < 2:
            score = INSUFFICIENT_HISTORY_CURIOSITY_SCORE
        else:
            try:
                score = self.koopman.curiosity_score(
                    state_vec,
                    history=history,
                    fit_if_possible=fit_if_possible,
                )
            except Exception as exc:
                logger.warning(
                    "Koopman manifold instability detected during curiosity score: %s",
                    exc,
                )
                score = self.baseline_curiosity

        if not np.isfinite(score):
            logger.warning(
                "Koopman manifold instability detected: non-finite curiosity score"
            )
            score = self.baseline_curiosity

        score = float(np.clip(score, 0.0, 1.0))

        if update_history:
            self._append_history(state_vec)

        return score

    def compute_gradient(self, concept_vec: Any, next_vec: Any) -> float:
        """
        Backward-compatible API replacing the deprecated prediction-error engine.

        Old behavior:
            predictor.predict_next(concept_vec) compared to `next_vec`.

        New behavior:
            Fit/advance Koopman manifold where possible and return residual
            energy between `concept_vec` and `next_vec`.
        """
        current = self._coerce_state(concept_vec)
        nxt = self._coerce_state(next_vec)

        if len(self.state_history) >= 2 and not self.koopman.is_fitted:
            self._fit_safely(self._history_matrix())

        if not self.koopman.is_fitted:
            trajectory = np.vstack([current, nxt])
            self._fit_safely(trajectory)

        try:
            residual = float(self.koopman.residual_energy(current, nxt))
        except Exception as exc:
            logger.warning(
                "Koopman manifold instability detected during gradient calculation: %s",
                exc,
            )
            residual = self.baseline_curiosity

        if not np.isfinite(residual):
            residual = self.baseline_curiosity

        # Normalize residual to [0, 1] while preserving high anomaly signal.
        score = residual / (1.0 + residual)
        score = float(np.clip(score, 0.0, 1.0))

        self.prediction_errors.append(score)
        if len(self.prediction_errors) > self.history_limit:
            del self.prediction_errors[
                : len(self.prediction_errors) - self.history_limit
            ]

        self._append_history(current)
        self._append_history(nxt)

        return score

    def rank_curiosity(self, candidates: Sequence[Any]) -> List[Any]:
        """
        Rank ConceptMonad-like objects by curiosity.

        Ranking combines:
        - Existing `uncertainty` field, if present.
        - Koopman novelty score from monad vectors/state.
        """
        scored: List[Tuple[float, Any]] = []

        for candidate in candidates:
            uncertainty = float(getattr(candidate, "uncertainty", 0.0))
            vector = self._extract_monad_vector(candidate)

            if vector is None:
                novelty = uncertainty
            else:
                novelty = self.compute_curiosity_score(vector, update_history=False)

            score = 0.5 * uncertainty + 0.5 * novelty
            if not np.isfinite(score):
                score = self.baseline_curiosity

            scored.append((float(score), candidate))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [candidate for _, candidate in scored]

    def rank_field_curiosity(self, top_k: Optional[int] = None) -> List[Any]:
        """
        Rank monads from the attached UniversalKuramotoField by curiosity.
        """
        monads = list(self._field_monads().values())
        ranked = self.rank_curiosity(monads)
        return ranked[:top_k] if top_k is not None else ranked

    # ------------------------------------------------------------------
    # BG3 / Self-Monad Weighted Curiosity (Task G)
    # ------------------------------------------------------------------

    def compute_resonance_potential(
        self,
        concept_cga: np.ndarray,
        self_monad_cga: np.ndarray,
    ) -> float:
        """
        Compute structural resonance between a concept CGA and the self monad CGA.

        Uses cosine similarity, normalised to [0, 1].
        High resonance means the concept is structurally close to the self monad —
        the system can recognise itself in it.

        Returns:
            float in [0, 1]: 0 = orthogonal (no resonance), 1 = perfect alignment.
        """
        c = np.asarray(concept_cga, dtype=np.float64).flatten()
        s = np.asarray(self_monad_cga, dtype=np.float64).flatten()
        norm_c = float(np.linalg.norm(c)) + 1e-8
        norm_s = float(np.linalg.norm(s)) + 1e-8
        # Align dims
        min_dim = min(c.size, s.size)
        resonance = float(np.dot(c[:min_dim], s[:min_dim]) / (norm_c * norm_s))
        return (resonance + 1.0) / 2.0  # map [-1, 1] → [0, 1]

    def compute_directed_curiosity(
        self,
        void_energy: float,
        resonance_potential: float,
    ) -> float:
        """
        Combine void energy and resonance potential into a directed curiosity score.

        Motivation:
          - High void + high resonance → maximum curiosity (unknown AND self-similar)
          - High void + low resonance  → moderate curiosity (pure novelty)
          - Low void + high resonance  → gentle pull (familiar territory, low novelty)

        Args:
            void_energy: Koopman void energy in [0, 1].
            resonance_potential: Self-monad resonance in [0, 1].

        Returns:
            Directed curiosity score in [0, 1].
        """
        directed = float(void_energy) * (0.6 + 0.4 * float(resonance_potential))
        return float(np.clip(directed, 0.0, 1.0))

    # ------------------------------------------------------------------
    # EB-JEPA Void-to-Dream Pipeline (Task H)
    # ------------------------------------------------------------------

    def get_high_void_states(
        self, threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Return top-N high-void states above ``threshold`` for dream-lab seeding.

        Each returned entry is tagged with metadata so the dream lab can use it
        as a seed for targeted simulation.

        The void energy of each historical state is estimated from its Koopman
        novelty score.  States are sorted descending by void energy.

        Args:
            threshold: Minimum void energy to include (default 0.7).

        Returns:
            List of dicts with keys 'void_energy', 'state', 'domain'.
        """
        self._void_check_count += 1

        if len(self.state_history) < 2:
            logger.debug(
                "[Curiosity] Pipeline dormant — Koopman needs at least 2 state "
                "observations (have %d). Void check #%d.",
                len(self.state_history), self._void_check_count,
            )
            return []

        results: List[Dict[str, Any]] = []
        history = self._history_matrix(limit=200)

        for i, state in enumerate(history):
            try:
                score = self.koopman.curiosity_score(
                    state,
                    history=history,
                    fit_if_possible=False,
                )
            except Exception:
                score = self.baseline_curiosity

            if not np.isfinite(score):
                score = self.baseline_curiosity

            score = float(np.clip(score, 0.0, 1.0))
            if score >= threshold:
                results.append(
                    {
                        "void_energy": score,
                        "state": state.copy(),
                        "domain": f"history_idx_{i}",
                    }
                )

        # Sort by void energy descending
        results.sort(key=lambda x: x["void_energy"], reverse=True)

        # [F] Pipeline activation logging
        if results and not self._pipeline_activated:
            self._pipeline_activated = True
            logger.info(
                "[Curiosity] Pipeline ACTIVATED — Koopman fitted=%s, history=%d states, "
                "first void above threshold=%.3f (check #%d)",
                self.koopman.is_fitted,
                len(self.state_history),
                results[0]["void_energy"],
                self._void_check_count,
            )
        elif not results and not self.koopman.is_fitted:
            needed = max(0, 10 - len(self.state_history))  # EDMD needs >=2, practical minimum ~10
            logger.debug(
                "[Curiosity] Pipeline dormant — Koopman needs %d more state observations "
                "before activating (threshold=%.2f, check #%d)",
                needed, threshold, self._void_check_count,
            )

        return results

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def get_state_summary(self) -> Dict[str, Any]:
        """Return non-fatal diagnostics for observability."""
        return {
            "history_length": len(self.state_history),
            "prediction_errors": len(self.prediction_errors),
            "koopman": self.koopman.to_dict(),
            "kuramoto_bound": self.kuramoto_field is not None,
            "baseline_curiosity": self.baseline_curiosity,
        }


# ---------------------------------------------------------------------------
# Singleton and convenience functions
# ---------------------------------------------------------------------------

_curiosity_engine: Optional[CuriosityEngine] = None


def get_curiosity_engine(
    kuramoto_field: Optional[Any] = None,
    state_dim: int = 32,
    observables_dim: int = 128,
) -> CuriosityEngine:
    """Get or create the production Koopman curiosity engine singleton."""
    global _curiosity_engine

    if _curiosity_engine is None:
        _curiosity_engine = CuriosityEngine(
            state_dim=state_dim,
            observables_dim=observables_dim,
            kuramoto_field=kuramoto_field,
        )
    elif kuramoto_field is not None:
        _curiosity_engine.bind_kuramoto_field(kuramoto_field)

    return _curiosity_engine


def hunt_for_voids(state_space: List[List[float]]) -> Dict[str, Any]:
    """Convenience wrapper for topological void discovery."""
    engine = get_curiosity_engine()
    return engine.hunt_voids(state_space)


def dream_new_concepts(voids: List[Dict[str, Any]]) -> List[str]:
    """Convenience wrapper for dream concept generation."""
    engine = get_curiosity_engine()
    return engine.dream_concepts(voids)


def compute_curiosity(state: List[float]) -> float:
    """Convenience wrapper for Koopman curiosity scoring."""
    engine = get_curiosity_engine()
    return engine.compute_curiosity_score(state, update_history=True)


def bind_kuramoto_field(field: Any) -> CuriosityEngine:
    """Bind the global curiosity engine to a UniversalKuramotoField."""
    engine = get_curiosity_engine(kuramoto_field=field)
    return engine
