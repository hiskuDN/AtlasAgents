"""Agent framework for AtlasAgents."""

from .base import (
    BaseAgent,
    AgentRole,
    AgentContext,
    AgentRequest,
    AgentResponse
)

from .factory import (
    AgentFactory,
    AgentRegistry,
    get_factory,
    set_factory
)

from .mock_agents import (
    MockPlannerAgent,
    MockSpecWriterAgent,
    MockCoderAgent,
    MockReviewerAgent
)

from .tool_interface import (
    AgentToolInterface,
    ToolCallRequest,
    ToolCallResponse
)

__all__ = [
    # Base
    'BaseAgent',
    'AgentRole',
    'AgentContext',
    'AgentRequest',
    'AgentResponse',

    # Factory
    'AgentFactory',
    'AgentRegistry',
    'get_factory',
    'set_factory',

    # Mock agents
    'MockPlannerAgent',
    'MockSpecWriterAgent',
    'MockCoderAgent',
    'MockReviewerAgent',

    # Tool interface
    'AgentToolInterface',
    'ToolCallRequest',
    'ToolCallResponse',
]