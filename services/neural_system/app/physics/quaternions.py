# services/neural_system/app/physics/quaternions.py
import numpy as np

class QuaternionDynamics:
    """
    Implements Quaternion-based physics for ARCA's semantic state rotation.
    
    Concept:
    Instead of 'jumping' between thoughts (which causes confusion/instability),
    we model thought changes as smooth rotations on a hypersphere.
    
    Metrics:
    - Rotational Energy (E_rot): How fast the thought is spinning.
    - SLERP (Spherical Linear Interpolation): Smooth path finding.
    """
    
    def __init__(self):
        pass
        
    def slerp(self, q1: np.ndarray, q2: np.ndarray, t: float) -> np.ndarray:
        """
        Spherical Linear Interpolation between two quaternions/vectors.
        Inputs: q1, q2 [D] arrays (normalized).
        t: interpolation factor [0, 1].
        """
        # Ensure normalization
        q1_norm = np.linalg.norm(q1)
        q2_norm = np.linalg.norm(q2)
        if q1_norm > 0:
            q1 = q1 / q1_norm
        if q2_norm > 0:
            q2 = q2 / q2_norm
         
        # Compute dot product (cosine of angle)
        dot = np.sum(q1 * q2)
         
        # If dot < 0, negate q2 to take shorter path
        if dot < 0.0:
            q2 = -q2
            dot = -dot
             
        # Clamp to avoid numerical errors
        dot = np.clip(dot, -1.0, 1.0)
         
        theta = np.arccos(dot)
        sin_theta = np.sin(theta)
         
        # Avoid division by zero for small angles
        if np.abs(sin_theta) < 1e-6:
            return (1.0 - t) * q1 + t * q2
             
        w1 = np.sin((1.0 - t) * theta) / sin_theta
        w2 = np.sin(t * theta) / sin_theta
         
        return w1 * q1 + w2 * q2

    def compute_rotational_energy(self, q_prev: np.ndarray, q_curr: np.ndarray, dt: float = 1.0) -> float:
        """
        Calculate 'Rotational Energy' (E_rot) based on angular velocity.
        High E_rot means the system is changing its mind too fast (Whiplash).
        """
        # Angular displacement
        # Ideally, dtheta = 2 * acos(q_prev . q_curr)
        dot = np.sum(q_prev * q_curr)
        dot = np.clip(dot, -1.0, 1.0)
        dtheta = np.arccos(dot)
         
        omega = dtheta / dt # Angular velocity
         
        # E_rot = 0.5 * I * omega^2 (Assuming Moment of Inertia I=1)
        return 0.5 * (omega ** 2)