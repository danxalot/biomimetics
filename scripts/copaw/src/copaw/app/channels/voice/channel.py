# -*- coding: utf-8 -*-
"""Voice Channel: Vultr Gemini 3.1 Live WebSocket Relay."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from ..base import BaseChannel, OnReplySent, ProcessHandler
from .vultr_relay_client import VultrRelayClient

logger = logging.getLogger(__name__)


class VoiceChannel(BaseChannel):
    """CoPaw Voice channel backed by Vultr Gemini 3.1 Live Relay.

    Uses a direct WebSocket connection to the Vultr VPS to bridge
    local audio I/O to the Gemini Live API.
    """

    channel = "voice"
    uses_manager_queue = False

    def __init__(
        self,
        process: ProcessHandler,
        on_reply_sent: OnReplySent = None,
        show_tool_details: bool = True,
        filter_tool_messages: bool = False,
        filter_thinking: bool = False,
    ) -> None:
        super().__init__(
            process,
            on_reply_sent,
            show_tool_details,
            filter_tool_messages=filter_tool_messages,
            filter_thinking=filter_thinking,
        )
        self.client: Optional[VultrRelayClient] = None
        self._config: Any = None
        self._enabled = False
        self._relay_task: Optional[asyncio.Task] = None

    @classmethod
    def from_config(
        cls,
        process: ProcessHandler,
        config: Any,
        on_reply_sent: OnReplySent = None,
        show_tool_details: bool = True,
        filter_tool_messages: bool = False,
        filter_thinking: bool = False,
    ) -> "VoiceChannel":
        instance = cls(
            process,
            on_reply_sent,
            show_tool_details,
            filter_tool_messages=filter_tool_messages,
            filter_thinking=filter_thinking,
        )
        instance._config = config
        instance._enabled = getattr(config, "enabled", False)
        return instance

    async def start(self) -> None:
        """Start the voice channel: connect to Vultr relay."""
        if not self._enabled:
            logger.info("Voice channel disabled, skipping start")
            return

        relay_url = getattr(self._config, "relay_url", "ws://100.X.X.X:8765/ws/live")
        self.client = VultrRelayClient(relay_url)
        
        logger.info(f"Starting Vultr Relay Client: {relay_url}")
        print("\n[🎤 MIC ACTIVE - Speak now...]\n")
        self._relay_task = asyncio.create_task(
            self.client.run(on_transcript_cb=self._handle_transcript)
        )

    async def stop(self) -> None:
        """Stop the voice channel: close relay connection."""
        if self.client:
            await self.client.close()
        
        if self._relay_task and not self._relay_task.done():
            self._relay_task.cancel()
            try:
                await self._relay_task
            except asyncio.CancelledError:
                pass

        logger.info("Voice channel stopped")

    def _handle_transcript(self, text: str) -> None:
        """Handle transcript received from relay."""
        # Wrap in AgentRequest and feed to process for memory/logging
        # Note: We don't await the process iterator here since it's a synchronous callback
        # from the receive_loop, and the relay/Gemini already handles the response.
        # This is primarily for local transcript logging/memory.
        asyncio.create_task(self._push_to_engine(text))

    async def _push_to_engine(self, text: str | dict) -> None:
        """Log transcript to session memory (Silence engine reasoning)."""
        # Ensure text is a string before slicing for the logger
        if isinstance(text, dict):
            text = text.get("text", str(text))
        
        payload = {"transcript": text, "session_id": "vultr_voice_session"}
        # We build the request for logging/history consistency, but do NOT 
        # push to the processing engine to avoid redundant reasoning loops.
        # Gemini Live is already handling the active reasoning.
        _request = self.build_agent_request_from_native(payload)
        logger.info(f"Voice Transcript Logged: {text[:50]}...")

    async def send(
        self,
        to_handle: str,
        text: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send text to the active voice session (proactive)."""
        # Proactive sends (e.g. from other channels) could be sent to the relay
        # if the relay supports a text-to-speech injection.
        # For now, we log it.
        logger.info(f"Proactive voice send requested: {text}")

    def build_agent_request_from_native(
        self,
        native_payload: Any,
    ) -> Any:
        """Convert a voice payload dict to AgentRequest."""
        from agentscope_runtime.engine.schemas.agent_schemas import (
            AgentRequest,
            Message,
            MessageType,
            Role,
            TextContent,
            ContentType,
        )

        raw_transcript = native_payload.get("transcript", "")
        if isinstance(raw_transcript, dict):
            text = raw_transcript.get("text", "")
        else:
            text = str(raw_transcript)
        session_id = native_payload.get("session_id", "vultr_voice_session")
        user_id = "terminal_user"

        msg = Message(
            type=MessageType.MESSAGE,
            role=Role.USER,
            content=[TextContent(type=ContentType.TEXT, text=text)],
        )
        return AgentRequest(
            session_id=session_id,
            user_id=user_id,
            input=[msg],
            channel=self.channel,
        )

    @property
    def config(self) -> Any:
        """Public accessor for the channel configuration."""
        return self._config

    @property
    def process(self) -> ProcessHandler:
        """Public accessor for the process handler."""
        return self._process
