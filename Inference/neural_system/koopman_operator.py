"""
Koopman Operator: Pure NumPy / Optional Numba Implementation
===========================================================

Production Koopman dynamics module for ARCA's neural system.

This implementation is intentionally free of PyTorch and other tensor-runtime
dependencies. Heavy feature-lifting and distance loops are accelerated with
Numba when available, while all linear algebra is delegated to NumPy/LAPACK.

Runtime safety policy
---------------------
The neural inference server must not crash because the learned manifold becomes
ill-conditioned, singular, non-finite, or otherwise unstable. When Koopman
fitting/prediction encounters numerical instability, this module logs an
explicit warning and returns safe baseline values.

Baseline fallbacks:
    - curiosity/anomaly score: 1.0
    - insufficient-history curiosity: 0.5
    - stability score after failed spectral analysis: 0.0
    - predictions before fitting: repeated current state
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Numba acceleration
# ---------------------------------------------------------------------------

try:
    _numba = importlib.import_module("numba")
    jit = _numba.jit
    NUMBA_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only when numba is absent
    NUMBA_AVAILABLE = False

    def jit(*jit_args, **jit_kwargs):  # type: ignore
        """Compatibility no-op for environments without Numba."""
        if jit_args and callable(jit_args[0]) and len(jit_args) == 1 and not jit_kwargs:
            return jit_args[0]

        def decorator(func):
            return func

        return decorator


BASELINE_CURIOSITY_SCORE = 1.0
INSUFFICIENT_HISTORY_CURIOSITY_SCORE = 0.5
_EPS = 1e-12


# ---------------------------------------------------------------------------
# JIT-accelerated numerical primitives
# ---------------------------------------------------------------------------


@jit(nopython=True, cache=True)
def _is_finite_matrix(x: np.ndarray) -> bool:
    for i in range(x.shape[0]):
        for j in range(x.shape[1]):
            if not np.isfinite(x[i, j]):
                return False
    return True


@jit(nopython=True, cache=True)
def _is_finite_vector(x: np.ndarray) -> bool:
    for i in range(x.shape[0]):
        if not np.isfinite(x[i]):
            return False
    return True


@jit(nopython=True, cache=True)
def _rbf_lift_batch(
    x: np.ndarray,
    centers: np.ndarray,
    widths: np.ndarray,
    out: np.ndarray,
) -> None:
    """RBF observable lift: exp(-||x-c||² / (2σ²))."""
    n_samples = x.shape[0]
    lifted_dim = centers.shape[0]
    state_dim = x.shape[1]

    for n in range(n_samples):
        for k in range(lifted_dim):
            dist_sq = 0.0
            for d in range(state_dim):
                diff = x[n, d] - centers[k, d]
                dist_sq += diff * diff

            width = widths[k]
            denom = 2.0 * width * width
            if denom <= _EPS:
                denom = _EPS

            out[n, k] = np.exp(-dist_sq / denom)


@jit(nopython=True, cache=True)
def _random_fourier_lift_batch(
    x: np.ndarray,
    weights: np.ndarray,
    bias: np.ndarray,
    out: np.ndarray,
) -> None:
    """Random Fourier feature lift using cos/sin pairs."""
    n_samples = x.shape[0]
    half_dim = weights.shape[0]
    state_dim = x.shape[1]
    lifted_dim = out.shape[1]

    for n in range(n_samples):
        for k in range(half_dim):
            acc = bias[k]
            for d in range(state_dim):
                acc += x[n, d] * weights[k, d]

            cos_idx = k
            sin_idx = k + half_dim

            if cos_idx < lifted_dim:
                out[n, cos_idx] = np.cos(acc)
            if sin_idx < lifted_dim:
                out[n, sin_idx] = np.sin(acc)


@jit(nopython=True, cache=True)
def _observable_lift_batch(
    x: np.ndarray,
    feature_kind: np.ndarray,
    feature_i: np.ndarray,
    feature_j: np.ndarray,
    out: np.ndarray,
) -> None:
    """
    Polynomial/trigonometric observable lift.

    feature_kind:
        0 = constant 1
        1 = linear x[i]
        2 = quadratic x[i] * x[j]
        3 = sin(x[i])
        4 = cos(x[i])
    """
    n_samples = x.shape[0]
    n_features = feature_kind.shape[0]

    for n in range(n_samples):
        for k in range(n_features):
            kind = feature_kind[k]
            i = feature_i[k]
            j = feature_j[k]

            if kind == 0:
                out[n, k] = 1.0
            elif kind == 1:
                out[n, k] = x[n, i]
            elif kind == 2:
                out[n, k] = x[n, i] * x[n, j]
            elif kind == 3:
                out[n, k] = np.sin(x[n, i])
            elif kind == 4:
                out[n, k] = np.cos(x[n, i])
            else:
                out[n, k] = 0.0


@jit(nopython=True, cache=True)
def _pairwise_distances_upper(x: np.ndarray) -> np.ndarray:
    """Return upper-triangle pairwise Euclidean distances for rows of x."""
    n = x.shape[0]
    dim = x.shape[1]
    total = n * (n - 1) // 2
    distances = np.zeros(total, dtype=np.float64)

    idx = 0
    for i in range(n):
        for j in range(i + 1, n):
            acc = 0.0
            for d in range(dim):
                diff = x[i, d] - x[j, d]
                acc += diff * diff
            distances[idx] = np.sqrt(acc)
            idx += 1

    return distances


@jit(nopython=True, cache=True)
def _rowwise_l2_mean(a: np.ndarray, b: np.ndarray) -> float:
    """Mean row-wise L2 distance between two equally shaped matrices."""
    n = a.shape[0]
    dim = a.shape[1]

    if n == 0:
        return 0.0

    total = 0.0
    for i in range(n):
        acc = 0.0
        for d in range(dim):
            diff = a[i, d] - b[i, d]
            acc += diff * diff
        total += np.sqrt(acc)

    return total / n


@jit(nopython=True, cache=True)
def _vector_l2(a: np.ndarray, b: np.ndarray) -> float:
    acc = 0.0
    for i in range(a.shape[0]):
        diff = a[i] - b[i]
        acc += diff * diff
    return np.sqrt(acc)


@jit(nopython=True, cache=True)
def _mean_distance_to_history(query: np.ndarray, history: np.ndarray) -> float:
    """Mean L2 distance from query vector to rows of history."""
    n = history.shape[0]
    dim = history.shape[1]

    if n == 0:
        return INSUFFICIENT_HISTORY_CURIOSITY_SCORE

    total = 0.0
    for i in range(n):
        acc = 0.0
        for d in range(dim):
            diff = query[d] - history[i, d]
            acc += diff * diff
        total += np.sqrt(acc)

    return total / n


# ---------------------------------------------------------------------------
# Koopman modes
# ---------------------------------------------------------------------------


@dataclass
class KoopmanMode:
    """A single Koopman mode from the spectral decomposition of K."""

    eigenvalue: complex
    eigenfunction: np.ndarray
    growth_rate: float
    frequency: float

    @property
    def is_stable(self) -> bool:
        """A discrete Koopman mode is stable if |λ| <= 1."""
        return abs(self.eigenvalue) <= 1.0 + 1e-6

    @property
    def is_oscillatory(self) -> bool:
        """A Koopman mode is oscillatory if λ has non-trivial phase."""
        return abs(self.eigenvalue.imag) > 1e-6


# ---------------------------------------------------------------------------
# Koopman operator
# ---------------------------------------------------------------------------


class KoopmanOperator:
    """
    Extended Dynamic Mode Decomposition (EDMD) Koopman operator.

    Parameters
    ----------
    state_dim:
        Dimension of the raw state space.
    lifted_dim:
        Dimension of the observable/lifted space.
    lifting_type:
        One of:
            - "polynomial"
            - "rbf"
            - "random_fourier"
            - "observable" (alias of "polynomial")
    observables_dim:
        Compatibility alias used by older curiosity-engine code. If provided,
        it overrides `lifted_dim`.
    baseline_curiosity:
        Score returned when manifold instability is detected.
    """

    def __init__(
        self,
        state_dim: int = 32,
        lifted_dim: int = 128,
        lifting_type: str = "polynomial",
        observables_dim: Optional[int] = None,
        baseline_curiosity: float = BASELINE_CURIOSITY_SCORE,
        seed: int = 42,
    ):
        if observables_dim is not None:
            lifted_dim = observables_dim

        if lifting_type == "observable":
            lifting_type = "polynomial"

        self.state_dim = int(state_dim)
        self.lifted_dim = int(lifted_dim)
        self.observables_dim = self.lifted_dim
        self.lifting_type = lifting_type
        self.baseline_curiosity = float(baseline_curiosity)
        self.seed = int(seed)

        self.K: Optional[np.ndarray] = None
        self.eigenvalues: Optional[np.ndarray] = None
        self.eigenvectors: Optional[np.ndarray] = None
        self.modes: List[KoopmanMode] = []

        self.fitted = False
        self.manifold_unstable = False
        self.reconstruction_error = self.baseline_curiosity
        self.last_warning: Optional[str] = None

        self._rng = np.random.default_rng(self.seed)
        self._init_lifting_params()

        logger.info(
            "KoopmanOperator initialized: %sD → %sD (%s, numba=%s)",
            self.state_dim,
            self.lifted_dim,
            self.lifting_type,
            NUMBA_AVAILABLE,
        )

    # ------------------------------------------------------------------
    # Compatibility aliases
    # ------------------------------------------------------------------

    @property
    def is_fitted(self) -> bool:
        return self.fitted

    @property
    def lift_type(self) -> str:
        return self.lifting_type

    @property
    def n_components(self) -> int:
        return self.lifted_dim

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _warn_instability(self, reason: str) -> None:
        self.last_warning = reason
        self.manifold_unstable = True
        logger.warning("Koopman manifold instability detected: %s", reason)

    def _init_lifting_params(self) -> None:
        if self.lifting_type == "rbf":
            self.rbf_centers = self._rng.normal(
                loc=0.0,
                scale=1.0,
                size=(self.lifted_dim, self.state_dim),
            ).astype(np.float64)
            self.rbf_widths = np.full(self.lifted_dim, 0.5, dtype=np.float64)

        elif self.lifting_type == "random_fourier":
            half_dim = max(1, (self.lifted_dim + 1) // 2)
            self.rff_weights = self._rng.normal(
                loc=0.0,
                scale=1.0,
                size=(half_dim, self.state_dim),
            ).astype(np.float64)
            self.rff_bias = self._rng.uniform(
                0.0,
                2.0 * np.pi,
                size=half_dim,
            ).astype(np.float64)

        elif self.lifting_type == "polynomial":
            self.feature_kind, self.feature_i, self.feature_j = (
                self._build_observable_schema()
            )

        else:
            self._warn_instability(
                f"unknown lifting_type={self.lifting_type!r}; using polynomial"
            )
            self.lifting_type = "polynomial"
            self.feature_kind, self.feature_i, self.feature_j = (
                self._build_observable_schema()
            )

    def _build_observable_schema(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        kinds: List[int] = []
        idx_i: List[int] = []
        idx_j: List[int] = []

        def add(kind: int, i: int = 0, j: int = 0) -> None:
            if len(kinds) < self.lifted_dim:
                kinds.append(kind)
                idx_i.append(i)
                idx_j.append(j)

        # Bias term stabilizes EDMD in low-data regimes.
        add(0, 0, 0)

        # Linear state terms.
        for i in range(self.state_dim):
            add(1, i, i)

        # Quadratic observables.
        for i in range(self.state_dim):
            for j in range(i, self.state_dim):
                add(2, i, j)
                if len(kinds) >= self.lifted_dim:
                    break
            if len(kinds) >= self.lifted_dim:
                break

        # Low-frequency trigonometric terms.
        for i in range(min(8, self.state_dim)):
            add(3, i, i)
            add(4, i, i)

        # Pad remaining slots with zeros represented as invalid kinds.
        while len(kinds) < self.lifted_dim:
            kinds.append(-1)
            idx_i.append(0)
            idx_j.append(0)

        return (
            np.asarray(kinds, dtype=np.int64),
            np.asarray(idx_i, dtype=np.int64),
            np.asarray(idx_j, dtype=np.int64),
        )

    # ------------------------------------------------------------------
    # Data validation
    # ------------------------------------------------------------------

    def _as_state_matrix(self, x: np.ndarray) -> Tuple[np.ndarray, bool]:
        arr = np.asarray(x, dtype=np.float64)
        was_1d = arr.ndim == 1

        if was_1d:
            arr = arr.reshape(1, -1)

        if arr.ndim != 2:
            self._warn_instability(f"expected 1D or 2D state input, got {arr.ndim}D")
            arr = np.zeros((1, self.state_dim), dtype=np.float64)
            return arr, True

        if arr.shape[1] != self.state_dim:
            if arr.shape[1] > self.state_dim:
                arr = arr[:, : self.state_dim]
                logger.warning(
                    "Koopman input dimension truncated from %s to %s",
                    x.shape[-1] if hasattr(x, "shape") else "unknown",
                    self.state_dim,
                )
            else:
                padded = np.zeros((arr.shape[0], self.state_dim), dtype=np.float64)
                padded[:, : arr.shape[1]] = arr
                arr = padded
                logger.warning(
                    "Koopman input dimension padded to %s",
                    self.state_dim,
                )

        if not _is_finite_matrix(arr):
            self._warn_instability("non-finite values in state input")
            arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)

        return arr, was_1d

    # ------------------------------------------------------------------
    # Lifting
    # ------------------------------------------------------------------

    def lift(self, x: np.ndarray) -> np.ndarray:
        """
        Lift raw states into Koopman observable space.

        Returns a 1D lifted vector when input is 1D, otherwise a 2D matrix.
        """
        arr, was_1d = self._as_state_matrix(x)
        out = np.zeros((arr.shape[0], self.lifted_dim), dtype=np.float64)

        try:
            if self.lifting_type == "rbf":
                _rbf_lift_batch(arr, self.rbf_centers, self.rbf_widths, out)
            elif self.lifting_type == "random_fourier":
                _random_fourier_lift_batch(arr, self.rff_weights, self.rff_bias, out)
            else:
                _observable_lift_batch(
                    arr,
                    self.feature_kind,
                    self.feature_i,
                    self.feature_j,
                    out,
                )
        except Exception as exc:
            self._warn_instability(f"observable lifting failed: {exc}")
            out = np.zeros((arr.shape[0], self.lifted_dim), dtype=np.float64)
            copy_dim = min(arr.shape[1], self.lifted_dim)
            out[:, :copy_dim] = arr[:, :copy_dim]

        if not _is_finite_matrix(out):
            self._warn_instability("non-finite values produced by observable lift")
            out = np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)

        return out[0] if was_1d else out

    # ------------------------------------------------------------------
    # Fitting / EDMD
    # ------------------------------------------------------------------

    def fit(self, trajectory: np.ndarray, regularization: float = 1e-4) -> float:
        """
        Fit the Koopman operator using EDMD.

        This method never raises for numerical instability. It logs warnings
        and returns `baseline_curiosity` when fitting cannot be trusted.
        """
        try:
            traj = np.asarray(trajectory, dtype=np.float64)
        except Exception as exc:
            self._warn_instability(f"trajectory conversion failed: {exc}")
            self._set_unstable_identity()
            return self.baseline_curiosity

        if traj.ndim != 2:
            self._warn_instability(
                f"expected trajectory shape (T, D), got {traj.shape}"
            )
            self._set_unstable_identity()
            return self.baseline_curiosity

        if traj.shape[0] < 2:
            self._warn_instability("insufficient trajectory length for EDMD")
            self._set_unstable_identity()
            return self.baseline_curiosity

        if traj.shape[1] != self.state_dim:
            traj, _ = self._as_state_matrix(traj)

        if not _is_finite_matrix(traj):
            self._warn_instability("non-finite values in trajectory")
            traj = np.nan_to_num(traj, nan=0.0, posinf=0.0, neginf=0.0)

        try:
            G = self.lift(traj)
            if G.ndim != 2 or G.shape[0] < 2:
                raise ValueError("lifted trajectory has invalid shape")

            G_x = G[:-1]
            G_y = G[1:]

            if not _is_finite_matrix(G_x) or not _is_finite_matrix(G_y):
                raise FloatingPointError("non-finite lifted trajectory")

            eye = np.eye(self.lifted_dim, dtype=np.float64)
            reg = max(float(regularization), 1e-10)
            A = G_x.T @ G_x + reg * eye
            B = G_x.T @ G_y

            if not _is_finite_matrix(A) or not _is_finite_matrix(B):
                raise FloatingPointError("non-finite EDMD normal equations")

            try:
                # A @ K.T = B, therefore K = solve(A, B).T
                self.K = np.linalg.solve(A, B).T
            except np.linalg.LinAlgError as exc:
                self._warn_instability(
                    f"singular EDMD system; attempting pseudoinverse fallback: {exc}"
                )
                try:
                    self.K = (np.linalg.pinv(A, rcond=1e-8) @ B).T
                except Exception as pinv_exc:
                    self._warn_instability(f"pseudoinverse fallback failed: {pinv_exc}")
                    self._set_unstable_identity()
                    return self.baseline_curiosity

            if self.K is None or not np.all(np.isfinite(self.K)):
                self._warn_instability("non-finite Koopman matrix after EDMD")
                self._set_unstable_identity()
                return self.baseline_curiosity

            G_y_pred = G_x @ self.K.T
            self.reconstruction_error = float(_rowwise_l2_mean(G_y, G_y_pred))

            if not np.isfinite(self.reconstruction_error):
                self._warn_instability("non-finite reconstruction error")
                self.reconstruction_error = self.baseline_curiosity

            self.fitted = True
            self.manifold_unstable = False

            self._compute_eigendecomposition()

            logger.info(
                "Koopman fitted: reconstruction_error=%.6f, stable=%.3f",
                self.reconstruction_error,
                self.stability_score(),
            )
            return float(self.reconstruction_error)

        except Exception as exc:
            self._warn_instability(f"fit failed safely: {exc}")
            self._set_unstable_identity()
            return self.baseline_curiosity

    def _set_unstable_identity(self) -> None:
        self.K = np.eye(self.lifted_dim, dtype=np.float64)
        self.eigenvalues = None
        self.eigenvectors = None
        self.modes = []
        self.fitted = False
        self.manifold_unstable = True
        self.reconstruction_error = self.baseline_curiosity

    def _compute_eigendecomposition(self) -> None:
        if self.K is None:
            self._warn_instability("cannot compute eigendecomposition before K exists")
            return

        try:
            if not np.all(np.isfinite(self.K)):
                raise FloatingPointError("non-finite Koopman matrix")

            self.eigenvalues, self.eigenvectors = np.linalg.eig(self.K)

            if self.eigenvalues is None or self.eigenvectors is None:
                raise FloatingPointError("empty eigendecomposition")

            if not np.all(np.isfinite(self.eigenvalues)):
                raise FloatingPointError("non-finite eigenvalues")

            self.modes = []
            for i, lam in enumerate(self.eigenvalues):
                if abs(lam) <= 1e-12:
                    growth_rate = -np.inf
                    frequency = 0.0
                else:
                    growth_rate = float(np.log(abs(lam)))
                    frequency = float(np.angle(lam))

                self.modes.append(
                    KoopmanMode(
                        eigenvalue=complex(lam),
                        eigenfunction=self.eigenvectors[:, i],
                        growth_rate=growth_rate,
                        frequency=frequency,
                    )
                )

            self.modes.sort(key=lambda mode: -abs(mode.eigenvalue))

        except Exception as exc:
            self._warn_instability(f"eigendecomposition failed: {exc}")
            self.eigenvalues = None
            self.eigenvectors = None
            self.modes = []

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def _reconstruct_state(self, g: np.ndarray) -> np.ndarray:
        if self.lifting_type == "rbf" and hasattr(self, "rbf_centers"):
            weights = np.maximum(np.asarray(g, dtype=np.float64), 0.0)
            denom = float(weights.sum())
            if denom <= _EPS:
                return np.zeros(self.state_dim, dtype=np.float64)
            return (weights[:, np.newaxis] * self.rbf_centers).sum(axis=0) / denom

        state = np.zeros(self.state_dim, dtype=np.float64)
        copy_dim = min(self.state_dim, g.shape[0])
        state[:copy_dim] = np.asarray(g[:copy_dim], dtype=np.float64)
        return state

    def predict(self, x: np.ndarray, horizon: int = 1) -> np.ndarray:
        """
        Predict future raw states.

        If the Koopman operator is not fitted, this returns repeated copies of
        the current state instead of raising.
        """
        horizon = max(1, int(horizon))
        arr, _ = self._as_state_matrix(x)
        current = arr[0]

        if self.K is None or not self.fitted:
            self._warn_instability(
                "predict requested before stable fitting; returning repeated state"
            )
            return np.repeat(current.reshape(1, -1), horizon, axis=0)

        try:
            g = np.asarray(self.lift(current), dtype=np.float64)
            preds = np.zeros((horizon, self.state_dim), dtype=np.float64)

            for t in range(horizon):
                g = self.K @ g
                if not _is_finite_vector(g):
                    self._warn_instability("non-finite lifted prediction")
                    return np.repeat(current.reshape(1, -1), horizon, axis=0)

                preds[t] = self._reconstruct_state(g)

            return preds

        except Exception as exc:
            self._warn_instability(f"prediction failed safely: {exc}")
            return np.repeat(current.reshape(1, -1), horizon, axis=0)

    def predict_lifted(self, g: np.ndarray, horizon: int = 1) -> np.ndarray:
        """
        Predict directly in observable space.

        If not fitted, returns repeated copies of the supplied lifted vector.
        """
        horizon = max(1, int(horizon))
        lifted = np.asarray(g, dtype=np.float64).reshape(-1)

        if lifted.shape[0] != self.lifted_dim:
            padded = np.zeros(self.lifted_dim, dtype=np.float64)
            copy_dim = min(self.lifted_dim, lifted.shape[0])
            padded[:copy_dim] = lifted[:copy_dim]
            lifted = padded

        if self.K is None or not self.fitted:
            self._warn_instability("predict_lifted requested before stable fitting")
            return np.repeat(lifted.reshape(1, -1), horizon + 1, axis=0)

        try:
            preds = np.zeros((horizon + 1, self.lifted_dim), dtype=np.float64)
            preds[0] = lifted

            current = lifted
            for t in range(1, horizon + 1):
                current = self.K @ current
                if not _is_finite_vector(current):
                    self._warn_instability("non-finite lifted prediction")
                    preds[t:] = preds[t - 1]
                    break
                preds[t] = current

            return preds

        except Exception as exc:
            self._warn_instability(f"lifted prediction failed safely: {exc}")
            return np.repeat(lifted.reshape(1, -1), horizon + 1, axis=0)

    # ------------------------------------------------------------------
    # Residuals / Curiosity
    # ------------------------------------------------------------------

    def residual_energy(self, x_current: np.ndarray, x_next: np.ndarray) -> float:
        """
        Koopman residual energy: ||K φ(x_t) - φ(x_{t+1})||.

        Returns baseline curiosity on instability instead of raising.
        """
        if self.K is None or not self.fitted:
            self._warn_instability("residual requested before stable fitting")
            return self.baseline_curiosity

        try:
            g_current = np.asarray(self.lift(x_current), dtype=np.float64)
            g_next = np.asarray(self.lift(x_next), dtype=np.float64)
            g_predicted = self.K @ g_current

            if (
                not _is_finite_vector(g_current)
                or not _is_finite_vector(g_next)
                or not _is_finite_vector(g_predicted)
            ):
                self._warn_instability("non-finite residual inputs")
                return self.baseline_curiosity

            residual = float(_vector_l2(g_predicted, g_next))
            if not np.isfinite(residual):
                self._warn_instability("non-finite residual energy")
                return self.baseline_curiosity

            return residual

        except Exception as exc:
            self._warn_instability(f"residual computation failed safely: {exc}")
            return self.baseline_curiosity

    def curiosity_score(
        self,
        state: np.ndarray,
        history: Optional[np.ndarray] = None,
        fit_if_possible: bool = True,
    ) -> float:
        """
        Compute curiosity/novelty for a state against manifold history.

        If a stable Koopman model exists and the history contains a previous
        state, this combines residual anomaly with distance-from-history.
        Otherwise it falls back to distance-based novelty.
        """
        try:
            state_arr, _ = self._as_state_matrix(state)
            state_vec = state_arr[0]

            if history is None:
                return INSUFFICIENT_HISTORY_CURIOSITY_SCORE

            hist, _ = self._as_state_matrix(history)

            if hist.shape[0] < 2:
                return INSUFFICIENT_HISTORY_CURIOSITY_SCORE

            if fit_if_possible and not self.fitted:
                self.fit(hist)

            lifted_state = np.asarray(self.lift(state_vec), dtype=np.float64)
            lifted_hist = np.asarray(
                self.lift(hist[-min(100, hist.shape[0]) :]), dtype=np.float64
            )

            novelty = float(_mean_distance_to_history(lifted_state, lifted_hist))
            novelty_norm = novelty / (1.0 + novelty)

            if self.fitted and self.K is not None:
                residual = self.residual_energy(hist[-1], state_vec)
                residual_norm = residual / (1.0 + residual)
                score = 0.5 * novelty_norm + 0.5 * residual_norm
            else:
                score = novelty_norm

            if self.manifold_unstable:
                return self.baseline_curiosity

            if not np.isfinite(score):
                self._warn_instability("non-finite curiosity score")
                return self.baseline_curiosity

            return float(np.clip(score, 0.0, 1.0))

        except Exception as exc:
            self._warn_instability(f"curiosity score failed safely: {exc}")
            return self.baseline_curiosity

    # ------------------------------------------------------------------
    # Stability / diagnostics
    # ------------------------------------------------------------------

    def stability_score(self) -> float:
        """
        Return spectral stability in [0, 1].

        1.0 = all modes stable.
        0.0 = no reliable spectral information or all modes unstable.
        """
        if self.manifold_unstable and not self.modes:
            return 0.0

        if not self.modes:
            return 1.0 if self.fitted else 0.0

        stable = sum(1 for mode in self.modes if mode.is_stable)
        return float(stable / len(self.modes))

    def dominant_modes(self, top_k: int = 5) -> List[Dict[str, Any]]:
        output: List[Dict[str, Any]] = []

        for mode in self.modes[: max(0, int(top_k))]:
            output.append(
                {
                    "eigenvalue_magnitude": float(abs(mode.eigenvalue)),
                    "eigenvalue_phase": float(np.angle(mode.eigenvalue)),
                    "growth_rate": float(mode.growth_rate),
                    "frequency": float(mode.frequency),
                    "is_stable": bool(mode.is_stable),
                    "is_oscillatory": bool(mode.is_oscillatory),
                }
            )

        return output

    def pairwise_lifted_distances(self, states: np.ndarray) -> np.ndarray:
        """JIT-backed upper-triangle pairwise distances in lifted space."""
        try:
            lifted = np.asarray(self.lift(states), dtype=np.float64)
            if lifted.ndim != 2 or lifted.shape[0] < 2:
                return np.zeros(0, dtype=np.float64)
            return _pairwise_distances_upper(lifted)
        except Exception as exc:
            self._warn_instability(
                f"pairwise distance computation failed safely: {exc}"
            )
            return np.zeros(0, dtype=np.float64)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state_dim": self.state_dim,
            "lifted_dim": self.lifted_dim,
            "observables_dim": self.observables_dim,
            "lifting_type": self.lifting_type,
            "fitted": self.fitted,
            "manifold_unstable": self.manifold_unstable,
            "last_warning": self.last_warning,
            "reconstruction_error": float(self.reconstruction_error),
            "stability_score": float(self.stability_score()),
            "n_modes": len(self.modes),
            "numba_available": NUMBA_AVAILABLE,
            "K": self.K.tolist() if self.K is not None else None,
        }


# ---------------------------------------------------------------------------
# Conformal prediction for calibrated uncertainty gates
# ---------------------------------------------------------------------------


class ConformalPredictor:
    """
    Lightweight pure-NumPy conformal predictor for residual/anomaly gates.
    """

    def __init__(self, target_coverage: float = 0.95):
        self.target_coverage = float(target_coverage)
        self.calibration_scores: List[float] = []
        self.threshold: Optional[float] = None
        self.calibrated = False

        logger.info(
            "ConformalPredictor initialized (coverage=%.3f)", self.target_coverage
        )

    def calibrate(self, nonconformity_scores: np.ndarray) -> None:
        scores = np.asarray(nonconformity_scores, dtype=np.float64).reshape(-1)
        scores = scores[np.isfinite(scores)]

        if scores.size == 0:
            logger.warning("Conformal calibration skipped: no finite scores")
            self.calibration_scores = []
            self.threshold = None
            self.calibrated = False
            return

        self.calibration_scores = sorted(float(s) for s in scores)
        n = len(self.calibration_scores)

        quantile_idx = int(np.ceil((n + 1) * self.target_coverage)) - 1
        quantile_idx = max(0, min(quantile_idx, n - 1))

        self.threshold = self.calibration_scores[quantile_idx]
        self.calibrated = True

        logger.info("Conformal calibrated: threshold=%.6f (n=%s)", self.threshold, n)

    def predict(self, score: float) -> Tuple[bool, float]:
        if not self.calibrated or self.threshold is None:
            return True, 1.0

        score = float(score)
        n = len(self.calibration_scores)
        rank = sum(1 for s in self.calibration_scores if s >= score)
        p_value = (rank + 1.0) / (n + 1.0)

        return score <= self.threshold, float(p_value)

    def gate_decision(
        self,
        predicted_or_score: Any,
        actual: Optional[np.ndarray] = None,
        action_on_anomaly: str = "block",
    ) -> Tuple[bool, float]:
        if actual is not None:
            predicted = np.asarray(predicted_or_score, dtype=np.float64)
            actual_arr = np.asarray(actual, dtype=np.float64)
            score = float(np.linalg.norm(predicted - actual_arr))
        else:
            score = float(predicted_or_score)

        is_normal, p_value = self.predict(score)

        if not is_normal:
            logger.warning(
                "Conformal gate %s: score=%.6f, p=%.6f",
                action_on_anomaly.upper(),
                score,
                p_value,
            )

        return bool(is_normal), float(score)

    def gate_decision_detailed(
        self,
        score: float,
        action_on_anomaly: str = "block",
    ) -> Dict[str, Any]:
        is_normal, p_value = self.predict(float(score))

        decision = {
            "allow": bool(is_normal),
            "score": float(score),
            "p_value": float(p_value),
            "threshold": float(self.threshold) if self.threshold is not None else None,
            "coverage_guarantee": float(self.target_coverage),
            "action": "proceed" if is_normal else action_on_anomaly,
            "statistical_validity": f"{self.target_coverage * 100:.0f}% coverage guaranteed",
        }

        if not is_normal:
            logger.warning(
                "Conformal gate %s: score=%.6f, p=%.6f",
                action_on_anomaly.upper(),
                score,
                p_value,
            )

        return decision


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------

_koopman: Optional[KoopmanOperator] = None
_conformal: Optional[ConformalPredictor] = None


def get_koopman_operator(
    state_dim: int = 32,
    lifted_dim: int = 128,
    lifting_type: str = "polynomial",
) -> KoopmanOperator:
    """Get or create the global Koopman operator."""
    global _koopman

    if (
        _koopman is None
        or _koopman.state_dim != state_dim
        or _koopman.lifted_dim != lifted_dim
        or _koopman.lifting_type != lifting_type
    ):
        _koopman = KoopmanOperator(
            state_dim=state_dim,
            lifted_dim=lifted_dim,
            lifting_type=lifting_type,
        )

    return _koopman


def get_koopman(
    lift_type: str = "polynomial", n_components: int = 128
) -> KoopmanOperator:
    """MCP-friendly alias for the global Koopman operator."""
    return get_koopman_operator(
        state_dim=32,
        lifted_dim=n_components,
        lifting_type=lift_type,
    )


def get_conformal_predictor(target_coverage: float = 0.95) -> ConformalPredictor:
    """Get or create the global conformal predictor."""
    global _conformal

    if _conformal is None or _conformal.target_coverage != float(target_coverage):
        _conformal = ConformalPredictor(target_coverage=target_coverage)

    return _conformal


def get_pipeline():
    """
    Import and return the TickFrame pipeline singleton.

    Kept as a lazy import to avoid startup cycles.
    """
    from services.neural_system.tickframe_pipeline import get_pipeline as _get_pipeline

    return _get_pipeline()
