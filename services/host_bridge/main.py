"""
ARCA Host Bridge (Pure Starlette Mode)
Runs natively on the Host Machine to provide secure filesystem access.
"""
import os
import sys
import logging
import subprocess
from typing import Optional
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("host-bridge")

# Project Root (Mounted Volume or Native)
PROJECT_ROOT = os.getenv("ARCA_PROJECT_ROOT", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def git_status_host(path: str = ".") -> str:
    """Run git status on Host."""
    try:
        full_path = os.path.abspath(os.path.join(PROJECT_ROOT, path))
        return subprocess.run(["git", "status", "-s"], cwd=full_path, capture_output=True, text=True).stdout
    except Exception as e:
        return f"Error: {e}"

def git_commit_host(path: str, message: str) -> str:
    """Run git commit on Host."""
    try:
        full_path = os.path.abspath(os.path.join(PROJECT_ROOT, path))
        result = subprocess.run(["git", "commit", "-m", message], cwd=full_path, capture_output=True, text=True)
        if result.returncode != 0:
            return f"Error (RC={result.returncode}): {result.stderr}\nStdout: {result.stdout}"
        return result.stdout
    except Exception as e:
        return f"Error: {e}"

def git_add_host(path: str, targets: list[str]) -> str:
    """Run git add on Host."""
    try:
        full_path = os.path.abspath(os.path.join(PROJECT_ROOT, path))
        cmd = ["git", "add"] + targets
        return subprocess.run(cmd, cwd=full_path, capture_output=True, text=True).stdout
    except Exception as e:
        return f"Error: {e}"

def read_file_host(path: str) -> str:
    """Read host file."""
    try:
        full_path = os.path.abspath(os.path.join(PROJECT_ROOT, path))
        if not full_path.startswith(PROJECT_ROOT): return "Error: Access denied"
        if not os.path.exists(full_path): return "Error: File not found"
        with open(full_path, 'r', encoding='utf-8') as f: return f.read()
    except Exception as e: return f"Error: {e}"

def write_file_host(path: str, content: str) -> str:
    """Write host file."""
    try:
        full_path = os.path.abspath(os.path.join(PROJECT_ROOT, path))
        if not full_path.startswith(PROJECT_ROOT): return "Error: Access denied"
        # Ensure directory exists
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return "Success"
    except Exception as e: return f"Error: {e}"

def git_push_host(path: str) -> str:
    """Run git push on Host."""
    try:
        full_path = os.path.abspath(os.path.join(PROJECT_ROOT, path))
        return subprocess.run(["git", "push"], cwd=full_path, capture_output=True, text=True).stdout
    except Exception as e:
        return f"Error: {e}"

async def api_git_command(request):
    data = await request.json()
    cmd = data.get("command")
    path = data.get("path", ".")
    
def git_rm_cached_host(path: str, targets: list[str]) -> str:
    """Run git rm --cached on Host."""
    try:
        full_path = os.path.abspath(os.path.join(PROJECT_ROOT, path))
        cmd = ["git", "rm", "--cached", "-r"] + targets
        return subprocess.run(cmd, cwd=full_path, capture_output=True, text=True).stdout
    except Exception as e:
        return f"Error: {e}"

async def api_git_command(request):
    data = await request.json()
    cmd = data.get("command")
    path = data.get("path", ".")
    
    if cmd == "status":
        return JSONResponse({"output": git_status_host(path)})
    elif cmd == "add":
        return JSONResponse({"output": git_add_host(path, data.get("targets", []))})
    elif cmd == "commit":
        return JSONResponse({"output": git_commit_host(path, data.get("message"))})
    elif cmd == "push":
        return JSONResponse({"output": git_push_host(path)})
    elif cmd == "rm_cached":
        return JSONResponse({"output": git_rm_cached_host(path, data.get("targets", []))})
        
    return JSONResponse({"error": "Unknown command"}, status_code=400)

async def api_read_file(request):
    path = request.query_params.get("path")
    if not path: return JSONResponse({"error": "Missing path parameter"}, status_code=400)
    content = read_file_host(path)
    if content.startswith("Error:"): return JSONResponse({"error": content}, status_code=500)
    return JSONResponse({"content": content})

async def api_write_file(request):
    data = await request.json()
    path = data.get("path")
    content = data.get("content")
    if not path or content is None: return JSONResponse({"error": "Missing path or content"}, status_code=400)
    
    result = write_file_host(path, content)
    if result.startswith("Error:"): return JSONResponse({"error": result}, status_code=500)
    return JSONResponse({"status": "success"})


def list_directory_host(path: str) -> dict:
    """List contents of a directory on host."""
    try:
        full_path = os.path.abspath(os.path.join(PROJECT_ROOT, path))
        if not full_path.startswith(PROJECT_ROOT):
            return {"error": "Access denied", "status": "failed"}
        if not os.path.exists(full_path):
            return {"error": f"Directory not found: {path}", "status": "failed"}
        if not os.path.isdir(full_path):
            return {"error": f"Not a directory: {path}", "status": "failed"}
        
        items = os.listdir(full_path)
        return {"files": items, "count": len(items), "path": path}
    except Exception as e:
        return {"error": str(e), "status": "failed"}


def exec_script_host(path: str) -> dict:
    """Execute a script on the host."""
    try:
        full_path = os.path.abspath(os.path.join(PROJECT_ROOT, path))
        if not full_path.startswith(PROJECT_ROOT):
            return {"error": "Access denied", "status": "failed"}
        if not os.path.exists(full_path):
            return {"error": f"Script not found: {path}", "status": "failed"}
        
        # Ensure executable
        subprocess.run(["chmod", "+x", full_path], check=False)
        
        # Run script
        # Using bash explicitly for .sh files
        cmd = ["bash", full_path] if full_path.endswith(".sh") else [full_path]
        
        result = subprocess.run(cmd, cwd=os.path.dirname(full_path), capture_output=True, text=True)
        
        status = "success" if result.returncode == 0 else "failed"
        return {
            "status": status, 
            "stdout": result.stdout, 
            "stderr": result.stderr, 
            "returncode": result.returncode
        }
    except Exception as e:
        return {"error": str(e), "status": "failed"}


async def api_exec_script(request):
    data = await request.json()
    path = data.get("path")
    if not path: return JSONResponse({"error": "Missing path parameter"}, status_code=400)
    
    result = exec_script_host(path)
    if result.get("status") == "failed":
        return JSONResponse(result, status_code=500)
    return JSONResponse(result)


async def api_list_directory(request):
    path = request.query_params.get("path", ".")
    result = list_directory_host(path)
    if "error" in result:
        return JSONResponse(result, status_code=500 if "Access denied" in result.get("error", "") else 404)
    return JSONResponse(result)


# Configure git safe directory
try:
    subprocess.run(["git", "config", "--global", "--add", "safe.directory", "*"], check=False)
except Exception as e:
    print(f"Warning: Failed to configure git safe.directory: {e}")

def main():
    print(f"Starting ARCA Host Bridge (Pure Starlette) in: {PROJECT_ROOT}")
    
    routes = [
        Route("/api/git", api_git_command, methods=["POST"]),
        Route("/api/read_file", api_read_file, methods=["GET"]),
        Route("/api/write_file", api_write_file, methods=["POST"]),
        Route("/api/list_directory", api_list_directory, methods=["GET"]),
        Route("/api/exec_script", api_exec_script, methods=["POST"]),
    ]
    
    app = Starlette(routes=routes)
    uvicorn.run(app, host="0.0.0.0", port=8092)

if __name__ == "__main__":
    main()
