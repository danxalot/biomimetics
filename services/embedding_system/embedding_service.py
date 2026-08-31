"""
DEPRECATED - embedding_service.py
==================================

This script is DEPRECATED.

Model conversion resources are available elsewhere.
Do NOT use this script for new development.

If you need model conversion, use resources outside this script.

For reference only - original functionality:
  - SigLIP conversion via torch/transformers/optimum
  - Google Text Embedding Service
  - Oracle database storage
  - SentenceTransformers for local inference

Last updated: 2026-04-28
Status: DEPRECATED - DO NOT USE
"""

import os
import logging

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

logger.warning("=" * 60)
logger.warning("DEPRECATED: embedding_service.py")
logger.warning("This script is NO LONGER MAINTAINED.")
logger.warning("Model conversion resources are available ELSEWHERE.")
logger.warning("Do NOT use this for new development.")
logger.warning("=" * 60)


def deprecated_warning():
    """Print deprecation warning."""
    print("=" * 60)
    print(" DEPRECATED: embedding_service.py")
    print(" This script is NO LONGER MAINTAINED.")
    print(" Model conversion resources are available ELSEWHERE.")
    print(" Do NOT use this for new development.")
    print("=" * 60)


# Stub functions that raise errors if anyone tries to use them
class DeprecatedError(Exception):
    """Exception raised when trying to use deprecated functionality."""
    pass


def convert_siglip(*args, **kwargs):
    """DEPRECATED - Do not use."""
    raise DeprecatedError(
        "convert_siglip is DEPRECATED. "
        "Use model conversion resources elsewhere."
    )


# Maintain minimal imports for backward compatibility
try:
    from dataclasses import dataclass
except ImportError:
    pass

try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    import oracledb
except ImportError:
    oracledb = None

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None


if __name__ == "__main__":
    deprecated_warning()
    print("\nThis script is deprecated. Exiting.")
    print("Use your existing model conversion resources instead.\n")
