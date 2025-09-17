"""MCP client wrapper for AtlasAgents."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any, AsyncIterator
from dataclasses import dataclass
import threading
from queue import Queue
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource

from orchestrator.utils.logging import get_logger
from orchestrator.utils.exceptions import MCPConnectionError, MCPToolError
from orchestrator.utils.shutdown import register_cleanup


logger = get_logger(__name__)


@dataclass
class MCPServer:
    """Configuration for an MCP server."""
    name: str
    transport: str  # stdio or http
    cmd: Optional[List[str]] = None
    url: Optional[str] = None
    env: Dict[str, str] = None
    enabled: bool = True
    session: Optional[ClientSession] = None
    process: Optional[subprocess.Popen] = None


class MCPClient:
    """Manages connections to MCP servers."""

    def __init__(self):
        self.servers: Dict[str, MCPServer] = {}
        self.tools: Dict[str, Tool] = {}
        self.tool_to_server: Dict[str, str] = {}
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._shutdown_event = threading.Event()

        # Register cleanup on shutdown
        register_cleanup(self.shutdown, name="MCP Client Shutdown")

        logger.info("MCP client initialized")

    def configure_servers(self, servers: List[Dict[str, Any]]):
        """Configure MCP servers from config."""
        for server_config in servers:
            if not server_config.get('enabled', True):
                logger.info(f"Skipping disabled server: {server_config['name']}")
                continue

            server = MCPServer(
                name=server_config['name'],
                transport=server_config.get('type', 'stdio'),
                cmd=server_config.get('cmd'),
                url=server_config.get('url'),
                env=server_config.get('env', {}),
                enabled=server_config.get('enabled', True)
            )

            self.servers[server.name] = server
            logger.info(f"Configured MCP server: {server.name}")

    def start(self):
        """Start the MCP client and connect to all configured servers."""
        if self._running:
            logger.warning("MCP client already running")
            return

        self._running = True
        self._shutdown_event.clear()

        # Start async event loop in separate thread
        self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._thread.start()

        # Wait a bit for connections to establish
        time.sleep(2)

        logger.info("MCP client started")

    def _run_async_loop(self):
        """Run the async event loop in a separate thread."""
        asyncio.set_event_loop(asyncio.new_event_loop())
        self._loop = asyncio.get_event_loop()

        try:
            self._loop.run_until_complete(self._connect_all_servers())

            # Keep the loop running
            self._loop.run_until_complete(self._maintain_connections())
        except Exception as e:
            logger.error(f"Error in MCP async loop: {e}", exc_info=True)
        finally:
            self._loop.close()

    async def _connect_all_servers(self):
        """Connect to all configured MCP servers."""
        tasks = []
        for server_name, server in self.servers.items():
            if server.enabled:
                tasks.append(self._connect_server(server))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for server_name, result in zip(self.servers.keys(), results):
            if isinstance(result, Exception):
                logger.error(f"Failed to connect to {server_name}: {result}")

    async def _connect_server(self, server: MCPServer):
        """Connect to a single MCP server."""
        logger.info(f"Connecting to MCP server: {server.name}")

        try:
            if server.transport == 'stdio':
                await self._connect_stdio_server(server)
            elif server.transport == 'http':
                await self._connect_http_server(server)
            else:
                raise MCPConnectionError(server.name, f"Unknown transport: {server.transport}")

            # Discover available tools
            await self._discover_tools(server)

            logger.info(f"Connected to MCP server: {server.name}")

        except Exception as e:
            logger.error(f"Failed to connect to {server.name}: {e}")
            raise MCPConnectionError(server.name, str(e))

    async def _connect_stdio_server(self, server: MCPServer):
        """Connect to an stdio-based MCP server."""
        if not server.cmd:
            raise MCPConnectionError(server.name, "No command specified for stdio server")

        # Prepare server parameters
        server_params = StdioServerParameters(
            command=server.cmd[0],
            args=server.cmd[1:] if len(server.cmd) > 1 else [],
            env=server.env
        )

        # Create and initialize session
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                server.session = session

                # Initialize the connection
                await session.initialize()

                # Keep session alive by storing it
                # Note: In real implementation, we'd need to manage this better
                # For MVP, we'll reconnect as needed

    async def _connect_http_server(self, server: MCPServer):
        """Connect to an HTTP-based MCP server."""
        # HTTP support would go here
        # For MVP, we're focusing on stdio
        raise NotImplementedError("HTTP transport not yet implemented")

    async def _discover_tools(self, server: MCPServer):
        """Discover available tools from a server."""
        if not server.session:
            return

        try:
            # List available tools
            tools_response = await server.session.list_tools()

            for tool in tools_response.tools:
                # Store tool with server mapping
                tool_id = f"{server.name}.{tool.name}"
                self.tools[tool_id] = tool
                self.tool_to_server[tool_id] = server.name

                logger.debug(f"Discovered tool: {tool_id}")

            logger.info(f"Discovered {len(tools_response.tools)} tools from {server.name}")

        except Exception as e:
            logger.error(f"Failed to discover tools from {server.name}: {e}")

    async def _maintain_connections(self):
        """Maintain connections to MCP servers."""
        while not self._shutdown_event.is_set():
            await asyncio.sleep(1)

            # Health check for servers
            for server_name, server in self.servers.items():
                if server.enabled and not await self._is_server_healthy(server):
                    logger.warning(f"Server {server_name} is unhealthy, attempting reconnect")
                    try:
                        await self._connect_server(server)
                    except Exception as e:
                        logger.error(f"Failed to reconnect to {server_name}: {e}")

    async def _is_server_healthy(self, server: MCPServer) -> bool:
        """Check if a server connection is healthy."""
        if not server.session:
            return False

        try:
            # Try to list tools as a health check
            await asyncio.wait_for(server.session.list_tools(), timeout=5.0)
            return True
        except:
            return False

    def call_tool(self, tool_id: str, arguments: Dict[str, Any]) -> Any:
        """
        Call a tool synchronously.

        Args:
            tool_id: Tool identifier (e.g., "filesystem.read")
            arguments: Tool arguments

        Returns:
            Tool response
        """
        if not self._running:
            raise MCPToolError(tool_id, "MCP client not running")

        if tool_id not in self.tools:
            raise MCPToolError(tool_id, f"Unknown tool: {tool_id}")

        # Run async call in the event loop
        future = asyncio.run_coroutine_threadsafe(
            self._call_tool_async(tool_id, arguments),
            self._loop
        )

        try:
            result = future.result(timeout=30)  # 30 second timeout
            return result
        except asyncio.TimeoutError:
            raise MCPToolError(tool_id, "Tool call timed out")
        except Exception as e:
            raise MCPToolError(tool_id, str(e))

    async def _call_tool_async(self, tool_id: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool asynchronously."""
        server_name = self.tool_to_server.get(tool_id)
        if not server_name:
            raise MCPToolError(tool_id, "No server mapping found")

        server = self.servers.get(server_name)
        if not server or not server.session:
            # Try to reconnect
            await self._connect_server(server)
            if not server.session:
                raise MCPToolError(tool_id, f"Server {server_name} not connected")

        # Get the actual tool name (remove server prefix)
        actual_tool_name = tool_id.split('.', 1)[1]

        try:
            # Call the tool
            response = await server.session.call_tool(
                name=actual_tool_name,
                arguments=arguments
            )

            # Extract content from response
            if response.content:
                # Handle different content types
                result = []
                for content_item in response.content:
                    if isinstance(content_item, TextContent):
                        result.append({"type": "text", "text": content_item.text})
                    elif isinstance(content_item, ImageContent):
                        result.append({"type": "image", "data": content_item.data})
                    else:
                        result.append({"type": "unknown", "data": str(content_item)})

                return result[0] if len(result) == 1 else result

            return {"success": True}

        except Exception as e:
            logger.error(f"Tool call failed for {tool_id}: {e}")
            raise MCPToolError(tool_id, str(e))

    def list_tools(self) -> Dict[str, Tool]:
        """List all available tools."""
        return self.tools.copy()

    def get_tool(self, tool_id: str) -> Optional[Tool]:
        """Get a specific tool by ID."""
        return self.tools.get(tool_id)

    def shutdown(self):
        """Shutdown the MCP client and all connections."""
        logger.info("Shutting down MCP client")

        self._running = False
        self._shutdown_event.set()

        # Stop the async loop
        if self._loop and self._loop.is_running():
            # Schedule shutdown coroutine
            asyncio.run_coroutine_threadsafe(
                self._shutdown_async(),
                self._loop
            ).result(timeout=5)

        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

        logger.info("MCP client shutdown complete")

    async def _shutdown_async(self):
        """Async shutdown tasks."""
        for server_name, server in self.servers.items():
            if server.session:
                try:
                    await server.session.close()
                except Exception as e:
                    logger.error(f"Error closing session for {server_name}: {e}")

            if server.process:
                try:
                    server.process.terminate()
                    server.process.wait(timeout=5)
                except Exception as e:
                    logger.error(f"Error terminating process for {server_name}: {e}")


# Global MCP client instance
_mcp_client: Optional[MCPClient] = None


def get_mcp_client() -> MCPClient:
    """Get or create the global MCP client instance."""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client