"""MCP connection manager for orchestrating multiple MCP servers."""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml
import json

from orchestrator.mcp.client import MCPClient, MCPServer, get_mcp_client
from orchestrator.mcp.registry import ToolRegistry, ToolMetadata, ToolCategory, ToolOperation
from orchestrator.core.config import MCPConfig, AtlasConfig
from orchestrator.utils.paths import PathManager
from orchestrator.utils.logging import get_logger
from orchestrator.utils.exceptions import MCPConnectionError, ConfigurationError
from orchestrator.utils.shutdown import register_cleanup


logger = get_logger(__name__)


class MCPManager:
    """Manages MCP server connections and tool execution."""

    def __init__(self, config: AtlasConfig, path_manager: PathManager):
        self.config = config
        self.path_manager = path_manager
        self.client = get_mcp_client()
        self.registry = ToolRegistry()
        self._started = False

        # Register cleanup
        register_cleanup(self.stop, name="MCP Manager Shutdown")

        logger.info("MCP Manager initialized")

    def load_mcp_config(self, project_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load MCP configuration for a project."""
        # Load base MCP config
        mcp_config = self.config.mcp_config

        servers = []
        for transport in mcp_config.transports:
            server_config = transport.dict()

            # Update paths if project is specified
            if project_name:
                server_config = self._update_server_paths(server_config, project_name)

            servers.append(server_config)

        return servers

    def _update_server_paths(self, server_config: Dict, project_name: str) -> Dict:
        """Update server configuration with project-specific paths."""
        project_dir = self.path_manager.get_project_dir(project_name)

        # Update environment variables based on server type
        if server_config['name'] == 'filesystem':
            server_config['env'] = server_config.get('env', {})
            server_config['env']['ROOT'] = str(project_dir)
            logger.debug(f"Updated filesystem ROOT to: {project_dir}")

        elif server_config['name'] == 'git':
            server_config['env'] = server_config.get('env', {})
            server_config['env']['REPO_PATH'] = str(project_dir)
            logger.debug(f"Updated git REPO_PATH to: {project_dir}")

        elif server_config['name'] == 'sqlite':
            server_config['env'] = server_config.get('env', {})
            db_path = project_dir / ".internal" / "atlas.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            server_config['env']['SQLITE_PATH'] = str(db_path)
            logger.debug(f"Updated sqlite SQLITE_PATH to: {db_path}")

        return server_config

    def start(self, project_name: Optional[str] = None):
        """Start MCP servers for a project."""
        if self._started:
            logger.warning("MCP Manager already started")
            return

        try:
            # Load configuration
            servers = self.load_mcp_config(project_name)

            # Configure MCP client with servers
            self.client.configure_servers(servers)

            # Start the client (connects to all servers)
            self.client.start()

            # Discover and register tools
            self._discover_and_register_tools()

            self._started = True
            logger.info(f"Started MCP Manager with {len(servers)} servers")

        except Exception as e:
            logger.error(f"Failed to start MCP Manager: {e}")
            raise MCPConnectionError("manager", str(e))

    def stop(self):
        """Stop all MCP servers."""
        if not self._started:
            return

        logger.info("Stopping MCP Manager")

        try:
            self.client.shutdown()
            self._started = False
            logger.info("MCP Manager stopped")

        except Exception as e:
            logger.error(f"Error stopping MCP Manager: {e}")

    def _discover_and_register_tools(self):
        """Discover tools from MCP servers and register them."""
        # Clear existing registry
        self.registry.clear()

        # Get tools from client
        tools = self.client.list_tools()

        # Register each tool
        for tool_id, tool in tools.items():
            server = self.client.tool_to_server.get(tool_id, "unknown")

            # Create tool info dict
            tool_info = {
                "name": tool.name if hasattr(tool, 'name') else tool_id,
                "description": tool.description if hasattr(tool, 'description') else None,
                "input_schema": tool.inputSchema if hasattr(tool, 'inputSchema') else {}
            }

            # Register with the registry
            self.registry.register_tool(tool_id, server, tool_info)

        logger.info(f"Registered {len(tools)} tools in registry")

        # Log statistics
        stats = self.registry.get_statistics()
        logger.info(f"Tool statistics: {stats}")

    def restart_for_project(self, project_name: str):
        """Restart MCP servers with new project context."""
        logger.info(f"Restarting MCP Manager for project: {project_name}")

        # Stop existing connections
        if self._started:
            self.stop()

        # Start with new project
        self.start(project_name)

    def list_tools(self) -> Dict[str, Any]:
        """List all available tools from all servers."""
        if not self._started:
            return {}

        # Use registry to get detailed tool information
        formatted_tools = {}
        for tool_id, metadata in self.registry.tools.items():
            formatted_tools[tool_id] = {
                "name": metadata.name,
                "description": metadata.description,
                "category": metadata.category.value,
                "operation": metadata.operation.value,
                "requires_approval": metadata.requires_approval,
                "server": metadata.server
            }

        return formatted_tools

    def get_tool_metadata(self, tool_id: str) -> Optional[ToolMetadata]:
        """Get metadata for a specific tool."""
        return self.registry.get_tool(tool_id)

    def get_tools_for_agent(self, agent_role: str) -> List[ToolMetadata]:
        """Get tools allowed for a specific agent role based on trust policy."""
        # This will be implemented in the permission system
        # For now, return all tools
        return list(self.registry.tools.values())

    def call_tool(self, tool_id: str, arguments: Dict[str, Any]) -> Any:
        """
        Execute a tool through MCP.

        Args:
            tool_id: Tool identifier (e.g., "filesystem.read")
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        if not self._started:
            raise MCPConnectionError("manager", "MCP Manager not started")

        logger.info(f"Executing tool: {tool_id}", tool_id=tool_id, arguments=arguments)

        try:
            result = self.client.call_tool(tool_id, arguments)
            logger.info(f"Tool execution successful: {tool_id}")
            return result

        except Exception as e:
            logger.error(f"Tool execution failed: {tool_id}", error=str(e))
            raise

    def get_server_status(self) -> Dict[str, Any]:
        """Get status of all MCP servers."""
        status = {
            "running": self._started,
            "servers": {}
        }

        if self._started:
            for server_name, server in self.client.servers.items():
                status["servers"][server_name] = {
                    "enabled": server.enabled,
                    "connected": server.session is not None,
                    "transport": server.transport
                }

        return status

    def health_check(self) -> bool:
        """Check if all enabled servers are healthy."""
        if not self._started:
            return False

        for server_name, server in self.client.servers.items():
            if server.enabled and not server.session:
                logger.warning(f"Server {server_name} is not connected")
                return False

        return True


class SimpleMCPManager:
    """Simplified MCP manager for testing without actual MCP servers."""

    def __init__(self):
        self.registry = ToolRegistry()
        self.mock_tools = {
            "filesystem.read": {"description": "Read a file", "server": "filesystem"},
            "filesystem.write": {"description": "Write to a file", "server": "filesystem"},
            "filesystem.list": {"description": "List directory contents", "server": "filesystem"},
            "git.status": {"description": "Get git status", "server": "git"},
            "git.branch": {"description": "Manage git branches", "server": "git"},
            "git.diff": {"description": "Show git differences", "server": "git"},
            "sqlite.query": {"description": "Query SQLite database", "server": "sqlite"},
            "sqlite.execute": {"description": "Execute SQLite command", "server": "sqlite"}
        }
        self._started = False
        self._register_mock_tools()
        logger.info("SimpleMCPManager initialized (mock mode)")

    def _register_mock_tools(self):
        """Register mock tools in the registry."""
        for tool_id, info in self.mock_tools.items():
            tool_info = {
                "name": tool_id.split('.')[-1],
                "description": info["description"],
                "input_schema": {}
            }
            self.registry.register_tool(tool_id, info["server"], tool_info)

    def start(self, project_name: Optional[str] = None):
        """Mock start."""
        self._started = True
        logger.info(f"SimpleMCPManager started for project: {project_name}")

    def stop(self):
        """Mock stop."""
        self._started = False
        logger.info("SimpleMCPManager stopped")

    def restart_for_project(self, project_name: str):
        """Mock restart."""
        self.stop()
        self.start(project_name)

    def list_tools(self) -> Dict[str, Any]:
        """Return mock tools."""
        formatted_tools = {}
        for tool_id, metadata in self.registry.tools.items():
            formatted_tools[tool_id] = {
                "name": metadata.name,
                "description": metadata.description,
                "category": metadata.category.value,
                "operation": metadata.operation.value,
                "requires_approval": metadata.requires_approval,
                "server": metadata.server
            }
        return formatted_tools

    def get_tool_metadata(self, tool_id: str) -> Optional[ToolMetadata]:
        """Get metadata for a specific tool."""
        return self.registry.get_tool(tool_id)

    def get_tools_for_agent(self, agent_role: str) -> List[ToolMetadata]:
        """Get tools allowed for a specific agent role."""
        # For mock, return all tools
        return list(self.registry.tools.values())

    def call_tool(self, tool_id: str, arguments: Dict[str, Any]) -> Any:
        """Mock tool execution."""
        logger.info(f"Mock executing tool: {tool_id} with args: {arguments}")

        # Return mock responses
        if tool_id == "filesystem.read":
            return {"type": "text", "text": "# Mock file content\nThis is a test file."}
        elif tool_id == "filesystem.list":
            return {"type": "text", "text": "file1.py\nfile2.md\ndir1/"}
        elif tool_id == "git.status":
            return {"type": "text", "text": "On branch main\nnothing to commit, working tree clean"}

        return {"success": True, "mock": True}

    def get_server_status(self) -> Dict[str, Any]:
        """Mock server status."""
        return {
            "running": self._started,
            "servers": {
                "filesystem": {"enabled": True, "connected": True, "transport": "mock"},
                "git": {"enabled": True, "connected": True, "transport": "mock"},
                "sqlite": {"enabled": True, "connected": True, "transport": "mock"}
            }
        }

    def health_check(self) -> bool:
        """Mock health check."""
        return self._started