import asyncio
import os
import sys
import time
import json
import logging
import requests
from datetime import datetime
from pathlib import Path
from openai import OpenAI

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
from creds import get_first

# Configuration
LOG_DIR = os.path.expanduser("~/biomimetics/logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "swarm_dispatcher.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("swarm_dispatcher")

# Notion Settings
NOTION_TOKEN = os.environ.get("NOTION_TOKEN") or get_first("notion")
if not NOTION_TOKEN:
    raise RuntimeError("Notion token missing (NOTION_TOKEN or credentials server)")
NOTION_DB_ID = "3284d2d9fc7c811188deeeaba9c5f845"
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# OpenCode Settings
OPENCODE_TOKEN_PATH = "/Users/danexall/biomimetics/secrets/opencode_api"
OPENCODE_ZEN_URL = "https://opencode.ai/zen/v1"
OPENCODE_GO_URL = "https://opencode.ai/zen/go/v1"

# Dynamic Model Mapping State
OPENCODE_MODELS = {
    "nemotron": "nemotron-3-super-free",
    "minimax": "minimax-m2.5-free",
    "deepseek": "deepseek-v4-flash-free",
}
OPENCODE_GO_MODELS = {
    "glm-5": "glm-5",
    "kimi": "kimi-k2.6",
    "minimax": "minimax-m2.7",
    "minimax-m2.5": "minimax-m2.5",
}

# Global State for Zen Poller (Task 3 Mandate: Reuse logic)
_opencode_cache = {}
_CACHE_TTL = 300
_RATE_LIMIT_COOLDOWN = 60
_last_rate_limit_hit = 0
_opencode_using_go = False

# Path to ReasoningBank failures
REASONING_BANK_FAILURES_DIR = "/Users/danexall/Documents/VS Code Projects/ARCA/shared_storage/reasoning_bank/failures"

def log_failure_to_reasoning_bank(model_name: str, task_title: str, error_msg: str):
    """Log model execution failure to ARCA ReasoningBank."""
    try:
        os.makedirs(REASONING_BANK_FAILURES_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"failure_{model_name}_{timestamp}.json"
        filepath = os.path.join(REASONING_BANK_FAILURES_DIR, filename)
        
        failure_doc = {
            "timestamp": datetime.now().isoformat(),
            "model": model_name,
            "task": task_title,
            "status": "failed",
            "error": error_msg,
            "source": "swarm_dispatcher"
        }
        
        with open(filepath, "w") as f:
            json.dump(failure_doc, f, indent=2)
        logger.info(f"Recorded execution failure for {model_name} to ReasoningBank: {filename}")
    except Exception as e:
        logger.error(f"Failed to write failure log to ReasoningBank: {e}")

def initialize_live_opencode_models():
    """Poll OpenCode Zen for available models and map them to roles dynamically."""
    global OPENCODE_MODELS, OPENCODE_GO_MODELS
    try:
        with open(OPENCODE_TOKEN_PATH, "r") as f:
            api_key = f.read().strip()
    except FileNotFoundError:
        logger.error(f"OpenCode token not found at {OPENCODE_TOKEN_PATH}")
        return

    try:
        logger.info("Polling OpenCode Zen for active models...")
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get(f"{OPENCODE_ZEN_URL}/models", headers=headers, timeout=10.0)
        
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            live_models = [m["id"] for m in data]
            logger.info(f"Live OpenCode Models: {live_models}")
            
            # Map available free models dynamically to roles
            free_models = [m for m in live_models if m.endswith("-free")]
            
            new_mappings = {}
            # 1. Nemotron Role (Verification / Verification Hub)
            if "nemotron-3-ultra-free" in free_models:
                new_mappings["nemotron"] = "nemotron-3-ultra-free"
            elif "nemotron-3-super-free" in free_models:
                new_mappings["nemotron"] = "nemotron-3-super-free"
                
            # 2. Minimax Role (Implementation)
            if "minimax-m3-free" in free_models:
                new_mappings["minimax"] = "minimax-m3-free"
            elif "minimax-m2.5-free" in free_models:
                new_mappings["minimax"] = "minimax-m2.5-free"
            elif "mimo-v2.5-free" in free_models:
                new_mappings["minimax"] = "mimo-v2.5-free"
                
            # 3. Deepseek Role
            if "deepseek-v4-flash-free" in free_models:
                new_mappings["deepseek"] = "deepseek-v4-flash-free"
                
            # Apply mappings if changed
            for role, model in new_mappings.items():
                if OPENCODE_MODELS.get(role) != model:
                    logger.info(f"Updated role '{role}' mapping: {OPENCODE_MODELS.get(role)} -> {model}")
                    OPENCODE_MODELS[role] = model
            
            # Also dynamically map paid/go models
            go_models = [m for m in live_models if not m.endswith("-free")]
            for model in go_models:
                if "kimi-k2.6" in model:
                    OPENCODE_GO_MODELS["kimi"] = model
                elif "minimax-m3" in model:
                    OPENCODE_GO_MODELS["minimax"] = model
                elif "nemotron-3-ultra" in model:
                    OPENCODE_GO_MODELS["nemotron"] = model
                elif "glm-5" in model:
                    OPENCODE_GO_MODELS["glm-5"] = model

        else:
            logger.error(f"Failed to fetch models from OpenCode Zen: {resp.status_code}")
    except Exception as e:
        logger.error(f"Error initializing OpenCode models dynamically: {e}")

# Run dynamic initialization at startup
initialize_live_opencode_models()


def _trigger_opencode_agent_sync(system_prompt, user_command, model_choice="nemotron"):
    """
    Standard Logic from jarvis_daemon.py - Fulfills 'Zen-first' cost optimization directive.
    """
    global _last_rate_limit_hit, _opencode_using_go

    if time.time() - _last_rate_limit_hit < _RATE_LIMIT_COOLDOWN:
        logger.warning("OpenCode rate limited. Cooldown active.")
        return None

    try:
        with open(OPENCODE_TOKEN_PATH, "r") as f:
            api_key = f.read().strip()
    except FileNotFoundError:
        logger.error(f"OpenCode token not found at {OPENCODE_TOKEN_PATH}")
        return None

    go_model = OPENCODE_GO_MODELS.get(model_choice)
    if go_model and _opencode_using_go:
        base_url = OPENCODE_GO_URL
        target_model = go_model
    else:
        base_url = OPENCODE_ZEN_URL
        target_model = OPENCODE_MODELS.get(model_choice, OPENCODE_MODELS["nemotron"])

    logger.info(f"OpenCode Routing: {target_model} via {base_url}")
    try:
        client = OpenAI(base_url=base_url, api_key=api_key, max_retries=0, timeout=60.0)
        response = client.chat.completions.create(
            model=target_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_command},
            ],
            temperature=0.2,
        )
        return {
            "model": target_model,
            "response": response.choices[0].message.content
        }
    except Exception as e:
        err_str = str(e).lower()
        log_failure_to_reasoning_bank(target_model, user_command[:100], str(e))
        if any(x in err_str for x in ["rate limit", "429", "freeusagelimit"]):
            _last_rate_limit_hit = time.time()
            if go_model and not _opencode_using_go:
                logger.info("Switching to GO tier due to rate limit.")
                _opencode_using_go = True
                return _trigger_opencode_agent_sync(system_prompt, user_command, model_choice)
        logger.error(f"OpenCode Error: {e}")
        return None

