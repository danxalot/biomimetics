#!/usr/bin/env python3
"""
Serena Notion Task Poller - The Architect Loop
===============================================

Polls the Notion Biomimetic OS database for "Ready for Dev" tasks,
claims them, and routes to Nemotron 3 Super (OpenCode) for deep repository planning.

Model Hierarchy:
- **Agent PM (Gemma 3 27b/12b)**: GitHub issue → Technical documentation → Notion
- **The Architect (Nemotron 3 Super)**: "Ready for Dev" → Deep repository planning (1M context)
- **The Executors**: Minimax 2.5 / Zhipu GLM-5 / Qwen 3.5 Max (code generation)

Usage:
    python3 serena_notion_poller.py

Environment Variables:
    NOTION_API_KEY
    NOTION_BIOMIMETIC_DB_ID
    OPENCODE_API_KEY
    OPENCODE_MODEL (default: nemotron-3-super-free for Architect)
    EXECUTOR_MODEL (default: minimax-m2.5-free for code generation)
    CLOUDFLARE_WORKER_URL (for WhatsApp notifications)
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path.home() / ".serena" / "notion_poller.log"),
    ],
)
log = logging.getLogger("serena_notion_poller")

# ============================================================================
# Secure Credential Loading from Credentials Server
# ============================================================================

SECRETS_DIR = Path("/Users/danexall/biomimetics/secrets")
CREDENTIALS_API_KEY_FILE = SECRETS_DIR / "credentials_api_key"
CREDENTIALS_SERVER_URL = "http://localhost:8089"


def load_credentials_api_key() -> str:
    """Load Credentials API key from secure file."""
    if CREDENTIALS_API_KEY_FILE.exists():
        return CREDENTIALS_API_KEY_FILE.read_text().strip()
    return os.getenv("CREDENTIALS_API_KEY", "")


def fetch_secret_from_credentials_server(secret_name: str) -> Optional[str]:
    """Fetch a secret from the local Credentials Server."""
    api_key = load_credentials_api_key()
    if not api_key:
        log.warning(f"No CREDENTIALS_API_KEY found for fetching {secret_name}")
        return None
    
    try:
        response = httpx.get(
            f"{CREDENTIALS_SERVER_URL}/secrets/{secret_name}",
            headers={"X-API-Key": api_key},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("value")
        else:
            log.warning(f"Failed to fetch {secret_name}: {response.status_code}")
            return None
    except Exception as e:
        log.warning(f"Error fetching {secret_name}: {e}")
        return None


# Configuration - Load secrets from Credentials Server at runtime
NOTION_API_KEY = fetch_secret_from_credentials_server("notion-api-key") or os.getenv("NOTION_API_KEY", "")
NOTION_BIOMIMETIC_DB_ID = os.getenv("NOTION_BIOMIMETIC_DB_ID", "3284d2d9-fc7c-8111-88de-eeaba9c5f845")  # ARCA Tasks
OPENCODE_API_KEY = fetch_secret_from_credentials_server("opencode-go-api-key") or os.getenv("OPENCODE_API_KEY", "")

# Model Configuration - The Architect & Executors
OPENCODE_MODEL = os.getenv("OPENCODE_MODEL", "nemotron-3-super-free")  # The Architect
OPENCODE_BASE_URL = "https://opencode.ai/zen/v1"

# Fallback Execution Matrix
EXECUTOR_MODELS = {
    "primary": os.getenv("EXECUTOR_MODEL_PRIMARY", "minimax-m2.5-free"),      # Code generation
    "fallback_1": os.getenv("EXECUTOR_MODEL_FALLBACK_1", "glm-5"),            # Zhipu GLM-5
    "fallback_2": os.getenv("EXECUTOR_MODEL_FALLBACK_2", "qwen-3.5-max"),     # Qwen 3.5 Max via Qwen Code
}

# Gemma-3 Router Configuration (Dynamic Model Selection)
GEMMA_ROUTER_ENABLED = os.getenv("GEMMA_ROUTER_ENABLED", "true").lower() == "true"
GEMMA_MODEL = "gemma-3-12b"
GEMMA_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMMA_API_KEY = fetch_secret_from_credentials_server("google_api_key") or os.getenv("GEMINI_API_KEY", "")

# Model selection prompt for Gemma-3 Router
MODEL_ROUTER_PROMPT = """You are the ARCA Model Dispatcher. Analyze this task and return ONLY the string name of the best model to use from this list:

