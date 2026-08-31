import numpy as np

def apply_householder_rotation(vector_32: np.ndarray, rotor_32: np.ndarray) -> np.ndarray:
    """NumPy-pure fallback for Cl(4,1) rotation without Cayley tensor.
    Uses Householder reflection to simulate geometric transformation.
    For true rotor (two reflections), call twice."""
    rotor_norm = np.linalg.norm(rotor_32) + 1e-12
    r = rotor_32 / rotor_norm
    dot_product = np.dot(vector_32, r)
    rotated = vector_32 - 2 * dot_product * r
    return rotated / (np.linalg.norm(rotated) + 1e-12)


def apply_householder_reflection_twice(vector_32: np.ndarray, rotor_32: np.ndarray) -> np.ndarray:
    """Apply Householder twice to simulate true rotor (two reflections)."""
    once = apply_householder_rotation(vector_32, rotor_32)
    twice = apply_householder_rotation(once, rotor_32)
    return twice


def extract_bivector_component(rotor_32: np.ndarray) -> float:
    """Extract bivector norm (indices 6-15) for phase coupling."""
    return np.linalg.norm(rotor_32[6:16])


def extract_translation_component(rotor_32: np.ndarray) -> float:
    """Extract translation component (indices 1-5) for Poincaré movement."""
    return np.linalg.norm(rotor_32[1:5])