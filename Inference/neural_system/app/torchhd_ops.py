"""
NumPy HDC Operations for ARCA Neural System
==========================================

Provides unified HDC operations using pure NumPy.
All HDC-related modules should import from this file.

Usage:
    from torchhd_ops import random_hv, bind, bundle, permute, similarity

    # Create hypervectors
    hv1 = random_hv(10000)
    hv2 = random_hv(10000)

    # Operations
    bound = bind(hv1, hv2)
    bundled = bundle([hv1, hv2])
    permuted = permute(hv1, shifts=1)
    sim = similarity(hv1, hv2)
"""

import numpy as np
from typing import List, Optional, Union

# Default dimensions
DEFAULT_DIM = 10000


def _ensure_array(x: Union[np.ndarray, list]) -> np.ndarray:
    """Ensure input is a NumPy array."""
    if isinstance(x, list):
        return np.array(x, dtype=np.float32)
    return np.asarray(x, dtype=np.float32)


def random_hv(
    dim: int = DEFAULT_DIM, 
    batch_size: int = 1,
    seed: Optional[int] = None,
    device: str = "cpu"  # Kept for API compatibility, ignored
) -> np.ndarray:
    """
    Generate random bipolar hypervector(s).
    
    Args:
        dim: Dimensionality of hypervector
        batch_size: Number of vectors to generate
        seed: Optional seed for reproducibility
        device: Device to create tensor on (ignored for NumPy)
    
    Returns:
        Array of shape [batch_size, dim] with values in {-1, +1}
    """
    if seed is not None:
        # Create a local random state to avoid affecting global state
        rng = np.random.RandomState(seed)
        return rng.randint(0, 2, (batch_size, dim)).astype(np.float32) * 2 - 1
    else:
        return np.random.randint(0, 2, (batch_size, dim)).astype(np.float32) * 2 - 1