- minimax_2.7 (For adventurous architecture/refactoring)
- super_nemotron_3_free (For deep investigation/troubleshooting)
- kimi_k2.5_thinking (For complex reasoning/logic mapping)
- qwen-coder (For standard, fast code generation)
- glm-5 (For native Zhipu free-tier general tasks)

Task Title: {title}
Task Description: {description}
Priority: {priority}
Complexity: {complexity}

Return ONLY the model name, nothing else."""

CLOUDFLARE_WORKER_URL = os.getenv("CLOUDFLARE_WORKER_URL", "")

POLL_INTERVAL_SECONDS = int(os.getenv("SERENA_POLL_INTERVAL", "30"))  # 30 seconds
TASK_CLAIM_TIMEOUT_MINUTES = int(os.getenv("SERENA_TASK_TIMEOUT", "30"))  # 30 min timeout


class NotionTaskPoller:
    """Polls Notion for Ready for Dev tasks and routes to OpenCode."""
    
    def __init__(self):
        self.notion_headers = {
            "Authorization": f"Bearer {NOTION_API_KEY}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        self.opencode_headers = {
            "Authorization": f"Bearer {OPENCODE_API_KEY}",
            "Content-Type": "application/json"
        }
        self.processed_tasks: set = set()  # Track processed task IDs
        self.current_task: Optional[Dict] = None

    async def route_with_gemma3(self, task: Dict) -> str:
        """
        Dynamic Model Router using Gemma-3-12b.
        
        Analyzes task and selects the optimal executor model from the MoE registry.
        Sets environment variable for downstream execution.
        
        Args:
            task: Task dict with title, description, priority, complexity
            
        Returns:
            Selected model name string
        """
        if not GEMMA_ROUTER_ENABLED:
            log.info("⚠️  Gemma-3 router disabled, using default executor")
            return EXECUTOR_MODELS["primary"]
        
        try:
            # Build prompt with task details
            prompt = MODEL_ROUTER_PROMPT.format(
                title=task.get("title", "Unknown"),
                description=task.get("description", "")[:500],  # Truncate for token efficiency
                priority=task.get("priority", "Medium"),
                complexity=task.get("complexity", "Medium")
            )
            
            # Call Gemma-3-12b via Google AI Studio
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{GEMMA_BASE_URL}/models/{GEMMA_MODEL}:generateContent",
                    params={"key": GEMMA_API_KEY},
                    json={
                        "contents": [{
                            "parts": [{"text": prompt}]
                        }],
                        "generationConfig": {
                            "temperature": 0.1,  # Low temp for deterministic selection
                            "maxOutputTokens": 50,
                            "topP": 0.8,
                            "topK": 1
                        }
                    }
                )
                
                if response.status_code != 200:
                    log.warning(f"Gemma-3 router API error: {response.status_code}, using default")
                    return EXECUTOR_MODELS["primary"]
                
                result = response.json()
                
                # Extract model name from response
                if "candidates" in result and len(result["candidates"]) > 0:
                    selected_model = result["candidates"][0]["content"]["parts"][0]["text"].strip()
                    
                    # Clean up response (remove quotes, backticks, etc.)
                    selected_model = selected_model.strip('"\'`').strip()
                    
                    # Validate against known models
                    valid_models = [
                        "minimax_2.7",
                        "super_nemotron_3_free", 
                        "kimi_k2.5_thinking",
                        "qwen-coder",
                        "glm-5"
                    ]
                    
                    if selected_model in valid_models:
                        # Set environment variable for downstream execution
                        os.environ["EXECUTOR_MODEL_PRIMARY"] = selected_model
                        log.info(f"✅ [Gemma-3 Router] Selected: {selected_model}")
                        return selected_model
                    else:
                        log.warning(f"Gemma selected unknown model: {selected_model}, using default")
                        return EXECUTOR_MODELS["primary"]
                
                log.warning("Gemma-3 returned empty response, using default")
                return EXECUTOR_MODELS["primary"]
                
        except Exception as e:
            log.error(f"Gemma-3 router error: {e}, using default executor")
            return EXECUTOR_MODELS["primary"]

    async def poll_notion_tasks(self) -> List[Dict]:
        """Query Notion for 'Ready for Dev' tasks."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"https://api.notion.com/v1/databases/{NOTION_BIOMIMETIC_DB_ID}/query",
                    headers=self.notion_headers,
                    json={
                        "filter": {
                            "property": "State",
                            "select": {"equals": "Ready for Dev"}
                        },
                        "page_size": 10
                    }
                )
                
                if response.status_code != 200:
                    log.error(f"Notion API error: {response.status_code} - {response.text}")
                    return []
                
                data = response.json()
                tasks = []
                
                for page in data.get("results", []):
                    task_id = page["id"]
                    
                    # Skip already processed tasks
                    if task_id in self.processed_tasks:
                        continue
                    
                    # Extract task properties
                    properties = page.get("properties", {})
                    
                    task = {
                        "id": task_id,
                        "title": self._get_title(properties),
                        "description": self._get_description(properties),
                        "priority": self._get_select_value(properties.get("Priority")),
                        "complexity": self._get_select_value(properties.get("Complexity")),
                        "github_link": properties.get("Github Link", {}).get("url", ""),
                        "source": self._get_rich_text(properties.get("Source")),
                        "created_time": page.get("created_time"),
                    }
                    
                    tasks.append(task)
                
                log.info(f"Found {len(tasks)} Ready for Dev tasks")
                return tasks
                
        except Exception as e:
            log.error(f"Error polling Notion: {e}")
            return []
    
    async def claim_task(self, task_id: str) -> bool:
        """Update task status to 'In Progress'."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.patch(
                    f"https://api.notion.com/v1/pages/{task_id}",
                    headers=self.notion_headers,
                    json={
                        "properties": {
                            "State": {"select": {"name": "In Progress"}},
                            "Push to GitHub": {"checkbox": True}
                        }
                    }
                )

                if response.status_code == 200:
                    log.info(f"✅ Claimed task: {task_id}")
                    return True
                else:
                    log.error(f"Failed to claim task: {response.status_code}")
                    return False

        except Exception as e:
            log.error(f"Error claiming task: {e}")
            return False
    
    async def execute_with_nemotron_architect(self, task: Dict) -> Dict:
        """
        Route task to Nemotron 3 Super (The Architect) for deep repository planning.
        
        BEFORE: Calls Gemma-3 Router to select optimal executor model.
        AFTER: Nemotron generates plan with recommended executor.

        Nemotron 3 Super features:
        - 1M token context window for full repository understanding
        - High-thinking mode for complex architectural decisions
        - Superior reasoning for multi-file changes

        Returns execution plan for The Executors to implement.
        """
        try:
            # STEP 1: Gemma-3 Router selects optimal executor BEFORE Architect planning
            log.info("🎯 [Gemma-3 Router] Analyzing task for model selection...")
            selected_executor = await self.route_with_gemma3(task)
            log.info(f"   Gemma-3 selected: {selected_executor}")
            
            # Build prompt for Nemotron 3 Super - The Architect role
            prompt = f"""You are The Architect - a senior principal engineer with deep repository understanding.
