# -*- coding: utf-8 -*-
"""MCP client manager for hot-reloadable client lifecycle management.

This module provides centralized management of MCP clients with support
for runtime updates without restarting the application.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, TYPE_CHECKING

from agentscope.mcp import HttpStatefulClient, StdIOStatefulClient

if TYPE_CHECKING:
    from ...config.config import MCPClientConfig, MCPConfig

logger = logging.getLogger(__name__)


class MCPClientManager:
    """Manages MCP clients with hot-reload support.

    This manager handles the lifecycle of MCP clients, including:
    - Initial loading from config
    - Runtime replacement when config changes
    - Cleanup on shutdown

    Design pattern mirrors ChannelManager for consistency.
    """

    def __init__(self) -> None:
        """Initialize an empty MCP client manager."""
        self._clients: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def init_from_config(self, config: "MCPConfig") -> None:
        """Initialize clients from configuration in parallel (Degraded Mode).

        Args:
            config: MCP configuration containing client definitions
        """
        logger.info("Initializing MCP clients from config (Parallel Mode)")
        
        tasks = []
        client_keys = []
        
        for key, client_config in config.clients.items():
            if not client_config.enabled:
                logger.debug(f"MCP client '{key}' is disabled, skipping")
                continue
            
            # Use 90s timeout as requested for Degraded Mode
            coro = self._add_client(key, client_config, timeout=90.0)
            tasks.append(coro)
            client_keys.append(key)

        if not tasks:
            return

        # Initialize all clients in parallel; return_exceptions=True ensures
        # we don't crash if one fails.
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for key, result in zip(client_keys, results):
            if isinstance(result, Exception):
                logger.error(
                    f"CRITICAL: Failed to initialize MCP client '{key}' (Degraded Mode Active): {result}",
                    exc_info=result if not isinstance(result, asyncio.TimeoutError) else False
                )
            else:
                logger.info(f"MCP client '{key}' initialized successfully.")


    async def get_clients(self) -> List[Any]:
        """Get list of all active MCP clients.

        This method is called by the runner on each query to get
        the latest set of clients.

        Returns:
            List of connected MCP client instances
        """
        async with self._lock:
            return [
                client
                for client in self._clients.values()
                if client is not None
            ]

    async def replace_client(
        self,
        key: str,
        client_config: "MCPClientConfig",
        timeout: float = 60.0,
    ) -> None:
        """Replace or add a client with new configuration.

        Flow: connect new (outside lock) → swap + close old (inside lock).
        This ensures minimal lock holding time.

        Args:
            key: Client identifier (from config)
            client_config: New client configuration
            timeout: Connection timeout in seconds (default 60s)
        """
        # 1. Create and connect new client outside lock (may be slow)
        logger.debug(f"Connecting new MCP client: {key}")
        new_client = self._build_client(client_config)

        try:
            # Add timeout to prevent indefinite blocking
            await asyncio.wait_for(new_client.connect(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                f"Timeout connecting MCP client '{key}' after {timeout}s",
            )
            try:
                await new_client.close()
            except Exception:
                pass
            raise
        except Exception as e:
            logger.warning(f"Failed to connect MCP client '{key}': {e}")
            try:
                await new_client.close()
            except Exception:
                pass
            raise

        # 2. Swap and close old client inside lock
        async with self._lock:
            old_client = self._clients.get(key)
            self._clients[key] = new_client

            if old_client is not None:
                logger.debug(f"Closing old MCP client: {key}")
                try:
                    # Give the subprocess 2 seconds to gracefully close before moving on
                    await asyncio.wait_for(old_client.close(), timeout=2.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    logger.warning(f"Forced shutdown of old MCP client: {key}")
                except Exception as e:
                    logger.warning(
                        f"Error closing old MCP client '{key}': {e}",
                    )
            else:
                logger.debug(f"Added new MCP client: {key}")

    async def remove_client(self, key: str) -> None:
        """Remove and close a client.

        Args:
            key: Client identifier to remove
        """
        async with self._lock:
            old_client = self._clients.pop(key, None)

        if old_client is not None:
            logger.debug(f"Removing MCP client: {key}")
            try:
                # Give the subprocess 2 seconds to gracefully close before moving on
                await asyncio.wait_for(old_client.close(), timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                logger.warning(f"Forced shutdown of MCP client: {key}")
            except Exception as e:
                logger.warning(f"Error closing MCP client '{key}': {e}")

    async def close_all(self) -> None:
        """Close all MCP clients.

        Called during application shutdown.
        """
        async with self._lock:
            clients_snapshot = list(self._clients.items())
            self._clients.clear()

        logger.debug("Closing all MCP clients")
        for key, client in clients_snapshot:
            if client is not None:
                try:
                    # Shield prevents FastAPI's cancellation from bleeding into the AnyIO scope
                    await asyncio.wait_for(asyncio.shield(client.close()), timeout=2.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    logger.warning(f"Forced shutdown of MCP client: {key}")
                except Exception as e:
                    logger.warning(f"Error closing MCP client '{key}': {e}")

    async def _add_client(
        self,
        key: str,
        client_config: "MCPClientConfig",
        timeout: float = 60.0,
    ) -> None:
        """Add a new client (used during initial setup).

        Args:
            key: Client identifier
            client_config: Client configuration
            timeout: Connection timeout in seconds (default 60s)
        """
        client = self._build_client(client_config)

        # Add timeout to prevent indefinite blocking
        await asyncio.wait_for(client.connect(), timeout=timeout)

        async with self._lock:
            self._clients[key] = client

    @staticmethod
    def _build_client(client_config: "MCPClientConfig") -> Any:
        """Build MCP client instance by configured transport."""
        rebuild_info = {
            "name": client_config.name,
            "transport": client_config.transport,
            "url": client_config.url,
            "headers": client_config.headers or None,
            "command": client_config.command,
            "args": list(client_config.args),
            "env": dict(client_config.env),
            "cwd": client_config.cwd or None,
        }

        if client_config.transport == "stdio":
            client = StdIOStatefulClient(
                name=client_config.name,
                command=client_config.command,
                args=client_config.args,
                env=client_config.env,
                cwd=client_config.cwd or None,
            )
            setattr(client, "_copaw_rebuild_info", rebuild_info)
            return client

        client = HttpStatefulClient(
            name=client_config.name,
            transport=client_config.transport,
            url=client_config.url,
            headers=client_config.headers or None,
        )
        setattr(client, "_copaw_rebuild_info", rebuild_info)
        return client
