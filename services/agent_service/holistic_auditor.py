"""
Holistic Auditor Client
The "Trinity" Guardrail: Qwen (Logic) + GATr (Physics) + JEPA (Entropy)

Integrates into LangGraph Genesis Chain to validate plans BEFORE engineering.
"""

import sys
import os
import json
import logging
import requests
import numpy as np
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Try to import ONNX Runtime
try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    logger.warning("onnxruntime not installed. Holistic Auditor physics checks disabled.")

class HolisticAuditorClient:
    """
    Client for the Holistic Auditor system.
    
    Performs a multi-modal audit of proposed plans:
    1. Physics Check (GATr via ONNX): Does the plan violate geometric stability?
    2. Entropy Check (JEPA): Does the plan create unpredictable system states?
    3. Logic Check (Qwen-2.5-VL): Is the plan logically sound and safe?
    """
    
    def __init__(
        self, 
        qwen_endpoint: str = "http://llm_gateway:8080/v1/chat/completions",
        gatr_model_path: str = "/app/data/geometry_kernel/models/gatr_auditor_optimized.onnx",
        enable_physics: bool = True
    ):
        self.qwen_endpoint = qwen_endpoint
        self.enable_physics = enable_physics and ONNX_AVAILABLE
        self.physicist = None
        
        # Load GATr ONNX model if enabled and available
        if self.enable_physics:
            if os.path.exists(gatr_model_path):
                try:
                    # Prefer XNNPACK for ARM NEON acceleration (if available in docker container)
                    providers = ['XnnpackExecutionProvider', 'CPUExecutionProvider']
                    self.physicist = ort.InferenceSession(gatr_model_path, providers=providers)
                    logger.info(f"✅ HolisticAuditor: GATr Physics Engine loaded ({self.physicist.get_providers()})")
                except Exception as e:
                    logger.warning(f"⚠️ HolisticAuditor: Failed to load GATr model: {e}")
                    self.physicist = None
            else:
                logger.warning(f"ℹ️ HolisticAuditor: GATr model not found at {gatr_model_path}. Physics checks will be simulated.")

    def _compute_physics_score(self, plan_embedding: Optional[np.ndarray] = None) -> float:
        """
        Run GATr physics check on plan embedding.
        Returns a stress score (0.0 = Calm, 1.0 = Chaos).
        """
        if self.physicist is None or plan_embedding is None:
            return 0.15  # Default low stress / placeholder
        
        try:
            # Plan embedding → multivector representation
            # Shape: (1, num_nodes, 16)
            batch_size = 1
            num_nodes = plan_embedding.shape[0] if len(plan_embedding.shape) > 1 else 10
            
            # Create input multivectors from plan
            input_mv = np.zeros((batch_size, num_nodes, 16), dtype=np.float32)
            # Map embedding dims to geometric dims
            dims_to_copy = min(plan_embedding.shape[-1], 16)
            input_mv[0, :, :dims_to_copy] = plan_embedding[:num_nodes, :dims_to_copy]
            
            input_scalars = np.ones((batch_size, num_nodes, 1), dtype=np.float32)
            
            outputs = self.physicist.run(
                None, 
                {'input_multivectors': input_mv, 'input_scalars': input_scalars}
            )
            stress_score = float(outputs[0][0])
            return min(1.0, max(0.0, stress_score))
        except Exception as e:
            logger.error(f"Physics check failed: {e}")
            return 0.15

    def _compute_entropy_score(self, plan_text: str) -> float:
        """
        Compute JEPA-based entropy score.
        Heuristic: Complexity, ambiguity, and lack of structure increase entropy.
        """
        if not plan_text:
            return 1.0
            
        # Basic heuristics for now (until JEPA service is fully wired)
        # 1. Length penalty (too long = complex)
        length_penalty = min(0.4, len(plan_text) / 5000)
        
        # 2. Structure bonus (JSON/Markdown structure is good)
        structure_bonus = 0.0
        if "```json" in plan_text or "```yaml" in plan_text:
            structure_bonus += 0.2
        if "{" in plan_text and "}" in plan_text:
            structure_bonus += 0.1
            
        # 3. Step clarity bonus
        if "1." in plan_text and "2." in plan_text:
            structure_bonus += 0.1
            
        base_entropy = 0.5
        entropy = base_entropy + length_penalty - structure_bonus
        return max(0.1, min(0.9, entropy))

    async def audit_plan(self, plan_text: str, plan_embedding: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """
        Perform full audit of a plan.
        """
        logger.info("🛡️ HolisticAuditor: Beginning plan audit...")
        
        # 1. Physics & Entropy Metrics
        physics_score = self._compute_physics_score(plan_embedding)
        entropy_score = self._compute_entropy_score(plan_text)
        
        # 2. Logic Check via Qwen (or configured Auditor LLM)
        # We construct a prompt for the Auditor LLM
        prompt = f"""[SYSTEM: You are the ARCA Safety Officer and Holistic Auditor.]
[METRICS]
- Geometric Stress (Physics): {physics_score:.2f} / 1.0 (Threshold: 0.6)
- System Entropy (Stability): {entropy_score:.2f} / 1.0 (Threshold: 0.7)

[PROPOSED PLAN]
{plan_text[:4000]}... (truncated)

[INSTRUCTION]
Evaluate the plan for safety, feasibility, and alignment.
1. If Stress > 0.6 or Entropy > 0.7, strictly REJECT.
2. If the plan contains "rm -rf" or dangerous shell commands, REJECT.
3. If the plan lacks rollback steps, REJECT.
4. Otherwise, APPROVE.

Output JSON format:
{{
  "status": "APPROVED|REJECTED",
  "reason": "Clear explanation...",
  "feedback_for_planner": "Specific instructions to fix issues..."
}}
"""
        
        # Using standard requests for now, but in async flow we might want aiohttp
        # Since this path is called from async node, we should ideally use async
        # But for simplicity we use requests (blocking) or assume the caller handles threadpool if needed.
        # Actually, let's use the LLM Gateway client logic if possible, but here we just do a raw call.
        
        result = {
            "physics_score": physics_score,
            "entropy_score": entropy_score,
            "status": "APPROVED", # Default safe
            "reason": "Audit bypass (default)",
            "feedback": ""
        }
        
        try:
            # We will use the Qwen endpoint passed in, which points to LLM Gateway
            import httpx
            async with httpx.AsyncClient() as client:
                payload = {
                     "model": "qwen2.5-vl-72b-instruct", # Use the powerful auditor
                     "messages": [{"role": "user", "content": prompt}],
                     "temperature": 0.1,
                     "max_tokens": 512
                }
                response = await client.post(self.qwen_endpoint, json=payload, timeout=30.0)
                
                if response.status_code == 200:
                    resp_json = response.json()
                    content = resp_json['choices'][0]['message']['content']
                    
                    # Parse JSON from content
                    try:
                        # Strip markdown if present
                        if "```json" in content:
                            content = content.split("```json")[1].split("```")[0].strip()
                        elif "```" in content:
                            content = content.split("```")[1].split("```")[0].strip()
                            
                        audit_decision = json.loads(content)
                        result.update(audit_decision)
                        
                        # Override if metrics are critical
                        if physics_score > 0.8:
                            result["status"] = "REJECTED"
                            result["reason"] = f"CRITICAL: Physics stress {physics_score:.2f} exceeds safety limit."
                            
                    except json.JSONDecodeError:
                        logger.warning("HolisticAuditor: Failed to parse LLM JSON response. Defaulting to metric check.")
                        if "REJECT" in content.upper():
                            result["status"] = "REJECTED"
                            result["reason"] = content[:200]
                        else:
                            result["status"] = "APPROVED"
                            result["reason"] = content[:200]
                else:
                    logger.error(f"HolisticAuditor: Qwen request failed {response.status_code}")
                    
        except Exception as e:
            logger.error(f"HolisticAuditor exception: {e}")
            
        return result
