
import logging
import os
import json
import numpy as np
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class TelemetryVAETool:
    """
    Geometry Kernel: VAE Transformer (Manifold Engine).
    Compresses high-dimensional telemetry (Loki/OTel) into 3D latent coordinates.
    """
    def __init__(self):
        # Service URL for the embedding/VAE service (assuming VAE runs alongside embeddings)
        self.service_url = os.environ.get("EMBEDDING_SERVICE_URL", "http://embedding_service:8005")
        self.endpoint = f"{self.service_url}/v1/vae/compress"
        self.loki_url = os.environ.get("LOKI_URL", "http://loki:3100")
        
        # Local fallback model path (if running locally on CPU)
        self.local_model_path = os.environ.get("VAE_MODEL_PATH", "/app/models/shape_vae_transformer_v1.pt")

    async def compress_telemetry(self, component_id: str, time_window: str = "5m", 
                               visual_embedding: Optional[List[float]] = None,
                               text_embedding: Optional[List[float]] = None) -> Dict[str, Any]:
        """
        Fetch telemetry for a component and compress into (x, y, z) coordinates.
        Can optionally accept pre-computed embeddings (e.g. from Cognitive Tick).
        """
        try:
            # 1. Fetch Telemetry (Logs/Metrics) if no text embedding provided
            telemetry_data = []
            if not text_embedding:
                telemetry_data = await self._fetch_loki_logs(component_id, time_window)
                if not telemetry_data and not visual_embedding:
                    return {"error": f"No telemetry found for {component_id}"}

            # 2. Call VAE Service to Compress
            payload = {
                "component_id": component_id,
                "timestamp": datetime.now().isoformat()
            }
            
            if text_embedding:
                payload["text_embedding"] = text_embedding
            if visual_embedding:
                payload["visual_embedding"] = visual_embedding
            if telemetry_data:
                payload["data"] = telemetry_data

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.endpoint,
                    json=payload,
                    timeout=10.0
                )
                
                if response.status_code != 200:
                    # Fallback or Error
                    logger.warning(f"VAE Service Error {response.status_code}: {response.text}")
                    return self._fallback_projection(component_id, telemetry_data)
                
                result = response.json()
                return {
                    "component_id": component_id,
                    "coordinates": result.get("coordinates", [0.0, 0.0, 0.0]), # [x, y, z]
                    "energy": result.get("energy", 0.0), # Reconstruction error
                    "confidence": result.get("confidence", 1.0)
                }

        except Exception as e:
            logger.error(f"VAE compression failed: {e}")
            return {"error": str(e)}

    async def _fetch_loki_logs(self, component_id: str, window: str) -> List[str]:
        """
        Fetch recent logs from Loki for the component.
        """
        # Mock implementation if Loki is not reachable
        if os.environ.get("MOCK_TELEMETRY", "false").lower() == "true":
            return [f"Sample log entry for {component_id} at {datetime.now()}"]

        try:
            query = f'{{service_name="{component_id}"}}'
            async with httpx.AsyncClient() as client:
                # Loki API query_range
                # This is a simplified call; actual Loki API requires start/end times
                resp = await client.get(
                    f"{self.loki_url}/loki/api/v1/query_range",
                    params={"query": query, "limit": 100}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # Extract log lines
                    logs = []
                    for result in data.get("data", {}).get("result", []):
                        for value in result.get("values", []):
                            logs.append(value[1]) # [timestamp, log_line]
                    return logs
        except Exception:
            pass
        
        return []

    def _fallback_projection(self, component_id: str, data: List[str]) -> Dict[str, Any]:
        """
        Deterministic fallback if VAE service is down. 
        Hashes input to a stable 3D point (not semantically meaningful but stable).
        """
        import hashlib
        h = hashlib.sha256(f"{component_id}".encode()).digest()
        # Use first 3 bytes for x, y, z normalized to [-1, 1]
        x = (h[0] / 255.0) * 2 - 1
        y = (h[1] / 255.0) * 2 - 1
        z = (h[2] / 255.0) * 2 - 1
        return {
            "component_id": component_id,
            "coordinates": [x, y, z],
            "energy": 0.5,
            "confidence": 0.1,
            "note": "FALLBACK_PROJECTION"
        }
