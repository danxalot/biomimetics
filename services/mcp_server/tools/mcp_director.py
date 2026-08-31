
import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
import numpy as np
import requests

logger = logging.getLogger(__name__)

ARCA_ROOT = Path(os.environ.get("ARCA_ROOT", "/home/ubuntu/ARCA"))
REASONING_BANK_PATH = Path(os.environ.get("REASONING_BANK_PATH", str(ARCA_ROOT / "services/mcp_server/data/reasoning_bank.json")))

class DirectorTools:
    """
    Implements the Meta-Cognitive tools for the ARCA Director Protocol.
    """
    def __init__(self, skills_manager=None):
        self.skills_manager = skills_manager
        # Placeholder for vector connection - in prod this connects to redis/HSE
        self.vector_dim = 768 

    async def read_system_intuition(self) -> Dict[str, Any]:
        """
        The Translator: Converts raw system state (vectors) into a conceptual brief.
        Real implementation would read from Redix/HSE.
        """
        # Mock for now until HSE is fully live
        return {
            "system_state": {
                "entropy_level": "low",
                "stress_vectors": [],
                "coherence_score": 0.95
            },
            "conceptual_brief": "System is stable. No active anomalies detected in the geometry. Ready for new context.",
            "recommendation": "Proceed with standard execution."
        }

    async def process_input_attention(self, text: str) -> Dict[str, Any]:
        """
        The HDC Filter: Re-ranks user input against local project vectors.
        """
        # Mock logic
        focus_points = []
        if "deploy" in text.lower():
            focus_points.append("Deployment Logic (scripts/oci)")
        if "memory" in text.lower():
            focus_points.append("Memory Systems (services/memory_system)")
        
        return {
            "original_input": text,
            "focus_points": focus_points or ["General Context"],
            "noise_filter_applied": True
        }

    async def promote_to_skill(self, task_name: str, python_code: str) -> Dict[str, Any]:
        """
        Formalizes successful ad-hoc logic into a permanent Skill Frame.
        """
        try:
            # 1. Save Code
            skills_dir = ARCA_ROOT / "skills"
            skills_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = skills_dir / f"{task_name}.py"
            with open(file_path, "w") as f:
                f.write(python_code)
            
            # 2. Register in Reasoning Bank
            if REASONING_BANK_PATH.exists():
                with open(REASONING_BANK_PATH, "r") as f:
                    data = json.load(f)
            else:
                data = {"patterns": [], "skills": []}
            
            # Check duplicates
            existing = next((s for s in data.get("skills", []) if s["name"] == task_name), None)
            if existing:
                existing["updated_at"] = datetime.now().isoformat()
            else:
                data["skills"].append({
                    "name": task_name,
                    "file_path": str(file_path),
                    "created_at": datetime.now().isoformat()
                })
            
            with open(REASONING_BANK_PATH, "w") as f:
                json.dump(data, f, indent=2)

            return {
                "status": "promoted",
                "skill_name": task_name,
                "file_path": str(file_path),
                "message": "Skill formalized and recorded in Reasoning Bank."
            }
        except Exception as e:
            logger.error(f"Failed to promote skill: {e}")
            return {"error": f"Failed to promote skill: {str(e)}"}

    async def read_mission_state(self) -> Dict[str, Any]:
        """
        Fetches current LangGraph mission state via Agent Service API.
        """
        try:
            agent_service_url = os.environ.get("AGENT_SERVICE_URL", "http://agent_service:8088")
            # This endpoint might need to be created in Agent Service, but we mock the client side for now
            # resp = requests.get(f"{agent_service_url}/mission/state", timeout=2)
            # return resp.json()
            return {
                "active_phase": "Unknown (API not connected)",
                "mission_goal": "Maintain System Homeostasis",
                "steps_completed": []
            }
        except Exception as e:
            return {"error": f"Failed to read mission state: {str(e)}"}

    async def dispatch_agent(self, agent_name: str, task: str) -> Dict[str, Any]:
        """
        Delegates a task to a specialized sub-agent (e.g., Serena, TheOracle).
        This tool call is intercepted by the LangGraph router to switch control flow.
        """
        valid_agents = ["serena", "builder", "oracle", "architect", "scout"]
        if agent_name.lower() not in valid_agents:
            return {
                "status": "error",
                "message": f"Invalid agent '{agent_name}'. Valid agents: {valid_agents}"
            }
        
        return {
            "status": "dispatched",
            "agent": agent_name,
            "task": task,
            "message": f"Task delegated to {agent_name}."
        }

# Global instance
_director = None

def get_director_tools():
    global _director
    if _director is None:
        _director = DirectorTools()
    return _director
