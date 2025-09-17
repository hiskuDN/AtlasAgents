"""Tool registry for managing available MCP tools."""

from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from enum import Enum
import json
import re

from orchestrator.utils.logging import get_logger


logger = get_logger(__name__)


class ToolCategory(str, Enum):
    """Categories for grouping tools."""
    FILESYSTEM = "filesystem"
    GIT = "git"
    DATABASE = "database"
    NETWORK = "network"
    COMPUTE = "compute"
    UNKNOWN = "unknown"


class ToolOperation(str, Enum):
    """Types of tool operations."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    QUERY = "query"
    UNKNOWN = "unknown"


@dataclass
class ToolMetadata:
    """Metadata for a registered tool."""
    tool_id: str
    name: str
    server: str
    category: ToolCategory
    operation: ToolOperation
    description: Optional[str] = None
    input_schema: Optional[Dict] = None
    requires_approval: bool = False
    is_mutating: bool = False
    tags: Set[str] = field(default_factory=set)


class ToolRegistry:
    """Registry for managing and categorizing MCP tools."""

    def __init__(self):
        self.tools: Dict[str, ToolMetadata] = {}
        self.server_tools: Dict[str, List[str]] = {}
        self.category_tools: Dict[ToolCategory, List[str]] = {}
        self.operation_tools: Dict[ToolOperation, List[str]] = {}

        logger.info("Tool registry initialized")

    def register_tool(self, tool_id: str, server: str, tool_info: Dict[str, Any]) -> ToolMetadata:
        """
        Register a tool with the registry.

        Args:
            tool_id: Unique tool identifier (e.g., "filesystem.read")
            server: Server providing the tool
            tool_info: Tool information from MCP

        Returns:
            ToolMetadata object
        """
        # Parse tool name
        name = tool_info.get('name', tool_id.split('.')[-1])
        description = tool_info.get('description', '')
        input_schema = tool_info.get('input_schema', {})

        # Determine category and operation
        category = self._determine_category(tool_id, server)
        operation = self._determine_operation(tool_id, name, description)

        # Check if mutating
        is_mutating = operation in [ToolOperation.WRITE, ToolOperation.DELETE, ToolOperation.EXECUTE]
        requires_approval = is_mutating  # For now, all mutations require approval

        # Extract tags
        tags = self._extract_tags(tool_id, description)

        # Create metadata
        metadata = ToolMetadata(
            tool_id=tool_id,
            name=name,
            server=server,
            category=category,
            operation=operation,
            description=description,
            input_schema=input_schema,
            requires_approval=requires_approval,
            is_mutating=is_mutating,
            tags=tags
        )

        # Store in registry
        self.tools[tool_id] = metadata

        # Update indices
        if server not in self.server_tools:
            self.server_tools[server] = []
        self.server_tools[server].append(tool_id)

        if category not in self.category_tools:
            self.category_tools[category] = []
        self.category_tools[category].append(tool_id)

        if operation not in self.operation_tools:
            self.operation_tools[operation] = []
        self.operation_tools[operation].append(tool_id)

        logger.debug(f"Registered tool: {tool_id} (category={category}, operation={operation})")

        return metadata

    def _determine_category(self, tool_id: str, server: str) -> ToolCategory:
        """Determine the category of a tool."""
        tool_lower = tool_id.lower()

        if 'filesystem' in tool_lower or 'fs' in server.lower() or 'file' in tool_lower:
            return ToolCategory.FILESYSTEM
        elif 'git' in tool_lower or 'git' in server.lower():
            return ToolCategory.GIT
        elif 'sql' in tool_lower or 'db' in tool_lower or 'database' in tool_lower:
            return ToolCategory.DATABASE
        elif 'http' in tool_lower or 'fetch' in tool_lower or 'request' in tool_lower:
            return ToolCategory.NETWORK
        elif 'exec' in tool_lower or 'run' in tool_lower or 'compute' in tool_lower:
            return ToolCategory.COMPUTE
        else:
            return ToolCategory.UNKNOWN

    def _determine_operation(self, tool_id: str, name: str, description: str) -> ToolOperation:
        """Determine the operation type of a tool."""
        combined = f"{tool_id} {name} {description}".lower()

        # Check for specific operations
        if any(word in combined for word in ['read', 'get', 'list', 'show', 'view', 'cat']):
            return ToolOperation.READ
        elif any(word in combined for word in ['write', 'create', 'update', 'save', 'put', 'append']):
            return ToolOperation.WRITE
        elif any(word in combined for word in ['delete', 'remove', 'rm', 'unlink']):
            return ToolOperation.DELETE
        elif any(word in combined for word in ['execute', 'run', 'exec', 'call']):
            return ToolOperation.EXECUTE
        elif any(word in combined for word in ['query', 'select', 'find', 'search']):
            return ToolOperation.QUERY
        else:
            return ToolOperation.UNKNOWN

    def _extract_tags(self, tool_id: str, description: str) -> Set[str]:
        """Extract tags from tool information."""
        tags = set()

        # Add basic tags from tool_id
        parts = tool_id.split('.')
        for part in parts:
            if part and len(part) > 2:  # Skip short parts
                tags.add(part.lower())

        # Extract tags from description
        # Look for common keywords
        keywords = ['async', 'sync', 'safe', 'unsafe', 'preview', 'apply', 'experimental']
        desc_lower = description.lower()
        for keyword in keywords:
            if keyword in desc_lower:
                tags.add(keyword)

        return tags

    def get_tool(self, tool_id: str) -> Optional[ToolMetadata]:
        """Get metadata for a specific tool."""
        return self.tools.get(tool_id)

    def list_tools(self,
                  server: Optional[str] = None,
                  category: Optional[ToolCategory] = None,
                  operation: Optional[ToolOperation] = None,
                  requires_approval: Optional[bool] = None) -> List[ToolMetadata]:
        """
        List tools with optional filters.

        Args:
            server: Filter by server name
            category: Filter by category
            operation: Filter by operation type
            requires_approval: Filter by approval requirement

        Returns:
            List of matching tools
        """
        results = []

        for tool_id, metadata in self.tools.items():
            # Apply filters
            if server and metadata.server != server:
                continue
            if category and metadata.category != category:
                continue
            if operation and metadata.operation != operation:
                continue
            if requires_approval is not None and metadata.requires_approval != requires_approval:
                continue

            results.append(metadata)

        return results

    def get_tools_by_server(self, server: str) -> List[ToolMetadata]:
        """Get all tools from a specific server."""
        tool_ids = self.server_tools.get(server, [])
        return [self.tools[tid] for tid in tool_ids if tid in self.tools]

    def get_tools_by_category(self, category: ToolCategory) -> List[ToolMetadata]:
        """Get all tools in a specific category."""
        tool_ids = self.category_tools.get(category, [])
        return [self.tools[tid] for tid in tool_ids if tid in self.tools]

    def get_tools_by_operation(self, operation: ToolOperation) -> List[ToolMetadata]:
        """Get all tools with a specific operation type."""
        tool_ids = self.operation_tools.get(operation, [])
        return [self.tools[tid] for tid in tool_ids if tid in self.tools]

    def get_mutating_tools(self) -> List[ToolMetadata]:
        """Get all tools that perform mutations."""
        return [t for t in self.tools.values() if t.is_mutating]

    def get_safe_tools(self) -> List[ToolMetadata]:
        """Get all tools that don't require approval."""
        return [t for t in self.tools.values() if not t.requires_approval]

    def search_tools(self, query: str) -> List[ToolMetadata]:
        """
        Search for tools matching a query.

        Args:
            query: Search query

        Returns:
            List of matching tools
        """
        query_lower = query.lower()
        results = []

        for metadata in self.tools.values():
            # Check if query matches tool_id, name, description, or tags
            if (query_lower in metadata.tool_id.lower() or
                query_lower in metadata.name.lower() or
                (metadata.description and query_lower in metadata.description.lower()) or
                query_lower in metadata.tags):
                results.append(metadata)

        return results

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about registered tools."""
        total_tools = len(self.tools)

        # Count by category
        category_counts = {}
        for category in ToolCategory:
            count = len(self.category_tools.get(category, []))
            if count > 0:
                category_counts[category.value] = count

        # Count by operation
        operation_counts = {}
        for operation in ToolOperation:
            count = len(self.operation_tools.get(operation, []))
            if count > 0:
                operation_counts[operation.value] = count

        # Count by server
        server_counts = {server: len(tools) for server, tools in self.server_tools.items()}

        # Count special types
        mutating_count = len(self.get_mutating_tools())
        safe_count = len(self.get_safe_tools())

        return {
            "total": total_tools,
            "by_category": category_counts,
            "by_operation": operation_counts,
            "by_server": server_counts,
            "mutating": mutating_count,
            "safe": safe_count,
            "requiring_approval": total_tools - safe_count
        }

    def export_catalog(self) -> Dict[str, Any]:
        """Export the tool catalog as a dictionary."""
        catalog = {
            "tools": {},
            "statistics": self.get_statistics()
        }

        for tool_id, metadata in self.tools.items():
            catalog["tools"][tool_id] = {
                "name": metadata.name,
                "server": metadata.server,
                "category": metadata.category.value,
                "operation": metadata.operation.value,
                "description": metadata.description,
                "requires_approval": metadata.requires_approval,
                "is_mutating": metadata.is_mutating,
                "tags": list(metadata.tags)
            }

        return catalog

    def clear(self):
        """Clear all registered tools."""
        self.tools.clear()
        self.server_tools.clear()
        self.category_tools.clear()
        self.operation_tools.clear()
        logger.info("Tool registry cleared")