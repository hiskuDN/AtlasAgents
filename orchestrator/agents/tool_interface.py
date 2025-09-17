"""Tool calling interface for agents."""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import logging

from ..mcp.executor import ToolExecutor
from ..mcp.permissions import PermissionEnforcer
from ..core.config import AtlasConfig

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRequest:
    """Request to call a tool."""
    tool_id: str
    arguments: Dict[str, Any]
    require_approval: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallResponse:
    """Response from a tool call."""
    success: bool
    result: Any
    error: Optional[str] = None
    approval_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentToolInterface:
    """Interface for agents to call MCP tools with permission checking."""

    def __init__(
        self,
        executor: ToolExecutor,
        permission_checker: PermissionEnforcer,
        agent_role: str,
        project_id: Optional[int] = None,
        job_id: Optional[int] = None
    ):
        """Initialize the tool interface.

        Args:
            executor: Tool executor instance
            permission_checker: Permission checker instance
            agent_role: Role of the agent using this interface
            project_id: Current project ID
            job_id: Current job ID
        """
        self.executor = executor
        self.permission_checker = permission_checker
        self.agent_role = agent_role
        self.project_id = project_id
        self.job_id = job_id
        self.config = AtlasConfig.get()

    async def call_tool(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        require_approval: Optional[bool] = None
    ) -> ToolCallResponse:
        """Call a tool with permission checking.

        Args:
            tool_id: ID of the tool to call
            arguments: Arguments for the tool
            require_approval: Override approval requirement

        Returns:
            ToolCallResponse with the result
        """
        try:
            # Check permissions first
            permission_result = self.permission_checker.check_permission(
                tool_id,
                self.agent_role,
                arguments
            )

            if not permission_result['allowed']:
                return ToolCallResponse(
                    success=False,
                    result=None,
                    error=f"Permission denied: {permission_result.get('reason', 'Unknown')}"
                )

            # Determine if approval is needed
            if require_approval is None:
                require_approval = permission_result.get('requires_approval', False)

            # Execute the tool
            result = await self._execute_tool(
                tool_id,
                arguments,
                require_approval
            )

            return ToolCallResponse(
                success=True,
                result=result['output'],
                approval_id=result.get('approval_id'),
                metadata={
                    'execution_time': result.get('execution_time'),
                    'tool_metadata': result.get('metadata', {})
                }
            )

        except Exception as e:
            logger.error(f"Tool call failed: {tool_id}", exc_info=True)
            return ToolCallResponse(
                success=False,
                result=None,
                error=str(e)
            )

    async def _execute_tool(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        require_approval: bool
    ) -> Dict[str, Any]:
        """Execute a tool through the executor.

        Args:
            tool_id: Tool to execute
            arguments: Tool arguments
            require_approval: Whether approval is required

        Returns:
            Execution result
        """
        # Use the synchronous executor method
        # In a real implementation, this would be async
        result = self.executor.request_tool(
            tool_id=tool_id,
            arguments=arguments,
            agent_role=self.agent_role,
            project_id=self.project_id,
            job_id=self.job_id
        )

        if require_approval:
            # Wait for approval (in real implementation)
            # For now, auto-approve in mock mode
            if hasattr(self.executor, 'auto_approve'):
                self.executor.approve_tool(result, approved=True)

        return {
            'output': result,
            'approval_id': None,  # Would be set if approval was required
            'execution_time': 0.1,  # Mock execution time
            'metadata': {}
        }

    async def batch_call_tools(
        self,
        requests: List[ToolCallRequest]
    ) -> List[ToolCallResponse]:
        """Call multiple tools in batch.

        Args:
            requests: List of tool call requests

        Returns:
            List of responses
        """
        responses = []
        for request in requests:
            response = await self.call_tool(
                tool_id=request.tool_id,
                arguments=request.arguments,
                require_approval=request.require_approval
            )
            responses.append(response)
        return responses

    def inject_context(
        self,
        project_id: Optional[int] = None,
        job_id: Optional[int] = None
    ):
        """Update the context for tool calls.

        Args:
            project_id: New project ID
            job_id: New job ID
        """
        if project_id is not None:
            self.project_id = project_id
        if job_id is not None:
            self.job_id = job_id

    def get_available_tools(self) -> List[str]:
        """Get list of tools available to this agent.

        Returns:
            List of tool IDs
        """
        # Get all tools from registry
        all_tools = self.executor.registry.list_tools()

        # Filter by permissions
        available = []
        for tool in all_tools:
            result = self.permission_checker.check_permission(
                tool['id'],
                self.agent_role,
                {}
            )
            if result['allowed']:
                available.append(tool['id'])

        return available

    def get_tool_info(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific tool.

        Args:
            tool_id: Tool ID

        Returns:
            Tool information or None
        """
        return self.executor.registry.get_tool(tool_id)