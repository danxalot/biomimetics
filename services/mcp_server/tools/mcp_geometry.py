import os
import logging
import json
from typing import Dict, Any, List, Optional
from tools.geometry_kernel.model_engine import CognitiveScheduler, CognitivePhase

logger = logging.getLogger(__name__)

class SemanticInterpreterTool:
    """
    Geometry Kernel: Semantic Interpreter.
    Uses Reasoning Core (DeepSeek R1) via Cognitive Scheduler.
    """
    def __init__(self):
        self.scheduler = CognitiveScheduler()
        logger.info("SemanticInterpreterTool initialized with CognitiveScheduler")

    def interpret(self, snapshot: Dict[str, Any], events: List[Dict[str, Any]], mode: str = "wake") -> Dict[str, Any]:
        """
        Interprets a system snapshot and recent events into geometric forces.
        """
        prompt = self._build_prompt(snapshot, events, mode)
        try:
            # Use Reasoning Core (DeepSeek R1)
            response = self.scheduler.call_reasoning(prompt)
            return self._parse_json_response(response)
        except Exception as e:
            logger.error(f"Semantic interpretation failed: {e}")
            return {"error": str(e), "force_vectors": [], "attractor_proposals": []}

    def _build_prompt(self, snapshot, events, mode):
        return f"""
        ROLE: You are the Semantic Interpreter for the ARCA Geometry Kernel.
        TASK: Translate the following system state and events into abstract geometric forces.
        MODE: {mode.upper()}

        INPUT STATE:
        {json.dumps(snapshot, indent=2)}

        RECENT EVENTS:
        {json.dumps(events, indent=2)}

        OUTPUT FORMAT:
        Return ONLY valid JSON with the following structure:
        {{
            "force_vectors": [
                {{"target_id": "concept_id", "vector": [x, y, z], "magnitude": 0.0-1.0, "source": "event_id"}}
            ],
            "attractor_proposals": [
                {{"center": [x, y, z], "radius": 0.0, "depth": 0.0, "reason": "..."}}
            ],
            "risk_estimate": 0.0-1.0
        }}
        """

    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        try:
            text = response_text.strip()
            # DeepSeek might include thinking tokens <think>...</think>. Clean them.
            if "<think>" in text:
                text = text.split("</think>")[-1].strip()
            
            if text.lower().startswith("```json"):
                text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text.rsplit("\n", 1)[0]
            text = text.strip("`") # Simple cleanup
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from model response")
            # Try to find JSON block
            try:
                start = text.find("{")
                end = text.rfind("}") + 1
                if start >= 0 and end > start:
                     return json.loads(text[start:end])
            except:
                pass
            return {"raw_output": response_text}

class FeasibilityAuditorTool:
    """
    Geometry Kernel: Feasibility Auditor.
    Uses Audit Core (Qwen-VL) via Cognitive Scheduler.
    """
    def __init__(self):
        self.scheduler = CognitiveScheduler()
        logger.info("FeasibilityAuditorTool initialized with CognitiveScheduler")

    def audit(self, state_before: Dict[str, Any], state_after: Dict[str, Any], forces: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Audits a proposed state transition for geometric feasibility/stability.
        """
        prompt = self._build_audit_prompt(state_before, state_after, forces)
        try:
            # Use Audit Core (Qwen-VL) - capable of logic + future visual checks
            response = self.scheduler.call_audit(prompt)
            return self._parse_json_response(response)
        except Exception as e:
            logger.error(f"Feasibility audit failed: {e}")
            return {"verdict": "reject", "reason": str(e)}

    def _build_audit_prompt(self, before, after, forces):
        return f"""
        ROLE: You are the Feasibility Auditor for the ARCA Geometry Kernel.
        TASK: Audit the transition from State A to State B under applied Forces.
        CRITERIA: Check for discontinuities, excessive curvature, and instability.

        STATE BEFORE:
        {json.dumps(before, indent=2)}

        STATE AFTER (PROPOSED):
        {json.dumps(after, indent=2)}

        APPLIED FORCES:
        {json.dumps(forces, indent=2)}

        OUTPUT FORMAT:
        Return ONLY valid JSON:
        {{
            "verdict": "accept" | "soften" | "reject",
            "confidence": 0.0-1.0,
            "issues": ["list", "of", "issues"],
            "notes": "Reasoning..."
        }}
        """

    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        try:
            text = response_text.strip()
            if text.lower().startswith("```json"):
                text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text.rsplit("\n", 1)[0]
            text = text.strip("`")
            return json.loads(text)
        except json.JSONDecodeError:
            try:
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                if start >= 0 and end > start:
                     return json.loads(response_text[start:end])
            except:
                pass
            return {"verdict": "reject", "reason": "Failed to parse model output"}

