"""Custom exceptions for AtlasAgents."""

from typing import Optional, Dict, Any


class AtlasError(Exception):
    """Base exception for all AtlasAgents errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self):
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


class ConfigurationError(AtlasError):
    """Raised when there's a configuration issue."""
    pass


class ProjectError(AtlasError):
    """Base exception for project-related errors."""
    pass


class ProjectNotFoundError(ProjectError):
    """Raised when a project cannot be found."""

    def __init__(self, project_name: str):
        super().__init__(f"Project '{project_name}' not found")
        self.project_name = project_name


class ProjectExistsError(ProjectError):
    """Raised when trying to create a project that already exists."""

    def __init__(self, project_name: str):
        super().__init__(f"Project '{project_name}' already exists")
        self.project_name = project_name


class StateTransitionError(AtlasError):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, from_state: str, to_state: str, reason: Optional[str] = None):
        message = f"Invalid transition from {from_state} to {to_state}"
        if reason:
            message += f": {reason}"
        super().__init__(message)
        self.from_state = from_state
        self.to_state = to_state


class JobExecutionError(AtlasError):
    """Raised when a job fails to execute."""

    def __init__(self, job_id: int, stage: str, error: str):
        super().__init__(f"Job {job_id} failed at stage {stage}: {error}")
        self.job_id = job_id
        self.stage = stage
        self.error = error


class AgentError(AtlasError):
    """Base exception for agent-related errors."""
    pass


class AgentNotFoundError(AgentError):
    """Raised when an agent cannot be found or created."""

    def __init__(self, agent_role: str):
        super().__init__(f"Agent for role '{agent_role}' not found")
        self.agent_role = agent_role


class AgentExecutionError(AgentError):
    """Raised when an agent fails during execution."""

    def __init__(self, agent_role: str, error: str):
        super().__init__(f"Agent '{agent_role}' failed: {error}")
        self.agent_role = agent_role
        self.error = error


class MCPError(AtlasError):
    """Base exception for MCP-related errors."""
    pass


class MCPConnectionError(MCPError):
    """Raised when MCP server connection fails."""

    def __init__(self, server_name: str, error: str):
        super().__init__(f"Failed to connect to MCP server '{server_name}': {error}")
        self.server_name = server_name
        self.error = error


class MCPToolError(MCPError):
    """Raised when an MCP tool operation fails."""

    def __init__(self, tool_name: str, error: str):
        super().__init__(f"MCP tool '{tool_name}' failed: {error}")
        self.tool_name = tool_name
        self.error = error


class ApprovalError(AtlasError):
    """Base exception for approval-related errors."""
    pass


class ApprovalNotFoundError(ApprovalError):
    """Raised when an approval cannot be found."""

    def __init__(self, approval_id: int):
        super().__init__(f"Approval {approval_id} not found")
        self.approval_id = approval_id


class ApprovalTimeoutError(ApprovalError):
    """Raised when an approval times out."""

    def __init__(self, approval_id: int, timeout_seconds: int):
        super().__init__(f"Approval {approval_id} timed out after {timeout_seconds} seconds")
        self.approval_id = approval_id
        self.timeout_seconds = timeout_seconds


class TelegramError(AtlasError):
    """Base exception for Telegram-related errors."""
    pass


class TelegramConnectionError(TelegramError):
    """Raised when Telegram bot connection fails."""

    def __init__(self, error: str):
        super().__init__(f"Telegram connection failed: {error}")
        self.error = error


class TelegramMessageError(TelegramError):
    """Raised when sending a Telegram message fails."""

    def __init__(self, error: str):
        super().__init__(f"Failed to send Telegram message: {error}")
        self.error = error


class PathSecurityError(AtlasError):
    """Raised when a path operation violates security constraints."""

    def __init__(self, path: str, reason: str):
        super().__init__(f"Path security violation for '{path}': {reason}")
        self.path = path
        self.reason = reason


class RetryableError(AtlasError):
    """Base class for retryable errors."""

    def __init__(self, message: str, max_retries: int = 3, retry_delay: float = 1.0):
        super().__init__(message)
        self.max_retries = max_retries
        self.retry_delay = retry_delay