"""
Dragonfly Cache Integration for 512-dim Vectors

Part of Stage 1: Exoteric Knowledge Graph Pipeline
Uses Redis-compatible Dragonfly for ultra-fast vector caching
"""

import os
import json
import redis
from typing import List, Dict, Any, Optional
import logging
import time

logger = logging.getLogger(__name__)


class DragonflyCache:
    """Cache 512-dim vectors in Dragonfly (Redis-compatible)"""

    def __init__(self, host: str = None, port: int = None):
        if host is None:
            host = os.getenv("DRAGONFLY_HOST", "localhost")
        if port is None:
            port = int(os.getenv("DRAGONFLY_PORT", "6381"))
        self.client = redis.Redis(host=host, port=port, decode_responses=True)
        self.vector_ttl = 3600  # 1 hour TTL

    def store_vector(
        self,
        vector_512: List[float],
        key: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Store a 512-dim vector with optional metadata"""
        try:
            data = {
                "vector": vector_512,
                "timestamp": time.time(),
                "metadata": metadata or {},
            }

            # Store in Dragonfly
            self.client.setex(f"vector:{key}", self.vector_ttl, json.dumps(data))

            logger.info(f"Cached vector {key} (dim: {len(vector_512)})")
            return True
        except Exception as e:
            logger.error(f"Error caching vector {key}: {e}")
            return False

    def retrieve_vector(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve a cached vector"""
        try:
            data = self.client.get(f"vector:{key}")
            if data:
                return json.loads(data)
        except Exception as e:
            logger.error(f"Error retrieving vector {key}: {e}")
        return None

    def batch_store(
        self,
        vectors: Dict[str, List[float]],
        metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> int:
        """Store multiple vectors efficiently"""
        stored = 0
        pipeline = self.client.pipeline()

        for key, vector in vectors.items():
            data = {
                "vector": vector,
                "timestamp": time.time(),
                "metadata": metadata.get(key, {}) if metadata else {},
            }
            pipeline.setex(f"vector:{key}", self.vector_ttl, json.dumps(data))
            stored += 1

        pipeline.execute()
        logger.info(f"Batch stored {stored} vectors")
        return stored

    def batch_retrieve(self, keys: List[str]) -> Dict[str, Dict[str, Any]]:
        """Retrieve multiple vectors efficiently"""
        pipeline = self.client.pipeline()
        for key in keys:
            pipeline.get(f"vector:{key}")

        results = pipeline.execute()
        return {
            key: json.loads(result) if result else None
            for key, result in zip(keys, results)
        }


# Singleton instance
_dragonfly_cache: Optional[DragonflyCache] = None


def get_dragonfly_cache() -> DragonflyCache:
    """Get or create Dragonfly cache singleton"""
    global _dragonfly_cache
    if _dragonfly_cache is None:
        _dragonfly_cache = DragonflyCache()
    return _dragonfly_cache


def cache_vector_512(
    vector_512: List[float], key: str, metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """Convenience function to cache a 512-dim vector"""
    cache = get_dragonfly_cache()
    return cache.store_vector(vector_512, key, metadata)


def retrieve_cached_vector(key: str) -> Optional[Dict[str, Any]]:
    """Convenience function to retrieve a cached vector"""
    cache = get_dragonfly_cache()
    return cache.retrieve_vector(key)
