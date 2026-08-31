"""
Serena Alert-Driven Agent Service
Monitors service health, receives alerts, analyzes issues, and dispatches remediation
Uses LangGraph StateGraph pattern with agent nodes (same as user_interaction_agent)
"""

import os
import json
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, TypedDict, Literal
from enum import Enum

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis
import docker
import httpx
import requests
from langgraph.graph import StateGraph, END, START

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("serena_alert_agent")

# Environment variables
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
SERENA_PORT = int(os.environ.get("SERENA_PORT", 8089))
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://mcp_server:8086")
DOCKER_HELPER_URL = os.environ.get("DOCKER_HELPER_URL", "http://docker_helper:8082")
MAINTAINER_AGENTS_URL = os.environ.get("MAINTAINER_AGENTS_URL", "http://maintainer_agents:8090")

# Alert severity levels
class AlertSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

# LLM Gateway URL
LLM_GATEWAY_URL = os.environ.get("LLM_GATEWAY_URL", "http://llm_gateway:8080/v1")
MISTRAL_MODEL = os.environ.get("ARCA_MISTRAL_MODEL", "mistral-large-latest") # Or devstral alias


# Alert status
class AlertStatus(str, Enum):
    PENDING = "pending"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    DISPATCHED = "dispatched"
    RESOLVED = "resolved"
    FAILED = "failed"

# LangGraph State for alert processing (same pattern as user_interaction_agent)
class AlertProcessingState(TypedDict):
    """State definition for alert processing workflow"""
    alert_id: str
    timestamp: datetime
    service_name: str
    status: str
    message: str
    severity: AlertSeverity
    health_data: Optional[Dict[str, Any]]
    
    # Analysis and routing
    analysis: str
    root_cause: Optional[str]
    recommended_actions: List[str]
    confidence: float
    
    # Workflow control
    current_step: Literal["received", "analyzing", "analyzed", "dispatching", "completed", "error"]
    error_state: Optional[Dict[str, Any]]
    action_history: List[Dict[str, Any]]

# Pydantic models
class HealthAlert(BaseModel):
    """Health alert from service health checks"""
    alert_id: str
    timestamp: datetime
    service_name: str
    status: str
    message: str
    severity: AlertSeverity
    health_data: Optional[Dict[str, Any]] = None

class AlertAnalysis(BaseModel):
    """Analysis result from Serena"""
    alert_id: str
    analysis: str
    root_cause: Optional[str] = None
    recommended_actions: List[str] = []
    confidence: float = 0.0
    timestamp: datetime

class RemediationTask(BaseModel):
    """Task to dispatch to orchestration system"""
    task_id: str
    alert_id: str
    action: str
    target_service: str
    parameters: Dict[str, Any]
    priority: AlertSeverity
    created_at: datetime


# ============================================================================
# ALERT MANAGER - Pure Monitoring & Alerting
# ============================================================================

# Initialize FastAPI app
app = FastAPI(title="ARCA Alert Manager")

# Redis connection
redis_client = None

# Docker client
docker_client = None

# In-memory alert tracking
active_alerts: Dict[str, HealthAlert] = {}

@app.on_event("startup")
async def startup_event():
    """Initialize connections on startup"""
    global redis_client, docker_client
    logger.info("🚀 Starting ARCA Alert Manager...")
    
    try:
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
            socket_connect_timeout=5
        )
        redis_client.ping()
        logger.info("✅ Redis connection established")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")
        redis_client = None
    
    try:
        docker_client = docker.from_env()
        docker_client.ping()
        logger.info("✅ Docker connection established")
    except Exception as e:
        logger.error(f"❌ Docker connection failed: {e}")
        docker_client = None
    
    logger.info("✅ Alert Manager ready - starting background monitoring...")
    await start_monitoring()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    if redis_client:
        redis_client.close()
    if docker_client:
        docker_client.close()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "alert_manager",
        "timestamp": datetime.utcnow().isoformat(),
        "active_alerts": len(active_alerts),
        "redis_connected": redis_client is not None,
        "docker_connected": docker_client is not None
    }

# Track if background monitoring has been started
_monitoring_started = False

@app.post("/start_monitoring")
async def start_monitoring():
    """Start background monitoring tasks"""
    global _monitoring_started
    if _monitoring_started:
        return {"status": "already_started"}
    
    _monitoring_started = True
    asyncio.create_task(monitor_service_health())
    asyncio.create_task(monitor_docker_events())
    asyncio.create_task(redis_alert_listener())
    logger.info("🔄 Background monitoring tasks started")
    return {"status": "started"}


