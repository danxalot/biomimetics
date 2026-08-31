#!/usr/bin/env python3
"""
Policy Manager Service

This service enforces operational policies for agents in the ARCA system.
It validates actions against a set of defined rules to ensure system stability and safety.
"""

import os
import logging
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv
import aiohttp
import uuid
from datetime import datetime

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="ARCA Policy Manager", version="1.0.0")

class PolicyRequest(BaseModel):
    """Request model for policy validation"""
    action_type: str
    agent_id: str
    parameters: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None

class PolicyResponse(BaseModel):
    """Response model for policy validation"""
    allowed: bool
    violation: Optional[str] = None
    policy_id: Optional[str] = None

@app.post("/validate", response_model=PolicyResponse)
async def validate_action(request: PolicyRequest):
    """Validate an agent action against active policies"""
    logger.info(f"Validating action: {request.action_type} by {request.agent_id}")
    
    allowed = True
    violation = None
    policy_id = None

    # Hardcoded safety policies for initial implementation
    
    # Policy 1: Critical Resource Protection
    if request.action_type in ["delete_database", "drop_table", "system_shutdown"]:
        allowed = False
        violation = "Critical resource protection: Action prohibited by global safety policy"
        policy_id = "critical_resource_protection"
        
    # Policy 2: Rate Limiting (Placeholder)
    # In a real implementation, we would check Redis for rate limits
    
    # Audit Logging
    audit_url = os.getenv("AUDIT_LOGGER_URL", "http://agent_service:8088/audit/log")
    try:
        async with aiohttp.ClientSession() as session:
            audit_payload = {
                "timestamp": datetime.now().isoformat(),
                "service_name": "policy_manager",
                "event_type": "policy_validation",
                "details": {
                    "action_type": request.action_type,
                    "agent_id": request.agent_id,
                    "allowed": allowed,
                    "violation": violation,
                    "policy_id": policy_id
                },
                "severity": "INFO" if allowed else "WARN",
                "trace_id": str(uuid.uuid4())
            }
            async with session.post(audit_url, json=audit_payload) as response:
                if response.status != 200:
                    logger.warning(f"Failed to send log to audit logger: {response.status}")
    except Exception as e:
            logger.warning(f"Failed to connect to audit logger: {e}")

    return PolicyResponse(allowed=allowed, violation=violation, policy_id=policy_id)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "policy_manager"}

if __name__ == "__main__":
    port = int(os.getenv("POLICY_MANAGER_PORT", "8003"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
