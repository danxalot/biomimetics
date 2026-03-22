#!/usr/bin/env python3
"""
WhatsApp Bridge - FastAPI receiver for Meta Cloud API webhooks
Receives WhatsApp messages and forwards to CoPaw Webhook Receiver

Tri-Factor Architecture Integration:
- WhatsApp messages → Bridge (port 8001) → CoPaw Receiver (port 8000) → Brain/Execution routing

Documentation: https://developers.facebook.com/docs/whatsapp/cloud-api
"""

import os
import json
import logging
import httpx
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Configuration
PORT = int(os.environ.get("PORT", "8001"))
COPAW_WEBHOOK_URL = os.environ.get(
    "COPAW_WEBHOOK_URL",
    "http://127.0.0.1:8000/webhook"
)
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("whatsapp_bridge")

# FastAPI app
app = FastAPI(
    title="WhatsApp Bridge",
    description="Meta Cloud API webhook receiver for CoPaw Tri-Factor system",
    version="1.0.0"
)

# Request log
request_log = []


class WhatsAppMessage(BaseModel):
    """WhatsApp message structure from Meta Cloud API"""
    from_: str  # Sender ID (phone number)
    id: str  # Message ID
    timestamp: str  # Unix timestamp
    type: str = "text"  # Message type (text, image, etc.)
    text: Optional[Dict[str, str]] = None  # Text content
    image: Optional[Dict[str, str]] = None  # Image content
    audio: Optional[Dict[str, str]] = None  # Audio content


class WhatsAppWebhookPayload(BaseModel):
    """WhatsApp webhook payload structure"""
    object: str = "whatsapp_business_account"
    entry: list  # Array of entry objects


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "whatsapp_bridge",
        "port": PORT,
        "copaw_webhook": COPAW_WEBHOOK_URL
    }


@app.get("/logs")
async def get_logs(limit: int = 50):
    """Return recent request logs"""
    return {
        "logs": request_log[-limit:],
        "total": len(request_log)
    }


@app.get("/webhook")
async def verify_webhook(
    mode: str = "",
    verify_token: str = "",
    challenge: str = ""
):
    """
    WhatsApp webhook verification (GET)
    
    Meta sends a GET request to verify the webhook URL during setup.
    Must return the challenge string if verification token matches.
    
    Docs: https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/set-up-developer-assets#verify-your-webhook
    """
    if mode == "subscribe" and verify_token == WHATSAPP_VERIFY_TOKEN:
        logger.info("✅ WhatsApp webhook verified")
        return challenge
    else:
        logger.warning("❌ WhatsApp webhook verification failed")
        raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/whatsapp-webhook")
async def handle_whatsapp_webhook(request: Request, x_hub_signature: Optional[str] = Header(None)):
    """
    Handle WhatsApp messages from Meta Cloud API (POST)
    
    Expected payload structure:
    {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "BUSINESS_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "PHONE_NUMBER",
                        "phone_number_id": "PHONE_NUMBER_ID"
                    },
                    "messages": [{
                        "from": "SENDER_ID",
                        "id": "MESSAGE_ID",
                        "timestamp": "TIMESTAMP",
                        "type": "text",
                        "text": {
                            "body": "Message text"
                        }
                    }]
                },
                "field": "messages"
            }]
        }]
    }
    
    Docs: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components
    """
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Invalid JSON payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Validate payload structure
    if payload.get("object") != "whatsapp_business_account":
        logger.warning(f"Invalid object type: {payload.get('object')}")
        raise HTTPException(status_code=400, detail="Invalid payload object")

    # Process each entry
    for entry in payload.get("entry", []):
        changes = entry.get("changes", [])
        
        for change in changes:
            value = change.get("value", {})
            messages = value.get("messages", [])
            
            for message in messages:
                # Extract message data
                from_id = message.get("from", "unknown")
                message_id = message.get("id", "unknown")
                timestamp = message.get("timestamp", "")
                message_type = message.get("type", "text")
                
                # Extract message body based on type
                body = ""
                if message_type == "text":
                    body = message.get("text", {}).get("body", "")
                elif message_type == "image":
                    body = f"[Image: {message.get('image', {}).get('caption', '')}]"
                elif message_type == "audio":
                    body = "[Audio message]"
                
                # Forward to CoPaw Webhook Receiver
                copaw_payload = {
                    "type": "whatsapp_message",
                    "from": from_id,
                    "message_id": message_id,
                    "timestamp": timestamp,
                    "message_type": message_type,
                    "body": body,
                    "metadata": {
                        "source": "whatsapp",
                        "received_at": datetime.now().isoformat(),
                        "phone_number_id": value.get("metadata", {}).get("phone_number_id", ""),
                        "display_phone_number": value.get("metadata", {}).get("display_phone_number", "")
                    }
                }
                
                # Forward to CoPaw receiver
                try:
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            COPAW_WEBHOOK_URL,
                            json=copaw_payload,
                            timeout=30.0
                        )
                        copaw_result = response.json()
                except Exception as e:
                    logger.error(f"Failed to forward to CoPaw: {e}")
                    copaw_result = {"error": str(e), "status": "forward_error"}
                
                # Log the request
                log_entry = {
                    "type": "whatsapp",
                    "time": datetime.now().isoformat(),
                    "from": from_id,
                    "message_id": message_id,
                    "body": body[:100] + "..." if len(body) > 100 else body,
                    "copaw_result": copaw_result
                }
                request_log.append(log_entry)
                logger.info(f"📱 WhatsApp message from {from_id}: {body[:50]}...")

    # Return success to Meta (must return 200 OK)
    return JSONResponse(content={"status": "received"})


@app.post("/whatsapp/send")
async def send_whatsapp_message(
    to: str,
    message: str,
    sender_phone_id: Optional[str] = None
):
    """
    Send a WhatsApp message (outbound)
    
    This endpoint would integrate with Meta Cloud API to send messages.
    Currently a placeholder for future implementation.
    
    Docs: https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages
    """
    # Placeholder - would need Meta API credentials
    return {
        "status": "not_implemented",
        "message": "Outbound messaging requires Meta API credentials"
    }


@app.on_event("startup")
async def startup_event():
    """Log startup information"""
    logger.info(f"🚀 WhatsApp Bridge starting on port {PORT}")
    logger.info(f"📡 CoPaw Webhook: {COPAW_WEBHOOK_URL}")
    logger.info(f"🔐 Verify Token: {'Set' if WHATSAPP_VERIFY_TOKEN else 'Not configured'}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "whatsapp_bridge:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level="info"
    )
