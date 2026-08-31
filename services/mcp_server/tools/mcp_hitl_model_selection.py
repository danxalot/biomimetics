"""
Human-In-The-Loop (HITL) Model Selection Tool

Enables agents to present available models with quota information to humans
when quota is exceeded (429 errors) or when manual model selection is needed.

This tool is accessible to all agents in the chain and handles user input
for model selection decisions.
"""

import os
import json
import logging
import httpx
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ModelQuotaInfo:
    """Model quota information for user presentation"""
    model_name: str
    calls_today: int
    quota_limit: int
    quota_remaining: int
    quota_percentage_used: float
    status: str  # "available", "low", "exhausted"
    
    def to_display(self) -> str:
        """Format for user display"""
        status_emoji = {
            "available": "✅",
            "low": "⚠️",
            "exhausted": "❌"
        }.get(self.status, "❓")
        
        return f"{status_emoji} {self.model_name}: {self.quota_remaining}/{self.quota_limit} remaining ({self.quota_percentage_used:.1f}% used)"


class HITLModelSelectionTool:
    """
    Human-In-The-Loop tool for manual model selection.
    
    Used when:
    1. A 429 (quota exceeded) error occurs
    2. An agent needs to select which model to use
    3. System needs human guidance on model selection strategy
    
    Accessible to: All agents in the chain (Planner, Engineer, Orchestrator, etc.)
    
    Workflow:
    1. Agent detects need for model selection (429 error or user request)
    2. Calls get_available_models() to fetch current quota status
    3. Presents models to human (via log/UI/API)
    4. Accepts human selection via select_model()
    5. Returns selected model to agent for retry
    """
    
    def __init__(self):
        self.llm_gateway_url = os.getenv("LLM_GATEWAY_URL", "http://llm_gateway:8000")
        self.api_key = os.getenv("ARCA_API_KEY", "")
        
        # Track current session selections
        self._selection_history: List[Dict[str, Any]] = []
        
    async def get_available_models(self) -> Dict[str, Any]:
        """
        Fetch current quota status for all models from llm_gateway.
        
        Returns:
        {
            "timestamp": "2025-12-19T15:30:45",
            "today_pt": "2025-12-19",
            "models": [
                {
                    "model_name": "gemini-3-pro",
                    "calls_today": 45,
                    "quota_limit": 1000,
                    "quota_remaining": 955,
                    "quota_percentage_used": 4.5,
                    "status": "available"
                },
                ...
            ],
            "recommendations": [
                "Primary model (gemini-3-pro) still has 955/1000 quota",
                "All models have good availability"
            ]
        }
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.llm_gateway_url}/usage",
                    timeout=10.0
                )
                
                if response.status_code != 200:
                    logger.error(f"Gateway returned {response.status_code}")
                    raise Exception(f"Gateway error: {response.status_code}")
                
                data = response.json()
                
                # Process quota data into model list
                models = []
                recommendations = []
                
                for model_name, quota_data in data.get("usage", {}).items():
                    quota_remaining = quota_data.get("quota_remaining", 0)
                    quota_limit = quota_data.get("quota_limit", 1)
                    quota_pct = (quota_data.get("calls_today", 0) / quota_limit * 100) if quota_limit > 0 else 0
                    
                    # Determine status
                    if quota_remaining <= 0:
                        status = "exhausted"
                    elif quota_pct >= 80:
                        status = "low"
                    else:
                        status = "available"
                    
                    model_info = {
                        "model_name": model_name,
                        "calls_today": quota_data.get("calls_today", 0),
                        "quota_limit": quota_limit,
                        "quota_remaining": quota_remaining,
                        "quota_percentage_used": round(quota_pct, 2),
                        "status": status
                    }
                    models.append(model_info)
                    
                    # Generate recommendation
                    if status == "exhausted":
                        recommendations.append(f"❌ {model_name} - QUOTA EXHAUSTED")
                    elif status == "low":
                        recommendations.append(f"⚠️ {model_name} - {quota_remaining} requests remaining ({quota_pct:.1f}% used)")
                    else:
                        recommendations.append(f"✅ {model_name} - {quota_remaining} requests available ({quota_pct:.1f}% used)")
                
                # Sort by available quota (descending)
                models.sort(key=lambda x: x["quota_remaining"], reverse=True)
                
                return {
                    "timestamp": datetime.utcnow().isoformat(),
                    "today_pt": data.get("today_pt", ""),
                    "models": models,
                    "recommendations": recommendations,
                    "reset_time": "midnight PT"
                }
                
        except Exception as e:
            logger.error(f"Failed to fetch available models: {e}")
            raise Exception(f"Could not fetch quota status: {str(e)}")

    def format_for_display(self, quota_status: Dict[str, Any]) -> str:
        """
        Format quota status for human-readable display.
        
        Returns a formatted string suitable for logs, UI, or prompts.
        """
        display_lines = [
            "=" * 70,
            "🔄 AVAILABLE MODELS FOR SELECTION",
            "=" * 70,
            f"Current Time: {quota_status['timestamp']} (Date in PT: {quota_status['today_pt']})",
            "",
            "MODEL QUOTA STATUS:",
            "-" * 70,
        ]
        
        for idx, model in enumerate(quota_status["models"], 1):
            status_emoji = {
                "available": "✅",
                "low": "⚠️",
                "exhausted": "❌"
            }.get(model["status"], "❓")
            
            display_lines.append(
                f"{idx}. {status_emoji} {model['model_name']}\n"
                f"   Remaining: {model['quota_remaining']}/{model['quota_limit']} requests\n"
                f"   Used: {model['quota_percentage_used']:.1f}%\n"
                f"   Status: {model['status'].upper()}"
            )
        
        display_lines.extend([
            "",
            "RECOMMENDATIONS:",
            "-" * 70,
        ])
        display_lines.extend(quota_status["recommendations"])
        
        display_lines.extend([
            "",
            "QUOTA RESET: " + quota_status.get("reset_time", "midnight PT"),
            "=" * 70,
        ])
        
        return "\n".join(display_lines)

    async def select_model(self, selected_model_name: str, reason: str = "") -> Dict[str, Any]:
        """
        Record human selection of model to use for retry.
        
        Args:
            selected_model_name: The model name selected by human
            reason: Optional reason/notes for the selection (for audit trail)
            
        Returns:
        {
            "selected_model": "gemini-2.5-flash",
            "timestamp": "2025-12-19T15:30:50",
            "reason": "Primary model quota exhausted, using faster model",
            "status": "ready_for_retry"
        }
        """
        selection_record = {
            "selected_model": selected_model_name,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": reason,
            "status": "ready_for_retry"
        }
        
        self._selection_history.append(selection_record)
        logger.info(f"HITL Model Selection: {selected_model_name} - Reason: {reason}")
        
        return selection_record

    async def confirm_model_switch(self, 
                                   original_model: str, 
                                   new_model: str,
                                   is_quota_issue: bool = True) -> Dict[str, Any]:
        """
        Confirm model switch with full context for audit trail.
        
        Args:
            original_model: The model that had quota/error issue
            new_model: The model selected to use instead
            is_quota_issue: True if this is a quota (429) issue, False for other reasons
            
        Returns:
        {
            "status": "confirmed",
            "original_model": "gemini-3-pro",
            "new_model": "gemini-2.5-flash",
            "issue_type": "quota_429",
            "timestamp": "2025-12-19T15:30:50",
            "can_retry": true
        }
        """
        issue_type = "quota_429" if is_quota_issue else "manual_selection"
        
        confirmation = {
            "status": "confirmed",
            "original_model": original_model,
            "new_model": new_model,
            "issue_type": issue_type,
            "timestamp": datetime.utcnow().isoformat(),
            "can_retry": True
        }
        
        logger.info(
            f"Model switch confirmed: {original_model} → {new_model} "
            f"(Reason: {issue_type})"
        )
        
        self._selection_history.append(confirmation)
        
        return confirmation

    def get_selection_history(self) -> List[Dict[str, Any]]:
        """Get history of all model selections in this session"""
        return self._selection_history

    async def get_fallback_recommendation(self, 
                                        failed_model: str,
                                        failure_reason: str = "quota_exceeded") -> Dict[str, Any]:
        """
        Get AI-suggested fallback model based on current quota status.
        
        This provides a recommendation to the human, but human makes final decision.
        
        Args:
            failed_model: Model that failed
            failure_reason: Reason for failure (quota_exceeded, timeout, etc.)
            
        Returns:
        {
            "recommended_model": "gemini-2.5-flash",
            "reason_for_recommendation": "Fastest available model with sufficient quota",
            "quota_available": 880,
            "tier": "tier_2",
            "human_should_confirm": true
        }
        """
        try:
            quota_status = await self.get_available_models()
            
            # Find best available model (most quota remaining)
            available_models = [m for m in quota_status["models"] if m["status"] != "exhausted"]
            
            if not available_models:
                return {
                    "status": "error",
                    "message": "All models have exhausted quota. Reset at midnight PT.",
                    "human_should_confirm": True
                }
            
            recommended = available_models[0]  # Already sorted by quota remaining
            
            return {
                "recommended_model": recommended["model_name"],
                "reason_for_recommendation": "Most quota remaining among available models",
                "quota_available": recommended["quota_remaining"],
                "quota_percentage_used": recommended["quota_percentage_used"],
                "failed_model": failed_model,
                "failure_reason": failure_reason,
                "human_should_confirm": True,
                "alternatives": [
                    {"model": m["model_name"], "quota_remaining": m["quota_remaining"]}
                    for m in available_models[1:3]  # Top 2 alternatives
                ]
            }
            
        except Exception as e:
            logger.error(f"Failed to get fallback recommendation: {e}")
            raise Exception(f"Could not generate recommendation: {str(e)}")

    def get_status(self) -> Dict[str, Any]:
        """Get status of HITL tool"""
        return {
            "tool_name": "HITLModelSelectionTool",
            "purpose": "Human-In-The-Loop model selection for 429 errors and manual override",
            "capabilities": [
                "get_available_models() - Fetch current quota status",
                "select_model(model, reason) - Record human selection",
                "confirm_model_switch() - Audit trail for model switches",
                "get_fallback_recommendation() - AI suggestion (human decides)"
            ],
            "selection_history_count": len(self._selection_history),
            "accessible_to": "All agents in the chain",
            "status": "ready"
        }


# Singleton instance
_hitl_tool_instance = None

def get_hitl_tool() -> HITLModelSelectionTool:
    """Get or create the singleton HITL tool instance"""
    global _hitl_tool_instance
    if _hitl_tool_instance is None:
        _hitl_tool_instance = HITLModelSelectionTool()
    return _hitl_tool_instance


if __name__ == "__main__":
    # Example usage
    import asyncio
    
    async def demo():
        tool = get_hitl_tool()
        
        print("=" * 70)
        print("HITL Model Selection Tool - Demo")
        print("=" * 70)
        
        # Get available models
        try:
            quota_status = await tool.get_available_models()
            print(tool.format_for_display(quota_status))
            
            # Simulate human selection
            selection = await tool.select_model(
                "gemini-2.5-flash",
                reason="Primary model quota exhausted, selecting fastest fallback"
            )
            print(f"\nSelection recorded: {json.dumps(selection, indent=2)}")
            
            # Confirm model switch
            confirmation = await tool.confirm_model_switch(
                original_model="gemini-3-pro",
                new_model="gemini-2.5-flash",
                is_quota_issue=True
            )
            print(f"\nConfirmed: {json.dumps(confirmation, indent=2)}")
            
            # Get status
            status = tool.get_status()
            print(f"\nTool status: {json.dumps(status, indent=2)}")
            
        except Exception as e:
            print(f"Error: {e}")
    
    asyncio.run(demo())
