# -*- coding: utf-8 -*-
"""API routes for programmatic tool-guard approval resolution."""

import logging
from typing import Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from ..approvals.service import get_approval_service
from ...security.tool_guard.approval import ApprovalDecision

router = APIRouter(prefix="/approvals", tags=["approvals"])
logger = logging.getLogger(__name__)

class ApprovalResolveRequest(BaseModel):
    """Request body for resolving a pending approval."""
    request_id: str = Field(..., description="The unique ID of the approval request")
    decision: str = Field(..., description="The decision: 'approved' or 'denied'")
    reason: Optional[str] = Field(None, description="Optional reason for the decision")

@router.post("/resolve")
async def resolve_approval(payload: ApprovalResolveRequest = Body(...)):
    """
    Resolve a pending tool-guard request.
    Allows agents to perform HITL approval based on verbal authorization.
    """
    svc = get_approval_service()
    
    # Map string decision to enum
    try:
        decision_enum = ApprovalDecision(payload.decision.lower())
    except ValueError:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid decision '{payload.decision}'. Must be 'approved' or 'denied'."
        )

    logger.info(f"Programmatic resolution for request {payload.request_id}: {decision_enum.value}")
    
    pending = await svc.resolve_request(payload.request_id, decision_enum)
    if not pending:
        raise HTTPException(
            status_code=404, 
            detail=f"Approval request '{payload.request_id}' not found or already resolved"
        )

    return {
        "status": "success",
        "request_id": payload.request_id,
        "decision": decision_enum.value,
        "tool_name": pending.tool_name
    }

@router.get("/pending/{session_id}")
async def get_pending_approval(session_id: str):
    """Retrieve the most recent pending approval for a session."""
    svc = get_approval_service()
    pending = await svc.get_pending_by_session(session_id)
    if not pending:
        return {"status": "none"}
    
    return {
        "status": "pending",
        "request_id": pending.request_id,
        "tool_name": pending.tool_name,
        "summary": pending.result_summary
    }
