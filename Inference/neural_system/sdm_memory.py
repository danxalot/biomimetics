"""
Sparse Distributed Memory (SDM) - Kanerva Memory
=================================================

Implements Pentti Kanerva's Sparse Distributed Memory for auto-associative
recall in the ARCA neural system.

Key Features:
- Fixed number of "hard locations" (address neurons)
- Activation radius determines which locations participate
- Graceful degradation under noise
- Auto-associative cleanup of partial/noisy patterns

References:
- Kanerva, P. (1988). Sparse Distributed Memory
- https://github.com/ctn-waterloo/sdm
"""

import numpy as np
import logging
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
import time

logger = logging.getLogger("SDMMemory")


@dataclass
class SDMConfig:
    """Configuration for Sparse Distributed Memory."""
    address_dim: int = 10000  # Dimension of address space (HDC dimension)
    data_dim: int = 10000     # Dimension of stored data
    num_hard_locations: int = 100000  # Number of hard address locations
    activation_radius: int = 451  # Hamming distance threshold (~1000 active)
    

class SDMMemory:
    """
    Sparse Distributed Memory for auto-associative recall.
    
    Given a noisy or partial vector, retrieves the nearest stored pattern.
    This is the "cleanup memory" that finds stable attractors.
    
    Architecture:
    - Hard Locations: Random binary addresses (fixed at init)
    - Counters: Integer accumulators for each bit position
    - Read/Write: Select locations within activation_radius, accumulate
    """
    
    def __init__(self, config: Optional[SDMConfig] = None):
        self.config = config or SDMConfig()
        
        self.address_dim = self.config.address_dim
        self.data_dim = self.config.data_dim
        self.num_locations = self.config.num_hard_locations
        self.activation_radius = self.config.activation_radius
        
        # Initialize hard locations as random binary addresses
        # Packed as uint8 for memory efficiency (8 bits per byte)
        self.packed_dim = self.address_dim // 8
        
        logger.info(f"Initializing SDM with {self.num_locations} hard locations...")
        
        # Generate random binary addresses for hard locations
        self._addresses = np.random.randint(
            0, 256, 
            size=(self.num_locations, self.packed_dim), 
            dtype=np.uint8
        )
        
        # Counters for data storage (int16 allows +/- 32767 writes)
        # Shape: [num_locations, data_dim]
        self._counters = np.zeros(
            (self.num_locations, self.data_dim), 
            dtype=np.int16
        )
        
        # Statistics
        self.write_count = 0
        self.read_count = 0
        
        logger.info(f"SDM initialized: {self.num_locations} locations, "
                   f"address_dim={self.address_dim}, data_dim={self.data_dim}")
    
    def _pack_binary(self, binary_vector: np.ndarray) -> np.ndarray:
        """Pack binary vector (0/1 or -1/1) into uint8."""
        # Convert bipolar (-1/1) to binary (0/1) if needed
        if binary_vector.min() < 0:
            binary_vector = (binary_vector + 1) // 2
        
        binary_vector = binary_vector.astype(np.uint8)
        
        # Pack 8 bits per byte
        packed = np.packbits(binary_vector)
        return packed
    
    def _unpack_binary(self, packed: np.ndarray) -> np.ndarray:
        """Unpack uint8 to binary vector."""
        return np.unpackbits(packed)[:self.address_dim]
    
    def _hamming_distance_packed(self, packed_a: np.ndarray, packed_b: np.ndarray) -> int:
        """Compute Hamming distance between two packed binary vectors."""
        xor_result = np.bitwise_xor(packed_a, packed_b)
        # Count bits using lookup or popcount
        return np.unpackbits(xor_result).sum()
    
    def _get_active_locations(self, address: np.ndarray) -> np.ndarray:
        """
        Find all hard locations within activation_radius of the address.
        Returns indices of active locations.
        """
        packed_address = self._pack_binary(address)
        
        # Compute Hamming distances to all locations (vectorized)
        xor_all = np.bitwise_xor(self._addresses, packed_address)
        
        # Count bits in each row
        distances = np.zeros(self.num_locations, dtype=np.int32)
        for i in range(self.packed_dim):
            # Use lookup table for bit counting
            distances += np.array([bin(x).count('1') for x in xor_all[:, i]], dtype=np.int32)
        
        # Find locations within radius
        active_mask = distances <= self.activation_radius
        return np.where(active_mask)[0]
    
    def _get_active_locations_fast(self, address: np.ndarray, 
                                   sample_size: int = 10000) -> np.ndarray:
        """
        Fast approximate version: sample locations and find nearest.
        For very large SDM, exact computation is slow.
        """
        packed_address = self._pack_binary(address)
        
        # Sample a subset of locations
        if sample_size < self.num_locations:
            sample_indices = np.random.choice(
                self.num_locations, sample_size, replace=False
            )
            sample_addresses = self._addresses[sample_indices]
        else:
            sample_indices = np.arange(self.num_locations)
            sample_addresses = self._addresses
        
        # Compute distances
        xor_all = np.bitwise_xor(sample_addresses, packed_address)
        
        # Vectorized popcount using numpy
        # Unpack each row and sum
        distances = np.array([
            np.unpackbits(row).sum() for row in xor_all
        ], dtype=np.int32)
        
        # Find locations within radius
        active_mask = distances <= self.activation_radius
        return sample_indices[active_mask]
    
    def write(self, address: np.ndarray, data: np.ndarray) -> Dict[str, Any]:
        """
        Write data to SDM at the given address.
        
        Args:
            address: Binary address vector [address_dim] (0/1 or -1/1)
            data: Binary data vector [data_dim] (0/1 or -1/1)
            
        Returns:
            Stats about the write operation
        """
        # Convert data to bipolar for counter update
        if data.min() >= 0:  # Binary (0/1)
            data_bipolar = 2 * data.astype(np.int16) - 1
        else:  # Already bipolar
            data_bipolar = data.astype(np.int16)
        
        # Find active locations
        active_indices = self._get_active_locations_fast(address)
        num_active = len(active_indices)
        
        if num_active == 0:
            logger.warning("No active locations found for write - consider increasing radius")
            return {"success": False, "active_locations": 0}
        
        # Update counters at active locations
        self._counters[active_indices] += data_bipolar
        
        self.write_count += 1
        
        logger.debug(f"SDM write: {num_active} active locations updated")
        
        return {
            "success": True,
            "active_locations": num_active,
            "total_writes": self.write_count
        }
    
    def read(self, address: np.ndarray, 
             return_confidence: bool = False) -> np.ndarray:
        """
        Read from SDM at the given address.
        
        Args:
            address: Binary address vector [address_dim]
            return_confidence: If True, return (data, confidence) tuple
            
        Returns:
            Retrieved binary data vector [data_dim] (bipolar -1/1)
        """
        # Find active locations
        active_indices = self._get_active_locations_fast(address)
        num_active = len(active_indices)
        
        if num_active == 0:
            logger.warning("No active locations found for read")
            result = np.zeros(self.data_dim, dtype=np.int8)
            if return_confidence:
                return result, 0.0
            return result
        
        # Sum counters at active locations
        counter_sum = self._counters[active_indices].sum(axis=0)
        
        # Threshold to get binary output
        data_out = np.sign(counter_sum).astype(np.int8)
        data_out[data_out == 0] = 1  # Tie-break
        
        self.read_count += 1
        
        if return_confidence:
            # Confidence = average magnitude / num_active
            confidence = np.abs(counter_sum).mean() / max(num_active, 1)
            return data_out, float(confidence)
        
        return data_out
    
    def cleanup(self, noisy_pattern: np.ndarray, 
                iterations: int = 3) -> np.ndarray:
        """
        Iterative cleanup: Use the pattern as both address and data.
        Converges to nearest stored attractor.
        
        Args:
            noisy_pattern: Noisy/partial binary pattern to clean up
            iterations: Number of cleanup iterations
            
        Returns:
            Cleaned pattern (nearest stored attractor)
        """
        pattern = noisy_pattern.copy()
        
        for i in range(iterations):
            # Read using pattern as address
            retrieved = self.read(pattern)
            
            # Check convergence
            if np.array_equal(pattern, retrieved):
                logger.debug(f"SDM cleanup converged after {i+1} iterations")
                break
            
            pattern = retrieved
        
        return pattern
    
    def store_attractor(self, pattern: np.ndarray) -> Dict[str, Any]:
        """
        Store a pattern as an attractor (write it to itself).
        
        This makes the pattern a stable fixed point in the SDM.
        """
        return self.write(pattern, pattern)
    
    def query_similarity(self, query: np.ndarray, 
                        stored_patterns: List[np.ndarray]) -> List[float]:
        """
        Query how similar the retrieved pattern is to known patterns.
        """
        retrieved = self.read(query)
        
        similarities = []
        for pattern in stored_patterns:
            # Hamming similarity
            matches = (retrieved == pattern).sum()
            similarity = matches / self.data_dim
            similarities.append(similarity)
        
        return similarities
    
    def get_stats(self) -> Dict[str, Any]:
        """Return memory statistics."""
        # Counter saturation check
        counter_max = np.abs(self._counters).max()
        saturation = counter_max / 32767  # int16 max
        
        # Estimate number of stored patterns (heuristic)
        nonzero_locations = (self._counters != 0).any(axis=1).sum()
        
        return {
            "num_locations": self.num_locations,
            "address_dim": self.address_dim,
            "data_dim": self.data_dim,
            "activation_radius": self.activation_radius,
            "write_count": self.write_count,
            "read_count": self.read_count,
            "counter_saturation": float(saturation),
            "active_locations_estimate": int(nonzero_locations)
        }
    
    def decay(self, factor: float = 0.99) -> None:
        """
        Apply decay to counters (forgetting).
        Reduces all counter magnitudes toward zero.
        """
        self._counters = (self._counters * factor).astype(np.int16)
        logger.debug(f"Applied decay factor {factor} to SDM counters")


