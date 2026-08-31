"""
HDC Infinite Memory Systems
============================

Implements infinite-capacity memory systems using HDC bundling:

1. HDCInfiniMemory - Compressive memory using bundled superposition
   (Inspired by Infini-attention paper)

2. HDCLongMemory - Long-term episodic memory with retrieval
   (Inspired by LONGMEM / MemGPT patterns)

3. HolographicAccumulator - Lossless bundled accumulator with position encoding

Key Insight: HDC bundling allows "infinite" memory by superimposing
all content into a single fixed-width vector. Information is preserved
holographically - the whole is greater than the sum of parts.

References:
- "Leave No Context Behind: Efficient Infinite Context Transformers"
- "Augmenting Language Models with Long-Term Memory"
- Kanerva's VSA work on distributed representations
"""

import numpy as np
import logging
import time
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("HDCInfiniMemory")


def hamming_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    """Compute Hamming similarity between two binary/bipolar vectors."""
    if v1.dtype == np.uint8 and v2.dtype == np.uint8:
        # Packed binary
        xor_result = np.bitwise_xor(v1, v2)
        diff_bits = np.unpackbits(xor_result).sum()
        total_bits = len(v1) * 8
        return 1.0 - (2.0 * diff_bits / total_bits)
    else:
        # Float/int representation
        matches = (np.sign(v1) == np.sign(v2)).sum()
        return matches / len(v1)


def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    """Compute cosine similarity."""
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))


def permute(v: np.ndarray, shifts: int) -> np.ndarray:
    """Cyclic permutation (roll) for temporal encoding."""
    return np.roll(v, shifts)


def bundle(vectors: List[np.ndarray], normalize: bool = True) -> np.ndarray:
    """Bundle (superimpose) multiple vectors."""
    if not vectors:
        raise ValueError("Cannot bundle empty list")
    
    result = np.sum(vectors, axis=0)
    
    if normalize:
        # Bipolarize (sign function)
        result = np.sign(result)
        result[result == 0] = 1  # Tie-break
    
    return result


def bind(v1: np.ndarray, v2: np.ndarray) -> np.ndarray:
    """Bind two vectors (element-wise multiplication for bipolar)."""
    return np.multiply(v1, v2)


