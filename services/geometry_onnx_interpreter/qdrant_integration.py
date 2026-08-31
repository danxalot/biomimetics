"""
Qdrant Integration for Storing 2048-dim Vectors

Part of Stage 1: Exoteric Knowledge Graph Pipeline
"""

import os
import uuid
import json
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams
import logging

logger = logging.getLogger(__name__)


class QdrantVectorStore:
    """Store and retrieve 2048-dim vectors in Qdrant"""

    def __init__(self, host: str = None, port: int = None):
        if host is None:
            host = os.getenv("QDRANT_HOST", "localhost")
        if port is None:
            port = int(os.getenv("QDRANT_PORT", "6334"))
        # Use location parameter for qdrant-client 1.x
        location = f"http://{host}:{port}"
        self.client = QdrantClient(location=location)
        self.collection_name = "geometry_vectors_2048"
        self._ensure_collection()

    def _ensure_collection(self):
        """Create collection if it doesn't exist"""
        try:
            self.client.get_collection(self.collection_name)
            logger.info(f"Collection {self.collection_name} exists")
        except Exception:
            logger.info(f"Creating collection {self.collection_name}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=2048, distance=Distance.COSINE),
            )

    def store_vector(
        self, vector_2048: List[float], metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Store a 2048-dim vector with metadata"""
        point_id = str(uuid.uuid4())

        # Validate vector size
        if len(vector_2048) != 2048:
            raise ValueError(f"Vector must be 2048 dimensions, got {len(vector_2048)}")

        # Prepare payload
        payload = metadata or {}
        payload["vector_id"] = point_id

        # Upsert to Qdrant
        self.client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(id=point_id, vector=vector_2048, payload=payload)],
        )

        logger.info(f"Stored vector {point_id} with metadata: {list(payload.keys())}")
        return point_id

    def retrieve_similar(
        self, query_vector: List[float], limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Retrieve similar vectors using cosine similarity"""
        # Use query_points method (newer API in qdrant-client 1.x)
        results = self.client.query_points(
            collection_name=self.collection_name, query=query_vector, limit=limit
        )

        # QueryResponse contains a 'points' attribute with the results
        if hasattr(results, "points"):
            points = results.points
        else:
            # Fallback if results is directly a list
            points = results

        return [
            {"id": str(point.id), "score": point.score, "payload": point.payload}
            for point in points
        ]

    def retrieve_by_id(self, point_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific vector by ID"""
        try:
            result = self.client.retrieve(
                collection_name=self.collection_name, ids=[point_id]
            )
            if result:
                return {
                    "id": str(result[0].id),
                    "vector": result[0].vector,
                    "payload": result[0].payload,
                }
        except Exception as e:
            logger.error(f"Error retrieving vector {point_id}: {e}")
        return None


# Singleton instance
_vector_store: Optional[QdrantVectorStore] = None


def get_vector_store() -> QdrantVectorStore:
    """Get or create Qdrant vector store singleton"""
    global _vector_store
    if _vector_store is None:
        _vector_store = QdrantVectorStore()
    return _vector_store


def store_vector_2048(
    vector_2048: List[float], metadata: Optional[Dict[str, Any]] = None
) -> str:
    """Convenience function to store a 2048-dim vector"""
    store = get_vector_store()
    return store.store_vector(vector_2048, metadata)


def retrieve_similar_vectors(
    query_vector: List[float], limit: int = 5
) -> List[Dict[str, Any]]:
    """Convenience function to retrieve similar vectors"""
    store = get_vector_store()
    return store.retrieve_similar(query_vector, limit)
