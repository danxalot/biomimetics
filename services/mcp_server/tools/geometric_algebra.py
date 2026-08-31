import numpy as np

class GeometricOperator:
    """
    Implements a Geometric Operator Layer over Hyperdimensional Vectors using Block-Quaternions.
    
    This treats a D-dimensional hypervector as D/4 Quaternions.
    It allows for smooth rotations (Rotors), Momentum tracking, and Manifold Shaping.
    
    Mathematical Basis:
    - State V is in R^D.
    - We reshape V to (D/4, 4) where each row is a quaternion q = w + xi + yj + zk.
    - A Rotor R is a unit quaternion.
    - Rotation: v' = R * v * R_conjugate (Hamilton product applied block-wise).
    
    This unifies:
    1. "Dynamics": Application of rotors over time.
    2. "Momentum": The rotor difference between V_t and V_{t-1}.
    3. "Shaping": Applying gravitational rotors to deform the state towards an attractor.
    """
    
    def __init__(self, dimensionality=10000):
        if dimensionality % 4 != 0:
            raise ValueError("Dimensionality must be divisible by 4 for block-quaternion encoding.")
        
        self.dim = dimensionality
        self.num_quats = dimensionality // 4
        
        # Identity Quaternion (w=1, x=0, y=0, z=0)
        self.identity_quat = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)

    def to_quaternions(self, vector):
        """Reshapes a (D,) vector into (D/4, 4) quaternion blocks."""
        # Ensure vector is float for geometric operations (even if HDC is binary/bipolar)
        v_float = vector.astype(np.float32)
        # Pad if necessary (though init checks dim % 4)
        return v_float.reshape(self.num_quats, 4)
    
    def from_quaternions(self, quats):
        """Flattens (D/4, 4) quaternion blocks back to (D,) vector."""
        return quats.flatten()

    def multiply_quaternions(self, q1, q2):
        """
        Hamilton Product of two arrays of quaternions (vectorized).
        q1, q2 shapes: (N, 4) or broadcastable.
        Order: w, x, y, z
        """
        w1, x1, y1, z1 = q1[..., 0], q1[..., 1], q1[..., 2], q1[..., 3]
        w2, x2, y2, z2 = q2[..., 0], q2[..., 1], q2[..., 2], q2[..., 3]
        
        w = w1*w2 - x1*x2 - y1*y2 - z1*z2
        x = w1*x2 + x1*w2 + y1*z2 - z1*y2
        y = w1*y2 - x1*z2 + y1*w2 + z1*x2
        z = w1*z2 + x1*y2 - y1*x2 + z1*w2
        
        return np.stack([w, x, y, z], axis=-1)

    def conjugate(self, q):
        """Returns the conjugate of quaternions (w, -x, -y, -z)."""
        conjs = q.copy()
        conjs[..., 1:] *= -1
        return conjs
    
    def normalize(self, q):
        """Normalizes quaternions to unit length."""
        norms = np.linalg.norm(q, axis=-1, keepdims=True)
        # Avoid division by zero
        norms[norms < 1e-8] = 1.0 
        return q / norms

    def apply_rotor(self, vector, rotor):
        """
        Rotates the vector state V using Rotor R.
        Operation: V' = R * V * R_conjugate (sandwich product).
        
        Args:
            vector: (D,) numpy array.
            rotor: (4,) unit quaternion (global rotation) OR (D/4, 4) (local field).
            
        Returns:
            Rotated vector (D,).
        """
        # 1. Convert State to Quaternion View
        q_state = self.to_quaternions(vector)
        
        # 2. Prepare Rotor
        if rotor.ndim == 1 and rotor.shape == (4,):
            # Broadcast global rotor
            q_rotor = np.tile(rotor, (self.num_quats, 1))
        else:
            q_rotor = rotor
            
        # 3. Apply Rotation: R * V * R_conj
        q_rotor_conj = self.conjugate(q_rotor)
        
        # R * V
        temp = self.multiply_quaternions(q_rotor, q_state)
        # (R * V) * R_conj
        rotated_q = self.multiply_quaternions(temp, q_rotor_conj)
        
        return self.from_quaternions(rotated_q)

    def get_momentum(self, v_prev, v_curr):
        """
        Calculates the 'Momentum' (Rotor) required to transform v_prev to v_curr.
        This represents the 'Velocity' of the conversation.
        
        Note: True calculation of the 'best fit' rotor between two separate high-dim vectors
        is complex (Kabsch algorithm). 
        
        For Block-Quaternions, we compute the delta quaternion per block: Q_delta = Q_curr * Q_prev_inverse.
        Then we average them to find the 'Global Momentum' of the system.
        
        Returns:
            (4,) Global Momentum Rotor (unit quaternion).
        """
        q_prev = self.to_quaternions(v_prev)
        q_curr = self.to_quaternions(v_curr)
        
        # Q_prev_inverse = Q_prev_conj / |Q_prev|^2
        # Assuming roughly normalized inputs, approximate with Conjugate
        q_prev_conj = self.conjugate(self.normalize(q_prev))
        q_curr_norm = self.normalize(q_curr)
        
        # Delta = Curr * Prev_inv
        # Wait, for rotation V' = R V R', recovering R is ambiguous (could be -R).
        # Simplified 'Translation' Momentum for High-Dim Space:
        # We model momentum simply as the quaternion difference or ratio.
        
        # Let's use the Geometric Product approach: M = V_curr * V_prev_inverse
        # This gives a transform.
        momentum_blocks = self.multiply_quaternions(q_curr_norm, q_prev_conj)
        
        # Average the blocks to get the "Global Heading" of the conversation
        global_momentum = np.mean(momentum_blocks, axis=0)
        
        # Normalize result
        norm = np.linalg.norm(global_momentum)
        if norm < 1e-8:
            return self.identity_quat
        return global_momentum / norm

    def shape_manifold(self, vector, attraction_point, strength=0.1):
        """
        'Shapes' the manifold by pulling the vector towards an attractor point using a SLERP-like rotation.
        
        Args:
            vector: Current state.
            attraction_point: Target state (Attractor).
            strength: 0.0 to 1.0 (How much to pull).
            
        Returns:
            Shaped vector.
        """
        # This is effectively SLERP (Spherical Linear Interpolation) in the Block-Quaternion space.
        # But since we treat the whole D-vector as state, simple linear interpolation + renorm 
        # is often sufficient and equivalent to SLERP for small angles in high dimensions.
        
        # V_new = (1-a)V + a*Target
        v_shaped = (1 - strength) * vector + strength * attraction_point
        
        # Renormalize to maintain energy
        norm = np.linalg.norm(v_shaped)
        if norm > 1e-8:
            v_shaped = v_shaped / norm
            # Scale back to original magnitude if needed? 
            # HDC vectors usually have magnitude ~sqrt(D). 
            # If input was bipolar {-1, 1}, we might want to sign() it back?
            # For "Soft" Manifold, keep it continuous floats.
            
        return v_shaped
