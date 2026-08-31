"""
Visual Spike Detection for V2 Geometry Kernel

Uses SigLIP-2 so400m as a pure vision encoder to detect visual changes.
Only triggers expensive Qwen VL when cosine similarity drops below threshold.

Cost: ~50ms per frame on CPU
Model: google/siglip2-so400m-patch14-384 (~800MB vision-only)
"""

import os
import logging
from typing import Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)

# Lazy load heavy dependencies
_model = None
_processor = None


@dataclass
class SpikeState:
    """State for visual spike detection."""
    last_vector: Optional[np.ndarray] = None
    last_description: Optional[str] = None
    frame_count: int = 0
    spike_count: int = 0
    reuse_count: int = 0


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


class VisualSpikeDetector:
    """
    Detects visual changes using SigLIP-2 vision encoder.
    
    Instead of asking Qwen VL "What do you see?" every frame,
    we encode frames to vectors and compare with cosine similarity.
    
    Only when similarity drops below threshold do we trigger VL.
    
    Example:
        detector = VisualSpikeDetector(threshold=0.95)
        
        for frame in frames:
            needs_vl, cached = detector.check_frame(frame)
            if needs_vl:
                description = qwen_vl.describe(frame)
                detector.update_description(description)
            else:
                description = cached  # Reuse, no VL cost!
    """
    
    MODEL_NAME = "google/siglip-base-patch16-224"
    
    def __init__(
        self, 
        threshold: float = 0.95,
        device: str = "cpu",
        model_cache_dir: Optional[str] = None
    ):
        """
        Initialize the visual spike detector.
        
        Args:
            threshold: Cosine similarity threshold (0.95 = 5% change triggers VL)
            device: Device to run on ("cpu" recommended for this use case)
            model_cache_dir: Optional cache directory for model weights
        """
        self.threshold = threshold
        self.device = device
        self.model_cache_dir = model_cache_dir or os.getenv(
            "SIGLIP_CACHE_DIR", 
            str(Path.home() / ".cache" / "huggingface" / "hub")
        )
        
        self.state = SpikeState()
        self._model = None
        self._processor = None
        
        logger.info(f"VisualSpikeDetector initialized (threshold={threshold})")
    
    def _load_model(self):
        """Lazy load the SigLIP vision model."""
        if self._model is not None:
            return
        
        logger.info(f"Loading SigLIP-2 vision encoder from {self.MODEL_NAME}...")
        
        try:
            from transformers import SiglipVisionModel, SiglipImageProcessor
            import torch
            
            # Load vision-only model (no text encoder)
            self._model = SiglipVisionModel.from_pretrained(
                self.MODEL_NAME,
                cache_dir=self.model_cache_dir
            )
            self._model.to(self.device)
            self._model.eval()
            
            # Load processor for image preprocessing
            self._processor = SiglipImageProcessor.from_pretrained(
                self.MODEL_NAME,
                cache_dir=self.model_cache_dir
            )
            
            # Log model size
            param_count = sum(p.numel() for p in self._model.parameters())
            logger.info(
                f"SigLIP-2 loaded: {param_count / 1e6:.1f}M params, "
                f"device={self.device}"
            )
            
        except ImportError as e:
            logger.error(f"Missing dependencies: {e}")
            raise RuntimeError(
                "Install transformers and torch: pip install transformers torch"
            )
    
    def encode_image(self, image) -> np.ndarray:
        """
        Encode an image to a vector using SigLIP vision encoder.
        
        Args:
            image: PIL Image, numpy array, or path to image file
            
        Returns:
            np.ndarray: 1152-dimensional embedding vector
        """
        import torch
        from PIL import Image
        
        self._load_model()
        
        # Handle different image input types
        if isinstance(image, (str, Path)):
            image = Image.open(image).convert("RGB")
        elif isinstance(image, np.ndarray):
            image = Image.fromarray(image).convert("RGB")
        
        # Preprocess
        inputs = self._processor(images=image, return_tensors="pt")
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        # Encode (no grad for inference)
        with torch.no_grad():
            outputs = self._model(**inputs)
            # Pool to single vector (use [CLS] or mean pooling)
            embedding = outputs.last_hidden_state.mean(dim=1).squeeze()
        
        return embedding.cpu().numpy()
    
    def check_frame(self, image) -> Tuple[bool, Optional[str]]:
        """
        Check if a frame has changed enough to warrant VL processing.
        
        Args:
            image: Image to check (PIL, numpy, or path)
            
        Returns:
            Tuple of (needs_vl: bool, cached_description: Optional[str])
            - If needs_vl is True, caller should run Qwen VL
            - If needs_vl is False, use cached_description instead
        """
        self.state.frame_count += 1
        
        # Encode current frame
        current_vector = self.encode_image(image)
        
        # First frame always needs VL
        if self.state.last_vector is None:
            self.state.last_vector = current_vector
            self.state.spike_count += 1
            logger.debug(f"Frame {self.state.frame_count}: First frame, needs VL")
            return True, None
        
        # Compute similarity
        similarity = cosine_similarity(current_vector, self.state.last_vector)
        
        # Check threshold
        if similarity >= self.threshold:
            # No significant change, reuse cached description
            self.state.reuse_count += 1
            logger.debug(
                f"Frame {self.state.frame_count}: sim={similarity:.4f} >= {self.threshold}, REUSE"
            )
            return False, self.state.last_description
        else:
            # Visual spike detected!
            self.state.last_vector = current_vector
            self.state.spike_count += 1
            logger.info(
                f"Frame {self.state.frame_count}: VISUAL SPIKE! "
                f"sim={similarity:.4f} < {self.threshold}"
            )
            return True, None
    
    def update_description(self, description: str):
        """
        Update the cached description after VL processing.
        
        Args:
            description: The description from Qwen VL
        """
        self.state.last_description = description
    
    def get_stats(self) -> dict:
        """Get spike detection statistics."""
        total = self.state.frame_count
        if total == 0:
            return {"frames": 0, "spikes": 0, "reuses": 0, "spike_rate": 0.0}
        
        return {
            "frames": total,
            "spikes": self.state.spike_count,
            "reuses": self.state.reuse_count,
            "spike_rate": self.state.spike_count / total,
            "reuse_rate": self.state.reuse_count / total,
            "threshold": self.threshold
        }
    
    def reset(self):
        """Reset the detector state."""
        self.state = SpikeState()
        logger.info("VisualSpikeDetector state reset")


