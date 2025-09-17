"""Base agent class and interfaces."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid


class AgentRole(Enum):
    """Enumeration of agent roles."""
    PLANNER = "planner"
    SPEC_WRITER = "spec_writer"
    CODER = "coder"
    REVIEWER = "reviewer"
    PM = "pm"  # Future


@dataclass
class AgentContext:
    """Context provided to agents for execution."""
    project_id: int
    job_id: int
    stage: str
    workspace_path: str

    # Previous outputs from other stages
    artifacts: Dict[str, Any] = field(default_factory=dict)

    # Files and their contents
    files: Dict[str, str] = field(default_factory=dict)

    # Configuration
    config: Dict[str, Any] = field(default_factory=dict)

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentRequest:
    """Input to an agent."""
    context: AgentContext
    prompt: str

    # Optional parameters for the agent
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Maximum tokens/time limits
    max_tokens: Optional[int] = None
    timeout_seconds: Optional[int] = None


@dataclass
class AgentResponse:
    """Output from an agent."""
    success: bool

    # Main output content
    content: str

    # Structured outputs (e.g., plan.md, spec.md, tasks.json)
    artifacts: Dict[str, Any] = field(default_factory=dict)

    # Tool calls made during execution
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)

    # Execution metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Error information if not successful
    error: Optional[str] = None

    # Timing information
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    def complete(self):
        """Mark the response as complete."""
        self.completed_at = datetime.now()
        if 'execution_time' not in self.metadata:
            self.metadata['execution_time'] = (
                self.completed_at - self.started_at
            ).total_seconds()


class BaseAgent(ABC):
    """Abstract base class for all agents."""

    def __init__(self, role: AgentRole, name: Optional[str] = None):
        """Initialize the agent.

        Args:
            role: The role of this agent
            name: Optional name for the agent
        """
        self.role = role
        self.name = name or f"{role.value}_agent"
        self.id = str(uuid.uuid4())
        self._initialized = False

    async def initialize(self, **kwargs):
        """Initialize the agent with any required resources.

        Override this method to set up connections, load models, etc.
        """
        self._initialized = True

    async def cleanup(self):
        """Clean up any resources used by the agent.

        Override this method to close connections, free memory, etc.
        """
        self._initialized = False

    @abstractmethod
    async def execute(self, request: AgentRequest) -> AgentResponse:
        """Execute the agent's task.

        Args:
            request: The agent request containing context and prompt

        Returns:
            AgentResponse with the results
        """
        pass

    async def validate_request(self, request: AgentRequest) -> bool:
        """Validate that the request is valid for this agent.

        Override to add custom validation logic.

        Args:
            request: The request to validate

        Returns:
            True if valid, raises exception otherwise
        """
        if not request.context:
            raise ValueError("Request must include context")
        if not request.prompt:
            raise ValueError("Request must include prompt")
        return True

    async def prepare_context(self, request: AgentRequest) -> Dict[str, Any]:
        """Prepare the context for execution.

        Override to customize context preparation.

        Args:
            request: The agent request

        Returns:
            Prepared context dictionary
        """
        return {
            'project_id': request.context.project_id,
            'job_id': request.context.job_id,
            'stage': request.context.stage,
            'workspace': request.context.workspace_path,
            'artifacts': request.context.artifacts,
            'files': request.context.files,
        }

    def __repr__(self):
        return f"<{self.__class__.__name__}(role={self.role.value}, name={self.name})>"