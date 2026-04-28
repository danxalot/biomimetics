"""
Serena MCP Server: The Gateway to Phase 2 Multi-Model Routing.
Provides tools for telemetry-driven model selection and OpenCode execution.
"""

import os
import json
import httpx
from mcp.server.fastmcp import FastMCP

# Configuration
TELEMETRY_PATH = "/Users/danexall/biomimetics/logs/model_telemetry.json"
OPENCODE_API_URL = "https://api.opencode.ai/v1/execute" # Placeholder for OpenCode Go subscription
DOCS_DIR = "/Users/danexall/biomimetics/docs"

mcp = FastMCP("serena")

@mcp.tool()
def get_model_metrics():
    """
    Retrieves the latest performance metrics for all available models.
    Use this tool to inform the Agent PM's routing decisions based on success_rate, 
    latency, and known_quirks.
    """
    if not os.path.exists(TELEMETRY_PATH):
        return {"error": "Telemetry file not found."}
    
    with open(TELEMETRY_PATH, "r") as f:
        return json.load(f)

@mcp.tool()
async def execute_opencode_task(target_model: str, task_brief: str, technical_context: str = ""):
    """
    Executes a technical task via the OpenCode Go subscription.
    
    Args:
       target_model: The specific model to route to (e.g., 'kimi-k2.5', 'glm-4v').
       task_brief: The detailed instructions for the task.
       technical_context: Optional architecture or codebase context to aid execution.
    """
    # This tool will interact with the OpenCode API once the key is provisioned.
    # For now, it logs the routing decision for audit.
    
    print(f"DEBUG: Routing task to {target_model}")
    print(f"DEBUG: Brief: {task_brief[:100]}...")
    
    # Placeholder for actual API call
    opencode_api_key = os.getenv("OPENCODE_API_KEY")
    if not opencode_api_key:
        return {
            "status": "dry_run",
            "message": f"Task routed to {target_model}, but OPENCODE_API_KEY is missing. Dry-run complete.",
            "target": target_model
        }

    # Potential implementation:
    # async with httpx.AsyncClient() as client:
    #     response = await client.post(
    #         OPENCODE_API_URL,
    #         json={"model": target_model, "prompt": task_brief, "context": technical_context},
    #         headers={"Authorization": f"Bearer {opencode_api_key}"}
    #     )
    #     return response.json()

    return {"status": "error", "message": "API Integration Pending."}

@mcp.tool()
def read_file(path: str) -> str:
    """
    Reads the content of a file from the local filesystem.
    
    Args:
        path: Absolute path to the file.
    """
    if not os.path.exists(path):
        return f"Error: File not found at {path}"
    with open(path, "r") as f:
        return f.read()

@mcp.tool()
def write_file(path: str, content: str) -> str:
    """
    Writes content to a file on the local filesystem. Creates directories if needed.
    
    Args:
        path: Absolute path to the destination file.
        content: The text content to write.
    """
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Success: File written to {path}"
    except Exception as e:
        return f"Error: Failed to write file: {str(e)}"

@mcp.tool()
def move_file(src: str, dest: str) -> str:
    """
    Moves or renames a file on the local filesystem.
    
    Args:
        src: Absolute path to the source file.
        dest: Absolute path to the destination.
    """
    try:
        if not os.path.exists(src):
            return f"Error: Source file not found: {src}"
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        os.rename(src, dest)
        return f"Success: Moved {src} to {dest}"
    except Exception as e:
        return f"Error: Failed to move file: {str(e)}"

@mcp.tool()
def list_files(directory: str) -> list:
    """
    Lists the contents of a directory.
    
    Args:
        directory: Absolute path to the directory.
    """
    try:
        if not os.path.exists(directory):
            return [f"Error: Directory not found: {directory}"]
        return os.listdir(directory)
    except Exception as e:
        return [f"Error: Failed to list directory: {str(e)}"]

if __name__ == "__main__":
    mcp.run()
