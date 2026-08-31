from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import Optional, List
import subprocess, json, logging, os

app = FastAPI()

# Default ARCA repo path on host
ARCA_REPO_PATH = os.environ.get("ARCA_REPO_PATH", "/home/ubuntu/ARCA")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "features": ["docker", "git"]}


# --- Git Operations ---

class GitRequest(BaseModel):
    operation: str
    repo_path: Optional[str] = None
    files: Optional[List[str]] = None
    message: Optional[str] = None
    branch: Optional[str] = None
    remote: Optional[str] = "origin"
    force: Optional[bool] = False


@app.post("/git")
async def git_operation(req: GitRequest):
    """Execute git operations on the host filesystem"""
    repo_path = req.repo_path or ARCA_REPO_PATH
    
    if not os.path.exists(repo_path):
        raise HTTPException(status_code=404, detail=f"Repository not found: {repo_path}")
    
    try:
        original_cwd = os.getcwd()
        os.chdir(repo_path)
        
        result = {"operation": req.operation, "success": True}
        
        if req.operation == "status":
            proc = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
            result["output"] = proc.stdout.strip()
            result["exit_code"] = proc.returncode
            
        elif req.operation == "add":
            files = req.files or ["."]
            proc = subprocess.run(["git", "add"] + files, capture_output=True, text=True)
            result["output"] = proc.stdout.strip() or "Files staged"
            result["exit_code"] = proc.returncode
            if proc.returncode != 0:
                result["error"] = proc.stderr.strip()
                result["success"] = False
                
        elif req.operation == "commit":
            message = req.message or "Auto-commit via ARCA"
            proc = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True)
            result["output"] = proc.stdout.strip()
            result["exit_code"] = proc.returncode
            if proc.returncode != 0:
                result["error"] = proc.stderr.strip()
                result["success"] = False
                
        elif req.operation == "push":
            remote = req.remote or "origin"
            branch = req.branch or "main"
            cmd = ["git", "push", remote, branch]
            if req.force:
                cmd.append("--force")
            proc = subprocess.run(cmd, capture_output=True, text=True)
            result["output"] = proc.stdout.strip() or proc.stderr.strip()
            result["exit_code"] = proc.returncode
            if proc.returncode != 0 and "error" in proc.stderr.lower():
                result["error"] = proc.stderr.strip()
                result["success"] = False
                
        elif req.operation == "pull":
            remote = req.remote or "origin"
            branch = req.branch or "main"
            proc = subprocess.run(["git", "pull", remote, branch], capture_output=True, text=True)
            result["output"] = proc.stdout.strip()
            result["exit_code"] = proc.returncode
            if proc.returncode != 0:
                result["error"] = proc.stderr.strip()
                result["success"] = False
                
        elif req.operation == "log":
            proc = subprocess.run(["git", "log", "--oneline", "-10"], capture_output=True, text=True)
            result["output"] = proc.stdout.strip()
            result["exit_code"] = proc.returncode
            
        elif req.operation == "diff":
            cmd = ["git", "diff"]
            if req.files:
                cmd.extend(req.files)
            proc = subprocess.run(cmd, capture_output=True, text=True)
            result["output"] = proc.stdout.strip()
            result["exit_code"] = proc.returncode
            
        elif req.operation == "branch":
            if req.branch:
                proc = subprocess.run(["git", "branch", req.branch], capture_output=True, text=True)
            else:
                proc = subprocess.run(["git", "branch", "-a"], capture_output=True, text=True)
            result["output"] = proc.stdout.strip()
            result["exit_code"] = proc.returncode
            
        elif req.operation == "checkout":
            branch = req.branch or "main"
            proc = subprocess.run(["git", "checkout", branch], capture_output=True, text=True)
            result["output"] = proc.stdout.strip() or proc.stderr.strip()
            result["exit_code"] = proc.returncode
            if proc.returncode != 0:
                result["error"] = proc.stderr.strip()
                result["success"] = False
                
        else:
            result["success"] = False
            result["error"] = f"Unknown git operation: {req.operation}"
            
        os.chdir(original_cwd)
        return result
        
    except Exception as e:
        logging.error(f"Git operation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- File Operations ---

class FileRequest(BaseModel):
    operation: str
    path: str
    content: Optional[str] = None
    mode: Optional[str] = None  # For chmod operations


@app.post("/file")
async def file_operation(req: FileRequest):
    """Execute file operations on the host filesystem"""
    
    # Security: Restrict to ARCA project directory
    arca_root = os.environ.get("ARCA_ROOT", "/Users/danexall/Documents/VS Code Projects/ARCA")
    
    # Handle both absolute and relative paths
    if os.path.isabs(req.path):
        full_path = os.path.abspath(req.path)
    else:
        full_path = os.path.abspath(os.path.join(arca_root, req.path))
    
    # Prevent path traversal attacks
    if not full_path.startswith(arca_root):
        raise HTTPException(status_code=403, detail=f"Access denied: Path outside ARCA root ({arca_root})")
    
    try:
        result = {"operation": req.operation, "path": req.path, "full_path": full_path, "success": True}
        
        if req.operation == "read":
            if not os.path.exists(full_path):
                raise HTTPException(status_code=404, detail=f"File not found: {req.path}")
            with open(full_path, 'r', encoding='utf-8') as f:
                result["content"] = f.read()
                
        elif req.operation == "write":
            # Create parent directories if needed
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(req.content or "")
            result["message"] = f"File written: {req.path}"
            
        elif req.operation == "append":
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'a', encoding='utf-8') as f:
                f.write(req.content or "")
            result["message"] = f"Content appended: {req.path}"
            
        elif req.operation == "delete":
            if os.path.exists(full_path):
                os.remove(full_path)
                result["message"] = f"File deleted: {req.path}"
            else:
                result["message"] = f"File not found (no action): {req.path}"
                
        elif req.operation == "exists":
            result["exists"] = os.path.exists(full_path)
            result["is_file"] = os.path.isfile(full_path) if os.path.exists(full_path) else False
            result["is_dir"] = os.path.isdir(full_path) if os.path.exists(full_path) else False
            
        elif req.operation == "list":
            if not os.path.exists(full_path):
                raise HTTPException(status_code=404, detail=f"Directory not found: {req.path}")
            if not os.path.isdir(full_path):
                raise HTTPException(status_code=400, detail=f"Not a directory: {req.path}")
            items = os.listdir(full_path)
            result["items"] = items
            result["count"] = len(items)
            
        elif req.operation == "chmod":
            if not req.mode:
                raise HTTPException(status_code=400, detail="mode required for chmod")
            os.chmod(full_path, int(req.mode, 8))  # Convert octal string to int
            result["message"] = f"Permissions changed: {req.path} -> {req.mode}"
            
        else:
            result["success"] = False
            result["error"] = f"Unknown file operation: {req.operation}"
            
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"File operation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Simple GET endpoints for MCP compatibility ---

