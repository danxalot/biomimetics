import os
import logging
import shutil
import json
import time
import requests
import redis
from datetime import datetime
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP
mcp = FastMCP("mcp-file-ops")
logger = logging.getLogger(__name__)

# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
POLICY_MANAGER_URL = os.getenv("POLICY_MANAGER_URL", "http://policy_manager:8003")
LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://llm_gateway:8080/v1/chat/completions")
HOST_BRIDGE_URL = os.getenv("HOST_BRIDGE_URL", "http://host_bridge:8092")
SOP_PATH = "/app/skills/FILE_OPS_SOP.md"
REASONING_BANK_PATH = os.getenv("REASONING_BANK_PATH", "/app/shared_storage/reasoning_bank")

# Initialize Redis
try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
except Exception as e:
    logger.error(f"Failed to connect to Redis: {e}")
    redis_client = None

class FileMaintainerAgent:
    """
    Autonomous File / Dev Ops Agent following "Read-Reason-Write" Protocol.
    """
    def __init__(self, headers: Optional[Dict] = None):
        self.sop_content = self._load_sop()
        self.headers = headers

    def _load_sop(self) -> str:
        try:
            if os.path.exists(SOP_PATH):
                with open(SOP_PATH, 'r') as f:
                    return f.read()
            return "Error: FILE_OPS_SOP.md not found."
        except Exception as e:
            return f"Error loading SOP: {e}"

    def _query_deepseek(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Query DeepSeek model for reasoning."""
        payload = {
            "model": "deepseek-r1",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"}
        }
        # Prepare headers for LLM Gateway
        final_headers = {"Content-Type": "application/json"}
        if self.headers:
            genesis = {k: v for k, v in self.headers.items() if k.lower().startswith("x-genesis-")}
            final_headers.update(genesis)
            
        try:
            resp = requests.post(LLM_GATEWAY_URL, json=payload, headers=final_headers, timeout=60)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"]
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].strip()
                return json.loads(content)
            return {"error": f"LLM Call Failed: {resp.text}"}
        except Exception as e:
            return {"error": str(e)}

    def _call_host_bridge(self, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Router to Host Bridge for Filesystem Access."""
        path = kwargs.get("path", "")
        
        # --- BYPASS: LOCAL SHARED STORAGE ---
        # If operation is on /app/shared_storage, perform it locally inside container
        if path and path.startswith("/app/shared_storage"):
            logger.info(f"FileOps: Intercepting local path {path}")
            try:
                if endpoint == "read_file":
                    if os.path.exists(path):
                        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                            return {"content": f.read()}
                    return {"error": f"File not found: {path}"}
                
                elif endpoint == "write_file":
                    content = kwargs.get("content", "")
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    return {"message": f"Successfully wrote to {path}"}
                
                elif endpoint == "list_directory":
                    if os.path.exists(path) and os.path.isdir(path):
                        files = os.listdir(path)
                        return {"files": files}
                    return {"error": f"Directory not found: {path}"}
            except Exception as e:
                return {"error": f"Local FS Error: {e}"}
        # ------------------------------------

        if not HOST_BRIDGE_URL:
             return {"error": "HOST_BRIDGE_URL not set."}
             
        headers = {
            "X-Genesis-Chain": "true",
            "X-Genesis-Agent": "mcp_server",
            "X-Genesis-Source": "internal_tool_delegation"
        }
        if self.headers:
            genesis = {k: v for k, v in self.headers.items() if k.lower().startswith("x-genesis-")}
            headers.update(genesis)

        try:
            if endpoint == "read_file":
                resp = requests.get(f"{HOST_BRIDGE_URL}/api/{endpoint}", params=kwargs, headers=headers, timeout=10)
            elif endpoint == "list_directory":
                 # API might be GET or POST depending on implementation, attempting compatible
                 resp = requests.get(f"{HOST_BRIDGE_URL}/api/{endpoint}", params=kwargs, headers=headers, timeout=10)
            else:
                resp = requests.post(f"{HOST_BRIDGE_URL}/api/{endpoint}", json=kwargs, headers=headers, timeout=10)
                
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"Host Bridge Error ({resp.status_code}): {resp.text}"}
        except Exception as e:
            return {"error": f"Connection Failed: {e}"}

    def execute_plan(self, plan: List[Dict[str, Any]]) -> str:
        results = []
        for step in plan:
            action = step.get("action")
            args = step.get("args", {})
            reasoning = step.get("reasoning", "No reasoning")
            
            logger.info(f"FileAgent: {action} - {reasoning}")
            
            if action == "read":
                path = args.get("path")
                data = self._call_host_bridge("read_file", path=path)
                res = data.get("content", data.get("error", "Unknown Error"))
            elif action == "write":
                path = args.get("path")
                content = args.get("content")
                data = self._call_host_bridge("write_file", path=path, content=content)
                res = data.get("message", "Success" if "error" not in data else data["error"])
            elif action == "list":
                path = args.get("path", ".")
                data = self._call_host_bridge("list_directory", path=path)
                res = "\n".join(data.get("files", [])) if "files" in data else data.get("error", "Error")
            elif action == "abort":
                return f"Aborted: {reasoning}"
            else:
                res = f"Unknown action: {action}"
            
            results.append(f"[{action} {args.get('path', '')}] {str(res)[:200]}...")
            
        return "\n".join(results)

    def think_and_act(self, goal: str) -> str:
        # 1. Search ReasoningBank
        past_strategies = ""
        reasoning_bank = None
        try:
            from mcp_reasoningbank import get_reasoningbank_client
            reasoning_bank = get_reasoningbank_client()
            search_res = reasoning_bank.search(f"file {goal}", limit=3)
            if search_res.get("success"):
                 traces = search_res.get("results", [])
                 past_strategies = json.dumps([t['trace'].get('reasoning', '') for t in traces], indent=2)
        except Exception as e:
            logger.warning(f"ReasoningBank search failed: {e}")

        # 2. Observe (Context is implicit in Request)
        
        # 3. Orient
        system_prompt = f"""You are the File Ops Maintainer Agent.
        SOP CONTENT:
        {self.sop_content}
        
        PAST EXPERIENCE (ReasoningBank):
        {past_strategies}
        
        Your Goal: {goal}
        
        You operate on the HOST filesystem via Bridge OR Local Mounts (/app/shared_storage).
        Create a JSON execution plan.
        Allowed actions: "read", "write", "list", "abort".
        
        Protocol SOP-FILE-01:
        1. Read target file first (if modifying).
        2. Verify content.
        3. Write new content.
        
        Output JSON:
        {{
            "analysis": "...",
            "plan": [
                {{"action": "read", "args": {{"path": "requirements.txt"}}, "reasoning": "Checking current deps..."}},
                {{"action": "write", "args": {{"path": "requirements.txt", "content": "..."}}, "reasoning": "Adding numpy..."}}
            ]
        }}
        """
        
        # 4. Decide
        decision = self._query_deepseek(system_prompt, f"Goal: {goal}")
        
        if "error" in decision:
             return f"Brain Fail: {decision['error']}"
             
        # 5. Act
        analysis = decision.get("analysis", "No analysis")
        plan = decision.get("plan", [])
        log = self.execute_plan(plan)
        
        # 6. Store Experience
        if reasoning_bank:
            try:
                reasoning_bank.store(
                    "file_ops",
                    {"goal": goal, "plan": plan, "analysis": analysis, "outcome": log[:200]}
                )
            except Exception as e:
                logger.warning(f"ReasoningBank store failed: {e}")
        
        return f"**Analysis**: {analysis}\n**Execution**:\n{log}"

