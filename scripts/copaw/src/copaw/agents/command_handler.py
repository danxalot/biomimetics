# -*- coding: utf-8 -*-
"""Agent command handler for system commands.

This module handles system commands like /compact, /new, /clear, etc.
"""
import logging
from typing import TYPE_CHECKING

from agentscope.agent._react_agent import _MemoryMark
from agentscope.message import Msg, TextBlock

from copaw.config import load_config

if TYPE_CHECKING:
    from reme.memory.file_based import ReMeInMemoryMemory

logger = logging.getLogger(__name__)


class ConversationCommandHandlerMixin:
    """Mixin for conversation (system) commands: /compact, /new, /clear, etc.

    Expects self to have: agent_name, memory, formatter, memory_manager,
    _enable_memory_manager.
    """

    # Supported conversation commands (unchanged set)
    SYSTEM_COMMANDS = frozenset(
        {
            "compact",
            "new",
            "clear",
            "history",
            "compact_str",
            "await_summary",
            "message",
        },
    )

    def is_conversation_command(self, query: str | None) -> bool:
        """Check if the query is a conversation system command.

        Args:
            query: User query string

        Returns:
            True if query is a system command
        """
        if not isinstance(query, str) or not query.startswith("/"):
            return False
        return query.strip().lstrip("/") in self.SYSTEM_COMMANDS


class CommandHandler(ConversationCommandHandlerMixin):
    """Handler for system commands (uses ConversationCommandHandlerMixin)."""

    def __init__(
        self,
        agent_name: str,
        memory: "ReMeInMemoryMemory",
    ):
        """Initialize command handler.

        Args:
            agent_name: Name of the agent for message creation
            memory: Agent's ReMeInMemoryMemory instance
        """
        self.agent_name = agent_name
        self.memory = memory

    def is_command(self, query: str | None) -> bool:
        """Check if the query is a system command (alias for mixin)."""
        return self.is_conversation_command(query)

    async def _make_system_msg(self, text: str) -> Msg:
        """Create a system response message.

        Args:
            text: Message text content

        Returns:
            System message
        """
        return Msg(
            name=self.agent_name,
            role="assistant",
            content=[TextBlock(type="text", text=text)],
        )

    def _has_memory_manager(self) -> bool:
        """Check if memory manager is available (Legacy)."""
        return False

    async def _process_compact(
        self,
        messages: list[Msg],
        _args: str = "",
    ) -> Msg:
        """Process /compact command."""
        return await self._make_system_msg(
            "**Feature Disabled**\n\n"
            "- Local memory compaction is deprecated in the new stateless architecture.\n"
            "- Explicit memories should be managed via the `memorize` tool."
        )

    async def _process_new(self, messages: list[Msg], _args: str = "") -> Msg:
        """Process /new command."""
        return await self._make_system_msg(
            "**Feature Disabled**\n\n"
            "- Local conversation summarization is deprecated.\n"
            "- Use the `memorize` tool to persist important context before starting fresh."
        )

    async def _process_clear(
        self,
        _messages: list[Msg],
        _args: str = "",
    ) -> Msg:
        """Process /clear command."""
        self.memory.clear_content()
        self.memory.clear_compressed_summary()
        return await self._make_system_msg(
            "**History Cleared!**\n\n"
            "- Compressed summary reset\n"
            "- Memory is now empty",
        )

    async def _process_compact_str(
        self,
        _messages: list[Msg],
        _args: str = "",
    ) -> Msg:
        """Process /compact_str command to show compressed summary."""
        summary = self.memory.get_compressed_summary()
        if not summary:
            return await self._make_system_msg(
                "**No Compressed Summary**\n\n"
                "- No summary has been generated yet\n"
                "- Use /compact or wait for auto-compaction",
            )
        return await self._make_system_msg(
            f"**Compressed Summary**\n\n{summary}",
        )

    async def _process_history(
        self,
        _messages: list[Msg],
        _args: str = "",
    ) -> Msg:
        """Process /history command."""
        config = load_config()
        max_input_length = config.agents.running.max_input_length
        history_str = await self.memory.get_history_str(
            max_input_length=max_input_length,
        )
        return await self._make_system_msg(history_str)

    async def _process_await_summary(
        self,
        _messages: list[Msg],
        _args: str = "",
    ) -> Msg:
        """Process /await_summary command."""
        return await self._make_system_msg(
            "**Feature Disabled**\n\n"
            "- Background summary tasks are no longer active in the stateless architecture."
        )

    async def _process_message(
        self,
        messages: list[Msg],
        args: str = "",
    ) -> Msg:
        """Process /message x command to show the nth message.

        Args:
            messages: List of messages in memory
            args: Command arguments (message index)

        Returns:
            System message with the requested message content
        """
        if not args:
            return await self._make_system_msg(
                "**Usage: /message <index>**\n\n"
                "- Example: /message 1 (show first message)\n"
                f"- Available messages: 1 to {len(messages)}",
            )

        try:
            index = int(args.strip())
        except ValueError:
            return await self._make_system_msg(
                f"**Invalid Index: '{args}'**\n\n"
                "- Index must be a number\n"
                "- Example: /message 1",
            )

        if not messages:
            return await self._make_system_msg(
                "**No Messages Available**\n\n- Current memory is empty",
            )

        if index < 1 or index > len(messages):
            return await self._make_system_msg(
                f"**Index Out of Range: {index}**\n\n"
                f"- Available range: 1 to {len(messages)}\n"
                f"- Example: /message 1",
            )

        msg = messages[index - 1]
        return await self._make_system_msg(
            f"**Message {index}/{len(messages)}**\n\n"
            f"- **Timestamp:** {msg.timestamp}\n"
            f"- **Name:** {msg.name}\n"
            f"- **Role:** {msg.role}\n"
            f"- **Content:**\n{msg.content}",
        )

    async def handle_conversation_command(self, query: str) -> Msg:
        """Process conversation system commands.

        Args:
            query: Command string (e.g., "/compact", "/new", "/message 5")

        Returns:
            System response message

        Raises:
            RuntimeError: If command is not recognized
        """
        messages = await self.memory.get_memory(
            exclude_mark=_MemoryMark.COMPRESSED,
            prepend_summary=False,
        )
        # Parse command and arguments
        parts = query.strip().lstrip("/").split(" ", maxsplit=1)
        command = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        logger.info(f"Processing command: {command}, args: {args}")

        handler = getattr(self, f"_process_{command}", None)
        if handler is None:
            raise RuntimeError(f"Unknown command: {query}")
        return await handler(messages, args)

    async def handle_command(self, query: str) -> Msg:
        """Process system commands (alias for handle_conversation_command)."""
        return await self.handle_conversation_command(query)