@app.get("/api/list_directory")
async def api_list_directory(path: str = "."):
    """List contents of a directory. GET endpoint for MCP tools."""
    arca_root = os.environ.get("ARCA_ROOT", "/Users/danexall/Documents/VS Code Projects/ARCA")
    
    # Handle both absolute and relative paths
    if os.path.isabs(path):
        full_path = os.path.abspath(path)
    else:
        full_path = os.path.abspath(os.path.join(arca_root, path))
    
    # Security check
    if not full_path.startswith(arca_root):
        return {"error": f"Access denied: Path outside ARCA root", "status": "failed"}
    
    if not os.path.exists(full_path):
        return {"error": f"Directory not found: {path}", "status": "failed"}
    
    if not os.path.isdir(full_path):
        return {"error": f"Not a directory: {path}", "status": "failed"}
    
    try:
        items = os.listdir(full_path)
        return {"files": items, "count": len(items), "path": path, "full_path": full_path}
    except Exception as e:
        return {"error": str(e), "status": "failed"}


@app.get("/api/read_file")
async def api_read_file(path: str):
    """Read a file. GET endpoint for MCP tools."""
    arca_root = os.environ.get("ARCA_ROOT", "/Users/danexall/Documents/VS Code Projects/ARCA")
    
    if os.path.isabs(path):
        full_path = os.path.abspath(path)
    else:
        full_path = os.path.abspath(os.path.join(arca_root, path))
    
    if not full_path.startswith(arca_root):
        return {"error": f"Access denied: Path outside ARCA root"}
    
    if not os.path.exists(full_path):
        return {"error": f"File not found: {path}"}
    
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            return {"content": f.read(), "path": path, "full_path": full_path}
    except Exception as e:
        return {"error": str(e)}


class ExecRequest(BaseModel):
    command: str
    cwd: Optional[str] = None
    timeout: Optional[int] = 60


