"""KinematicBridge — NumPy runtime.

1:1 parity port of Gold_Standard_Archive/pytorch/bridges.py.

Two flavours (matching pytorch originals):
  ConformalKinematicBridge  — active training flavour. Domain-aware grade-0/1
                              algebraic content + learned encoder for grades 2-5.
  LearnedKinematicBridge    — MLP-encoded bridge: x → 3D → conformal_lift.

KinematicBridge = ConformalKinematicBridge  (default alias).

Weight contract — ConformalKinematicBridge:
  higher_grade_enc_0_weight: [hidden, in_dim]  float32
  higher_grade_enc_0_bias:   [hidden]          float32
  higher_grade_enc_2_weight: [hidden, hidden]  float32   (LayerNorm weight)
  higher_grade_enc_2_bias:   [hidden]          float32   (LayerNorm bias)
  higher_grade_enc_3_weight: [26, hidden]      float32
  higher_grade_enc_3_bias:   [26]              float32

Weight contract — LearnedKinematicBridge:
  enc_0_weight: [64, in_dim]  float32
  enc_0_bias:   [64]          float32
  enc_2_weight: [3, 64]       float32
  enc_2_bias:   [3]           float32
"""
import numpy as np
from .config import CONFIG
from .geometry import conformal_lift


class ConformalKinematicBridge:
    """Domain-aware bridge populating ALL grades 0-5 of Cl(4,1).

    Forward shape: x [..., in_dim] → mv [..., 32].

    Cl(4,1) grade decomposition:
      grade 0 (scalar):       1 comp  → mv[0]      (time for relativity)
      grade 1 (vectors):      5 comps → mv[1:6]
      grade 2 (bivectors):   10 comps → mv[6:16]
      grade 3 (trivectors):  10 comps → mv[16:26]
      grade 4 (quadvectors):  5 comps → mv[26:31]
      grade 5 (pseudoscalar): 1 comp  → mv[31]
    """

    def __init__(self, in_dim: int, domain: str = "", weights: dict = None):
        self.in_dim        = in_dim
        self.domain        = domain
        self.is_relativity = (domain == "relativity")

        hidden = max(64, in_dim * 4)
        self.hidden = hidden

        if weights is not None:
            def _w(k): return np.asarray(weights[k], dtype=np.float32)
            # Linear 0: [hidden, in_dim]
            self.W0 = _w("higher_grade_enc_0_weight")
            self.b0 = _w("higher_grade_enc_0_bias")
            # LayerNorm 2: scale/shift over hidden
            self.ln_w = _w("higher_grade_enc_2_weight")
            self.ln_b = _w("higher_grade_enc_2_bias")
            # Linear 3: [26, hidden]
            self.W3 = _w("higher_grade_enc_3_weight")
            self.b3 = _w("higher_grade_enc_3_bias")
        else:
            # Near-zero init — preserves C1 prior behavior at inference without weights
            rng = np.random.default_rng(2)
            self.W0   = rng.standard_normal((hidden, in_dim)).astype(np.float32) * 0.02
            self.b0   = np.zeros(hidden, dtype=np.float32)
            self.ln_w = np.ones(hidden,  dtype=np.float32)
            self.ln_b = np.zeros(hidden, dtype=np.float32)
            self.W3   = rng.standard_normal((26, hidden)).astype(np.float32) * 0.01
            self.b3   = np.zeros(26, dtype=np.float32)

    @staticmethod
    def _silu(x: np.ndarray) -> np.ndarray:
        return x / (1.0 + np.exp(-x))

    @staticmethod
    def _tanh(x: np.ndarray) -> np.ndarray:
        return np.tanh(x)

    @staticmethod
    def _layer_norm(x: np.ndarray, w: np.ndarray, b: np.ndarray, eps: float = 1e-5) -> np.ndarray:
        mean = x.mean(axis=-1, keepdims=True)
        var  = x.var(axis=-1,  keepdims=True)
        return w * (x - mean) / np.sqrt(var + eps) + b

    def _higher_grade_encoder(self, x: np.ndarray) -> np.ndarray:
        """Sequential: Linear → SiLU → LayerNorm → Linear → Tanh → [..., 26]."""
        h = x @ self.W0.T + self.b0          # [..., hidden]
        h = self._silu(h)
        h = self._layer_norm(h, self.ln_w, self.ln_b)
        h = h @ self.W3.T + self.b3          # [..., 26]
        return self._tanh(h)

    def __call__(self, x: np.ndarray) -> np.ndarray:
        """Args: x [..., in_dim]. Returns mv [..., 32] float32."""
        x  = np.asarray(x, dtype=np.float32)
        mv = np.zeros(x.shape[:-1] + (CONFIG["mv_dim"],), dtype=np.float32)

        # Log-squash
        x_sq = np.sign(x) * np.log1p(np.abs(x))

        # Grade 0/1 — algebraic
        if self.is_relativity:
            mv[..., 0:1] = x_sq[..., 0:1]
            spatial_core  = x_sq[..., 1:4]
        else:
            spatial_core  = x_sq[..., :3]

        r2 = np.sum(spatial_core ** 2, axis=-1, keepdims=True)
        mv[..., 1:4] = spatial_core
        mv[..., 4:5] = 0.5 * r2 - 0.5    # n_inf (e4)
        mv[..., 5:6] = 0.5 * r2 + 0.5    # n_o   (e5)

        # Grades 2-5 — learned encoder
        mv[..., 6:32] = self._higher_grade_encoder(x_sq)

        return mv


class LearnedKinematicBridge:
    """MLP-encoded bridge: x → 3D points → conformal_lift.

    Weight contract:
      enc_0_weight: [64, in_dim]
      enc_0_bias:   [64]
      enc_2_weight: [3, 64]
      enc_2_bias:   [3]
    """

    def __init__(self, in_dim: int, weights: dict = None):
        if weights is not None:
            self.W0 = np.asarray(weights["enc_0_weight"], dtype=np.float32)
            self.b0 = np.asarray(weights["enc_0_bias"],   dtype=np.float32)
            self.W2 = np.asarray(weights["enc_2_weight"], dtype=np.float32)
            self.b2 = np.asarray(weights["enc_2_bias"],   dtype=np.float32)
        else:
            rng = np.random.default_rng(3)
            self.W0 = rng.standard_normal((64, in_dim)).astype(np.float32) * 0.02
            self.b0 = np.zeros(64, dtype=np.float32)
            self.W2 = rng.standard_normal((3, 64)).astype(np.float32) * 0.02
            self.b2 = np.zeros(3, dtype=np.float32)

    @staticmethod
    def _silu(x: np.ndarray) -> np.ndarray:
        return x / (1.0 + np.exp(-x))

    def __call__(self, x: np.ndarray) -> np.ndarray:
        """Args: x [..., in_dim]. Returns mv [..., 32] float32."""
        x = np.asarray(x, dtype=np.float32)
        leading = x.shape[:-1]
        h = self._silu(x @ self.W0.T + self.b0)           # [..., 64]
        pts = np.tanh(h @ self.W2.T + self.b2) * 5.0      # [..., 3]
        pts_flat = pts.reshape(-1, 3)
        mv_flat  = conformal_lift(pts_flat)                # [-1, 32]
        return mv_flat.reshape(leading + (CONFIG["mv_dim"],))


# Default alias — matches Kaggle bundle import
KinematicBridge = ConformalKinematicBridge
