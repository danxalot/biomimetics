import os
import logging
import json
import requests
import redis
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
try:
    from shared.model_config import get_model
except ImportError:
    def get_model(key): return "deepseek-r1-distill-qwen-1.5b"

# Define tool explicitly
mcp = FastMCP("mcp-git-ops")
logger = logging.getLogger(__name__)

# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://llm_gateway:8080/v1/chat/completions")
HOST_BRIDGE_URL = "http://host_bridge:8092"
SOP_PATH = "/app/skills/GIT_OPS_SOP.md"
REASONING_BANK_PATH = os.getenv("REASONING_BANK_PATH", "/app/shared_storage/reasoning_bank")

# Initialize Redis
try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
except Exception as e:
    logger.error(f"Failed to connect to Redis: {e}")
    redis_client = None

class GitMaintainerAgent:
    """
    Autonomous Git Agent following SOPs and learning from ReasoningBank.
    """
    def __init__(self, headers: Optional[Dict] = None):
        self.sop_content = self._load_sop()
        self.headers = headers
        # ReasoningBank Client
        try:
            from mcp_reasoningbank import get_reasoningbank_client
            self.reasoning_bank = get_reasoningbank_client()
        except ImportError:
            self.reasoning_bank = None
            logger.warning("ReasoningBank client could not be imported.")

    def _load_sop(self) -> str:
        try:
            if os.path.exists(SOP_PATH):
                with open(SOP_PATH, 'r') as f:
                    return f.read()
            return "Error: GIT_OPS_SOP.md not found."
        except Exception as e:
            return f"Error loading SOP: {e}"

    def _query_deepseek(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Query DeepSeek model for reasoning."""
        payload = {
            "model": get_model("MAINTAINER_MODEL"),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt + "\n\nRespond with JSON only."}
            ],
            "temperature": 0.2,
            "max_tokens": 2048,
            "response_format": {"type": "json_object"}
        }
        
        # Prepare headers for LLM Gateway
        final_headers = {"Content-Type": "application/json"}
        if self.headers:
            genesis = {k: v for k, v in self.headers.items() if k.lower().startswith("x-genesis-")}
            final_headers.update(genesis)
            
        try:
            resp = requests.post(LLM_GATEWAY_URL, json=payload, headers=final_headers, timeout=120)
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

    def _execute_git_cmd(self, command: str, path: str, **kwargs) -> str:
        """Execute git via Host Bridge"""
        payload = {"command": command, "path": path, **kwargs}
        headers = {
            "X-Genesis-Chain": "true",
            "X-Genesis-Agent": "mcp_server",
            "X-Genesis-Source": "internal_tool_delegation"
        }
        if self.headers:
            genesis = {k: v for k, v in self.headers.items() if k.lower().startswith("x-genesis-")}
            headers.update(genesis)
            
        try:
            resp = requests.post(f"{HOST_BRIDGE_URL}/api/git", json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("output", data.get("error", "No output"))
            return f"Bridge Error ({resp.status_code}): {resp.text}"
        except Exception as e:
            return f"Bridge Connection Error: {e}"

    def execute_plan(self, plan: List[Dict[str, Any]], repo_path: str) -> str:
        results = []
        for step in plan:
            action = step.get("action")
            args = step.get("args", {})
            reasoning = step.get("reasoning", "No reasoning")
            
            logger.info(f"GitAgent: {action} - {reasoning}")
            
            if action == "status":
                res = self._execute_git_cmd("status", repo_path)
            elif action == "add":
                targets = args.get("targets", ["."])
                res = self._execute_git_cmd("add", repo_path, targets=targets)
            elif action == "commit":
                msg = args.get("message", "update")
                res = self._execute_git_cmd("commit", repo_path, message=msg)
                # Trigger Code Crawler (Memory Population)
                try:
                    crawler_payload = {"name": "mcp_code_crawler", "arguments": {"path": "."}}
                    # Propagate headers for loopback call
                    crawler_headers = {"Content-Type": "application/json"}
                    if self.headers:
                        genesis = {k: v for k, v in self.headers.items() if k.lower().startswith("x-genesis-")}
                        crawler_headers.update(genesis)
                        
                    # Call MCP server loopback
                    requests.post("http://localhost:8086/tools/call", json=crawler_payload, headers=crawler_headers, timeout=2)
                    res += "\n[Memory] Code Crawler Triggered."
                except:
                    res += "\n[Memory] Crawler trigger failed."
            elif action == "push":
                remote = args.get("remote", "origin")
                branch = args.get("branch", "main")
                res = self._execute_git_cmd("push", repo_path, remote=remote, branch=branch)
            elif action == "pull":
                res = self._execute_git_cmd("pull", repo_path)
            elif action == "reset":
                 # Safety: Soft reset only
                 res = self._execute_git_cmd("reset", repo_path, mode="soft", target="HEAD~1")
            elif action == "abort":
                return f"Aborted: {reasoning}"
            else:
                res = f"Unknown action: {action}"
            
            results.append(f"[{action}] {str(res)[:500]}...")
            if "Error" in str(res):
                 return "\n".join(results) + "\nHALTED on Error."
                 
        return "\n".join(results)

    def think_and_act(self, goal: str, repo_path: str = ".") -> str:
        # 1. Search ReasoningBank
        past_strategies = ""
        if self.reasoning_bank:
            try:
                search_res = self.reasoning_bank.search(f"git {goal}", limit=3)
                if search_res.get("success"):
                    traces = search_res.get("results", [])
                    past_strategies = json.dumps([t['trace'].get('reasoning', '') for t in traces], indent=2)
            except Exception as e:
                logger.warning(f"ReasoningBank search failed: {e}")

        # 2. Observe
        status = self._execute_git_cmd("status", repo_path)
        
        # 3. Orient
        system_prompt = f"""You are the Git Ops Maintainer Agent.
        SOP CONTENT:
        {self.sop_content}
        
        PAST EXPERIENCE (ReasoningBank):
        {past_strategies}
        
        Your Goal: {goal}
        Repo Path: {repo_path}
        
        Current Git Status:
        {status}
        
        Create a JSON execution plan.
        Allowed actions: "status", "add", "commit", "push", "pull", "reset", "abort".
        
        Protocol:
        1. Check status.
        2. Add files (be specific or ".").
        3. Commit with semantic message.
        4. Push.
        
        Output JSON:
        {{
            "analysis": "...",
            "plan": [
                {{"action": "add", "args": {{"targets": ["."]}}, "reasoning": "Staging changes..."}},
                {{"action": "commit", "args": {{"message": "feat: ..."}}, "reasoning": "Saving..."}}
            ]
        }}
        """
        
        # 4. Decide
        decision = self._query_deepseek(system_prompt, f"Goal: {goal}")
        
        # Fallback if Brain Fails
        if "error" in decision:
             logger.warning(f"Brain Fail: {decision['error']}. Falling back to direct execution.")
             # Simple heuristic fallback
             if "commit" in goal:
                 return self.execute_plan([{"action": "add", "args": {"targets": ["."]}}, {"action": "commit", "args": {"message": goal.split('message')[-1].strip("' ")}}], repo_path)
             elif "push" in goal:
                 return self.execute_plan([{"action": "push", "args": {}}], repo_path)
             return f"Brain Fail and no fallback for: {goal}"
             
        # 5. Act
        analysis = decision.get("analysis", "No analysis")
        plan = decision.get("plan", [])
        log = self.execute_plan(plan, repo_path)
        
        # 6. Store Experience
        if self.reasoning_bank:
            try:
                self.reasoning_bank.store(
                    "git_ops",
                    {"goal": goal, "plan": plan, "analysis": analysis, "outcome": log[:200]},
                    {"repo": repo_path}
                )
            except Exception as e:
                logger.warning(f"ReasoningBank store failed: {e}")
        
        return f"**Analysis**: {analysis}\n**Execution**:\n{log}"

@mcp.tool()
def git_maintainer_operation(operation: str, repo_path: str = "/mnt/host", message: str = None, headers: Optional[Dict] = None, **kwargs) -> str:
    """
    Autonomous Git Agent Operation with ReasoningBank integration.
    """
    agent = GitMaintainerAgent(headers=headers)
    goal = f"Perform {operation}"
    if message: goal += f" with message '{message}'"
    return agent.think_and_act(goal, repo_path)
