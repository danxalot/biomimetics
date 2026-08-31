# -*- coding: utf-8 -*-
"""WhatsApp (Green API) router."""
from __future__ import annotations

import logging
import json
from fastapi import APIRouter, Request, Response, HTTPException

logger = logging.getLogger(__name__)

whatsapp_router = APIRouter(tags=["whatsapp"])

def _get_whatsapp_channel(request: Request):
    """Retrieve the WhatsAppChannel from app state, or None."""
    app = getattr(request, "app", None)
    if not app:
        return None
    cm = getattr(app.state, "channel_manager", None)
    if not cm:
        return None
    for ch in cm.channels:
        if ch.channel == "whatsapp":
            return ch
    return None

@whatsapp_router.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request) -> Response:
    """Green API webhook: receive incoming messages."""
    wa_ch = _get_whatsapp_channel(request)
    if not wa_ch:
        logger.error("WhatsApp channel not found in manager.")
        return Response(status_code=503)

    try:
        payload = await request.json()
        logger.debug(f"Received WhatsApp webhook: {json.dumps(payload)}")
        
        # Green API sends various webhook types. We only care about incoming messages.
        type_webhook = payload.get("typeWebhook")
        if type_webhook == "incomingMessageReceived":
            # Enqueue to channel manager for stateful processing
            if wa_ch._enqueue:
                wa_ch._enqueue(payload)
                return Response(status_code=200)
            else:
                logger.error("WhatsApp channel enqueue callback missing.")
                return Response(status_code=500)
        
        # Acknowledge other webhook types (device status, etc.) without processing
        return Response(status_code=200)

    except Exception as e:
        logger.exception(f"Error processing WhatsApp webhook: {e}")
        return Response(status_code=500)