async def poll_notion_tasks():
    """Check for 'Ready for Dev' tasks and initiate the Swarm Loop."""
    try:
        query_url = f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query"
        payload = {
            "filter": {
                "property": "Status",
                "status": { "equals": "Ready for Dev" }
            }
        }
        resp = requests.post(query_url, headers=NOTION_HEADERS, json=payload)
        if resp.status_code != 200:
            logger.error(f"Notion Query Failed: {resp.status_code} - {resp.text}")
            return

        tasks = resp.json().get("results", [])
        for task in tasks:
            task_id = task["id"]
            title = task["properties"].get("Task Name", {}).get("title", [{}])[0].get("plain_text", "Untitled")
            logger.info(f"🚀 Found Task: {title} ({task_id})")

            # 1. Claim the task (Status -> In Progress)
            update_url = f"https://api.notion.com/v1/pages/{task_id}"
            claim_payload = {
                "properties": {
                    "Status": { "status": { "name": "In Progress" } }
                }
            }
            requests.patch(update_url, headers=NOTION_HEADERS, json=claim_payload)
            logger.info(f"Task {task_id} marked 'In Progress'.")

            # 2. Trigger Swarm Architect (Zen Tier)
            # We pass the Task Name and any internal context to the OpenCode engine.
            # In a real loop, we might read the content of the Notion page here too.
            prompt = f"Executing task: {title}\nSystem context: {json.dumps(task)}"
            sys_prompt = "You are the BiOS Swarm Architect. Provide a specific implementation plan for the following task."
            
            # Offload blocking request to thread
            result = await asyncio.to_thread(_trigger_opencode_agent_sync, sys_prompt, prompt)
            
            if result:
                logger.info(f"Swarm Architect generated plan using {result['model']}.")
                # Here we would append the plan back to Notion and trigger the Executor
                # This logic will be expanded as the Serena loop stabilizes.
                logger.debug(f"Plan summary: {result['response'][:100]}...")

    except Exception as e:
        logger.exception(f"Error in poll_notion_tasks: {e}")

async def poll_approvals():
    """Poll for 'Approved' tools in the notion database (Integration of approval_poller.py)."""
    # Placeholder for the approval_poller logic which identifies 'Is Approved' flags.
    # This will be refined as the manual verification workflow matures.
    pass

async def main():
    logger.info("⚡ BiOS Swarm Dispatcher Online.")
    while True:
        await poll_notion_tasks()
        await poll_approvals()
        await asyncio.sleep(15)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Dispatcher shutting down.")