Your role is to analyze coding tasks and create comprehensive implementation plans.

**Task**: {task['title']}
**Priority**: {task['priority']}
**Complexity**: {task['complexity']}
**Description**:
{task['description']}

**GitHub Link**: {task['github_link']}

**Pre-selected Executor**: {selected_executor}
(The Gemma-3 Router has selected this model based on task analysis)

Using your 1M token context and high-thinking mode, provide:

1. **Repository Analysis**: Which files/directories are affected
2. **Architecture Decision**: Design patterns, interfaces, abstractions needed
3. **Implementation Plan**: Step-by-step coding tasks
4. **File Manifest**: List of files to create/modify/delete with paths
5. **Testing Strategy**: Unit tests, integration tests needed
6. **Risk Assessment**: Potential issues, edge cases, migration concerns

Respond in JSON format:
{{
    "repository_analysis": "...",
    "architecture_decision": "...",
    "implementation_plan": ["step1", "step2"],
    "file_manifest": [{{"path": "src/file.py", "action": "create/modify/delete", "description": "..."}}],
    "testing_strategy": "...",
    "risk_assessment": "...",
    "recommended_executor": "{selected_executor}",
    "estimated_tokens": 1000
}}
"""
            
            # Call Nemotron 3 Super (The Architect)
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{OPENCODE_BASE_URL}/chat/completions",
                    headers=self.opencode_headers,
                    json={
                        "model": OPENCODE_MODEL,  # nemotron-3-super-free
                        "messages": [
                            {"role": "system", "content": "You are The Architect - a senior principal engineer with deep repository understanding. Use your 1M token context and high-thinking mode for comprehensive implementation planning."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.2,  # Lower temperature for precise planning
                        "max_tokens": 8192,
                        "response_format": {"type": "json_object"}
                    }
                )
                
                if response.status_code != 200:
                    log.error(f"Nemotron Architect API error: {response.status_code} - {response.text}")
                    return {"error": f"Nemotron API error: {response.status_code}"}
                
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                architect_plan = json.loads(content)
                
                log.info(f"✅ [Architect] Nemotron 3 Super plan generated")
                log.info(f"   Recommended executor: {architect_plan.get('recommended_executor', 'minimax-m2.5-free')}")
                log.info(f"   Files to modify: {len(architect_plan.get('file_manifest', []))}")
                
                return architect_plan
                
        except Exception as e:
            log.error(f"Error executing with Nemotron Architect: {e}")
            return {"error": str(e)}
    
    async def execute_with_executor(self, task: Dict, architect_plan: Dict) -> Dict:
        """
        Route code generation to The Executors based on Architect's recommendation.
        
        Execution Matrix:
        1. Minimax 2.5 (Free) - Primary for code generation
        2. Zhipu GLM-5 - Fallback for complex reasoning
        3. Qwen 3.5 Max - Fallback via Qwen Code
        """
        # Get recommended executor or use primary
        recommended = architect_plan.get("recommended_executor", EXECUTOR_MODELS["primary"])
        
        # Try models in order: recommended → primary → fallback_1 → fallback_2
        model_order = [recommended]
        for model in EXECUTOR_MODELS.values():
            if model not in model_order:
                model_order.append(model)
        
        # Build code generation prompt
        code_prompt = f"""You are a code executor implementing The Architect's plan.