async def receive_alert(alert: HealthAlert):
    """Receive health alert and publish to ecosystem"""
    logger.info(f"📨 Alert Manager received: {alert.service_name} - {alert.status}")
    active_alerts[alert.alert_id] = alert
    
    # Publish to Redis for Serena/Observer to consume
    if redis_client:
        try:
            redis_client.publish(
                "arca:health:alerts", # Standard channel for Serena
                json.dumps(alert.model_dump(mode='json'), default=str)
            )
            logger.info(f"📢 Published alert to arca:health:alerts")
        except Exception as e:
            logger.error(f"Failed to publish alert to Redis: {e}")
    
    return {"alert_id": alert.alert_id, "status": "published"}

@app.post("/alerts/receive")
async def api_receive_alert(alert: HealthAlert):
    return await receive_alert(alert)

# ... (Monitoring loops remain same, just removed the Serena Agent class calls)

async def monitor_docker_events():
    """Monitor Docker events for state changes (die, restart, oom)"""
    # ... (same logic as before, keeps calling receive_alert)
    await asyncio.sleep(5)
    loop = asyncio.get_event_loop()
    
    while True:
        try:
            if not docker_client:
                await asyncio.sleep(30)
                continue
                
            logger.info("👀 Starting Docker event monitoring...")
            
            # Run blocking generator in executor
            await loop.run_in_executor(None, _process_docker_events_blocking)
            
            logger.warning("Docker event stream ended, restarting...")
            await asyncio.sleep(5)
            
        except Exception as e:
            logger.error(f"Docker event monitoring error: {e}")
            await asyncio.sleep(10)

def _process_docker_events_blocking():
    """Blocking function to process docker events"""
    try:
        if not docker_client: return
        for event in docker_client.events(decode=True, filters={"type": "container", "event": ["die", "restart", "oom"]}):
            try:
                # ... event parsing ...
                actor = event.get('Actor', {})
                attributes = actor.get('Attributes', {})
                service_name = attributes.get('name', 'unknown')
                action = event.get('Action', 'unknown')
                
                logger.info(f"⚠️ Docker Event: {service_name} -> {action}")
                
                alert = HealthAlert(
                    alert_id=f"event-{service_name}-{action}-{datetime.utcnow().timestamp()}",
                    timestamp=datetime.utcnow(),
                    service_name=service_name,
                    status=f"state_change_{action}",
                    message=f"Container state change: {action}",
                    severity=AlertSeverity.CRITICAL if action == 'oom' else AlertSeverity.HIGH,
                    health_data={"event": event}
                )
                
                # Use requests to self (thread-safe simple way)
                try:
                    requests.post(
                        f"http://localhost:{SERENA_PORT}/alerts/receive", 
                        json=alert.model_dump(mode='json'),
                        timeout=5
                    )
                except Exception: pass

            except Exception as e:
                print(f"Error processing event: {e}")
    except Exception as e:
        print(f"Event stream error: {e}")

async def monitor_service_health():
    """Monitor Docker container health periodically"""
    await asyncio.sleep(5)
    loop = asyncio.get_event_loop()
    while True:
        try:
            if not docker_client:
                await asyncio.sleep(30)
                continue
            
            # ... (Logic identical to previous, just calling receive_alert for unhealthy)
            # Simplified for brevity in replace - assumes existing logic structure
            # Reusing existing logic but stripping agent dispatch:
            
            try:
                containers = await loop.run_in_executor(None, docker_client.containers.list)
                for container in containers:
                    try:
                        health_status = container.attrs.get('State', {}).get('Health', {})
                        if health_status:
                            status = health_status.get('Status')
                            if status in ['unhealthy']: # Only care about unhealthy for now
                                alert = HealthAlert(
                                    alert_id=f"{container.name}-{datetime.utcnow().timestamp()}",
                                    timestamp=datetime.utcnow(),
                                    service_name=container.name,
                                    status=status,
                                    message=f"Container health check: {status}",
                                    severity=AlertSeverity.HIGH,
                                    health_data={"state": container.status}
                                )
                                await receive_alert(alert)
                    except Exception: continue
            except Exception: pass
            
            await asyncio.sleep(30)
        except Exception as e:
            logger.debug(f"Health monitoring error: {e}")
            await asyncio.sleep(30)

async def redis_alert_listener():
    """Listen for alerts from Redis pub/sub (external triggers)"""
    loop = asyncio.get_event_loop()
    while True:
        try:
            if not redis_client:
                await asyncio.sleep(10)
                continue
            
            pubsub = redis_client.pubsub()
            pubsub.subscribe('arca:alerts:external') # Changed channel to avoid loop
            
            while True:
                message = await loop.run_in_executor(None, lambda: pubsub.get_message(timeout=1.0))
                if message and message['type'] == 'message':
                    try:
                        alert_data = json.loads(message['data'])
                        alert = HealthAlert(**alert_data)
                        if alert.alert_id not in active_alerts:
                            await receive_alert(alert)
                    except Exception: pass
                await asyncio.sleep(0.1)
            
        except Exception:
            await asyncio.sleep(10)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=SERENA_PORT, log_level="info")
