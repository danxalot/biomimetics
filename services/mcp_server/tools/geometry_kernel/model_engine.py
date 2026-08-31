"""
V2 Geometry Kernel - Model Engine (Cognitive Scheduler)

Orchestrates the Cognitive Tick with Visual Spike Detection:
...
Architecture:
- GPU Router (:8080) - DeepSeek R1 (always hot)
- Vision / Reasoning (:11435) - Qwen3 VL / 4B (on host)
- CPU Guardian (:11436) - Granite Guardian (one-shot)
- Python - SigLIP (change detection)
"""

import os
import time
import logging
import requests
from typing import Optional, Dict, Any
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))) # Adjusted for tools/geometry_kernel/... path
try:
    from shared.model_config import get_model
except ImportError:
    def get_model(key):
        if "VISION" in key or "VL" in key: return "qwen3-vl-2b"
        return "deepseek-r1-distill-qwen-1.5b"
from dataclasses import dataclass, field
from pathlib import Path

try:
    from .visual_spike import VisualSpikeDetector
except ImportError:
    from visual_spike import VisualSpikeDetector

logger = logging.getLogger(__name__)


@dataclass
class CognitiveTickResult:
    """Result of a single cognitive tick."""
    frame_id: int
    visual_description: str
    visual_spike: bool
    reasoning_output: Optional[str] = None
    safety_verdict: Optional[str] = None
    
    # Timing
    perception_ms: float = 0.0
    reasoning_ms: float = 0.0
    safety_ms: float = 0.0
    total_ms: float = 0.0
    
    # Metrics
    similarity: Optional[float] = None


@dataclass
class ServerConfig:
    """llama.cpp server configuration."""
    name: str
    host: str
    port: int
    model: str
    
    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"