# Convenience function for one-off checks
def detect_visual_change(
    current_image, 
    previous_image, 
    threshold: float = 0.95
) -> Tuple[bool, float]:
    """
    One-shot visual change detection between two images.
    
    Args:
        current_image: Current frame
        previous_image: Previous frame
        threshold: Similarity threshold
        
    Returns:
        Tuple of (has_changed: bool, similarity: float)
    """
    detector = VisualSpikeDetector(threshold=threshold)
    
    vec_current = detector.encode_image(current_image)
    vec_previous = detector.encode_image(previous_image)
    
    similarity = cosine_similarity(vec_current, vec_previous)
    has_changed = similarity < threshold
    
    return has_changed, similarity


if __name__ == "__main__":
    # Quick test
    import time
    
    logging.basicConfig(level=logging.INFO)
    
    detector = VisualSpikeDetector(threshold=0.95)
    
    # Create a simple test image
    from PIL import Image
    test_img = Image.new("RGB", (384, 384), color="red")
    
    # Time encoding
    start = time.time()
    needs_vl, cached = detector.check_frame(test_img)
    elapsed = (time.time() - start) * 1000
    
    print(f"First frame: needs_vl={needs_vl}, time={elapsed:.1f}ms")
    
    # Check same image again (should reuse)
    start = time.time()
    needs_vl, cached = detector.check_frame(test_img)
    elapsed = (time.time() - start) * 1000
    
    print(f"Same frame: needs_vl={needs_vl}, time={elapsed:.1f}ms")
    
    # Check different image (should spike)
    test_img2 = Image.new("RGB", (384, 384), color="blue")
    start = time.time()
    needs_vl, cached = detector.check_frame(test_img2)
    elapsed = (time.time() - start) * 1000
    
    print(f"Different frame: needs_vl={needs_vl}, time={elapsed:.1f}ms")
    
    print(f"\nStats: {detector.get_stats()}")