class SDMMemoryCompact:
    """
    Lightweight SDM for resource-constrained environments.
    Uses lazy initialization and smaller default sizes.
    """
    
    def __init__(self, 
                 address_dim: int = 4096,
                 num_locations: int = 10000,
                 activation_radius: int = 200):
        
        self.address_dim = address_dim
        self.num_locations = num_locations
        self.activation_radius = activation_radius
        
        # Lazy initialization
        self._initialized = False
        self._addresses = None
        self._counters = None
    
    def _ensure_initialized(self):
        if not self._initialized:
            logger.info(f"Lazy-initializing compact SDM ({self.num_locations} locations)")
            
            # Generate addresses on demand
            self._addresses = np.random.randint(
                0, 256,
                size=(self.num_locations, self.address_dim // 8),
                dtype=np.uint8
            )
            
            self._counters = np.zeros(
                (self.num_locations, self.address_dim),
                dtype=np.int8  # Smaller counters
            )
            
            self._initialized = True
    
    def write(self, address: np.ndarray, data: np.ndarray):
        self._ensure_initialized()
        # Simplified write - find nearest locations and update
        packed = np.packbits((address > 0).astype(np.uint8))
        
        # Sample and find nearest
        sample_idx = np.random.choice(self.num_locations, 1000, replace=False)
        xor_result = np.bitwise_xor(self._addresses[sample_idx], packed)
        distances = np.array([np.unpackbits(row).sum() for row in xor_result])
        
        # Activate nearest
        active = sample_idx[distances < self.activation_radius]
        if len(active) > 0:
            data_bipolar = np.sign(data).astype(np.int8)
            data_bipolar[data_bipolar == 0] = 1
            self._counters[active] = np.clip(
                self._counters[active] + data_bipolar, -127, 127
            )
        
        return {"active": len(active)}
    
    def read(self, address: np.ndarray) -> np.ndarray:
        self._ensure_initialized()
        packed = np.packbits((address > 0).astype(np.uint8))
        
        sample_idx = np.random.choice(self.num_locations, 1000, replace=False)
        xor_result = np.bitwise_xor(self._addresses[sample_idx], packed)
        distances = np.array([np.unpackbits(row).sum() for row in xor_result])
        
        active = sample_idx[distances < self.activation_radius]
        if len(active) == 0:
            return np.zeros(self.address_dim, dtype=np.int8)
        
        result = np.sign(self._counters[active].sum(axis=0)).astype(np.int8)
        result[result == 0] = 1
        return result
