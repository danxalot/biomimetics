
from mcp.server.fastmcp import FastMCP
import requests
import json
import logging

mcp = FastMCP("git-bypass")

@mcp.tool()
def git_bypass_commit(message: str, repo_path: str = ".") -> str:
    """
    Direct Git Commit Bypass.
    """
    HOST_BRIDGE_URL = "http://host_bridge:8092"
    try:
        import requests
        # Add All
        requests.post(f"{HOST_BRIDGE_URL}/api/git", json={"command": "add", "path": repo_path, "targets": ["."]}, timeout=10)
        # Commit
        r = requests.post(f"{HOST_BRIDGE_URL}/api/git", json={"command": "commit", "path": repo_path, "message": message}, timeout=10)
        return r.json().get("output", r.text)
    except Exception as e:
        return f"Error: {e}"
