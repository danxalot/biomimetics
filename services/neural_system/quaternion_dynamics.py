import numpy as np
from dataclasses import dataclass
from typing import Tuple

@dataclass
class QDC:
    """Quaternion Dynamics Container"""
    q: np.ndarray       # [w, x, y, z] - Orientation
    omega: np.ndarray   # [x, y, z]    - Angular Velocity
    alpha: np.ndarray   # [x, y, z]    - Angular Acceleration

class QuaternionDynamics:
    """
    Manages continuous orientation of system state using Quaternions.
    Used for smooth interpolation of concept states to prevent 'teleporting'.
    """
    
    @staticmethod
    def slerp(q0: np.ndarray, q1: np.ndarray, t: float) -> np.ndarray:
        """Spherical Linear Interpolation between two quaternions."""
        # Normalize
        q0 = q0 / np.linalg.norm(q0)
        q1 = q1 / np.linalg.norm(q1)
        
        dot = np.dot(q0, q1)
        
        # If dot is negative, slerp won't take the shorter path. Fix by negating one.
        if dot < 0.0:
            q1 = -q1
            dot = -dot
            
        if dot > 0.9995:
            # Too close, linear interpolation is fine
            result = q0 + t * (q1 - q0)
            return result / np.linalg.norm(result)
            
        theta_0 = np.arccos(dot)
        sin_theta_0 = np.sin(theta_0)
        
        theta = theta_0 * t
        sin_theta = np.sin(theta)
        
        s0 = np.cos(theta) - dot * sin_theta / sin_theta_0
        s1 = sin_theta / sin_theta_0
        
        return (s0 * q0) + (s1 * q1)

    @staticmethod
    def compute_rotational_energy(omega: np.ndarray, inertia: float = 1.0) -> float:
        """
        Computes Rotational Kinetic Energy: E = 0.5 * I * omega^2
        """
        return 0.5 * inertia * np.dot(omega, omega)

    @staticmethod
    def update_state(current: QDC, torque: np.ndarray, dt: float, damping: float = 0.95) -> QDC:
        """
        Updates the quaternion state based on applied torque (Force).
        """
        # 1. Update Acceleration (alpha = Torque / I)
        alpha = torque  # Assuming I=1 for simplicity
        
        # 2. Update Velocity (omega += alpha * dt)
        omega_new = (current.omega + alpha * dt) * damping # Damping
        
        # 3. Update Orientation (q += 0.5 * w * q * dt)
        # q_dot = 0.5 * omega * q
        # Quaternion multiplication representation of omega (pure quaternion [0, wx, wy, wz])
        w_q = np.array([0, *omega_new])
        
        # Standard quat multiplication rules for w_q * q
        # ... simplified for update:
        # q_new = q + 0.5 * w * q * dt (Using small angle approx/integration)
        
        # To keep it robust, convert omega to axis-angle rotation
        theta_mag = np.linalg.norm(omega_new) * dt
        if theta_mag > 1e-6:
            axis = omega_new / np.linalg.norm(omega_new)
            delta_q = np.array([np.cos(theta_mag/2), *(axis * np.sin(theta_mag/2))])
            
            # Multiply q_new = delta_q * q_current (Hamilton product)
            w1, x1, y1, z1 = delta_q
            w2, x2, y2, z2 = current.q
            
            w = w1*w2 - x1*x2 - y1*y2 - z1*z2
            x = w1*x2 + x1*w2 + y1*z2 - z1*y2
            y = w1*y2 - x1*z2 + y1*w2 + z1*x2
            z = w1*z2 + x1*y2 - y1*x2 + z1*w2
            
            q_new = np.array([w, x, y, z])
            q_new = q_new / np.linalg.norm(q_new)
        else:
            q_new = current.q

        return QDC(q=q_new, omega=omega_new, alpha=alpha)