class CognitiveScheduler:
    """
    Orchestrates the V2 Geometry Kernel Cognitive Tick.
    
    Uses Visual Spike Detection to minimize expensive VL calls.
    Routes requests to appropriate llama.cpp servers.
    
    Example:
        scheduler = CognitiveScheduler()
        
        for frame in frames:
            result = scheduler.tick(frame)
            if result.visual_spike:
                print(f"Visual change detected: {result.visual_description}")
    """
    
    # Server configurations
    # Server configurations
    # Pointing to OCI Tailscale IP
    OCI_HOST = os.getenv("OCI_LLM_HOST", "100.70.0.13")
    
    GPU_ROUTER = ServerConfig(
        name="OCI Reasoner",
        host=OCI_HOST,
        port=8082, # STReasoner Port
        model="st-reasoner"
    )
    
    CPU_VL = ServerConfig(
        name="OCI Vision",
        host=OCI_HOST, 
        port=8082, # GeoUni/Qwen Port
        model="geouni"
    )
    
    def __init__(
        self,
        spike_threshold: float = 0.95,
        enable_safety: bool = False,
        force_mute_vision: bool = False,  # No longer muted by default since NanoVLM is VRAM-safe
        timeout: float = 30.0
    ):
        """
        Initialize the cognitive scheduler.
        
        Args:
            spike_threshold: Cosine similarity threshold for visual spike
            enable_safety: Whether to run Guardian safety screening
            force_mute_vision: If True, bypass VL calls (Audit/Perception)
            timeout: Request timeout in seconds
        """
        self.spike_threshold = spike_threshold
        self.enable_safety = enable_safety
        self.force_mute_vision = force_mute_vision or os.getenv("ARCA_MUTE_VISION", "false").lower() == "true"
        self.timeout = timeout
        
        # Initialize spike detector
        self.spike_detector = VisualSpikeDetector(threshold=spike_threshold)
        
        # State
        self.tick_count = 0
        self.last_result: Optional[CognitiveTickResult] = None
        
        logger.info(
            f"CognitiveScheduler initialized "
            f"(threshold={spike_threshold}, safety={enable_safety})"
        )
    
    def _check_server(self, server: ServerConfig) -> bool:
        """Check if a server is available."""
        try:
            resp = requests.get(
                f"{server.base_url}/health",
                timeout=2.0
            )
            return resp.status_code == 200
        except Exception:
            return False
    
    def _call_completion(
        self, 
        server: ServerConfig,
        prompt: str,
        max_tokens: int = 200,
        system: Optional[str] = None
    ) -> str:
        """Call a llama.cpp server for completion."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        try:
            resp = requests.post(
                f"{server.base_url}/v1/chat/completions",
                json={
                    "model": server.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.3
                },
                timeout=self.timeout
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Error calling {server.name}: {e}")
            return f"[ERROR: {e}]"
    
    def _run_perception(self, image) -> tuple[bool, str, float]:
        """
        Run perception phase with spike detection.
        
        Returns:
            Tuple of (needs_vl, description, elapsed_ms)
        """
        start = time.time()
        # Phase 1: Visual Spike Detection (CPU-based SigLIP/CLIP)
        needs_vl, cached, similarity = self.spike_detector.check(image)
        
        # Phase 2: Lightweight Vision Audit (NanoVLM / CPU)
        # We run this even if no spike is detected to get a "Vision Heartbeat" description
        audit_description = cached
        if not needs_vl or self.force_mute_vision:
            try:
                # Call NEW NanoVLM endpoint in embedding_service
                # This provides a description/signature without using Host GPU
                import base64
                from io import BytesIO
                if hasattr(image, 'save'): # PIL Image
                    buffered = BytesIO()
                    image.save(buffered, format="JPEG")
                    img_str = base64.b64encode(buffered.getvalue()).decode()
                else: # Path or B64
                    img_str = str(image)

                resp = requests.post(
                    "http://embedding_service:8005/v1/vision/audit",
                    json={"image_input": img_str},
                    headers={"X-Genesis-Chain": "true"},
                    timeout=10.0
                )
                if resp.status_code == 200:
                    audit_data = resp.json()
                    audit_description = f"NanoVLM Audit: {audit_data.get('audit_signature', 'active')}"
                    logger.info(f"✅ Vision Audit (CPU) Success: {audit_description}")
            except Exception as e:
                logger.warning(f"⚠️ Vision Audit (CPU) failed: {e}. Falling back to cache.")

        if not needs_vl:
            elapsed = (time.time() - start) * 1000
            return False, audit_description, elapsed
        
        # Phase 3: High-Fidelity Perception (GPU Qwen-VL)
        # ONLY if there is a massive change AND we aren't muted
        if self.force_mute_vision:
            logger.info("High-Fidelity Vision (Qwen) is MUTED. Using CPU Audit only.")
            elapsed = (time.time() - start) * 1000
            return True, audit_description, elapsed

        logger.info("🚀 Visual spike detected - calling Qwen VL via Gateway...")
        
        # Use LLM Gateway for Qwen-VL (Port 8080)
        gateway_url = os.environ.get("LLM_GATEWAY_URL", "http://llm_gateway:8080")
        description = self._call_completion(
            ServerConfig(name="Gateway-VL", host="llm_gateway", port=8080, model="vision"),
            "Describe what you see in this image briefly.",
            max_tokens=100
        )
        
        # Update cached description
        self.spike_detector.update_description(description)
        
        elapsed = (time.time() - start) * 1000
        logger.debug(f"Perception Complete: {elapsed:.1f}ms")
        return True, description, elapsed
    
    def _run_reasoning(self, context: str) -> tuple[str, float]:
        """
        Run reasoning phase with DeepSeek R1.
        
        Returns:
            Tuple of (reasoning_output, elapsed_ms)
        """
        start = time.time()
        
        output = self._call_completion(
            self.GPU_ROUTER,
            context,
            max_tokens=200,
            system="You are a reasoning assistant. Think step by step."
        )
        
        elapsed = (time.time() - start) * 1000
        logger.debug(f"Reasoning: {elapsed:.1f}ms")
        return output, elapsed
    
    
    def tick(self, image) -> CognitiveTickResult:
        """
        Execute a single cognitive tick.
        
        Args:
            image: Image to process (PIL, numpy, or path)
            
        Returns:
            CognitiveTickResult with all outputs and timing
        """
        self.tick_count += 1
        tick_start = time.time()
        
        # Phase 1: Perception (with spike detection)
        visual_spike, description, perception_ms = self._run_perception(image)
        
        # Phase 2: Reasoning (only if we have new visual info or first tick)
        reasoning_output = None
        reasoning_ms = 0.0
        if visual_spike or self.tick_count == 1:
            context = f"Visual observation: {description}\n\nWhat should we do?"
            reasoning_output, reasoning_ms = self._run_reasoning(context)
        
        # Phase 3: Safety (placeholder - not yet implemented)
        safety_verdict = None
        safety_ms = 0.0
        
        total_ms = (time.time() - tick_start) * 1000
        
        result = CognitiveTickResult(
            frame_id=self.tick_count,
            visual_description=description,
            visual_spike=visual_spike,
            reasoning_output=reasoning_output,
            safety_verdict=safety_verdict,
            perception_ms=perception_ms,
            reasoning_ms=reasoning_ms,
            safety_ms=safety_ms,
            total_ms=total_ms
        )
        
        self.last_result = result
        
        logger.info(
            f"Tick {self.tick_count}: spike={visual_spike}, "
            f"perception={perception_ms:.0f}ms, "
            f"reasoning={reasoning_ms:.0f}ms, "
            f"total={total_ms:.0f}ms"
        )
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        spike_stats = self.spike_detector.get_stats()
        return {
            "ticks": self.tick_count,
            "spike_rate": spike_stats.get("spike_rate", 0.0),
            "reuse_rate": spike_stats.get("reuse_rate", 0.0),
            "threshold": self.spike_threshold,
            "safety_enabled": self.enable_safety
        }

    def run_reasoning_phase(self, context_text: str, prompt_template: str) -> str:
        """
        Run reasoning phase for RLM document walking.
        
        Used by recursive_ingestion.py to extract concepts from document chunks.
        
        Args:
            context_text: The document chunk to analyze
            prompt_template: The prompt with {context} placeholder
            
        Returns:
            LLM response with extracted concepts as JSON
        """
        # Build the full prompt
        full_prompt = prompt_template.format(context=context_text) if "{context}" in prompt_template else f"{prompt_template}\n\nContent:\n{context_text}"
        
        # Use LLM Gateway instead of local llama.cpp for reliability
        import os
        llm_gateway_url = os.environ.get("LLM_GATEWAY_URL", "http://llm_gateway:8080")
        
        # Ensure base URL doesn't have path suffix
        if llm_gateway_url.endswith("/v1/chat/completions"):
            llm_gateway_url = llm_gateway_url.replace("/v1/chat/completions", "")
        
        try:
            # Using configured Learn Model
            model_name = get_model("LEARN_MODEL")
            logger.info(f"Running Reasoning Phase with model: {model_name}")
            
            resp = requests.post(
                f"{llm_gateway_url}/v1/chat/completions",
                json={
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": "You are a document analyzer. Extract key concepts and return ONLY valid JSON. Do not include thinking process or preamble."},
                        {"role": "user", "content": full_prompt}
                    ],
                    "max_tokens": 4096, # Increased for Gemma 3 27B
                    "temperature": 0.2
                },
                timeout=600.0
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            
            # Robo-fix: Strip markdown fences if present
            import re
            json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                content = json_match.group(1)
            
            return content
        except Exception as e:
            logger.error(f"Reasoning phase failed: {e}")
            return '{"error": "' + str(e) + '"}'


if __name__ == "__main__":
    import sys
    from PIL import Image
    
    logging.basicConfig(level=logging.INFO)
    
    scheduler = CognitiveScheduler(
        spike_threshold=0.95,
        enable_safety=False  # Disable for quick testing
    )
    
    # Create test images
    img1 = Image.new("RGB", (224, 224), color="red")
    img2 = Image.new("RGB", (224, 224), color="red")  # Same
    img3 = Image.new("RGB", (224, 224), color="blue")  # Different
    
    print("Testing Cognitive Scheduler...")
    print()
    
    # Tick 1 - First frame
    result = scheduler.tick(img1)
    print(f"Tick 1: spike={result.visual_spike}, total={result.total_ms:.0f}ms")
    
    # Tick 2 - Same frame (should reuse)
    result = scheduler.tick(img2)
    print(f"Tick 2: spike={result.visual_spike}, total={result.total_ms:.0f}ms")
    
    # Tick 3 - Different frame (should spike)
    result = scheduler.tick(img3)
    print(f"Tick 3: spike={result.visual_spike}, total={result.total_ms:.0f}ms")
    
    print()
    print(f"Stats: {scheduler.get_stats()}")
