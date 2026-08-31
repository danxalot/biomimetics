# -*- coding: utf-8 -*-
"""Approval tools for HITL resolution in CoPaw agent."""
import logging
from typing import Any
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock
from ...app.approvals import get_approval_service
from ...security.tool_guard.approval import ApprovalDecision

logger = logging.getLogger(__name__)

def create_approvals_tools(session_id: str):
    """Factory to create session-aware approval tools."""

    async def get_pending_approvals() -> ToolResponse:
        """
        Check for any outstanding tool execution requests requiring your approval for the current session.
        If a tool is blocked by a guard, use this to find the request_id.

        Returns:
            ToolResponse: List of pending requests with request_id and tool_name.
        """
        svc = get_approval_service()
        pending = await svc.get_pending_by_session(session_id)
        
        if not pending:
            return ToolResponse(
                content=[TextBlock(type="text", text="No pending approvals found for this session.")]
            )
            
        summary = (
            f"PENDING APPROVAL:\n"
            f"- Request ID: {pending.request_id}\n"
            f"- Tool: {pending.tool_name}\n"
            f"- Context: {pending.result_summary}\n"
            f"You can approve or deny this using 'approve_request' with the request_id."
        )
        return ToolResponse(content=[TextBlock(type="text", text=summary)])

    async def approve_request(request_id: str, decision: str, passphrase: str = None) -> ToolResponse:
        """
        Approve or deny a pending tool execution request (HITL).
        REQUIRED: You must have verbal or written authorization from the user before calling this.
        REQUIRIED: You must provide the correct passphrase for programmatic resolution.

        Args:
            request_id (str): The unique ID of the request to resolve.
            decision (str): Use 'approved' to grant permission or 'denied' to block execution.
            passphrase (str, optional): The security passphrase for JIT authorization.

        Returns:
            ToolResponse: Confirmation of the decision.
        """
        try:
            # 1. JIT Passphrase Validation
            # Fetches validation key from Azure Key Vault via Credentials Server
            from copaw_secret_fetcher import get_secret
            valid_passphrase = get_secret("approvals-passphrase")
            
            if not valid_passphrase:
                return ToolResponse(content=[TextBlock(type="text", text="Error: Security vault unreachable or passphrase unset.")])
                
            if passphrase != valid_passphrase:
                logger.warning(f"Security: Failed programmatic approval attempt for request {request_id}")
                return ToolResponse(content=[TextBlock(type="text", text="Error: Invalid security passphrase. Access denied.")])

            # 2. Resolve Resolution
            target_decision = ApprovalDecision.APPROVED if decision.lower() == "approved" else ApprovalDecision.DENIED
            svc = get_approval_service()
            result = await svc.resolve_request(request_id, target_decision)
            
            if not result:
                return ToolResponse(
                    content=[TextBlock(type="text", text=f"Error: Request ID {request_id} not found or expired.")]
                )
                
            return ToolResponse(
                content=[TextBlock(type="text", text=f"Request {request_id} has been {decision}.")]
            )
        except Exception as e:
            logger.error(f"Approval tool error: {e}")
            return ToolResponse(content=[TextBlock(type="text", text=f"Error resolving request: {str(e)}")])

    return get_pending_approvals, approve_request
