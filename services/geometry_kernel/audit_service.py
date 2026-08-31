"""
Geometry Kernel - Audit Service
Uses Qwen-VL to visually audit proposed trajectories for safety and stability.
"""

import logging
import os
import requests
from typing import Optional, Dict, Any
try:
    from .core import Force, KernelState
except ImportError:
    from core import Force, KernelState

logger = logging.getLogger(__name__)

class LocalAuditor:
    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.llm_gateway_url = os.environ.get("LLM_GATEWAY_URL", "http://llm_gateway:8080")

    def audit_trajectory(self, proposed_state: KernelState, trajectory_plot_path: str) -> str:
        """
        Instead of sending data to cloud, we show the trajectory plot to Qwen-VL.
        """
        # 1. Fast path check: if index is very high, auto-approve
        # Note: Core might not have stability_index directly on proposed_state.health_metrics
        health = proposed_state.health_metrics or {}
        stability = health.get("stability_index", 1.0)
        
        if stability > 0.9:
            logger.info(f"Audit auto-approved (stability={stability:.2f})")
            return "APPROVED"

        # 2. Visual audit via Cognitive Tick (simulated here)
        logger.info(f"Stability low ({stability:.2f}). Triggering visual audit of {trajectory_plot_path}...")
        
        # In V2, we call Qwen-VL via the scheduler/gateway
        prompt = "Analyze this trajectory plot. Is it stable or does it show diverging/chaotic behavior? Answer APPROVED or REJECTED."
        
        try:
            # We use the scheduler's reasoning phase but with the vision model
            # Since scheduler.tick handles images, we'll call completion directly for now 
            # or use scheduler._call_completion with CPU_VL config
            
            # For simplicity, we call the gateway directly for the vision model
            resp = requests.post(
                f"{self.llm_gateway_url}/v1/chat/completions",
                json={
                    "model": "qwen3-vl-2b",
                    "messages": [
                        {
                            "role": "user", 
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": f"file://{trajectory_plot_path}"}}
                            ]
                        }
                    ],
                    "max_tokens": 10
                },
                timeout=30.0
            )
            
            if resp.status_code == 200:
                verdict = resp.json()["choices"][0]["message"]["content"].upper()
                if "REJECTED" in verdict or "UNSTABLE" in verdict:
                    return "REJECTED"
                return "APPROVED"
            
        except Exception as e:
            logger.error(f"Visual audit failed: {e}")
            
        # Fallback to approve if visual audit fails but stability isn't CRITICAL
        return "APPROVED" if stability > 0.6 else "REJECTED"
