import os
import json
import logging
import httpx
import hmac
import hashlib
from typing import Dict, Any, Optional

# Initialize FastMCP
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("dispatch_agent")
logger = logging.getLogger(__name__)

# Configuration
# Configuration
import time 
import uuid
import pika


MAINTAINER_AGENTS_URL = os.getenv("MAINTAINER_AGENTS_URL", "http://maintainer_agents:8090")
GENESIS_CHAIN_API_KEY = os.getenv("GENESIS_CHAIN_API_KEY")

def monitor_task(task_id: str, timeout: int = 15) -> Dict[str, Any]:
    """Monitor task for early failure or completion (Synchronous)"""
    start_time = time.time()
    
    status_url = f"{MAINTAINER_AGENTS_URL}/task/{task_id}"
    logger.info(f"👀 Monitoring Task {task_id} for {timeout}s...")
    
    last_status = None
    
    # Use sync Client
    with httpx.Client(timeout=5.0) as client:
        while (time.time() - start_time) < timeout:
            try:
                resp = client.get(status_url)
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get("status")
                    last_status = data
                    
                    if status == "failed":
                        return {"status": "failed", "error": data.get("error"), "logs": data.get("logs")}
                    
                    if status == "completed":
                        # Fast task finished!
                        return {
                            "status": "completed", 
                            "result": data.get("result"), 
                            "logs": data.get("logs")
                        }
                        
                time.sleep(1) # Polling interval
            except Exception as e:
                logger.warning(f"Monitoring poll failed: {e}")
                time.sleep(1)
            
    # Timeout reached - Task is healthy/running
    logs = last_status.get("logs") if last_status else ["Monitoring timeout - check manually."]
    # Sanitize logs to strings to prevent RPC errors
    if isinstance(logs, list):
        logs = [str(l) for l in logs]
        
    return {
        "status": "running_verified", 
        "task_id": task_id,
        "logs": logs
    }

@mcp.tool()
def dispatch_agent(agent_type: str, operation: str, params: Dict[str, Any] = None, intent_hv: list = None, instruct: str = None, headers: Optional[Dict[str, str]] = None) -> str:
    """
    Unified Dispatcher: Route tasks to the ARCA Maintainer Agents Service (The Brain).
    
    Args:
        agent_type (str): 'docker', 'git', 'security', 'code_maintainer'
        operation (str): High-level operation (e.g. 'execute', 'audit')
        params (dict): Parameters for the agent (e.g. {'target': 'api', 'details': 'Restart safely'})
        intent_hv (list): Optional HDC vector for geometric intent validation
        instruct (str): Optional per-job instructions for the instruct models
        headers (dict): Optional Genesis Chain headers to propagate
    
    Returns:
        JSON string containing the agent's analysis, plan, and execution result.
    """
    if not GENESIS_CHAIN_API_KEY:
        return json.dumps({"error": "GENESIS_CHAIN_API_KEY not configured on MCP Server."})

    payload = {
        "agent_type": agent_type,
        "operation": operation,
        "params": params or {},
        "intent_hv": intent_hv,
        "instruct": instruct
    }
    
    # 1. Sign Request (Genesis Chain Authority)
    # Sort keys for consistent signing - sign the same payload httpx will send
    body_str = json.dumps(payload, sort_keys=True)
    signature = hmac.new(
        GENESIS_CHAIN_API_KEY.encode("utf-8"),
        body_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    # 2. Prepare headers (Propagate incoming if available)
    final_headers = {
        "X-Genesis-Chain": "true",
        "X-Genesis-Agent": "mcp_server",
        "X-Genesis-Signature": signature,
        "Content-Type": "application/json"
    }
    if headers:
        # Propagation: Incoming Genesis headers take precedence for audit trail
        # while signature remains tied to the local generation (matching the payload)
        final_headers.update({k: v for k, v in headers.items() if k.lower().startswith("x-genesis-") and k.lower() != "x-genesis-signature"})
    
    # 2. Dispatch to Brain
    try:
        url = f"{MAINTAINER_AGENTS_URL}/execute"
        logger.info(f"--- DISPATCHING AGENT v2 --- {agent_type}:{operation} to {url}")
        logger.info(f"HEADERS SENT: {list(final_headers.keys())}")
        
        # Long timeout allows Agent to Think & Act (ReAct Loop)
        # Use data= with pre-serialized body_str to match signature
        # Sync dispatch request
        resp = httpx.post(url, data=body_str, headers=final_headers, timeout=30.0)
        
        if resp.status_code == 200:
            data = resp.json()
            task_id = data.get("task_id")
            
            if not task_id:
                 if data.get("success"):
                     return json.dumps({"status": "success (legacy)", "result": data.get("result")})
                 else:
                     return json.dumps({"status": "failure (legacy)", "error": data.get("error")})

            # --- MONITORING PHASE (The Watchdog) ---
            # Call sync monitor directly
            monitor_result = monitor_task(task_id, 15)
            
            # SANITIZE LOGS (Aggressive fix for RPC Error)
            raw_logs = monitor_result.get("logs", [])
            safe_logs = []
            if isinstance(raw_logs, list):
                safe_logs = [str(l) for l in raw_logs]
            else:
                safe_logs = [str(raw_logs)]

            if monitor_result["status"] == "failed":
                 # Fallback log print
                 logger.error(f"Task Failed Logs: {safe_logs}")
                 return f"Task Failed: {monitor_result.get('error')}"
            
            elif monitor_result["status"] == "completed":
                 logger.info(f"Task Completed Logs: {safe_logs}")
                 return f"Task Completed: {task_id}. Check Reasoning Bank."
                 
            else:
                 # Running Verified
                 return f"Task Running: {task_id}. Check logs manually."
                 
        else:
            return json.dumps({
                "status": "http_error",
                "code": resp.status_code,
                "body": resp.text
            })
            
            
    except Exception as e:
        logger.warning(f"⚠️ Direct Dispatch Failed: {e}. Attempting Async Brain Queue...")
        try:
            # Fallback: Async Brain Queue (RabbitMQ)
            task_id = str(uuid.uuid4())
            payload["task_id"] = task_id # Embed ID for tracking
            
            # Simple Routing Logic
            routing_key = 'agent_tasks'
            if agent_type in ['docker', 'git']:
                 routing_key = 'agent_tasks_secondary'
                 
            logger.info(f"🔀 Routing to Queue: {routing_key}")
            
            # Connect to RabbitMQ (Sync Blocking)
            connection = pika.BlockingConnection(
                pika.URLParameters(os.getenv("RABBITMQ_URL", "amqp://arca:arca_password@rabbitmq:5672/arca_vhost"))
            )
            channel = connection.channel()
            channel.queue_declare(queue=routing_key, durable=True)
            
            channel.basic_publish(
                exchange='',
                routing_key=routing_key,
                body=json.dumps(payload),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent
                )
            )
            connection.close()
            
            logger.info(f"✅ Queued to Async Brain: {task_id}")
            return json.dumps({
                "status": "queued_offline",
                "task_id": task_id,
                "message": "Model service unavailable. Task queued in Async Brain (RabbitMQ) and will execute when healthy.",
                "mode": "async_persistent"
            }, indent=2)
            
        except Exception as queue_error:
            logger.error(f"❌ Total Dispatch Failure (HTTP + Queue): {queue_error}")
            return json.dumps({"status": "dispatch_critical_failure", "error": f"HTTP: {str(e)} | Queue: {str(queue_error)}"})

