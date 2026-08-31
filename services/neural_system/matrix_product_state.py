import numpy as np
from typing import List, Tuple

class MatrixProductState:
    """
    Representation of the 'Holographic Self' using Matrix Product States (MPS).
    
    Why MPS?
    - Allows representing the joint state of N concepts with linear complexity O(N*chi^2) 
      instead of exponential O(d^N).
    - Supports 'Entanglement' (Schmidt Rank / Bond Dimension).
    - Efficiently computes overlaps <Psi|Phi> (Similarity of complex thoughts).
    
    Used for:
    - Fusing multiple concepts into a complex thought (Tensor Network).
    - Compressing the 'Global State' into a manageable footprint.
    """
    
    def __init__(self, tensors: List[np.ndarray]):
        """
        tensors: List of tensors [node_1, node_2, ... node_N]
        Each tensor is rank-3 (left_bond, physical_dim, right_bond)
        except ends which are rank-2.
        """
        self.tensors = tensors
        
    @classmethod
    def from_vectors(cls, vectors: List[np.ndarray], bond_dim: int = 10):
        """
        Create a product state (unentangled) from a list of vectors.
        Then we can evolve it to entail entanglement.
        """
        tensors = []
        for vec in vectors:
            # Reshape vector to (1, D, 1) to fit MPS chain form
            # D = physical dimension
            d = len(vec)
            # Normalize
            vec = vec / (np.linalg.norm(vec) + 1e-9)
            tensor = vec.reshape(1, d, 1) 
            tensors.append(tensor)
            
        return cls(tensors)

    def contract(self) -> np.ndarray:
        """
        Contract the MPS into a dense vector via a left-to-right sweep.

        Standard MPS left-contraction:
          result starts as T[0] reshaped to (d_0, right_bond_0)
          at each site k: result = result @ T[k].reshape(left_bond_k, d_k * right_bond_k)
          then flatten the physical dimension into the accumulated vector

        For product states (bond_dim=1) this simply concatenates / outer-products
        the physical indices.  For entangled states the bond dimension carries
        correlations.

        WARNING: Output size grows as prod(d_k) — use only for small N or
        small physical dimensions.

        Returns:
            1D numpy array representing the contracted MPS state vector.
        """
        if not self.tensors:
            return np.array([1.0], dtype=np.float64)

        # Validate all tensors are rank-3
        validated: List[np.ndarray] = []
        for t in self.tensors:
            arr = np.asarray(t, dtype=np.float64)
            if arr.ndim == 2:
                # Rank-2 edge tensor: treat as (1, d, 1) or (left, d)
                arr = arr[np.newaxis, :, :]  # (1, d, right) — rare edge case
            if arr.ndim != 3:
                raise ValueError(f"MPS tensor must be rank-3, got shape {arr.shape}")
            validated.append(arr)

        # Left boundary: site 0 → shape (left=1, d_0, right_0) → collapse left
        # result shape: (d_0, right_0)
        result = validated[0][0, :, :]  # (d_0, right_0)

        for k in range(1, len(validated)):
            left_bond, d_k, right_bond = validated[k].shape
            # result: (physical_accumulated, left_bond)
            # T[k]:   (left_bond, d_k, right_bond)
            # Contract over left_bond:
            #   new_result: (physical_accumulated * d_k, right_bond)
            t_k = validated[k].reshape(left_bond, d_k * right_bond)  # (lb, d_k*rb)
            result = result @ t_k  # (phys_acc, d_k * right_bond)
            # result currently has shape (phys_acc, d_k * right_bond)
            # Keep flat — the physical dimension is implicitly tracked in the row count

        # Final result: collapse any remaining right virtual bond
        # If last bond dim > 1, average over it (projection to state vector)
        if result.ndim == 2 and result.shape[1] > 1:
            result = result.mean(axis=1)
        elif result.ndim == 2:
            result = result[:, 0]

        # L2-normalise the state vector
        norm = float(np.linalg.norm(result))
        if norm > 1e-12:
            result = result / norm

        return result.astype(np.float64)

    def calculate_overlap(self, other: 'MatrixProductState') -> float:
        """
        Compute <Self | Other>.
        Efficient O(N) calculation.
        """
        if len(self.tensors) != len(other.tensors):
            return 0.0
            
        # Left-to-right contraction of the transfer matrix
        # E = Sum_s (A[s] * B[s]*)
        
        # Start with identity (scalar)
        left_env = np.ones((1, 1))
        
        for T1, T2 in zip(self.tensors, other.tensors):
            # T1 shape: (a, d, b)
            # T2 shape: (a', d, b')
            # environment shape: (a, a')
            
            # Contract T1 with Env: (d, b, a')
            temp = np.tensordot(left_env, T1, axes=(0, 0)) 
            
            # Contract with T2 (conjugate): (b, b')
            # T2 -> (a', d, b') 
            # We enforce physical dim 'd' matches
            # Temp (a', d, b)
            # T2 (a', d, b')
            # Contract over a' and d
            left_env = np.tensordot(temp, T2, axes=([0, 1], [0, 1]))
            
        return float(left_env[0, 0])
