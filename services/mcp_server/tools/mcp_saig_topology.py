
import logging
import os
import base64
import httpx
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class SAIGTopologyTool:
    """
    Implements SAIG-S (Spatial Anchor & Invariant Geometry - Symbiotic).
    Replaces TransGeo. Client-side tool that delegates to embedding_service.
    """
    def __init__(self):
        self.service_url = os.environ.get("EMBEDDING_SERVICE_URL", "http://embedding_service:8005")
        self.endpoint = f"{self.service_url}/v1/topology"

    async def generate_topology(self, image_input: str) -> Dict[str, Any]:
        """
        Generate topology features from a query image.
        Delegates to embedding_service.
        
        Args:
            image_input: Path to local image file or Base64 string
        """
        try:
            # Handle image input
            payload_input = image_input
            if os.path.exists(image_input):
                 try:
                     with open(image_input, "rb") as f:
                         payload_input = base64.b64encode(f.read()).decode('utf-8')
                 except Exception as e:
                     return {"error": f"Failed to read image file: {e}"}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.endpoint,
                    json={"image_input": payload_input},
                    timeout=60.0 # SAIG-S can be fast, but give it time
                )
                
                if response.status_code != 200:
                    return {"error": f"Service returned {response.status_code}: {response.text}"}
                
                result = response.json()
                return {
                    "status": "success", 
                    "features": result.get("features", {}),
                    "model": os.environ.get("ARCA_TOPOLOGY_MODEL", "SAIG-S")
                }

        except Exception as e:
            logger.error(f"SAIG Topology inference failed: {e}")
            return {"error": str(e)}

    # Alias for compatibility if needed
    async def localization_estimate(self, image_input: str) -> Dict[str, Any]:
        return await self.generate_topology(image_input)
