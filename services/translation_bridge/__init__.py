"""
Translation Bridge Module
=========================

Converts between Pythia's 10,000-dimensional HDC vectors and
2,048-dimensional dense embedding space.
"""

from .translation_bridge import (
    get_translation_bridge,
    hdc_to_dense,
    dense_to_hdc,
    NumpyTranslationBridge,
    HDC_DIM,
    DENSE_DIM,
    HIDDEN_DIM,
)

__all__ = [
    "get_translation_bridge",
    "hdc_to_dense",
    "dense_to_hdc",
    "NumpyTranslationBridge",
    "HDC_DIM",
    "DENSE_DIM",
    "HIDDEN_DIM",
]