**Task**: {task['title']}

**Architect's Plan**:
- Repository Analysis: {architect_plan.get('repository_analysis', 'N/A')}
- Architecture Decision: {architect_plan.get('architecture_decision', 'N/A')}
- Implementation Steps: {architect_plan.get('implementation_plan', [])}
- Files: {architect_plan.get('file_manifest', [])}

Generate the complete code implementation following the Architect's plan exactly.

Respond in JSON format:
{{
    "files": [{{"path": "...", "content": "...", "action": "create/modify"}}],
    "git_commands": ["git add ...", "git commit -m '...'"],
    "commit_message": "feat: ...",
    "test_commands": ["pytest ..."]
}}
"""
        
        last_error = None
        
        for model in model_order:
            try:
                log.info(f"🔨 [Executor] Trying {model}...")
                
                async with httpx.AsyncClient(timeout=180.0) as client:
                    response = await client.post(
                        f"{OPENCODE_BASE_URL}/chat/completions",
                        headers=self.opencode_headers,
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": "You are a code executor. Implement The Architect's plan precisely."},
                                {"role": "user", "content": code_prompt}
                            ],
                            "temperature": 0.3,
                            "max_tokens": 8192,
                            "response_format": {"type": "json_object"}
                        }
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        content = result["choices"][0]["message"]["content"]
                        execution_result = json.loads(content)
                        
                        log.info(f"✅ [Executor] {model} generated code successfully")
                        execution_result["executor_model"] = model
                        return execution_result
                    else:
                        log.warning(f"⚠️  {model} failed: {response.status_code}")
                        last_error = f"{model}: {response.status_code}"
                        
            except Exception as e:
                log.warning(f"⚠️  {model} error: {e}")
                last_error = str(e)
                continue
        
        # All executors failed
        return {"error": f"All executors failed. Last error: {last_error}"}
    
    async def execute_with_opencode(self, task: Dict) -> Dict:
        """
        Two-stage execution: Architect (Nemotron) → Executors (Minimax/GLM/Qwen).
        """
        # Stage 1: The Architect plans
        log.info("🏛️  Stage 1: The Architect (Nemotron 3 Super) planning...")
        architect_plan = await self.execute_with_nemotron_architect(task)
        
        if "error" in architect_plan:
            return architect_plan
        
        # Stage 2: The Executors implement
        log.info("🔨 Stage 2: The Executors implementing...")
        execution_result = await self.execute_with_executor(task, architect_plan)
        
        # Merge results
        execution_result["architect_plan"] = architect_plan
        return execution_result
    
    async def complete_task(self, task_id: str, execution_result: Dict):
        """Update task to 'Review' status and trigger WhatsApp notification."""
        try:
            # Update Notion status to Review
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.patch(
                    f"https://api.notion.com/v1/pages/{task_id}",
                    headers=self.notion_headers,
                    json={
                        "properties": {
                            "Status": {"status": {"name": "Review"}},
                            "Completed At": {
                                "date": {"start": datetime.now().isoformat()}
                            }
                        }
                    }
                )
                
                if response.status_code == 200:
                    log.info(f"✅ Task {task_id} marked as Review")
                else:
                    log.error(f"Failed to update task status: {response.status_code}")
            
            # Trigger WhatsApp notification via Cloudflare Worker
            if CLOUDFLARE_WORKER_URL and execution_result.get("commit_message"):
                await self.trigger_whatsapp_notification(task_id, execution_result)
            
            # Mark as processed
            self.processed_tasks.add(task_id)
            
        except Exception as e:
            log.error(f"Error completing task: {e}")
    
    async def trigger_whatsapp_notification(self, task_id: str, execution_result: Dict):
        """Send WhatsApp notification via Cloudflare Worker."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{CLOUDFLARE_WORKER_URL}/notify",
                    headers={"Content-Type": "application/json"},
                    json={
                        "approval_id": f"task_{task_id[:8]}",
                        "tool_name": "serena_code_execution",
                        "arguments": {
                            "commit_message": execution_result.get("commit_message", ""),
                            "files_modified": len(execution_result.get("files", []))
                        },
                        "context": f"Serena completed task: {execution_result.get('analysis', '')[:200]}",
                        "risk_level": "medium"
                    }
                )
                
                if response.status_code == 200:
                    log.info(f"✅ WhatsApp notification sent for task {task_id}")
                else:
                    log.error(f"Failed to send WhatsApp notification: {response.status_code}")
                    
        except Exception as e:
            log.error(f"Error sending WhatsApp notification: {e}")
    
    def _get_title(self, properties: Dict) -> str:
        """Extract title from Notion properties."""
        title_prop = properties.get("Name", {})
        title_array = title_prop.get("title", [])
        if title_array:
            return title_array[0].get("text", {}).get("content", "")
        return ""
    
    def _get_description(self, properties: Dict) -> str:
        """Extract description from Notion properties."""
        desc_prop = properties.get("Description", {})
        rich_text = desc_prop.get("rich_text", [])
        if rich_text:
            return rich_text[0].get("text", {}).get("content", "")
        return ""
    
    def _get_select_value(self, select_prop: Dict) -> str:
        """Extract select value from Notion property."""
        if select_prop and select_prop.get("select"):
            return select_prop["select"].get("name", "")
        return ""
    
    def _get_rich_text(self, rich_text_prop: Dict) -> str:
        """Extract rich text value."""
        if rich_text_prop and rich_text_prop.get("rich_text"):
            return rich_text_prop["rich_text"][0].get("text", {}).get("content", "")
        return ""
    
    async def run_polling_loop(self):
        """Main polling loop."""
        log.info("🚀 Serena Notion Poller started (The Architect Loop)")
        log.info(f"   Database: {NOTION_BIOMIMETIC_DB_ID}")
        log.info(f"   The Architect: {OPENCODE_MODEL} (Nemotron 3 Super)")
        log.info(f"   The Executors: {EXECUTOR_MODELS['primary']} → {EXECUTOR_MODELS['fallback_1']} → {EXECUTOR_MODELS['fallback_2']}")
        log.info(f"   Poll Interval: {POLL_INTERVAL_SECONDS}s")

        while True:
            try:
                # Poll for tasks
                tasks = await self.poll_notion_tasks()

                if tasks:
                    # Process first task (highest priority)
                    task = tasks[0]
                    log.info(f"📋 Processing task: {task['title']}")

                    # Claim the task
                    if await self.claim_task(task["id"]):
                        self.current_task = task

                        # Execute with Architect + Executors
                        execution_result = await self.execute_with_opencode(task)

                        if "error" not in execution_result:
                            log.info(f"✅ Execution complete: {execution_result.get('commit_message', '')}")
                            log.info(f"   Architect: Nemotron 3 Super")
                            log.info(f"   Executor: {execution_result.get('executor_model', 'unknown')}")

                            # Complete task
                            await self.complete_task(task["id"], execution_result)
                        else:
                            log.error(f"Execution failed: {execution_result['error']}")

                # Wait for next poll
                await asyncio.sleep(POLL_INTERVAL_SECONDS)

            except asyncio.CancelledError:
                log.info("Polling loop cancelled")
                break
            except Exception as e:
                log.error(f"Error in polling loop: {e}")
                await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def main():
    """Main entry point."""
    # Validate configuration
    if not NOTION_API_KEY:
        log.error("NOTION_API_KEY not set")
        sys.exit(1)
    
    if not OPENCODE_API_KEY:
        log.warning("OPENCODE_API_KEY not set - OpenCode execution will fail")
    
    # Create and run poller
    poller = NotionTaskPoller()
    
    try:
        await poller.run_polling_loop()
    except KeyboardInterrupt:
        log.info("Shutting down...")


if __name__ == "__main__":
    asyncio.run(main())
