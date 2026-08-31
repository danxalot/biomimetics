
import logging
import os
import base64
import httpx
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class VisionEncoder:
    """
    Client for ARCA Embedding Service (Vision Encoder).
    Delegates heavy lifting to the embedding_service container.
    """
    def __init__(self):
        self.service_url = os.environ.get("EMBEDDING_SERVICE_URL", "http://embedding_service:8005")
        self.endpoint = f"{self.service_url}/v1/embed/image"
        
        # LLM Gateway for Qwen 3 VL (Vision Language Model)
        self.gateway_url = os.environ.get("LLM_GATEWAY_URL", "http://llm_gateway:8080/v1/chat/completions")
        self.vision_model = os.environ.get("ARCA_QWEN_3_VL_MODEL", "qwen3-vl-2b")

    async def analyze_image(self, image_input: str, prompt: str = "Describe this image in detail.") -> str:
        """
        Analyze image using Qwen 3 VL via Cognitive Scheduler (Audit Phase).
        """
        # Lazy import
        from tools.geometry_kernel.model_engine import CognitiveScheduler
        scheduler = CognitiveScheduler()

        try:
             # Prepare Image (Base64)
             img_b64 = image_input
             if os.path.exists(image_input):
                 with open(image_input, "rb") as f:
                     img_b64 = base64.b64encode(f.read()).decode('utf-8')

             # Use Audit Core (Qwen-VL)
             # Note: call_audit is synchronous in model_engine, but we are async here. 
             # For MVP, blocking is acceptable or wrap in executor if needed.
             # Ideally internalize async in scheduler later.
             response = scheduler.call_audit(prompt, image_base64=img_b64)
             return response
                     
        except Exception as e:
            logger.error(f"Vision Analysis error: {e}")
            return f"Error: {e}"

    async def encode_image(self, image_input: str) -> Dict[str, Any]:
        """
        Generate embedding for an image via Embedding Service.
        
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
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    error_msg = f"Service returned {response.status_code}: {response.text}"
                    logger.error(error_msg)
                    return {"error": error_msg}
                
                result = response.json()
                embedding = result.get("embeddings", [])
                
                return {
                    "embedding": embedding,
                    "dimensions": len(embedding),
                    "model": os.environ.get("ARCA_SIGLIP_MODEL", "google/siglip2-so400m-patch14-384"),
                    "status": "success"
                }

        except Exception as e:
            logger.error(f"Vision Encoder inference failed: {e}")
            return {"error": str(e)}
