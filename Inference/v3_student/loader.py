"""
loader.py — Single entry point for loading the V3 NumPy student stack.

Usage (from neural_system):
    from Inference.v3_student.loader import load_v3_student
    stack = load_v3_student("/path/to/pythia_c3_v3_65k.npz")
    # stack.forward(x)  or  stack.step(x_t)

Replaces NumpyPythiaManifold's weight-loading in phenomenological_core.py.
The engine object exposes forward(x) → (B,T,768) and step(x_t) → (B,768).
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def load_v3_student(npz_path: str):
    """Load and return a ready VersorMemMambaStackNP from an npz checkpoint.

    Parameters
    ----------
    npz_path : str
        Absolute path to pythia_c3_v3_65k.npz (or equivalent V3 student npz).

    Returns
    -------
    VersorMemMambaStackNP
        A fully loaded, ready-to-infer 32-layer NumPy stack.

    Raises
    ------
    FileNotFoundError
        If the npz file does not exist at the given path.
    ValueError
        If key completeness assertion fails (missing or leftover keys).
    KeyError
        If a specific expected key is absent from the npz.
    """
    if not os.path.isfile(npz_path):
        raise FileNotFoundError(
            f"V3 student npz not found at: '{npz_path}'\n"
            "Ensure pythia_c3_v3_65k.npz is mounted at the correct path."
        )

    logger.info("load_v3_student: loading from '%s'", npz_path)

    from .numpy_stack import VersorMemMambaStackNP
    stack = VersorMemMambaStackNP.from_npz(npz_path)

    if not stack.is_ready:
        raise RuntimeError("VersorMemMambaStackNP.is_ready is False after load — unexpected.")

    logger.info(
        "load_v3_student: OK — 32 layers, d_model=768, d_state=256, nheads=24"
    )
    return stack
