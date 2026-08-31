import os
import logging
import subprocess
import json
import requests
import hmac
import hashlib
from typing import Dict, Any, List, Optional

# Initialize FastMCP
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("mcp-docker-ops")
logger = logging.getLogger(__name__)

# Configuration
MAINTAINER_AGENTS_URL = os.getenv("MAINTAINER_AGENTS_URL", "http://maintainer_agents:8090")
GENESIS_CHAIN_API_KEY = os.getenv("GENESIS_CHAIN_API_KEY")

# =============================================================================
# 1. THE PRIMITIVES (The Mechanical Hands)
# Only authorized agents (Genesis Chain) should call these.
# =============================================================================

@mcp.tool()
def docker_execution_primitive(operation: str, cmd: List[str] = None, target: str = None) -> str:
    """
    Primitive Docker Execution Tool.
    Performs the actual subprocess calls.
    NO REASONING. pure execution.
    """
    if operation == "exec_raw":
        if not cmd: return "Error: cmd required for exec_raw"
        try:
            # Security: Basic sanity check
            if "rm -rf" in " ".join(cmd): return "Safety Blocked: rm -rf detected"
            
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                return res.stdout.strip()
            return f"Error ({res.returncode}): {res.stderr.strip()}"
        except Exception as e:
            return f"Execution Failed: {e}"
            
    elif operation == "build":
        if not target: return "Error: target required for build"
        # Hardcoded build logic matching SOP
        tag = f"ghcr.io/danxalot/arca-{target}:latest"
        build_cmd = ["docker", "build", "-t", tag, "-f", f"services/{target}/Dockerfile", "."]
        
        try:
            res = subprocess.run(build_cmd, capture_output=True, text=True)
            return res.stdout + res.stderr
        except Exception as e:
            return f"Build Failed: {e}"

    elif operation == "buildx_multiarch":
        # Multi-Architecture Build Support
        if not cmd: return "Error: cmd parameters required for buildx (platforms, context, tags)"
        
        # We expect 'cmd' to key params passed via JSON string or we parse 'target' if simpler
        # For safety/simplicity in primitive, we'll verify the structure carefully.
        # However, primitive signature takes list[str], so we need to be careful.
        # Let's assume the AGENT constructs the full command list.
        
        # Verify it's a buildx command
        if cmd[0] != "docker" or cmd[1] != "buildx":
            return "Error: Command must start with 'docker buildx'"
            
        try:
            # Execute with full output capture
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                return f"Multi-Arch Build Success:\n{res.stdout}"
            return f"Multi-Arch Build Failed ({res.returncode}):\n{res.stderr}\n{res.stdout}"
        except Exception as e:
            return f"Buildx Execution Failed: {e}"

    return f"Unknown primitive operation: {operation}"

@mcp.tool()
def list_containers(all: bool = False) -> str:
    cmd = ["docker", "ps"]
    if all: cmd.append("-a")
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.stdout

@mcp.tool()
def get_container_logs(container_name: str, tail: int = 100) -> str:
    res = subprocess.run(["docker", "logs", "--tail", str(tail), container_name], capture_output=True, text=True)
    return res.stdout + res.stderr

@mcp.tool()
def restart_container(container_name: str) -> str:
    if container_name in ["redis", "host_bridge", "neo4j", "postgres"]: 
         return "Safety Prevented: Cannot restart infra core via simple tool."
    subprocess.run(["docker", "restart", container_name], capture_output=True, text=True)
    return f"Restarted {container_name}"


# =============================================================================
# 2. THE DISPATCHER (The Router)
# Routes high-level intent to the Maintainer Agents Service (The Brain).
# =============================================================================

@mcp.tool()
def docker_maintainer_operation(operation: str, target: str = None, details: str = None, headers: Optional[Dict[str, str]] = None) -> str:
    """
    Dispatch a Docker task to the Maintainer Agents Service.
    This routes the request to the 'docker' agent for reasoning and SOP compliance.
    """
    if not GENESIS_CHAIN_API_KEY:
        return "Error: GENESIS_CHAIN_API_KEY not configured. Cannot dispatch."

    payload = {
        "agent_type": "docker",
        "operation": operation,
        "params": {
            "target": target,
            "details": details
        },
        "intent_hv": None
    }
    
    # 1. Sign Request
    body_str = json.dumps(payload, sort_keys=True)
    signature = hmac.new(
        GENESIS_CHAIN_API_KEY.encode("utf-8"),
        body_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    final_headers = {
        "X-Genesis-Chain": "true",
        "X-Genesis-Agent": "mcp_server",
        "X-Genesis-Signature": signature,
        "Content-Type": "application/json"
    }
    
    if headers:
        # Propagation: Incoming Genesis headers take precedence for audit trail
        final_headers.update({k: v for k, v in headers.items() if k.lower().startswith("x-genesis-") and k.lower() != "x-genesis-signature"})
    
    # 2. Dispatch
    try:
        url = f"{MAINTAINER_AGENTS_URL}/execute"
        logger.info(f"Dispatching to {url} with sig {signature[:8]}...")
        
        resp = requests.post(url, data=body_str, headers=final_headers, timeout=60)
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                return f"Agent Execution Successful:\n{json.dumps(data.get('result'), indent=2)}"
            else:
                return f"Agent Reported Failure: {data.get('error')}"
        else:
            return f"Dispatch Error ({resp.status_code}): {resp.text}"
            
    except Exception as e:
        logger.error(f"Dispatch Exception: {e}")
        return f"Dispatch Failed: {str(e)}"
