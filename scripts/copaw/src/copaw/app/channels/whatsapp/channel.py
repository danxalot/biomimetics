# -*- coding: utf-8 -*-
"""WhatsApp Channel using Green API."""
from __future__ import annotations

import logging
import httpx
import os
import asyncio
from typing import Any, Dict, Optional, List

from ..base import BaseChannel, OnReplySent, ProcessHandler
from ....config.config import WhatsAppConfig

logger = logging.getLogger(__name__)

class WhatsAppChannel(BaseChannel):
    """WhatsApp Channel: State-full interaction via Green API."""

    channel = "whatsapp"

    def __init__(
        self,
        process: ProcessHandler,
        instance_id: str,
        api_token: str,
        enabled: bool = True,
        on_reply_sent: OnReplySent = None,
        show_tool_details: bool = True,
        filter_tool_messages: bool = False,
        filter_thinking: bool = False,
    ):
        super().__init__(
            process,
            on_reply_sent=on_reply_sent,
            show_tool_details=show_tool_details,
            filter_tool_messages=filter_tool_messages,
            filter_thinking=filter_thinking,
        )
        self.instance_id = instance_id
        self.api_token = api_token
        self.enabled = enabled
        self.base_url = f"https://api.green-api.com/waInstance{instance_id}"

    @classmethod
    def from_config(
        cls,
        process: ProcessHandler,
        config: WhatsAppConfig,
        on_reply_sent: OnReplySent = None,
        show_tool_details: bool = True,
        filter_tool_messages: bool = False,
        filter_thinking: bool = False,
    ) -> "WhatsAppChannel":
        return cls(
            process=process,
            instance_id=config.instance_id,
            api_token=config.api_token,
            enabled=config.enabled,
            on_reply_sent=on_reply_sent,
            show_tool_details=show_tool_details,
            filter_tool_messages=filter_tool_messages,
            filter_thinking=filter_thinking,
        )

    def build_agent_request_from_native(self, native_payload: Any) -> Any:
        """Map WhatsApp chatId to CoPaw session_id."""
        # Expected native_payload is the webhook JSON from Green API
        # Or a simplified version from the webhook router
        chat_id = native_payload.get("chatId") or native_payload.get("senderData", {}).get("chatId")
        text = native_payload.get("textMessage") or native_payload.get("messageData", {}).get("textMessageData", {}).get("text", "")
        
        # Resolve persistent session
        session_id = self.resolve_session_id(chat_id)
        
        # Build standard content parts
        from agentscope_runtime.engine.schemas.agent_schemas import TextContent, ContentType
        content_parts = [TextContent(type=ContentType.TEXT, text=text)]
        
        request = self.build_agent_request_from_user_content(
            channel_id=self.channel,
            sender_id=chat_id,
            session_id=session_id,
            content_parts=content_parts
        )
        return request

    async def send(
        self,
        to_handle: str,
        text: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send message via Green API."""
        if not self.enabled or not text:
            return

        url = f"{self.base_url}/sendMessage/{self.api_token}"
        payload = {
            "chatId": to_handle,
            "message": text
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=10.0)
                resp.raise_for_status()
                logger.info(f"WhatsApp sent to {to_handle}")
        except Exception as e:
            logger.error(f"Failed to send WhatsApp: {e}")

    async def start(self) -> None:
        """Startup routine: Register and catch up on missed messages."""
        logger.info("WhatsApp channel (Green API) started.")
        if self.enabled:
            # Run catch-up in background to not block startup
            asyncio.create_task(self.sync_missed_messages())

    async def sync_missed_messages(self, minutes_back: int = 60) -> None:
        """Query Green API Journal for messages missed during downtime."""
        try:
            # 1. Fetch last 100 messages from the journal
            # Note: minutes_back filter is conceptual; Green API returns latest N messages.
            url = f"{self.base_url}/lastIncomingMessages/{self.api_token}?minutes={minutes_back}"
            
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=10.0)
                if resp.status_code != 200:
                    logger.warning(f"Failed to fetch WhatsApp journal: {resp.status_code}")
                    return

                messages = resp.json()
                if not messages:
                    return

                logger.info(f"Retrieved {len(messages)} messages from WhatsApp journal. Processing missed turns...")
                
                # 2. Process each message (BaseChannel.resolve_session_id handles dedup if logic added,
                # but for simplicity we rely on the fact that if it was already processed, 
                # the session state would have it. For now, we process all latest.)
                for msg in reversed(messages):
                    # Standardize format for build_agent_request_from_native
                    # Journal format slightly different from webhook
                    if msg.get("type") == "incomingMessage":
                        payload = {
                            "chatId": msg.get("chatId"),
                            "textMessage": msg.get("textMessage"),
                            "timestamp": msg.get("timestamp"),
                            "metadata": {"source": "startup_sync"}
                        }
                        if self._enqueue:
                            self._enqueue(payload)
                            
            logger.info("✅ WhatsApp startup sync complete.")
        except Exception as e:
            logger.error(f"Error during WhatsApp startup sync: {e}")

    async def stop(self) -> None:
        logger.info("WhatsApp channel stopped.")
