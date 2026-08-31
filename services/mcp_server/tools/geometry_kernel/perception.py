from typing import Dict, Any, List
import requests
import os
import logging
from .core import Vector3D

logger = logging.getLogger(__name__)

class PerceptionEngine:
    """
    Phase 1: Visual Perception
    Uses SigLIP via Embedding Service to encode visual states.
    """
    def __init__(self):
        # Default to OCI Llama Service (Port 8081 for Embeddings)
        self.embedding_url = os.getenv("OCI_EMBEDDING_URL", "http://100.70.0.13:8081")

    def encode_state(self, image_base64: str) -> Vector3D:
        """
        Sends image to embedding service, returns a reduced 3D vector for the Kernel.
        """
        try:
            # Call embedding service
            # Assuming endpoint /embed/image or similar exists, or we use standard OpenAI embedding format
            # user said "siglip 2 is configured via embedding_service".
            # Check embedding_service API docs or assume /v1/embeddings with model=siglip
            
            payload = {
                "input": [image_base64],
                "model": "siglip",
                "encoding_format": "float"
            }
            url = f"{self.embedding_url}/v1/embeddings" # Proxy to local embedding
            res = requests.post(url, json=payload, timeout=10)
            
            if res.status_code == 200:
                # SigLIP returns huge vector (e.g. 1152 dim).
                # We need to project this to 3D for the Geometry Kernel (Semantic Space).
                # For MVP, we can take the first 3 components or learn a projection.
                # Let's take mean/PCA or just slice for now (dumb but functional for plumbing).
                vec_data = res.json()["data"][0]["embedding"]
                return Vector3D(vec_data[0], vec_data[1], vec_data[2]) 
            else:
                logger.error(f"Perception failed: {res.text}")
                return Vector3D.zero()

        except Exception as e:
            logger.error(f"Perception error: {e}")
            return Vector3D.zero()