class HDCInfiniMemory:
    """
    Infini-attention style memory using HDC bundling.
    
    Instead of a learned compressive memory, use holographic superposition
    to accumulate context into a single hypervector.
    
    Key Properties:
    - Fixed memory footprint regardless of history length
    - Temporal ordering via permutation encoding
    - Graceful degradation (older memories become noisier)
    - Query-based relevance retrieval
    """
    
    def __init__(self, hv_dim: int = 10000, decay_rate: float = 0.99):
        self.hv_dim = hv_dim
        self.decay_rate = decay_rate
        
        # Accumulated memory (running bundle) - using float for soft accumulation
        self.memory_hv = np.zeros(hv_dim, dtype=np.float32)
        self.memory_initialized = False
        
        # Temporal position counter (for permutation-based ordering)
        self.position = 0
        
        # Statistics
        self.update_count = 0
        self.query_count = 0
        
        logger.info(f"HDCInfiniMemory initialized: dim={hv_dim}, decay={decay_rate}")
    
    def update(self, new_content_hv: np.ndarray, importance: float = 1.0) -> Dict[str, Any]:
        """
        Add new content to the infinite memory.
        
        Uses temporal binding (permutation) to preserve order information.
        
        Args:
            new_content_hv: New content as hypervector [hv_dim]
            importance: Weight for this content (higher = more memorable)
            
        Returns:
            Update statistics
        """
        # Ensure correct shape and type
        content = new_content_hv.astype(np.float32).flatten()[:self.hv_dim]
        if len(content) < self.hv_dim:
            content = np.pad(content, (0, self.hv_dim - len(content)))
        
        # Apply positional permutation (encodes temporal position)
        positioned_hv = permute(content, self.position)
        self.position += 1
        
        if not self.memory_initialized:
            self.memory_hv = positioned_hv * importance
            self.memory_initialized = True
        else:
            # Decay old memory slightly (simulates forgetting curve)
            if self.decay_rate < 1.0:
                self.memory_hv *= self.decay_rate
            
            # Bundle with new content (weighted)
            # Soft bundling: add rather than threshold
            self.memory_hv = self.memory_hv + positioned_hv * importance
        
        self.update_count += 1
        
        return {
            "position": self.position - 1,
            "total_updates": self.update_count,
            "memory_magnitude": float(np.linalg.norm(self.memory_hv))
        }
    
    def query(self, query_hv: np.ndarray) -> float:
        """
        Query the memory for relevance to a given vector.
        
        Returns similarity score indicating how much the query
        "resonates" with accumulated memory.
        """
        if not self.memory_initialized:
            return 0.0
        
        query = query_hv.astype(np.float32).flatten()[:self.hv_dim]
        if len(query) < self.hv_dim:
            query = np.pad(query, (0, self.hv_dim - len(query)))
        
        self.query_count += 1
        
        return cosine_similarity(query, self.memory_hv)
    
    def retrieve_at_position(self, position: int) -> np.ndarray:
        """
        Attempt to retrieve content at a specific temporal position.
        
        Uses inverse permutation and the current memory state.
        Note: Result is noisy due to interference from other stored content.
        """
        if not self.memory_initialized:
            return np.zeros(self.hv_dim, dtype=np.float32)
        
        # Apply inverse permutation to memory
        shifted_memory = permute(self.memory_hv, -position)
        
        # The result is a noisy version of the content at that position
        # Can be cleaned up using SDM or Hopfield memory
        return shifted_memory
    
    def retrieve_recent(self, window_size: int = 5) -> np.ndarray:
        """
        Retrieve a bundled representation of recent memories.
        """
        if not self.memory_initialized:
            return np.zeros(self.hv_dim, dtype=np.float32)
        
        # Unbundle recent positions
        recent_vectors = []
        for i in range(max(0, self.position - window_size), self.position):
            retrieved = self.retrieve_at_position(i)
            recent_vectors.append(retrieved)
        
        if not recent_vectors:
            return np.zeros(self.hv_dim, dtype=np.float32)
        
        return bundle(recent_vectors, normalize=False)
    
    def get_hard_memory(self) -> np.ndarray:
        """
        Get a bipolarized (hard) version of the memory.
        Useful for storage or comparison.
        """
        hard = np.sign(self.memory_hv).astype(np.int8)
        hard[hard == 0] = 1
        return hard
    
    def get_stats(self) -> Dict[str, Any]:
        """Return memory statistics."""
        return {
            "hv_dim": self.hv_dim,
            "decay_rate": self.decay_rate,
            "position": self.position,
            "update_count": self.update_count,
            "query_count": self.query_count,
            "memory_magnitude": float(np.linalg.norm(self.memory_hv)),
            "initialized": self.memory_initialized
        }
    
    def reset(self):
        """Clear the memory."""
        self.memory_hv = np.zeros(self.hv_dim, dtype=np.float32)
        self.memory_initialized = False
        self.position = 0
        self.update_count = 0
        self.query_count = 0
        logger.info("HDCInfiniMemory reset")


