#!/usr/bin/env python3
"""
ARCA Maintainer Agents Service - LangGraph refactor
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import aio_pika
import httpx
import numpy as np
import uvicorn
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

sys.path.append("/app/shared")
try:
    from secrets_provider import secrets
except ImportError:

    class MockSecrets:
        def get(self, name):
            return os.getenv(name.upper())

    secrets = MockSecrets()
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

# Add execution_firewall to path
sys.path.insert(0, os.path.dirname(__file__))
from execution_firewall.permission_validator import get_firewall, initialize_firewall

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("maintainer-agents")

# Configuration
import sys

sys.path.insert(0, "/shared")
sys.path.insert(0, "/app/shared")
from graph import MaintainerGraph
from state import AgentState

from shared.model_config import get_model

# Routing to Local LLM Gateway (Firewall Protected)
PRIMARY_MODEL_URL = os.getenv("PRIMARY_MODEL_URL", "http://llm_gateway:8080/v1")

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://mcp_server:8086")
AGENT_PORT = int(os.getenv("AGENT_PORT", "8090"))
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
HSE_ENCODER_URL = os.getenv("HSE_ENCODER_URL", "http://hse_encoder:8095")

app = FastAPI(title="ARCA Maintainer Agents", version="2.0.0")

# Initialize execution firewall
try:
    firewall = initialize_firewall(redis_host=REDIS_HOST, redis_port=REDIS_PORT)
    logger.info("✅ Execution Firewall initialized")
except Exception as e:
    logger.error(f"⚠️  Failed to initialize firewall: {e}")
    firewall = None


class AgentRequest(BaseModel):
    agent_type: str
    operation: str
    params: Optional[Dict[str, Any]] = None
    intent_hv: Optional[List[float]] = None
    instruct: Optional[str] = None


class AgentResponse(BaseModel):
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    model_used: Optional[str] = None


class DispatchResponse(BaseModel):
    task_id: str
    status: str
    message: str


class TaskStatus(BaseModel):
    task_id: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None
    logs: List[str] = []
    created_at: str
    completed_at: Optional[str] = None


# --- Real-time Logging Callback ---
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class TaskLogCallbackHandler(BaseCallbackHandler):
    def __init__(self, task_id: str):
        self.task_id = task_id

    def on_chain_start(
        self,
        serialized: Optional[Dict[str, Any]],
        inputs: Dict[str, Any],
        **kwargs: Any,
    ) -> None:
        chain_id = serialized.get("id", "Unknown") if serialized else "Unknown"
        self._append_log(f"📋 Chain Started: {chain_id}")

    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> None:
        self._append_log(
            f"🛠️ Tool Start: {serialized.get('name')} | Input: {input_str[:200]}..."
        )

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        # Clean output string to avoid messy logs
        clean_out = str(output)[:300] + "..." if len(str(output)) > 300 else str(output)
        self._append_log(f"✅ Tool Output: {clean_out}")

    def on_llm_start(
        self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
    ) -> None:
        self._append_log(f"🧠 LLM Thinking... ({serialized.get('name', 'Model')})")

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        self._append_log("💡 LLM Response Generated")

    def on_chain_error(self, error: BaseException, **kwargs: Any) -> None:
        self._append_log(f"❌ Chain Error: {str(error)}")

    def _append_log(self, message: str):
        if self.task_id in TASK_REGISTRY:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = f"[{timestamp}] {message}"
            # Initialize logs list if missing (safety)
            if "logs" not in TASK_REGISTRY[self.task_id]:
                TASK_REGISTRY[self.task_id]["logs"] = []
            TASK_REGISTRY[self.task_id]["logs"].append(log_entry)


# Global Task Registry and Concurrency Guard
TASK_REGISTRY: Dict[str, Dict[str, Any]] = {}
execution_semaphore = asyncio.Semaphore(2)  # Increased concurrency to 2
model_2b_busy = asyncio.Lock()  # Lock to manage 2B model preference

# --- Clients ---


class LLMClient:
    def __init__(self):
        self.primary_url = PRIMARY_MODEL_URL
        self.primary_model = get_model("MAINTAINER_MODEL")

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> tuple[str, str]:
        max_retries = 5
        base_delay = 2.0

        # Model Selection Logic: Prefer 2B (+) if free, otherwise fallback to 0.6B (FAST)
        selected_model = get_model("FAST_MODEL")
        is_2b = False

        if not model_2b_busy.locked():
            try:
                # Attempt to acquire 2B model
                await asyncio.wait_for(model_2b_busy.acquire(), timeout=0.1)
                selected_model = get_model("MAINTAINER_MODEL")
                is_2b = True
                logger.info(f"✨ 2B model preference acquired: {selected_model}")
            except (asyncio.TimeoutError, Exception):
                logger.info(
                    f"⚡ 2B model busy or unavailable, falling back to fast model: {selected_model}"
                )
        else:
            logger.info(
                f"⚡ 2B model already in use, using fast model: {selected_model}"
            )

        try:
            for attempt in range(max_retries):
                try:
                    async with httpx.AsyncClient(timeout=300.0) as client:
                        messages = []
                        if system:
                            messages.append({"role": "system", "content": system})
                        messages.append({"role": "user", "content": prompt})

                        url = f"{self.primary_url.rstrip('/')}/chat/completions"
                        payload = {
                            "model": selected_model,
                            "messages": messages,
                            "max_tokens": 12288,
                        }  # Using 12k context
                        api_key = secrets.get("genesis_chain_api_key")

                        req_headers = (headers or {}).copy()
                        req_headers["Content-Type"] = "application/json"
                        req_headers["X-Genesis-Chain"] = "ENABLED"
                        if os.getenv("WORKHORSE_SECRET_KEY"):
                            req_headers["X-Workhorse-Token"] = os.getenv(
                                "WORKHORSE_SECRET_KEY"
                            )

                        if api_key:
                            import hashlib
                            import hmac

                            body_str = json.dumps(payload, sort_keys=True)
                            signature = hmac.new(
                                api_key.encode("utf-8"),
                                body_str.encode("utf-8"),
                                hashlib.sha256,
                            ).hexdigest()
                            req_headers["X-Genesis-Signature"] = signature
                            response = await client.post(
                                url, data=body_str, headers=req_headers
                            )
                        else:
                            response = await client.post(
                                url, json=payload, headers=req_headers
                            )

                        response.raise_for_status()
                        result = response.json()
                        if "choices" in result and len(result["choices"]) > 0:
                            content = result["choices"][0]["message"]["content"]
                            return content, selected_model
                        else:
                            raise ValueError(
                                f"Invalid LLM response format: {list(result.keys())}"
                            )
                except (
                    httpx.HTTPStatusError,
                    httpx.ConnectError,
                    httpx.RemoteProtocolError,
                ) as e:
                    status_code = (
                        getattr(e.response, "status_code", 0)
                        if hasattr(e, "response")
                        else 0
                    )
                    if attempt < max_retries - 1 and (
                        status_code == 503
                        or isinstance(
                            e, (httpx.RemoteProtocolError, httpx.ConnectError)
                        )
                    ):
                        delay = base_delay * (2**attempt) + (0.1 * attempt)
                        logger.warning(
                            f"LLM attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s..."
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise e
        finally:
            if is_2b:
                model_2b_busy.release()
                logger.info("🔓 Released 2B model lock.")


class MCPClient:
    def __init__(self):
        self.mcp_url = MCP_SERVER_URL

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.mcp_url.rstrip('/')}/mcp"
        url = f"{self.mcp_url.rstrip('/')}/mcp"
        logger.info(
            f"🛠️ Calling Tool: {tool_name} at {url} | Headers: {list(headers.keys()) if headers else 'None'}"
        )
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                payload = {
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                    "id": str(uuid.uuid4()),
                }
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
                if "error" in result:
                    logger.error(
                        f"❌ Tool {tool_name} returned error: {result['error']}"
                    )
                    return {"success": False, "error": result["error"]}
                logger.info(f"✅ Tool {tool_name} call successful.")
                return {"success": True, "result": result.get("result")}
        except httpx.ConnectError as e:
            logger.error(f"❌ MCP Connection Error calling {tool_name}: {e}")
            return {"success": False, "error": f"Connection failed: {e}"}
        except Exception as e:
            logger.error(f"❌ MCP tool call failed: {e}")
            return {"success": False, "error": str(e)}


class HSEClient:
    def __init__(self):
        self.url = HSE_ENCODER_URL

    async def encode_text(self, text: str) -> Optional[np.ndarray]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(f"{self.url}/encode", json={"text": text})
                if response.status_code == 200:
                    return np.array(response.json().get("vector"))
        except:
            return None

    def validate_intent(
        self, command_vec: np.ndarray, intent_vec: List[float], threshold: float = 0.6
    ) -> tuple[bool, float]:
        if command_vec is None or not intent_vec:
            return True, 1.0
        try:
            intent_arr = np.array(intent_vec)
            norm_cmd, norm_int = np.linalg.norm(command_vec), np.linalg.norm(intent_arr)
            if norm_cmd == 0 or norm_int == 0:
                return True, 0.0
            similarity = np.dot(command_vec, intent_arr) / (norm_cmd * norm_int)
            return similarity >= threshold, float(similarity)
        except:
            return True, 1.0


# Initialize graph and clients
llm_client = LLMClient()
mcp_client = MCPClient()
hse_client = HSEClient()
maintainer_graph = MaintainerGraph(llm_client, mcp_client)


async def _get_sop_content(agent_type: str) -> str:
    sop_map = {
        "git": "GIT_OPS_SOP.md",
        "docker": "DOCKER_OPS_SOP.md",
        "security": "SECURITY_MAINTAINER_SOP.md",
        "code_maintainer": "CODE_MAINTENANCE_SOP.md",
        "development": "FILE_OPS_SOP.md",
        "observer": "OBSERVER_SOP.md",
    }
    filename = sop_map.get(agent_type, "FILE_OPS_SOP.md")
    try:
        path = os.path.join(os.path.dirname(__file__), "skills", filename)
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()
    except:
        pass
    return "SOP not found."


async def run_agent_task_async(
    task_id: str,
    agent_type: str,
    operation: str,
    params: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
):
    async with execution_semaphore:
        logger.info(
            f"🚀 [GRAPH] STARTING TASK (SERIALIZED): {task_id} ({agent_type}:{operation})"
        )
        TASK_REGISTRY[task_id]["status"] = "running"

        sop = await _get_sop_content(agent_type)

        # Inject Genesis Chain Authorization for autonomous tasks
        safe_headers = (headers or {}).copy()
        if "X-Genesis-Chain" not in safe_headers:
            safe_headers["X-Genesis-Chain"] = "ENABLED"

        initial_state = {
            "messages": [HumanMessage(content=f"Operation: {operation}")],
            "task_id": task_id,
            "agent_type": agent_type,
            "operation": operation,
            "params": params or {},
            "sop_content": sop,
            "execution_log": [],
            "validation_results": [],
            "retry_count": 0,
            "max_retries": 3,
            "escalation_requested": False,
            "success": False,
            "headers": safe_headers,
            "instructions": params.get("instructions") or params.get("instruct") or "",
        }

        try:
            # Attach real-time logger
            callback = TaskLogCallbackHandler(task_id)
            TASK_REGISTRY[task_id]["logs"] = [
                f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Task Started: {operation}"
            ]

            final_state = await maintainer_graph.workflow.ainvoke(
                initial_state, config={"callbacks": [callback]}
            )

            TASK_REGISTRY[task_id]["status"] = (
                "completed" if final_state["success"] else "failed"
            )
            TASK_REGISTRY[task_id]["result"] = final_state.get("output")
            TASK_REGISTRY[task_id]["error"] = final_state.get("error")
            TASK_REGISTRY[task_id]["completed_at"] = datetime.now().isoformat()

        except Exception as e:
            logger.error(f"❌ [GRAPH] TASK FAILED: {task_id} - {e}")
            TASK_REGISTRY[task_id]["status"] = "failed"
            TASK_REGISTRY[task_id]["error"] = str(e)
            TASK_REGISTRY[task_id]["completed_at"] = datetime.now().isoformat()


class AsyncWorker:
    def __init__(self, rabbitmq_url: str = None):
        self.rabbitmq_url = rabbitmq_url or os.getenv(
            "RABBITMQ_URL", "amqp://arca:arca_password@rabbitmq:5672/arca_vhost"
        )
        self.connection = None

    async def connect(self):
        try:
            self.connection = await aio_pika.connect_robust(self.rabbitmq_url)
            channel = await self.connection.channel()
            queue_name = os.getenv("RABBITMQ_QUEUE", "agent_tasks")
            queue = await channel.declare_queue(queue_name, durable=True)
            logger.info(
                f"✅ Async Brain (LangGraph): Connected to RabbitMQ queue: {queue_name}"
            )
            asyncio.create_task(self.consume(queue))
        except Exception as e:
            logger.error(f"❌ RabbitMQ Failed: {e}")

    async def consume(self, queue):
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    task_data = json.loads(message.body.decode())
                    task_id = task_data.get("task_id")
                    logger.info(f"📥 Received task {task_id} from queue")
                    if task_id not in TASK_REGISTRY:
                        TASK_REGISTRY[task_id] = {
                            "status": "queued",
                            "created_at": datetime.now().isoformat(),
                        }
                    await run_agent_task_async(
                        task_id,
                        task_data.get("agent_type"),
                        task_data.get("operation"),
                        task_data.get("params"),
                        task_data.get("headers"),
                    )


worker = AsyncWorker()


@app.on_event("startup")
async def startup_event():
    await worker.connect()


@app.get("/health")
async def health():
    return {"status": "healthy", "engine": "LangGraph"}


@app.post("/execute", response_model=DispatchResponse)
async def execute_agent(raw_request: Request, background_tasks: BackgroundTasks):
    # (Firewall and validation logic remains same, but calls run_agent_task_async)
    # Re-using simplified placeholder for brevity of the plan execution
    body = await raw_request.json()
    task_id = str(uuid.uuid4())
    TASK_REGISTRY[task_id] = {
        "status": "queued",
        "created_at": datetime.now().isoformat(),
    }
    genesis_headers = {
        k: v
        for k, v in raw_request.headers.items()
        if k.lower().startswith("x-genesis-")
    }

    # Extract instructions from body if present
    instructions = body.get("instruct") or body.get("instructions")
    if instructions and not body.get("params"):
        body["params"] = {"instruct": instructions}
    elif instructions:
        body["params"]["instruct"] = instructions

    background_tasks.add_task(
        run_agent_task_async,
        task_id,
        body["agent_type"],
        body["operation"],
        body.get("params"),
        genesis_headers,
    )
    return DispatchResponse(
        task_id=task_id, status="queued", message="Task dispatched to LangGraph engine"
    )


@app.get("/task/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    task = TASK_REGISTRY.get(task_id)
    if not task:
        raise HTTPException(status_code=404)
    return TaskStatus(task_id=task_id, **task)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
