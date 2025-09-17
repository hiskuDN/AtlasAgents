"""Tool executor for handling MCP tool calls with approval flow."""

import json
import uuid
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from orchestrator.models.database import Database, ApprovalStatus
from orchestrator.mcp.registry import ToolMetadata
from orchestrator.mcp.permissions import PermissionManager, PermissionEnforcer
from orchestrator.utils.logging import get_logger
from orchestrator.utils.exceptions import MCPToolError, ApprovalTimeoutError


logger = get_logger(__name__)


class ToolCallStatus(str, Enum):
    """Status of a tool call."""
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ToolCallRequest:
    """Represents a tool call request."""
    call_id: str
    tool_id: str
    arguments: Dict[str, Any]
    agent_role: str
    project_id: Optional[int] = None
    job_id: Optional[int] = None
    requires_approval: bool = False
    status: ToolCallStatus = ToolCallStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Optional[Dict] = None


@dataclass
class ToolCallResult:
    """Result of a tool execution."""
    call_id: str
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    executed_at: datetime = field(default_factory=datetime.utcnow)


class ToolExecutor:
    """Executes tools with approval flow and database recording."""

    def __init__(self, db: Database, mcp_manager: Any,
                 permission_manager: PermissionManager):
        self.db = db
        self.mcp_manager = mcp_manager
        self.permission_manager = permission_manager
        self.permission_enforcer = PermissionEnforcer(permission_manager)

        # Pending tool calls awaiting approval
        self.pending_calls: Dict[str, ToolCallRequest] = {}

        # Completed calls
        self.completed_calls: Dict[str, ToolCallResult] = {}

        logger.info("Tool executor initialized")

    def request_tool(self,
                     tool_id: str,
                     arguments: Dict[str, Any],
                     agent_role: str,
                     project_id: Optional[int] = None,
                     job_id: Optional[int] = None) -> str:
        """
        Request to execute a tool.

        Returns:
            call_id for tracking the request
        """
        # Generate unique call ID
        call_id = str(uuid.uuid4())

        # Get tool metadata
        tool_metadata = self.mcp_manager.get_tool_metadata(tool_id)

        # Check permissions
        allowed, error_msg = self.permission_enforcer.enforce(
            agent_role, tool_id, tool_metadata, project_id, job_id
        )

        if not allowed:
            # Record denied call in database
            self._record_tool_call(
                call_id=call_id,
                job_id=job_id,
                tool_id=tool_id,
                arguments=arguments,
                status=ToolCallStatus.DENIED,
                error=error_msg
            )
            raise MCPToolError(tool_id, error_msg)

        # Check if approval is required
        permission_check = self.permission_manager.check_permission(
            agent_role, tool_id, tool_metadata, project_id, job_id
        )

        requires_approval = permission_check.requires_approval

        # Create request
        request = ToolCallRequest(
            call_id=call_id,
            tool_id=tool_id,
            arguments=arguments,
            agent_role=agent_role,
            project_id=project_id,
            job_id=job_id,
            requires_approval=requires_approval
        )

        # Store request
        self.pending_calls[call_id] = request

        # Record in database
        db_id = self._record_tool_call(
            call_id=call_id,
            job_id=job_id,
            tool_id=tool_id,
            arguments=arguments,
            status=ToolCallStatus.PENDING
        )

        logger.info(f"Tool call requested: {call_id} for {tool_id}",
                   call_id=call_id,
                   tool_id=tool_id,
                   requires_approval=requires_approval)

        # If no approval required, execute immediately
        if not requires_approval:
            return self._execute_immediate(request)

        # Otherwise, return call_id for approval flow
        return call_id

    def _execute_immediate(self, request: ToolCallRequest) -> str:
        """Execute a tool immediately without approval."""
        try:
            # Execute through MCP manager
            result = self.mcp_manager.call_tool(
                request.tool_id,
                request.arguments,
                agent_role=request.agent_role,
                project_id=request.project_id,
                job_id=request.job_id
            )

            # Update status
            request.status = ToolCallStatus.EXECUTED

            # Store result
            tool_result = ToolCallResult(
                call_id=request.call_id,
                success=True,
                result=result
            )
            self.completed_calls[request.call_id] = tool_result

            # Update database
            self._update_tool_call(
                request.call_id,
                status=ToolCallStatus.EXECUTED,
                result=result
            )

            logger.info(f"Tool executed immediately: {request.call_id}")
            return request.call_id

        except Exception as e:
            # Handle execution failure
            request.status = ToolCallStatus.FAILED

            tool_result = ToolCallResult(
                call_id=request.call_id,
                success=False,
                error=str(e)
            )
            self.completed_calls[request.call_id] = tool_result

            # Update database
            self._update_tool_call(
                request.call_id,
                status=ToolCallStatus.FAILED,
                error=str(e)
            )

            logger.error(f"Tool execution failed: {request.call_id}: {e}")
            raise MCPToolError(request.tool_id, str(e))

    def approve_tool(self, call_id: str, actor: str,
                    reason: Optional[str] = None) -> ToolCallResult:
        """
        Approve and execute a pending tool call.

        Args:
            call_id: ID of the tool call to approve
            actor: Who is approving
            reason: Optional reason for approval

        Returns:
            ToolCallResult
        """
        if call_id not in self.pending_calls:
            raise ValueError(f"Unknown tool call: {call_id}")

        request = self.pending_calls[call_id]

        if request.status != ToolCallStatus.PENDING:
            raise ValueError(f"Tool call {call_id} is not pending (status: {request.status})")

        # Update status
        request.status = ToolCallStatus.APPROVED

        # Record approval in database
        if request.job_id:
            self.db.create_approval(
                job_id=request.job_id,
                status=ApprovalStatus.APPROVED.value,
                actor=actor,
                reason=reason
            )

        logger.info(f"Tool call approved: {call_id} by {actor}")

        try:
            # Execute the tool
            result = self.mcp_manager.call_tool(
                request.tool_id,
                request.arguments,
                agent_role=request.agent_role,
                project_id=request.project_id,
                job_id=request.job_id
            )

            # Update status
            request.status = ToolCallStatus.EXECUTED

            # Create result
            tool_result = ToolCallResult(
                call_id=call_id,
                success=True,
                result=result
            )

            # Store result
            self.completed_calls[call_id] = tool_result

            # Update database
            self._update_tool_call(
                call_id,
                status=ToolCallStatus.EXECUTED,
                result=result
            )

            # Remove from pending
            del self.pending_calls[call_id]

            logger.info(f"Tool executed after approval: {call_id}")
            return tool_result

        except Exception as e:
            # Handle execution failure
            request.status = ToolCallStatus.FAILED

            tool_result = ToolCallResult(
                call_id=call_id,
                success=False,
                error=str(e)
            )

            self.completed_calls[call_id] = tool_result

            # Update database
            self._update_tool_call(
                call_id,
                status=ToolCallStatus.FAILED,
                error=str(e)
            )

            # Remove from pending
            del self.pending_calls[call_id]

            logger.error(f"Tool execution failed after approval: {call_id}: {e}")
            return tool_result

    def deny_tool(self, call_id: str, actor: str,
                 reason: Optional[str] = None) -> None:
        """
        Deny a pending tool call.

        Args:
            call_id: ID of the tool call to deny
            actor: Who is denying
            reason: Optional reason for denial
        """
        if call_id not in self.pending_calls:
            raise ValueError(f"Unknown tool call: {call_id}")

        request = self.pending_calls[call_id]

        if request.status != ToolCallStatus.PENDING:
            raise ValueError(f"Tool call {call_id} is not pending (status: {request.status})")

        # Update status
        request.status = ToolCallStatus.DENIED

        # Record denial in database
        if request.job_id:
            self.db.create_approval(
                job_id=request.job_id,
                status=ApprovalStatus.REVISE.value,
                actor=actor,
                reason=reason or "Tool call denied"
            )

        # Update database
        self._update_tool_call(
            call_id,
            status=ToolCallStatus.DENIED,
            error=reason or "Denied by user"
        )

        # Remove from pending
        del self.pending_calls[call_id]

        logger.info(f"Tool call denied: {call_id} by {actor}")

    def get_pending_calls(self, project_id: Optional[int] = None) -> List[ToolCallRequest]:
        """Get all pending tool calls."""
        calls = list(self.pending_calls.values())

        if project_id:
            calls = [c for c in calls if c.project_id == project_id]

        return calls

    def get_call_status(self, call_id: str) -> Optional[ToolCallStatus]:
        """Get the status of a tool call."""
        if call_id in self.pending_calls:
            return self.pending_calls[call_id].status

        if call_id in self.completed_calls:
            result = self.completed_calls[call_id]
            if result.success:
                return ToolCallStatus.EXECUTED
            else:
                return ToolCallStatus.FAILED

        return None

    def get_call_result(self, call_id: str) -> Optional[ToolCallResult]:
        """Get the result of a completed tool call."""
        return self.completed_calls.get(call_id)

    def _record_tool_call(self, call_id: str, job_id: Optional[int],
                         tool_id: str, arguments: Dict,
                         status: ToolCallStatus,
                         error: Optional[str] = None) -> int:
        """Record a tool call in the database."""
        if not job_id:
            return 0  # Skip recording if no job context

        # Prepare params for database
        params = {
            "call_id": call_id,
            "arguments": arguments
        }

        # Create tool call record
        db_id = self.db.create_tool_call(
            job_id=job_id,
            server=tool_id.split('.')[0] if '.' in tool_id else "unknown",
            tool=tool_id,
            params=params
        )

        # If there's an error or it's denied, update with that info
        if error:
            self.db.update_tool_call(
                db_id,
                executed=False,
                result={"status": status.value, "error": error}
            )

        return db_id

    def _update_tool_call(self, call_id: str, status: ToolCallStatus,
                         result: Optional[Any] = None,
                         error: Optional[str] = None):
        """Update a tool call record in the database."""
        # Find the tool call by call_id
        # For simplicity, we'll store the status in the result
        result_data = {
            "status": status.value,
            "call_id": call_id
        }

        if result:
            result_data["result"] = result
        if error:
            result_data["error"] = error

        # This is simplified - in production, we'd look up by call_id
        logger.debug(f"Updated tool call {call_id} with status {status}")

    def get_statistics(self) -> Dict[str, int]:
        """Get statistics about tool calls."""
        return {
            "pending": len(self.pending_calls),
            "completed": len(self.completed_calls),
            "approved": sum(1 for r in self.completed_calls.values() if r.success),
            "failed": sum(1 for r in self.completed_calls.values() if not r.success),
            "denied": sum(1 for r in self.pending_calls.values()
                         if r.status == ToolCallStatus.DENIED)
        }