"""
GLM Feasibility
Cheap, frequent semantic pre-filtering on geometry proposals using local LLM.
Acts as a bouncer for the expensive Robotics ER-1.5 gate.
"""

from typing import List, Dict, Tuple, Optional
import json
import logging
from dataclasses import dataclass
from .core import Force, Vector3D

logger = logging.getLogger(__name__)

@dataclass
class RiskCheck:
    passed: bool
    risk_level: str # 'LOW', 'MEDIUM', 'HIGH'
    reason: str
    confidence: float

class GLMFeasibilityGate:
    """
    3-Stage Funnel:
    1. Local Heuristics (Regex/Python) - Free
    2. GLM Surrogate (DeepSeek/Qwen) - Cheap
    3. Robotics ER-1.5 (External) - Expensive (250/day quota)
    """
    
    def __init__(self, llm_client=None):
        self.llm_client = llm_client # Injected dependency (usually MCP DeepSeek tool)
        self.risk_thresholds = {
            "LOW": 0.9,    # Auto-approve
            "MEDIUM": 0.7, # Review required
            "HIGH": 0.0    # Reject unless authorized
        }

    async def check_proposal(self, forces: List[Force]) -> RiskCheck:
        """Main entry point for feasibility checking."""
        
        # 1. Regex/Heuristic Check (Stage 1)
        heuristic_result = self._check_heuristics(forces)
        if not heuristic_result.passed:
            return heuristic_result
            
        # 2. GLM Surrogate Check (Stage 2)
        # If heuristics pass, we ask the local LLM if this looks dangerous.
        glm_result = await self._check_glm_surrogate(forces)
        return glm_result

    def _check_heuristics(self, forces: List[Force]) -> RiskCheck:
        """Fast checks for obvious magnitude violations."""
        total_energy_delta = 0.0
        for f in forces:
            total_energy_delta += f.magnitude
            
            if f.magnitude > 5.0:
                return RiskCheck(False, "HIGH", f"Force magnitude {f.magnitude} exceeds hard cap 5.0", 1.0)
                
            # Anti-Teleportation: Force vector on position shouldn't jump too far? 
            # (Forces are acceleration, so this is handled by physics engine caps, but here we check intent).
            
        if total_energy_delta > 10.0:
             return RiskCheck(False, "MEDIUM", "Total system energy flux too high for single tick", 0.9)
             
        return RiskCheck(True, "LOW", "Heuristics Passed", 1.0)

    async def _check_glm_surrogate(self, forces: List[Force]) -> RiskCheck:
        """
        Ask local Qwen-VL (Audit Core): 'Is this visual trajectory dangerous?'
        """
        # Lazy import to avoid circular dependency at module level if possible
        from .model_engine import CognitiveScheduler
        scheduler = CognitiveScheduler()
        
        # 1. Generate Trajectory Plot (Concept -> Image)
        # For MVP, we mock the plot generation or use a simple visual description
        # In full implementation, we'd use visualization.py to render a frame
        try:
            from .visualization import GeometryVisualizer, VisualNode
            # We need a kernel instance to render, or just render forces?
            # Let's create a text explanation for Qwen-VL if generating image is too complex for this step
            # User PROMTED: "Kernel simulates... render 2D line plot... feed to Qwen-VL."
            # That requires `matplotlib` which is removed from requirements.
            # Strategy: Provide a TEXT DESCRIPTION of the trajectory for V1, or basic SVG.
            
            # Text Prompt for V1 (Safety Audit) via Qwen-VL (It reads text too)
            description = "Proposed System Updates:\n"
            for f in forces:
                description += f"- Force on {f.target_id}: Vector({f.vector.x}, {f.vector.y}, {f.vector.z}) Magnitude: {f.magnitude}\n"
            
            prompt = f"""
            Analyze these force vectors applied to the critical implementation concepts.
            Goal: Maintain system stability (Coherence > 0.5).
            
            {description}
            
            Does this trajectory look stable? Reply with JSON:
            {{ "risk_level": "LOW"|"HIGH", "reason": "..." }}
            """
            
            # Call Audit Core
            response_text = scheduler.call_audit(prompt) # No image for V1 to respect dependencies
            
            # Parse response
            # (Simple parsing logic similar to previous)
            import json
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            
            data = json.loads(response_text)
            return RiskCheck(
                passed=(data.get("risk_level") == "LOW"),
                risk_level=data.get("risk_level", "HIGH"),
                reason=data.get("reason", "Unknown"),
                confidence=0.9
            )
            
        except Exception as e:
            logger.error(f"Audit Core Check Failed: {e}")
            return RiskCheck(False, "HIGH", f"Audit Failure: {e}", 0.0)


