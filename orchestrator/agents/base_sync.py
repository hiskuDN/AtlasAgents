"""Synchronous base agent class and interfaces."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid


# Reuse the existing dataclasses from base.py
from .base import (
    AgentRole,
    AgentContext,
    AgentRequest,
    AgentResponse
)


class SyncBaseAgent(ABC):
    """Synchronous base class for all agents."""

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

    def initialize(self, **kwargs):
        """Initialize the agent with any required resources.

        Override this method to set up connections, load models, etc.
        """
        self._initialized = True

    def cleanup(self):
        """Clean up any resources used by the agent.

        Override this method to close connections, free memory, etc.
        """
        self._initialized = False

    @abstractmethod
    def execute(self, request: AgentRequest) -> AgentResponse:
        """Execute the agent's task synchronously.

        Args:
            request: The agent request containing context and prompt

        Returns:
            AgentResponse with the results
        """
        pass

    def validate_request(self, request: AgentRequest) -> bool:
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

    def prepare_context(self, request: AgentRequest) -> Dict[str, Any]:
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