def bind(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """
    Bind two hypervectors (multiplicative/XOR binding).
    
    For bipolar {-1, +1}: element-wise multiplication
    For binary {0, 1}: XOR (not implemented as we use bipolar)
    
    Properties:
    - bind(a, b) = bind(b, a) (commutative)
    - bind(a, bind(a, b)) = b (self-inverse)
    - Preserves similarity structure
    """
    a = _ensure_array(a)
    b = _ensure_array(b)
    
    # Ensure same shape
    if a.shape != b.shape:
        # Broadcast if possible
        if a.ndim == 1 and b.ndim == 2 and a.shape[0] == b.shape[1]:
            a = a.reshape(1, -1)
        elif b.ndim == 1 and a.ndim == 2 and b.shape[0] == a.shape[1]:
            b = b.reshape(1, -1)
        elif a.shape != b.shape:
            raise ValueError(f"Shape mismatch: {a.shape} vs {b.shape}")
    
    # Element-wise multiplication for bipolar binding
    return a * b


def bundle(vectors: List[Union[np.ndarray, list]], normalize: bool = True) -> np.ndarray:
    """
    Bundle multiple hypervectors (additive superposition).
    
    The result is similar to all input vectors.
    
    Args:
        vectors: List of hypervectors to bundle
        normalize: If True, threshold to {-1, +1}
    
    Returns:
        Bundled hypervector
    """
    if not vectors:
        raise ValueError("Cannot bundle empty list")
    
    # Convert all to arrays
    arrays = [_ensure_array(v) for v in vectors]
    
    # Stack and sum
    stacked = np.stack(arrays, axis=0)
    bundled = np.sum(stacked, axis=0)
    
    if normalize:
        # Threshold: positive -> +1, negative -> -1, zero -> random
        bundled = np.sign(bundled)
        zeros = (bundled == 0)
        if np.any(zeros):
            # Generate random values for zeros
            random_vals = np.random.randint(0, 2, size=zeros.sum()).astype(np.float32) * 2 - 1
            bundled = bundled.copy()  # Avoid modifying potential read-only array
            bundled[zeros] = random_vals
    
    return bundled.astype(np.float32)


def permute(hv: Union[np.ndarray, list], shifts: int = 1) -> np.ndarray:
    """
    Permute (circular shift) a hypervector.
    
    Used for positional/sequence encoding.
    permute(a, n) is dissimilar to a for n > 0.
    """
    hv = _ensure_array(hv)
    return np.roll(hv, shift=shifts, axis=-1)


def similarity(a: Union[np.ndarray, list], b: Union[np.ndarray, list]) -> float:
    """
    Compute cosine similarity between hypervectors.
    
    Returns:
        Similarity in range [-1, +1]
        +1 = identical
        0 = orthogonal (random)
        -1 = opposite
    """
    a = _ensure_array(a)
    b = _ensure_array(b)
    
    # Flatten for computation
    a_flat = a.flatten()
    b_flat = b.flatten()
    
    # Compute cosine similarity
    dot_product = np.dot(a_flat, b_flat)
    norm_a = np.linalg.norm(a_flat)
    norm_b = np.linalg.norm(b_flat)
    
    # Avoid division by zero
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return float(dot_product / (norm_a * norm_b))


def hamming_similarity(a: Union[np.ndarray, list], b: Union[np.ndarray, list]) -> float:
    """
    Compute Hamming similarity (for binary vectors converted from bipolar).
    
    Returns:
        Similarity in range [-1, +1]
    """
    a = _ensure_array(a)
    b = _ensure_array(b)
    
    # Convert to binary if bipolar (>{0} -> 1, <={0} -> 0)
    a_bin = (a > 0).astype(np.float32)
    b_bin = (b > 0).astype(np.float32)
    
    matches = np.sum(a_bin == b_bin)
    total = a.size
    
    return float(2 * matches / total - 1)


def create_basis_vectors(
    names: List[str],
    dim: int = DEFAULT_DIM
) -> dict:
    """
    Create deterministic basis vectors for named concepts.
    
    Same name always produces same vector.
    
    Args:
        names: List of concept names
        dim: Dimensionality
    
    Returns:
        Dict mapping name -> hypervector
    """
    basis = {}
    for name in names:
        seed = hash(name) % (2**32)
        basis[name] = random_hv(dim, seed=seed)
    return basis


def encode_sequence(
    item_hvs: List[Union[np.ndarray, list]],
    positional: bool = True
) -> np.ndarray:
    """
    Encode a sequence of items.
    
    Uses permutation for positional encoding.
    """
    if not item_hvs:
        raise ValueError("Cannot encode empty sequence")
    
    # Convert to arrays
    arrays = [_ensure_array(hv) for hv in item_hvs]
    
    if positional:
        # Apply position-dependent permutation
        positioned = [
            permute(hv, shifts=i) 
            for i, hv in enumerate(arrays)
        ]
        return bundle(positioned)
    else:
        return bundle(arrays)


def thermometer_encode(
    value: float,
    min_val: float = 0.0,
    max_val: float = 1.0,
    levels: int = 100,
    dim: int = DEFAULT_DIM
) -> np.ndarray:
    """
    Thermometer encoding for continuous values.
    
    Preserves ordinal relationships:
    similarity(encode(a), encode(b)) increases as |a - b| decreases
    """
    # Normalize to [0, 1]
    normalized = max(0.0, min(1.0, (value - min_val) / (max_val - min_val)))
    active_levels = int(normalized * levels)
    
    # Generate level vectors
    level_hvs = [
        random_hv(dim, seed=i)
        for i in range(active_levels)
    ]
    
    if not level_hvs:
        return random_hv(dim, seed=0)  # Empty/zero value
    
    return bundle(level_hvs)


# Backward compatibility alias
HDCOps = {
    'random_hv': random_hv,
    'bind': bind,
    'bundle': bundle,
    'permute': permute,
    'similarity': similarity,
    'hamming_similarity': hamming_similarity,
    'create_basis_vectors': create_basis_vectors,
    'encode_sequence': encode_sequence,
    'thermometer_encode': thermometer_encode
}