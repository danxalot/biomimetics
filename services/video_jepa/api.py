"""
V-JEPA API Service - NumPy/ONNX Version
====================================

FastAPI service for video embedding using ONNX Runtime.
Replaces torch hub loading with ONNX model inference.

Usage:
    uvicorn api:app --host 0.0.0.0 --port 8000
"""

import os
import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VJEPA_Service")

app = FastAPI(title="V-JEPA Int8 Embedding Service")

# Global Model Storage
session = None
model_loaded = False


class VideoPayload(BaseModel):
    video_path: str


def load_model():
    """Load V-JEPA model (ONNX format for ARM64)."""
    global session, model_loaded
    
    try:
        import onnxruntime as ort
        
        # Look for ONNX model in standard locations
        model_paths = [
            "models/vjepa_vit_huge_int8.onnx",
            "/Users/danexall/Documents/VS Code Projects/ARCA/models/vjepa_vit_huge_int8.onnx",
            os.path.join(os.path.dirname(__file__), "..", "models", "vjepa_vit_huge_int8.onnx"),
        ]
        
        model_path = None
        for p in model_paths:
            if os.path.exists(p):
                model_path = p
                break
        
        if model_path is None:
            logger.warning("V-JEPA ONNX model not found. Using mock mode.")
            model_loaded = False
            return
        
        logger.info(f"Loading V-JEPA from {model_path}...")
        session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        model_loaded = True
        logger.info("✅ V-JEPA ONNX Loaded.")
        
    except ImportError:
        logger.warning("onnxruntime not installed. Using mock mode.")
        model_loaded = False
    except Exception as e:
        logger.error(f"Failed to load V-JEPA: {e}")
        model_loaded = False
        raise e


@app.on_event("startup")
async def startup_event():
    load_model()


def load_video_frames(video_path: str, num_frames: int = 16) -> np.ndarray:
    """
    Load video frames and preprocess.
    
    Args:
        video_path: Path to video file
        num_frames: Number of frames to extract
        
    Returns:
        Array of shape (num_frames, 3, 224, 224) ready for model
    """
    # Placeholder: In production, use OpenCV or ffmpeg
    # For now, return random tensor as placeholder
    
    logger.warning("Video loading not implemented. Using random frames.")
    
    # Shape: (num_frames, channels, height, width)
    frames = np.random.randn(num_frames, 3, 224, 224).astype(np.float32)
    
    # Normalize with ImageNet stats (if using ViT)
    mean = np.array([0.485, 0.456, 0.406]).reshape(1, 3, 1, 1)
    std = np.array([0.229, 0.224, 0.225]).reshape(1, 3, 1, 1)
    frames = (frames - mean) / std
    
    return frames


@app.post("/embed")
async def embed_video(payload: VideoPayload):
    global session, model_loaded
    
    if not os.path.exists(payload.video_path):
        raise HTTPException(status_code=404, detail="Video file not found")
    
    try:
        # Load and preprocess video
        frames = load_video_frames(payload.video_path)
        
        if session is not None:
            # Run ONNX inference
            # Input shape: (batch, frames, channels, height, width)
            input_data = frames[np.newaxis, :]  # Add batch dimension
            
            input_name = session.get_inputs()[0].name
            outputs = session.run(None, {input_name: input_data})
            
            # Get embedding (typically from [CLS] token or mean pooling)
            embedding = outputs[0]
            
            # Flatten to 1D vector
            if embedding.ndim > 1:
                embedding = np.mean(embedding, axis=1)  # Mean pool over frames
            
            vector = embedding.flatten().tolist()
            model_name = "vjepa-vit-h-int8-onnx"
        else:
            # Mock mode: return random vector
            logger.warning("Using mock embedding (model not loaded)")
            vector = np.random.randn(1280).tolist()
            model_name = "vjepa-vit-h-mock"
        
        return {
            "embedding": vector,
            "model": model_name,
            "status": "success" if session else "mock_mode",
            "embedding_dim": len(vector),
        }
    
    except Exception as e:
        logger.error(f"Inference failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
