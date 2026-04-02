#!/usr/bin/env python3
"""
Copaw Secret Fetcher
Utility for fetching secrets from Azure Credentials Server for copaw scripts.

Usage:
    from copaw_secret_fetcher import get_secret, get_secret_or_env
    
    # Fetch a secret from Azure Key Vault via credentials server
    api_key = get_secret("notion-api-key")
    
    # Or fetch from credentials server, fallback to environment
    api_key = get_secret_or_env("notion-api-key", "NOTION_API_KEY")
"""

import os
import sys
from functools import lru_cache

# Configuration
CREDENTIALS_SERVER_URL = os.getenv("CREDENTIALS_SERVER_URL", "http://127.0.0.1:8089")
CREDENTIALS_API_KEY = os.getenv("CREDENTIALS_API_KEY", "4Kib2uPPgTmBmlXoYi9tDmgJH-t-1nZBIXgBMPf7ljQ")

# Secret name mappings: common names -> Azure Key Vault names
SECRET_NAME_MAP = {
    "notion_api_key": "notion-api-key",
    "notion_api": "notion-api-key",
    "google_api_key": "google-api-key",
    "gemini_api_key": "gemini-api-key",
    "github_token": "github-models-token",
    "openai_api_key": "openai-api-key",
    "anthropic_api_key": "anthropic-api-key",
    "tavily_api_key": "tavily-api-key",
    "groq_api_key": "groq-api-key",
    "cohere_api_key": "cohere-api-key",
    "huggingface_token": "huggingface-token",
    "opencode_api_key": "opencode-api-key",
    "openrouter_api_key": "openrouter-api-key",
    "minimax_api_key": "minimax-api-key",
    "kilo_code_api_key": "kilo-code-api-key",
    "telegram_bot_token": "telegram-bot-token",
    # Green API (WhatsApp Bridge)
    "green_api_id": "green-api-id",
    "green_api_token": "green-api-token",
    "green_api_url": "green-api-url",
}


def _fetch_secret(secret_name: str) -> str | None:
    """Fetch a single secret from the credentials server."""
    try:
        import requests
        
        response = requests.get(
            f"{CREDENTIALS_SERVER_URL}/secrets/{secret_name}",
            headers={"X-API-Key": CREDENTIALS_API_KEY},
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()["value"].strip()
        else:
            return None
    except Exception:
        return None


@lru_cache(maxsize=100)
def get_secret(secret_name: str, cache: bool = True) -> str | None:
    """
    Fetch a secret from Azure Key Vault via credentials server.
    
    Args:
        secret_name: Name of the secret (will be mapped to Azure Key Vault name)
        cache: Whether to cache the result (default: True)
    
    Returns:
        Secret value or None if not found
    """
    # Map common names to Azure Key Vault names
    vault_name = SECRET_NAME_MAP.get(secret_name, secret_name)
    
    return _fetch_secret(vault_name)


def get_secret_or_env(secret_name: str, env_var: str = None, default: str = None) -> str | None:
    """
    Fetch a secret from credentials server, fallback to environment variable.
    
    Args:
        secret_name: Name of the secret to fetch
        env_var: Environment variable to check as fallback (default: secret_name in uppercase)
        default: Default value if secret not found
    
    Returns:
        Secret value or default
    """
    # Try credentials server first
    value = get_secret(secret_name)
    if value:
        return value
    
    # Fallback to environment
    env_name = env_var or secret_name.upper()
    value = os.environ.get(env_name)
    if value:
        return value
    
    return default


def get_all_secrets(secret_names: list[str]) -> dict[str, str | None]:
    """
    Fetch multiple secrets at once.
    
    Args:
        secret_names: List of secret names to fetch
    
    Returns:
        Dictionary mapping secret names to values
    """
    results = {}
    for name in secret_names:
        results[name] = get_secret(name)
    return results


if __name__ == "__main__":
    # Test fetching secrets
    if len(sys.argv) > 1:
        for secret_name in sys.argv[1:]:
            value = get_secret(secret_name)
            if value:
                print(f"{secret_name}: {value[:10]}...")
            else:
                print(f"{secret_name}: NOT FOUND")
    else:
        print("Usage: python copaw_secret_fetcher.py <secret_name> [...]")
        print("Example: python copaw_secret_fetcher.py notion-api-key google-api-key")