class HDCLongMemory:
    """
    Long-term memory system using HDC for efficient retrieval.
    
    Stores episodic memories as HDC vectors with associated content.
    Retrieval uses similarity for O(n) lookup (fast for moderate n).
    
    Unlike HDCInfiniMemory which compresses everything, this stores
    discrete episodes that can be retrieved individually.
    """
    
    def __init__(self, hv_dim: int = 10000, memory_size: int = 100000):
        self.hv_dim = hv_dim
        self.memory_size = memory_size
        
        # Memory bank: array of HDC vectors (keys)
        self.memory_keys = np.zeros((memory_size, hv_dim), dtype=np.float32)
        self.memory_values: List[Any] = [None] * memory_size
        self.memory_timestamps = np.zeros(memory_size, dtype=np.float64)
        
        self.write_pointer = 0
        self.num_memories = 0
        
        logger.info(f"HDCLongMemory initialized: dim={hv_dim}, capacity={memory_size}")
    
    def store(self, key_hv: np.ndarray, value: Any, 
              timestamp: Optional[float] = None) -> int:
        """
        Store a memory with HDC key.
        
        Args:
            key_hv: HDC vector key for retrieval
            value: Arbitrary Python object to store
            timestamp: Optional timestamp (defaults to current time)
            
        Returns:
            Index where memory was stored
        """
        if timestamp is None:
            timestamp = time.time()
        
        key = key_hv.astype(np.float32).flatten()[:self.hv_dim]
        if len(key) < self.hv_dim:
            key = np.pad(key, (0, self.hv_dim - len(key)))
        
        idx = self.write_pointer
        
        self.memory_keys[idx] = key
        self.memory_values[idx] = value
        self.memory_timestamps[idx] = timestamp
        
        self.write_pointer = (self.write_pointer + 1) % self.memory_size
        self.num_memories = min(self.num_memories + 1, self.memory_size)
        
        return idx
    
    def retrieve(self, query_hv: np.ndarray, top_k: int = 5,
                 recency_weight: float = 0.1) -> List[Tuple[Any, float]]:
        """
        Retrieve memories most similar to query.
        
        Combines HDC similarity with recency for ranking.
        
        Args:
            query_hv: Query hypervector
            top_k: Number of results to return
            recency_weight: Weight for recency bonus (0 = pure similarity)
            
        Returns:
            List of (value, score) tuples
        """
        if self.num_memories == 0:
            return []
        
        query = query_hv.astype(np.float32).flatten()[:self.hv_dim]
        if len(query) < self.hv_dim:
            query = np.pad(query, (0, self.hv_dim - len(query)))
        
        # Compute similarities (vectorized)
        # Cosine similarity
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return []
        
        key_norms = np.linalg.norm(self.memory_keys[:self.num_memories], axis=1)
        valid_mask = key_norms > 0
        
        similarities = np.zeros(self.num_memories)
        if valid_mask.any():
            dots = np.dot(self.memory_keys[:self.num_memories][valid_mask], query)
            similarities[valid_mask] = dots / (key_norms[valid_mask] * query_norm)
        
        # Compute recency scores
        current_time = time.time()
        time_deltas = current_time - self.memory_timestamps[:self.num_memories]
        recency_scores = np.exp(-time_deltas / 3600)  # 1-hour half-life
        
        # Combined score
        scores = similarities + recency_weight * recency_scores
        
        # Top-k
        top_k = min(top_k, self.num_memories)
        top_indices = np.argsort(scores)[-top_k:][::-1]
        
        return [(self.memory_values[i], float(scores[i])) for i in top_indices]
    
    def retrieve_by_similarity(self, query_hv: np.ndarray, 
                               threshold: float = 0.5) -> List[Tuple[Any, float]]:
        """Retrieve all memories above similarity threshold."""
        if self.num_memories == 0:
            return []
        
        query = query_hv.astype(np.float32).flatten()[:self.hv_dim]
        if len(query) < self.hv_dim:
            query = np.pad(query, (0, self.hv_dim - len(query)))
        
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return []
        
        key_norms = np.linalg.norm(self.memory_keys[:self.num_memories], axis=1)
        valid_mask = key_norms > 0
        
        similarities = np.zeros(self.num_memories)
        if valid_mask.any():
            dots = np.dot(self.memory_keys[:self.num_memories][valid_mask], query)
            similarities[valid_mask] = dots / (key_norms[valid_mask] * query_norm)
        
        # Filter by threshold
        above_threshold = np.where(similarities >= threshold)[0]
        
        results = [(self.memory_values[i], float(similarities[i])) 
                   for i in above_threshold]
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Return memory statistics."""
        return {
            "hv_dim": self.hv_dim,
            "capacity": self.memory_size,
            "num_memories": self.num_memories,
            "write_pointer": self.write_pointer,
            "oldest_timestamp": float(self.memory_timestamps[:self.num_memories].min()) 
                if self.num_memories > 0 else 0.0,
            "newest_timestamp": float(self.memory_timestamps[:self.num_memories].max())
                if self.num_memories > 0 else 0.0
        }


class HolographicAccumulator:
    """
    Lossless bundled accumulator with position encoding.
    
    This is a specialized memory for accumulating conversation/interaction
    history into a single holographic representation while maintaining
    the ability to query specific aspects.
    
    Features:
    - Separate channels for different content types (text, action, feedback)
    - Position-encoded bundling for temporal queries
    - Weighted importance accumulation
    - Decay and consolidation operations
    """
    
    def __init__(self, hv_dim: int = 10000):
        self.hv_dim = hv_dim
        
        # Multi-channel accumulation
        self.channels: Dict[str, np.ndarray] = {
            "content": np.zeros(hv_dim, dtype=np.float32),
            "context": np.zeros(hv_dim, dtype=np.float32),
            "actions": np.zeros(hv_dim, dtype=np.float32),
            "feedback": np.zeros(hv_dim, dtype=np.float32),
            "metadata": np.zeros(hv_dim, dtype=np.float32)
        }
        
        # Channel positions (for temporal encoding)
        self.channel_positions: Dict[str, int] = {k: 0 for k in self.channels}
        
        # Role basis vectors (for binding)
        np.random.seed(42)  # Deterministic roles
        self.role_vectors: Dict[str, np.ndarray] = {
            name: np.random.choice([-1.0, 1.0], size=hv_dim).astype(np.float32)
            for name in self.channels
        }
        
        # Combined holographic state
        self._combined_cache = None
        self._cache_valid = False
        
        logger.info(f"HolographicAccumulator initialized: dim={hv_dim}, "
                   f"channels={list(self.channels.keys())}")
    
    def accumulate(self, channel: str, content_hv: np.ndarray, 
                   importance: float = 1.0) -> Dict[str, Any]:
        """
        Accumulate content into a specific channel.
        
        Args:
            channel: Channel name ("content", "context", "actions", "feedback", "metadata")
            content_hv: Content hypervector
            importance: Weighting factor
            
        Returns:
            Accumulation statistics
        """
        if channel not in self.channels:
            logger.warning(f"Unknown channel '{channel}', using 'content'")
            channel = "content"
        
        content = content_hv.astype(np.float32).flatten()[:self.hv_dim]
        if len(content) < self.hv_dim:
            content = np.pad(content, (0, self.hv_dim - len(content)))
        
        # Bind with role vector (marks which channel this came from)
        bound_content = bind(content, self.role_vectors[channel])
        
        # Apply positional permutation
        positioned = permute(bound_content, self.channel_positions[channel])
        self.channel_positions[channel] += 1
        
        # Accumulate
        self.channels[channel] = self.channels[channel] + positioned * importance
        
        # Invalidate combined cache
        self._cache_valid = False
        
        return {
            "channel": channel,
            "position": self.channel_positions[channel] - 1,
            "channel_magnitude": float(np.linalg.norm(self.channels[channel]))
        }
    
    def get_combined_state(self) -> np.ndarray:
        """
        Get the combined holographic state across all channels.
        """
        if not self._cache_valid:
            self._combined_cache = bundle(
                list(self.channels.values()), 
                normalize=False
            )
            self._cache_valid = True
        
        return self._combined_cache
    
    def query_channel(self, channel: str, query_hv: np.ndarray) -> float:
        """Query relevance within a specific channel."""
        if channel not in self.channels:
            return 0.0
        
        # Unbind the role to isolate the channel
        unbound_query = bind(query_hv, self.role_vectors[channel])
        
        return cosine_similarity(
            unbound_query.flatten()[:self.hv_dim], 
            self.channels[channel]
        )
    
    def query_all_channels(self, query_hv: np.ndarray) -> Dict[str, float]:
        """Query relevance across all channels."""
        return {
            channel: self.query_channel(channel, query_hv)
            for channel in self.channels
        }
    
    def decay_channel(self, channel: str, factor: float = 0.99) -> None:
        """Apply decay to a specific channel."""
        if channel in self.channels:
            self.channels[channel] *= factor
            self._cache_valid = False
    
    def decay_all(self, factor: float = 0.99) -> None:
        """Apply decay to all channels."""
        for channel in self.channels:
            self.channels[channel] *= factor
        self._cache_valid = False
    
    def consolidate(self) -> np.ndarray:
        """
        Consolidate all channels into a single hard vector.
        Good for long-term storage.
        """
        combined = self.get_combined_state()
        hard = np.sign(combined).astype(np.int8)
        hard[hard == 0] = 1
        return hard
    
    def get_stats(self) -> Dict[str, Any]:
        """Return accumulator statistics."""
        return {
            "hv_dim": self.hv_dim,
            "channels": {
                name: {
                    "position": self.channel_positions[name],
                    "magnitude": float(np.linalg.norm(self.channels[name]))
                }
                for name in self.channels
            },
            "combined_magnitude": float(np.linalg.norm(self.get_combined_state()))
        }


# Factory function for easy instantiation
def create_memory_system(memory_type: str = "infini", **kwargs) -> Any:
    """
    Factory function to create memory systems.
    
    Args:
        memory_type: One of "infini", "long", "accumulator", "sdm"
        **kwargs: Configuration for the specific memory type
        
    Returns:
        Memory system instance
    """
    if memory_type == "infini":
        return HDCInfiniMemory(
            hv_dim=kwargs.get("hv_dim", 10000),
            decay_rate=kwargs.get("decay_rate", 0.99)
        )
    elif memory_type == "long":
        return HDCLongMemory(
            hv_dim=kwargs.get("hv_dim", 10000),
            memory_size=kwargs.get("memory_size", 100000)
        )
    elif memory_type == "accumulator":
        return HolographicAccumulator(
            hv_dim=kwargs.get("hv_dim", 10000)
        )
    else:
        raise ValueError(f"Unknown memory type: {memory_type}")
