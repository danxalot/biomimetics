import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# ============================================================================
# BIOS 1.5.2 MODEL REGISTRY (EXACT STRING LITERALS)
# ============================================================================

# Zen (Free Tier) - Quarantined for Wiki/Docs
ZEN_REGISTRY = {
    "nemotron-3-super-free": "https://opencode.ai/zen/v1/",
    "minimax-m2.5-free": "https://opencode.ai/zen/v1/chat/completions",
}

# Go (Premium Tier) - For Serena Executions
GO_REGISTRY = {
    "opencode-go/glm-5.1": "https://opencode.ai/zen/go/v1/chat/completions",
    "opencode-go/mimo-v2-pro": "https://opencode.ai/zen/go/v1/chat/completions",
    "opencode-go/kimi-k2.5": "https://opencode.ai/zen/go/v1/chat/completions",
    "opencode-go/minimax-m2.7": "https://opencode.ai/zen/go/v1/messages",
}

def get_opencode_routing(capability_tag: str, preferred_model: str = None) -> dict:
    """
    Routes the LLM request based on strict BiOS 1.5.2 directives.
    Capability 'Deep_Reasoning' defaults to the Zen Free Tier heavyweight models.
    Go-tier access is reserved for Serena task execution.
    """
    logger.info(f"Routing model selection for capability: {capability_tag} (Preferred: {preferred_model})")
    
    # 1. Determine Model & Endpoint
    model_id = preferred_model
    endpoint = ""
    schema = "openai-compatible" # Default
    
    if capability_tag == "Deep_Reasoning" or capability_tag == "Wiki":
        # Force Zen Free Tier for documentation and reasoning
        if not model_id or model_id not in ZEN_REGISTRY:
            model_id = "nemotron-3-super-free" # Heavyweight fallback
        endpoint = ZEN_REGISTRY[model_id]
    else:
        # Default to free tier for general fast edits unless Go is specified
        if model_id and model_id in GO_REGISTRY:
            endpoint = GO_REGISTRY[model_id]
            if "minimax-m2.7" in model_id:
                schema = "@ai-sdk/anthropic"
        else:
            model_id = "minimax-m2.5-free"
            endpoint = ZEN_REGISTRY[model_id]
            schema = "@ai-sdk/anthropic" # Per Phase 1.5.2 directives for Minimax
            
    return {
        "model": model_id,
        "base_url": endpoint,
        "schema": schema,
        "mode": "ZEN_FAILFAST" if model_id in ZEN_REGISTRY else "GO_PREMIUM"
    }

def wrap_payload(model: str, messages: list, schema: str) -> dict:
    """
    Formats the payload wrapper logic for either OpenAI-compatible or Anthropic-style schemas.
    """
    if schema == "@ai-sdk/anthropic":
        return {
            "model": model,
            "messages": messages,
            "max_tokens": 4096,
            "system": "System instructions are provided in the message stream." # Placeholder for Anthropic-style system prompt if needed
        }
    else:
        return {
            "model": model,
            "messages": messages,
            "temperature": 0.3
        }
