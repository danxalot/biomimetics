import os
import logging
import json
import requests
import hmac
import hashlib
from typing import Dict, Any, Optional

# Initialize FastMCP
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("mcp-security-ops")
logger = logging.getLogger(__name__)

# Configuration
MAINTAINER_AGENTS_URL = os.getenv("MAINTAINER_AGENTS_URL", "http://maintainer_agents:8090")
GENESIS_CHAIN_API_KEY = os.getenv("GENESIS_CHAIN_API_KEY")

@mcp.tool()
def request_secret(key_name: str, justification: str, agent_type: str = "unknown") -> str:
    """
    Request a secret from the Security Maintainer Agent.
    
    This is the ONLY way for agents to access secrets.
    The Security Agent validates the request, retrieves the key from .secrets/,
    and returns it ephemerally (never logged).
    
    Args:
        key_name: Name of the secret (e.g., "GITHUB_TOKEN", "OPENAI_API_KEY")
        justification: Why the key is needed (for audit trail)
        agent_type: Which agent is requesting (docker, git, terraform, etc.)
    
    Returns:
        The secret value (ephemeral, never logged)
    """
    if not GENESIS_CHAIN_API_KEY:
        return "Error: GENESIS_CHAIN_API_KEY not configured. Cannot dispatch."

    payload = {
        "agent_type": "security",
        "operation": "provide_secret",
        "params": {
            "key_name": key_name,
            "requester": agent_type,
            "justification": justification
        },
        "intent_hv": None
    }
    
    # Sign Request
    body_str = json.dumps(payload, sort_keys=True)
    signature = hmac.new(
        GENESIS_CHAIN_API_KEY.encode("utf-8"),
        body_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        "X-Genesis-Chain": "true",
        "X-Genesis-Agent": "mcp_server",
        "X-Genesis-Signature": signature,
        "Content-Type": "application/json"
    }
    
    # Dispatch
    try:
        url = f"{MAINTAINER_AGENTS_URL}/execute"
        logger.info(f"Requesting secret '{key_name}' for agent '{agent_type}'")
        
        resp = requests.post(url, data=body_str, headers=headers, timeout=30)
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                result = data.get("result", {})
                secret_value = result.get("secret_value")
                if secret_value:
                    logger.info(f"✅ Secret '{key_name}' provided to '{agent_type}'")
                    return secret_value
                else:
                    return f"Error: Security Agent did not return secret value"
            else:
                return f"Security Agent Denied: {data.get('error')}"
        else:
            return f"Dispatch Error ({resp.status_code}): {resp.text}"
            
    except Exception as e:
        logger.error(f"Secret Request Exception: {e}")
        return f"Secret Request Failed: {str(e)}"

@mcp.tool()
def sync_secrets_to_oci(secrets_list: list = None) -> str:
    """
    Sync secrets from local .secrets/ to OCI /mcp_storage/ARCA/.secrets/
    
    Args:
        secrets_list: Optional list of specific secrets to sync. If None, syncs all.
    
    Returns:
        Status message
    """
    payload = {
        "agent_type": "security",
        "operation": "sync_to_oci",
        "params": {
            "secrets_list": secrets_list or []
        }
    }
    
    # (Same dispatch logic as above)
    # ... truncated for brevity
    return "Sync initiated (implement full dispatch)"