# Global Tool Wrapper
@mcp.tool()
def read_file(file_path: str, headers: Optional[Dict] = None) -> str:
    """Read file via Host Bridge."""
    agent = FileMaintainerAgent(headers=headers)
    return str(agent._call_host_bridge("read_file", path=file_path).get("content", "Error reading file"))

@mcp.tool()
def write_file(file_path: str, content: str, headers: Optional[Dict] = None) -> str:
    """Write file via Host Bridge."""
    agent = FileMaintainerAgent(headers=headers)
    return str(agent._call_host_bridge("write_file", path=file_path, content=content).get("message", "Error writing file"))

@mcp.tool()
def list_directory(dir_path: str = ".", headers: Optional[Dict] = None) -> str:
    """List dir via Host Bridge."""
    agent = FileMaintainerAgent(headers=headers)
    data = agent._call_host_bridge("list_directory", path=dir_path)
    return "\n".join(data.get("files", [])) if "files" in data else str(data)

@mcp.tool()
def file_maintainer_operation(operation: str, path: str = None, content: str = None, headers: Optional[Dict] = None, **kwargs) -> str:
    """
    Autonomous File Ops Agent Operation.
    Operation: "read", "write", "update", "verify"
    """
    agent = FileMaintainerAgent(headers=headers)
    goal = f"Perform {operation}"
    if path: goal += f" on {path}"
    if content: goal += f" with content length {len(content)}"
    
    return agent.think_and_act(goal)
