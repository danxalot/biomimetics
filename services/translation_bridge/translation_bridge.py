"""
Translation Bridge — Pure NumPy Implementation
===============================================

Definitive, torch-free translation layer between Pythia's 10,000-dimensional
sparse Holographic Distributed Computing (HDC) vectors and the 2,048-dimensional
dense language-model embedding space used by Qwen3-VL.

Architecture (from trained checkpoint ``translation_bridge_v1.npz``)
--------------------------------------------------------------------

**ForwardBridge** (HDC 10,000 sparse → Dense 2,048):
    Linear(10000, 4096) → GELU → Linear(4096, 2048)

    Checkpoint keys:
        forward.net.0.weight  (4096, 10000)
        forward.net.0.bias    (4096,)
        forward.net.2.weight  (2048, 4096)
        forward.net.2.bias    (2048,)

**InverseBridge** (Dense 2,048 → HDC 10,000 sparse):
    Linear(2048, 4096) → GELU → Linear(4096, 10000) → ReLU

    Checkpoint keys:
        inverse.net.0.weight  (4096, 2048)
        inverse.net.0.bias    (4096,)
        inverse.net.2.weight  (10000, 4096)
        inverse.net.2.bias    (10000,)

Total parameters: 98,717,456
    Forward:  ~49,358,848  (10000*4096 + 4096 + 4096*2048 + 2048)
    Inverse:  ~49,358,608  (2048*4096 + 4096 + 4096*10000 + 10000)

Weights are loaded from a NumPy ``.npz`` archive.
Default path: ``<project_root>/models/translation_bridge_v1.npz``
Override via env-var ``TRANSLATION_BRIDGE_WEIGHTS``.

The ``.npz`` file (~377 MB) is produced by exporting a PyTorch checkpoint
with ``numpy.savez`` using the key names listed above.

Usage
-----
>>> from translation_bridge.translation_bridge import hdc_to_dense, dense_to_hdc
>>> dense = hdc_to_dense(np.random.randn(10000))
>>> roundtrip = dense_to_hdc(dense)

Or via the class directly:

>>> from translation_bridge.translation_bridge import get_translation_bridge
>>> bridge = get_translation_bridge()
>>> dense = bridge.hdc_to_dense(hdc_vec)
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Project root — two levels up from this file:
#   <root>/services/translation_bridge/translation_bridge.py
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_DEFAULT_WEIGHTS_PATH = _PROJECT_ROOT / "models" / "translation_bridge_v1.npz"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GELU approximation (matches PyTorch's default tanh approximation)
# ---------------------------------------------------------------------------
_GELU_COEFF = np.sqrt(2.0 / np.pi)


def _gelu(x: np.ndarray) -> np.ndarray:
    """Gaussian Error Linear Unit — tanh approximation (matches PyTorch)."""
    return 0.5 * x * (1.0 + np.tanh(_GELU_COEFF * (x + 0.044715 * x**3)))


def _relu(x: np.ndarray) -> np.ndarray:
    """Rectified Linear Unit."""
    return np.maximum(x, 0.0, out=np.empty_like(x))


# ---------------------------------------------------------------------------
# Weight key constants
# ---------------------------------------------------------------------------
_FWD_W0 = "forward.net.0.weight"  # (4096, 10000)
_FWD_B0 = "forward.net.0.bias"  # (4096,)
_FWD_W2 = "forward.net.2.weight"  # (2048, 4096)
_FWD_B2 = "forward.net.2.bias"  # (2048,)

_INV_W0 = "inverse.net.0.weight"  # (4096, 2048)
_INV_B0 = "inverse.net.0.bias"  # (4096,)
_INV_W2 = "inverse.net.2.weight"  # (10000, 4096)
_INV_B2 = "inverse.net.2.bias"  # (10000,)

_ALL_KEYS = [_FWD_W0, _FWD_B0, _FWD_W2, _FWD_B2, _INV_W0, _INV_B0, _INV_W2, _INV_B2]

# Expected shapes for validation
_EXPECTED_SHAPES = {
    _FWD_W0: (4096, 10000),
    _FWD_B0: (4096,),
    _FWD_W2: (2048, 4096),
    _FWD_B2: (2048,),
    _INV_W0: (4096, 2048),
    _INV_B0: (4096,),
    _INV_W2: (10000, 4096),
    _INV_B2: (10000,),
}

# Dimensions
HDC_DIM = 10_000
DENSE_DIM = 2_048
HIDDEN_DIM = 4_096


# ---------------------------------------------------------------------------
# Main Bridge Class
# ---------------------------------------------------------------------------
class NumpyTranslationBridge:
    """
    Pure-numpy translation bridge between HDC and dense embedding spaces.

    Parameters
    ----------
    weights_path : str or Path or None
        Path to the ``.npz`` weights file.  If *None*, the path is resolved in
        this order:
        1. ``TRANSLATION_BRIDGE_WEIGHTS`` environment variable
        2. ``<project_root>/models/translation_bridge_v1.npz``

        If the resolved path does not exist the bridge falls back to random
        (Xavier-uniform) initialisation and logs a warning.
    """

    # ---- construction ------------------------------------------------------
    def __init__(self, weights_path: Optional[str | Path] = None) -> None:
        # Resolve weights path
        if weights_path is not None:
            self._weights_path = Path(weights_path)
        else:
            env = os.environ.get("TRANSLATION_BRIDGE_WEIGHTS")
            self._weights_path = Path(env) if env else _DEFAULT_WEIGHTS_PATH

        # Storage — will be populated by _load or _random_init
        self._w: dict[str, np.ndarray] = {}

        if self._weights_path.is_file():
            self._load(self._weights_path)
        else:
            logger.warning(
                "⚠️  Translation-bridge weights not found at '%s'. "
                "Falling back to random initialisation — outputs will be MEANINGLESS.",
                self._weights_path,
            )
            self._random_init()

    # ---- weight loading ----------------------------------------------------
    def _load(self, path: Path) -> None:
        """Load weights from a ``.npz`` archive and validate shapes."""
        t0 = time.perf_counter()
        data = np.load(str(path))

        missing = [k for k in _ALL_KEYS if k not in data]
        if missing:
            raise KeyError(
                f"Weight file is missing keys: {missing}.  "
                f"Available keys: {list(data.keys())}"
            )

        for key in _ALL_KEYS:
            arr = data[key].astype(np.float32, copy=False)
            expected = _EXPECTED_SHAPES[key]
            if arr.shape != expected:
                raise ValueError(
                    f"Shape mismatch for '{key}': expected {expected}, got {arr.shape}"
                )
            self._w[key] = arr

        elapsed = time.perf_counter() - t0
        total_params = sum(a.size for a in self._w.values())
        logger.info(
            "✅ Loaded translation-bridge weights from '%s' (%s params, %.2f s)",
            path,
            f"{total_params:,}",
            elapsed,
        )

    def _random_init(self) -> None:
        """Xavier-uniform random initialisation (for testing only)."""
        rng = np.random.default_rng(42)

        def _xavier(shape: tuple[int, ...]) -> np.ndarray:
            fan_in = shape[-1] if len(shape) > 1 else shape[0]
            fan_out = shape[0]
            limit = np.sqrt(6.0 / (fan_in + fan_out))
            return rng.uniform(-limit, limit, size=shape).astype(np.float32)

        for key, shape in _EXPECTED_SHAPES.items():
            if len(shape) == 1:
                self._w[key] = np.zeros(shape, dtype=np.float32)
            else:
                self._w[key] = _xavier(shape)

        total_params = sum(a.size for a in self._w.values())
        logger.info(
            "🎲 Random-initialised translation bridge (%s params)",
            f"{total_params:,}",
        )

    # ---- helpers -----------------------------------------------------------
    @staticmethod
    def _ensure_2d(x: np.ndarray, expected_dim: int, name: str) -> np.ndarray:
        """Ensure *x* is 2-D ``(batch, dim)``; validate last dimension."""
        x = np.asarray(x, dtype=np.float32)
        if x.ndim == 1:
            x = x[np.newaxis, :]  # (dim,) → (1, dim)
        if x.ndim != 2:
            raise ValueError(f"{name}: expected 1-D or 2-D input, got {x.ndim}-D")
        if x.shape[-1] != expected_dim:
            raise ValueError(
                f"{name}: last dimension must be {expected_dim}, got {x.shape[-1]}"
            )
        return x

    # ---- forward bridge (HDC → Dense) --------------------------------------
    def hdc_to_dense(self, hdc_vector: np.ndarray) -> np.ndarray:
        """
        Project HDC 10,000-d sparse vector(s) into 2,048-d dense space.

        Parameters
        ----------
        hdc_vector : np.ndarray
            Shape ``(10000,)`` or ``(batch, 10000)``.

        Returns
        -------
        np.ndarray
            Shape ``(2048,)`` if input was 1-D, else ``(batch, 2048)``.
        """
        x = self._ensure_2d(hdc_vector, HDC_DIM, "hdc_to_dense")
        was_1d = np.asarray(hdc_vector).ndim == 1

        # Layer 1: Linear(10000, 4096) → GELU
        x = x @ self._w[_FWD_W0].T + self._w[_FWD_B0]  # (B, 4096)
        x = _gelu(x)

        # Layer 2: Linear(4096, 2048)
        x = x @ self._w[_FWD_W2].T + self._w[_FWD_B2]  # (B, 2048)

        return x[0] if was_1d else x

    # ---- inverse bridge (Dense → HDC) --------------------------------------
    def dense_to_hdc(self, dense_vector: np.ndarray) -> np.ndarray:
        """
        Project 2,048-d dense vector(s) back to HDC 10,000-d sparse space.

        Parameters
        ----------
        dense_vector : np.ndarray
            Shape ``(2048,)`` or ``(batch, 2048)``.

        Returns
        -------
        np.ndarray
            Shape ``(10000,)`` if input was 1-D, else ``(batch, 10000)``.
        """
        x = self._ensure_2d(dense_vector, DENSE_DIM, "dense_to_hdc")
        was_1d = np.asarray(dense_vector).ndim == 1

        # Layer 1: Linear(2048, 4096) → GELU
        x = x @ self._w[_INV_W0].T + self._w[_INV_B0]  # (B, 4096)
        x = _gelu(x)

        # Layer 2: Linear(4096, 10000) → ReLU
        x = x @ self._w[_INV_W2].T + self._w[_INV_B2]  # (B, 10000)
        x = _relu(x)

        return x[0] if was_1d else x

    # ---- repr --------------------------------------------------------------
    def __repr__(self) -> str:
        total = sum(a.size for a in self._w.values())
        loaded = "trained" if self._weights_path.is_file() else "random-init"
        return (
            f"NumpyTranslationBridge("
            f"params={total:,}, "
            f"status={loaded}, "
            f"weights='{self._weights_path}')"
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_singleton: Optional[NumpyTranslationBridge] = None


def get_translation_bridge() -> NumpyTranslationBridge:
    """Return the module-level singleton ``NumpyTranslationBridge`` instance.

    Thread-safety note: Python's GIL makes the first-call race benign (at
    worst two instances are created; only one is kept).
    """
    global _singleton
    if _singleton is None:
        _singleton = NumpyTranslationBridge()
    return _singleton


# ---------------------------------------------------------------------------
# Convenience functions (drop-in replacements for old cycle_consistent API)
# ---------------------------------------------------------------------------
def hdc_to_dense(hdc_vector: np.ndarray) -> np.ndarray:
    """Convenience: HDC 10,000-d → Dense 2,048-d (uses singleton bridge)."""
    return get_translation_bridge().hdc_to_dense(hdc_vector)


def dense_to_hdc(dense_vector: np.ndarray) -> np.ndarray:
    """Convenience: Dense 2,048-d → HDC 10,000-d (uses singleton bridge)."""
    return get_translation_bridge().dense_to_hdc(dense_vector)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
    )

    print("=" * 72)
    print("  Translation Bridge — Self-Test")
    print("=" * 72)

    bridge = get_translation_bridge()
    print(f"\n{bridge!r}\n")

    # --- parameter count ---
    total_params = sum(a.size for a in bridge._w.values())
    print(f"Total parameters : {total_params:>12,}")
    fwd_params = (
        bridge._w[_FWD_W0].size
        + bridge._w[_FWD_B0].size
        + bridge._w[_FWD_W2].size
        + bridge._w[_FWD_B2].size
    )
    inv_params = (
        bridge._w[_INV_W0].size
        + bridge._w[_INV_B0].size
        + bridge._w[_INV_W2].size
        + bridge._w[_INV_B2].size
    )
    print(f"  Forward params : {fwd_params:>12,}")
    print(f"  Inverse params : {inv_params:>12,}")
    assert total_params == 98_717_456, (
        f"Expected 98,717,456 params, got {total_params:,}"
    )
    print("  ✅ Parameter count matches expected 98,717,456\n")

    # --- 1-D forward + inverse roundtrip ---
    rng = np.random.default_rng(0)
    hdc_vec = rng.standard_normal(HDC_DIM).astype(np.float32)

    t0 = time.perf_counter()
    dense_vec = bridge.hdc_to_dense(hdc_vec)
    fwd_ms = (time.perf_counter() - t0) * 1000
    assert dense_vec.shape == (DENSE_DIM,), f"Bad shape: {dense_vec.shape}"
    print(f"Forward  (1-D) : {hdc_vec.shape} → {dense_vec.shape}  [{fwd_ms:.1f} ms]")

    t0 = time.perf_counter()
    hdc_rt = bridge.dense_to_hdc(dense_vec)
    inv_ms = (time.perf_counter() - t0) * 1000
    assert hdc_rt.shape == (HDC_DIM,), f"Bad shape: {hdc_rt.shape}"
    print(f"Inverse  (1-D) : {dense_vec.shape} → {hdc_rt.shape}  [{inv_ms:.1f} ms]")

    # ReLU on inverse means output is non-negative
    assert np.all(hdc_rt >= 0.0), "Inverse output contains negative values!"
    print("  ✅ Inverse output is non-negative (ReLU applied)\n")

    # --- Batched forward + inverse ---
    batch_size = 8
    hdc_batch = rng.standard_normal((batch_size, HDC_DIM)).astype(np.float32)

    t0 = time.perf_counter()
    dense_batch = bridge.hdc_to_dense(hdc_batch)
    fwd_batch_ms = (time.perf_counter() - t0) * 1000
    assert dense_batch.shape == (batch_size, DENSE_DIM), (
        f"Bad shape: {dense_batch.shape}"
    )
    print(
        f"Forward  (batch={batch_size}) : {hdc_batch.shape} → "
        f"{dense_batch.shape}  [{fwd_batch_ms:.1f} ms]"
    )

    t0 = time.perf_counter()
    hdc_batch_rt = bridge.dense_to_hdc(dense_batch)
    inv_batch_ms = (time.perf_counter() - t0) * 1000
    assert hdc_batch_rt.shape == (batch_size, HDC_DIM), (
        f"Bad shape: {hdc_batch_rt.shape}"
    )
    print(
        f"Inverse  (batch={batch_size}) : {dense_batch.shape} → "
        f"{hdc_batch_rt.shape}  [{inv_batch_ms:.1f} ms]"
    )
    assert np.all(hdc_batch_rt >= 0.0), (
        "Batched inverse output contains negative values!"
    )
    print("  ✅ Batched roundtrip shapes and constraints OK\n")

    # --- Convenience functions ---
    dense_conv = hdc_to_dense(hdc_vec)
    np.testing.assert_array_equal(dense_conv, dense_vec)
    hdc_conv = dense_to_hdc(dense_vec)
    np.testing.assert_array_equal(hdc_conv, hdc_rt)
    print("  ✅ Convenience functions match class methods\n")

    # --- Singleton identity ---
    bridge2 = get_translation_bridge()
    assert bridge is bridge2, "Singleton returned different instance!"
    print("  ✅ Singleton pattern works\n")

    # --- GELU sanity check ---
    test_x = np.array([-3.0, -1.0, 0.0, 1.0, 3.0], dtype=np.float32)
    gelu_out = _gelu(test_x)
    # GELU(0) == 0, GELU(x) ≈ x for large positive x
    assert abs(gelu_out[2]) < 1e-7, f"GELU(0) should be 0, got {gelu_out[2]}"
    assert abs(gelu_out[4] - 3.0) < 0.01, f"GELU(3) should be ≈3.0, got {gelu_out[4]}"
    print("  ✅ GELU approximation sanity check passed\n")

    # --- Error handling ---
    try:
        bridge.hdc_to_dense(np.zeros(999))
        assert False, "Should have raised ValueError"
    except ValueError:
        print("  ✅ Dimension mismatch correctly raises ValueError")

    try:
        bridge.dense_to_hdc(np.zeros(999))
        assert False, "Should have raised ValueError"
    except ValueError:
        print("  ✅ Dimension mismatch correctly raises ValueError")

    try:
        bridge.hdc_to_dense(np.zeros((2, 3, 4)))
        assert False, "Should have raised ValueError"
    except ValueError:
        print("  ✅ 3-D input correctly raises ValueError")

    print("\n" + "=" * 72)
    print("  All self-tests PASSED ✅")
    print("=" * 72)
