"""Lyapunov Stability Analysis — NumPy runtime.

1:1 parity port of Gold_Standard_Archive/pytorch/lyapunov.py.
No autograd. FP32 strict.
"""
import numpy as np
from typing import Callable, Optional


class LyapunovStability:
    """Evaluates and enforces Lyapunov stability: V(x) > 0 and V̇(x) < 0.

    Mirrors pytorch LyapunovStability(nn.Module).

    Args:
        dim:    dimensionality of the state space (default 32 — matches mv_dim).
        center: optional attractor center [dim] float32.
                If None, defaults to the origin.
    """

    def __init__(self, dim: int = 32, center: Optional[np.ndarray] = None):
        self.dim    = dim
        self.center = np.asarray(center, dtype=np.float32) if center is not None \
                      else np.zeros(dim, dtype=np.float32)

    def candidate_v(self, x: np.ndarray) -> np.ndarray:
        """Quadratic Lyapunov candidate: V(x) = ½‖x − c‖².

        Args:
            x: [..., dim]
        Returns:
            [...] scalar potential
        """
        x    = np.asarray(x, dtype=np.float32)
        diff = x - self.center
        return 0.5 * np.sum(diff ** 2, axis=-1)

    def stability_loss(
        self,
        x_curr: np.ndarray,
        x_next: np.ndarray,
        alpha: float = 0.1,
    ) -> float:
        """Enforce V̇ < −α · V (exponential stability toward center).

        V̇ ≈ V(x_next) − V(x_curr)   (dt=1 discretization)
        Loss = mean relu(V̇ + α · V_curr)  — violation of stability condition.

        Args:
            x_curr: [..., dim]
            x_next: [..., dim]
            alpha:  decay rate (default 0.1)
        Returns:
            scalar float — stability violation loss
        """
        v_curr    = self.candidate_v(x_curr)
        v_next    = self.candidate_v(x_next)
        v_dot     = v_next - v_curr
        violation = np.maximum(0.0, v_dot + alpha * v_curr)
        return float(np.mean(violation))

    def find_attractor(
        self,
        x: np.ndarray,
        f: Callable,
        steps: int = 100,
    ) -> np.ndarray:
        """Trace the trajectory under dynamics f to find the local attractor.

        Args:
            x:     initial state [..., dim]
            f:     dynamics function x → x (same shape)
            steps: number of integration steps
        Returns:
            [..., dim] estimated attractor state
        """
        curr = np.asarray(x, dtype=np.float32)
        for _ in range(steps):
            curr = np.asarray(f(curr), dtype=np.float32)
        return curr

    def __call__(self, x_curr: np.ndarray, x_next: np.ndarray) -> float:
        """Return the stability violation loss."""
        return self.stability_loss(x_curr, x_next)