@app.post("/exec")
async def execute_command(req: ExecRequest):
    """Execute a command on the host filesystem (for scripts, etc.)"""
    
    # Security: Restrict to ARCA directory
    arca_root = os.environ.get("ARCA_ROOT", "/Users/danexall/Documents/VS Code Projects/ARCA")
    cwd = req.cwd or arca_root
    
    if not os.path.abspath(cwd).startswith(arca_root):
        raise HTTPException(status_code=403, detail="Access denied: Working directory outside ARCA root")
    
    try:
        proc = subprocess.run(
            req.command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=req.timeout
        )
        
        return {
            "command": req.command,
            "cwd": cwd,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
            "success": proc.returncode == 0
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail=f"Command timeout after {req.timeout}s")
    except Exception as e:
        logging.error(f"Command execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- Docker Operations ---


def _curl_docker(path: str, params: str = '', binary: bool = False):
    url = f"http://localhost{path}{('?'+params) if params else ''}"
    try:
        result = subprocess.check_output([
            'curl', '--silent', '--show-error', '--unix-socket', '/var/run/docker.sock', url
        ], timeout=5)
        if binary:
            # Return raw bytes decoded with error handling for logs
            return result.decode('utf-8', errors='replace')
        return result.decode('utf-8')
    except subprocess.CalledProcessError as e:
        logging.error(f"curl to docker failed: {e}")
        raise


@app.get('/containers')
async def list_containers(all: bool = True):
    try:
        out = _curl_docker('/containers/json', f'all={str(all).lower()}')
        return json.loads(out)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/containers/{cid}/stats')
async def container_stats(cid: str):
    try:
        out = _curl_docker(f'/containers/{cid}/stats', 'stream=false')
        return json.loads(out)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/containers/{cid}/logs')
async def container_logs(cid: str, tail: int = 200):
    try:
        # Use binary mode for logs since they may contain non-UTF8 bytes
        out = _curl_docker(f'/containers/{cid}/logs', f'stdout=1&stderr=1&tail={tail}', binary=True)
        # Clean up common Docker log prefixes (8-byte header per line)
        import re
        # Remove Docker log stream header bytes (first 8 bytes of each chunk)
        cleaned = re.sub(r'[\x00-\x08]', '', out)
        return PlainTextResponse(content=cleaned)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/containers/{cid}/restart')
async def restart_container(cid: str):
    """Restart a container by name or ID"""
    try:
        proc = subprocess.run(
            ['curl', '--silent', '-X', 'POST', '--unix-socket', '/var/run/docker.sock',
             f'http://localhost/containers/{cid}/restart'],
            capture_output=True, text=True, timeout=30
        )
        if proc.returncode == 0:
            return {"status": "restarted", "container": cid}
        else:
            raise HTTPException(status_code=500, detail=proc.stderr)
    except subprocess.TimeoutExpired:
        return {"status": "restart_initiated", "container": cid, "note": "Restart may still be in progress"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class DockerRequest(BaseModel):
    operation: str
    container: Optional[str] = None
    image: Optional[str] = None
    command: Optional[str] = None
    tail: Optional[int] = 100


@app.post('/docker')
async def docker_operation(req: DockerRequest):
    """Execute docker operations via docker socket"""
    try:
        result = {"operation": req.operation, "success": True}
        
        if req.operation == "ps":
            out = _curl_docker('/containers/json', 'all=true')
            containers = json.loads(out)
            result["containers"] = [
                {
                    "id": c["Id"][:12],
                    "name": c["Names"][0].lstrip("/") if c["Names"] else "unknown",
                    "image": c["Image"],
                    "status": c["Status"],
                    "state": c["State"]
                }
                for c in containers
            ]
            
        elif req.operation == "logs":
            if not req.container:
                raise HTTPException(status_code=400, detail="container required for logs")
            out = _curl_docker(f'/containers/{req.container}/logs', 
                             f'stdout=1&stderr=1&tail={req.tail or 100}', binary=True)
            import re
            cleaned = re.sub(r'[\x00-\x08]', '', out)
            result["logs"] = cleaned
            
        elif req.operation == "restart":
            if not req.container:
                raise HTTPException(status_code=400, detail="container required for restart")
            proc = subprocess.run(
                ['curl', '--silent', '-X', 'POST', '--unix-socket', '/var/run/docker.sock',
                 f'http://localhost/containers/{req.container}/restart'],
                capture_output=True, text=True, timeout=30
            )
            result["output"] = "Container restart initiated"
            
        elif req.operation == "stop":
            if not req.container:
                raise HTTPException(status_code=400, detail="container required for stop")
            proc = subprocess.run(
                ['curl', '--silent', '-X', 'POST', '--unix-socket', '/var/run/docker.sock',
                 f'http://localhost/containers/{req.container}/stop'],
                capture_output=True, text=True, timeout=30
            )
            result["output"] = "Container stopped"
            
        elif req.operation == "start":
            if not req.container:
                raise HTTPException(status_code=400, detail="container required for start")
            proc = subprocess.run(
                ['curl', '--silent', '-X', 'POST', '--unix-socket', '/var/run/docker.sock',
                 f'http://localhost/containers/{req.container}/start'],
                capture_output=True, text=True, timeout=30
            )
            result["output"] = "Container started"
            
        else:
            result["success"] = False
            result["error"] = f"Unknown docker operation: {req.operation}"
            
        return result
        
    except Exception as e:
        logging.error(f"Docker operation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == '__main__':
    import os
    import uvicorn
    port = int(os.getenv("PORT", "9091"))
    uvicorn.run(app, host='0.0.0.0', port=port)
