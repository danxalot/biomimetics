#!/usr/bin/env python3
"""
User Interaction Agent Configuration Generator
Generates llm_config.json dynamically from centralized model_config.py
"""

import json
import os
import sys

# Add shared module to path for model_config import
sys.path.insert(0, "/shared")
sys.path.insert(0, "/app/shared")  # Alternative path for containers
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
)  # Development path

try:
    from shared.model_config import chat_model, engineer_model

    MODEL_CONFIG_AVAILABLE = True
    print(
        "✅ User Interaction Agent: Successfully imported centralized model configuration"
    )
except ImportError as e:
    MODEL_CONFIG_AVAILABLE = False
    print(
        f"⚠️ User Interaction Agent: Could not import centralized model_config, using fallbacks: {e}"
    )

    # Fallback functions
    def chat_model():
        return "gemini-2.5-flash-lite"

    def engineer_model():
        return "gemini-2.5-flash"


def generate_config():
    """Generate configuration using centralized models"""
    config = {
        "llms": [
            {
                "name": "interaction-agent",
                "model": chat_model(),  # Dynamic from model_config
                "api_style": "google_ai_studio",
                "api_key_env_var": "GOOGLE_API_KEY",
                "is_primary": True,
                "rate_limit_rpm": 15,
                "description": f"Fast user interaction model: {chat_model()}",
            },
            {
                "name": "reasoning-agent",
                "model": engineer_model(),  # Dynamic from model_config
                "api_style": "google_ai_studio",
                "api_key_env_var": "GOOGLE_API_KEY",
                "is_primary": False,
                "rate_limit_rpm": 10,
                "description": f"Reasoning and analysis model: {engineer_model()}",
            },
        ],
        "mcp_server": {"url": "http://mcp_server:8086/mcp", "timeout": 30},
        "agent_service": {"url": "http://agent_service:8001", "timeout": 60},
        "_generated_from": "centralized model_config.py",
        "_model_config_available": MODEL_CONFIG_AVAILABLE,
    }
    return config


def main():
    """Generate and save configuration"""
    config = generate_config()

    # Write to llm_config.json
    config_path = os.path.join(os.path.dirname(__file__), "llm_config.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"✅ Generated llm_config.json with models:")
    print(f"   - Interaction Agent: {config['llms'][0]['model']}")
    print(f"   - Reasoning Agent: {config['llms'][1]['model']}")


if __name__ == "__main__":
    main()
