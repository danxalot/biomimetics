"""JEPA — NumPy runtime.

1:1 parity port of Gold_Standard_Archive/pytorch/jepa.py.

Inference-only: EMA update is preserved as a utility method for offline
evaluation of representation quality, but is not called during the forward pass.
No autograd. FP32 strict.

Weight contract (target_encoder mirrors encoder structure):
  encoder_0_weight:        [latent_dim, state_dim]  float32
  encoder_0_bias:          [latent_dim]              float32
  encoder_0_ln_weight:     [latent_dim]              float32   (LayerNorm)
  encoder_0_ln_bias:       [latent_dim]              float32
  encoder_3_weight:        [latent_dim, latent_dim]  float32
  encoder_3_bias:          [latent_dim]              float32
  predictor_0_weight:      [latent_dim, latent_dim+action_dim]  float32
  predictor_0_bias:        [latent_dim]              float32
  predictor_2_weight:      [latent_dim, latent_dim]  float32
  predictor_2_bias:        [latent_dim]              float32
  (same keys prefixed target_ for the EMA target encoder)
"""
import numpy as np


class JEPA:
    """Joint-Embedding Predictive Architecture.

    Predicts the embedding of next_state from (curr_state, action).
    L = ‖Predictor(Encoder(x_curr), action) − TargetEncoder(x_next)‖²

    Mirrors pytorch JEPA(nn.Module). EMA decay = 0.99.

    Args:
        state_dim:  raw state dimensionality (default 32 — matches mv_dim).
        latent_dim: latent embedding dimension (default 128).
        action_dim: action vector dimensionality (default 8).
        weights:    optional dict with weight arrays (see module docstring).
    """

    def __init__(
        self,
        state_dim: int  = 32,
        latent_dim: int = 128,
        action_dim: int = 8,
        weights: dict   = None,
    ):
        self.state_dim  = state_dim
        self.latent_dim = latent_dim
        self.action_dim = action_dim
        self.ema_decay  = 0.99

        if weights is not None:
            def _w(k): return np.asarray(weights[k], dtype=np.float32)
            # Online encoder
            self.enc_W0    = _w("encoder_0_weight")
            self.enc_b0    = _w("encoder_0_bias")
            self.enc_ln_w  = _w("encoder_0_ln_weight")
            self.enc_ln_b  = _w("encoder_0_ln_bias")
            self.enc_W3    = _w("encoder_3_weight")
            self.enc_b3    = _w("encoder_3_bias")
            # Target encoder (EMA copy)
            self.tgt_W0    = _w("target_encoder_0_weight")
            self.tgt_b0    = _w("target_encoder_0_bias")
            self.tgt_ln_w  = _w("target_encoder_0_ln_weight")
            self.tgt_ln_b  = _w("target_encoder_0_ln_bias")
            self.tgt_W3    = _w("target_encoder_3_weight")
            self.tgt_b3    = _w("target_encoder_3_bias")
            # Predictor
            self.pred_W0   = _w("predictor_0_weight")
            self.pred_b0   = _w("predictor_0_bias")
            self.pred_W2   = _w("predictor_2_weight")
            self.pred_b2   = _w("predictor_2_bias")
        else:
            rng = np.random.default_rng(8)
            def _rand(shape): return rng.standard_normal(shape).astype(np.float32) * 0.02
            self.enc_W0   = _rand((latent_dim, state_dim))
            self.enc_b0   = np.zeros(latent_dim, dtype=np.float32)
            self.enc_ln_w = np.ones(latent_dim,  dtype=np.float32)
            self.enc_ln_b = np.zeros(latent_dim, dtype=np.float32)
            self.enc_W3   = _rand((latent_dim, latent_dim))
            self.enc_b3   = np.zeros(latent_dim, dtype=np.float32)
            # Target starts as a copy of online encoder
            self.tgt_W0   = self.enc_W0.copy()
            self.tgt_b0   = self.enc_b0.copy()
            self.tgt_ln_w = self.enc_ln_w.copy()
            self.tgt_ln_b = self.enc_ln_b.copy()
            self.tgt_W3   = self.enc_W3.copy()
            self.tgt_b3   = self.enc_b3.copy()
            self.pred_W0  = _rand((latent_dim, latent_dim + action_dim))
            self.pred_b0  = np.zeros(latent_dim, dtype=np.float32)
            self.pred_W2  = _rand((latent_dim, latent_dim))
            self.pred_b2  = np.zeros(latent_dim, dtype=np.float32)

    @staticmethod
    def _silu(x: np.ndarray) -> np.ndarray:
        return x / (1.0 + np.exp(-x))

    @staticmethod
    def _layer_norm(x: np.ndarray, w: np.ndarray, b: np.ndarray, eps: float = 1e-5) -> np.ndarray:
        mean = x.mean(axis=-1, keepdims=True)
        var  = x.var(axis=-1, keepdims=True)
        return w * (x - mean) / np.sqrt(var + eps) + b

    def _encode(self, x: np.ndarray) -> np.ndarray:
        """Online encoder: Linear → LayerNorm → SiLU → Linear."""
        x = np.asarray(x, dtype=np.float32)
        h = x @ self.enc_W0.T + self.enc_b0
        h = self._layer_norm(h, self.enc_ln_w, self.enc_ln_b)
        h = self._silu(h)
        return h @ self.enc_W3.T + self.enc_b3

    def _encode_target(self, x: np.ndarray) -> np.ndarray:
        """Target (EMA) encoder."""
        x = np.asarray(x, dtype=np.float32)
        h = x @ self.tgt_W0.T + self.tgt_b0
        h = self._layer_norm(h, self.tgt_ln_w, self.tgt_ln_b)
        h = self._silu(h)
        return h @ self.tgt_W3.T + self.tgt_b3

    def _predict(self, z: np.ndarray, action: np.ndarray) -> np.ndarray:
        """Predictor: [z_curr ‖ action] → latent."""
        action = np.asarray(action, dtype=np.float32)
        inp = np.concatenate([z, action], axis=-1)
        h   = self._silu(inp @ self.pred_W0.T + self.pred_b0)
        return h @ self.pred_W2.T + self.pred_b2

    def encode(self, x: np.ndarray) -> np.ndarray:
        """Return the stable target representation (for inference use)."""
        return self._encode_target(np.asarray(x, dtype=np.float32))

    def update_target(self) -> None:
        """EMA update of target encoder from online encoder.

        Call after each training step if using JEPA at inference-time fine-tuning.
        In pure inference mode this is not needed.
        """
        d = self.ema_decay
        for (a, b) in [
            (self.tgt_W0,  self.enc_W0),
            (self.tgt_b0,  self.enc_b0),
            (self.tgt_ln_w, self.enc_ln_w),
            (self.tgt_ln_b, self.enc_ln_b),
            (self.tgt_W3,  self.enc_W3),
            (self.tgt_b3,  self.enc_b3),
        ]:
            a[:] = d * a + (1.0 - d) * b

    def __call__(
        self,
        x_curr: np.ndarray,
        x_next: np.ndarray,
        action: np.ndarray,
    ) -> float:
        """Compute JEPA MSE loss.

        L = ‖Predictor(Encoder(x_curr), action) − TargetEncoder(x_next)‖²

        Args:
            x_curr: [..., state_dim]
            x_next: [..., state_dim]
            action: [..., action_dim]
        Returns:
            scalar float — MSE in latent space
        """
        z_curr   = self._encode(x_curr)
        z_pred   = self._predict(z_curr, action)
        z_target = self._encode_target(x_next)
        return float(np.mean((z_pred - z_target) ** 2))
