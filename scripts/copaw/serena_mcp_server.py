"""
Serena MCP Server: The Gateway to Phase 2 Multi-Model Routing.
Provides tools for telemetry-driven model selection and OpenCode execution.
"""

import os
import json
import asyncio
import httpx
from mcp.server.fastmcp import FastMCP

# Configuration
TELEMETRY_PATH = "/Users/danexall/biomimetics/logs/model_telemetry.json"
OPENCODE_ZEN_URL = "https://opencode.ai/zen/v1"
OPENCODE_GO_URL = "https://opencode.ai/zen/go/v1"
OPENCODE_TOKEN_PATH = "/Users/danexall/biomimetics/secrets/opencode_api"
DOCS_DIR = "/Users/danexall/biomimetics/docs"

mcp = FastMCP("serena")

def get_opencode_key():
    if os.path.exists(OPENCODE_TOKEN_PATH):
        with open(OPENCODE_TOKEN_PATH, "r") as f:
            return f.read().strip()
    return os.getenv("OPENCODE_API_KEY")

@mcp.tool()
async def execute_opencode_task(target_model: str, task_brief: str, technical_context: str = ""):
    """
    Executes a technical task via the OpenCode Go subscription.
    """
    api_key = get_opencode_key()
    if not api_key:
        return {"status": "error", "message": "Missing OPENCODE_API_KEY"}

    # Map roles if needed, or use target_model directly
    # For autonomous loops, we default to the GO URL
    from openai import OpenAI
    client = OpenAI(base_url=OPENCODE_GO_URL, api_key=api_key)
    
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=target_model,
            messages=[
                {"role": "system", "content": f"You are the BiOS Serena Agent. Technical Context: {technical_context}"},
                {"role": "user", "content": task_brief},
            ],
            temperature=0.2,
        )
        return {
            "status": "success",
            "model": target_model,
            "response": response.choices[0].message.content
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

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
