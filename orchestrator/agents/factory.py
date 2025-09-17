"""Agent factory and registry."""

from typing import Dict, Type, Optional, Any
import logging

from .base import BaseAgent, AgentRole
from .mock_agents import (
    MockPlannerAgent,
    MockSpecWriterAgent,
    MockCoderAgent,
    MockReviewerAgent
)
from ..core.state_machine import JobStage

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Registry for available agents."""

    def __init__(self):
        """Initialize the registry."""
        self._agents: Dict[AgentRole, Type[BaseAgent]] = {}
        self._stage_mapping: Dict[JobStage, AgentRole] = {}
        self._register_default_agents()
        self._setup_stage_mapping()

    def _register_default_agents(self):
        """Register the default mock agents."""
        self.register(AgentRole.PLANNER, MockPlannerAgent)
        self.register(AgentRole.SPEC_WRITER, MockSpecWriterAgent)
        self.register(AgentRole.CODER, MockCoderAgent)
        self.register(AgentRole.REVIEWER, MockReviewerAgent)

    def _setup_stage_mapping(self):
        """Set up the mapping from job stages to agent roles."""
        self._stage_mapping = {
            JobStage.PLAN: AgentRole.PLANNER,
            JobStage.SPEC: AgentRole.SPEC_WRITER,
            JobStage.CODE: AgentRole.CODER,
            JobStage.REVIEW: AgentRole.REVIEWER,
        }

    def register(self, role: AgentRole, agent_class: Type[BaseAgent]):
        """Register an agent class for a role.

        Args:
            role: The agent role
            agent_class: The agent class to register
        """
        if not issubclass(agent_class, BaseAgent):
            raise ValueError(f"{agent_class} must be a subclass of BaseAgent")
        self._agents[role] = agent_class
        logger.info(f"Registered agent {agent_class.__name__} for role {role.value}")

    def get_agent_class(self, role: AgentRole) -> Optional[Type[BaseAgent]]:
        """Get the agent class for a role.

        Args:
            role: The agent role

        Returns:
            The agent class or None
        """
        return self._agents.get(role)

    def get_agent_for_stage(self, stage: JobStage) -> Optional[AgentRole]:
        """Get the appropriate agent role for a job stage.

        Args:
            stage: The job stage

        Returns:
            The agent role or None
        """
        return self._stage_mapping.get(stage)

    def list_registered_agents(self) -> Dict[str, str]:
        """List all registered agents.

        Returns:
            Dict mapping role names to agent class names
        """
        return {
            role.value: agent_class.__name__
            for role, agent_class in self._agents.items()
        }


class AgentFactory:
    """Factory for creating agent instances."""

    def __init__(self, registry: Optional[AgentRegistry] = None):
        """Initialize the factory.

        Args:
            registry: Agent registry to use (creates default if None)
        """
        self.registry = registry or AgentRegistry()
        self._instances: Dict[str, BaseAgent] = {}
        self._config: Dict[AgentRole, Dict[str, Any]] = {}

    def create_agent(
        self,
        role: AgentRole,
        config: Optional[Dict[str, Any]] = None,
        reuse_instance: bool = True
    ) -> Optional[BaseAgent]:
        """Create an agent instance.

        Args:
            role: The agent role
            config: Configuration for the agent
            reuse_instance: Whether to reuse existing instances

        Returns:
            The agent instance or None
        """
        # Check for existing instance
        instance_key = f"{role.value}"
        if reuse_instance and instance_key in self._instances:
            logger.debug(f"Reusing existing agent instance for {role.value}")
            return self._instances[instance_key]

        # Get the agent class
        agent_class = self.registry.get_agent_class(role)
        if not agent_class:
            logger.error(f"No agent registered for role {role.value}")
            return None

        # Create new instance
        try:
            agent = agent_class()

            # Store configuration if provided
            if config:
                self._config[role] = config

            # Cache the instance
            if reuse_instance:
                self._instances[instance_key] = agent

            logger.info(f"Created agent {agent_class.__name__} for role {role.value}")
            return agent

        except Exception as e:
            logger.error(f"Failed to create agent for role {role.value}: {e}")
            return None

    def create_agent_for_stage(
        self,
        stage: JobStage,
        config: Optional[Dict[str, Any]] = None
    ) -> Optional[BaseAgent]:
        """Create an agent for a specific job stage.

        Args:
            stage: The job stage
            config: Configuration for the agent

        Returns:
            The agent instance or None
        """
        role = self.registry.get_agent_for_stage(stage)
        if not role:
            logger.error(f"No agent role mapped for stage {stage.value}")
            return None

        return self.create_agent(role, config)

    def get_config(self, role: AgentRole) -> Optional[Dict[str, Any]]:
        """Get the configuration for an agent role.

        Args:
            role: The agent role

        Returns:
            The configuration or None
        """
        return self._config.get(role)

    def set_config(self, role: AgentRole, config: Dict[str, Any]):
        """Set the configuration for an agent role.

        Args:
            role: The agent role
            config: The configuration
        """
        self._config[role] = config

    async def cleanup_all(self):
        """Clean up all cached agent instances."""
        for agent in self._instances.values():
            try:
                await agent.cleanup()
            except Exception as e:
                logger.error(f"Failed to cleanup agent {agent.name}: {e}")
        self._instances.clear()


# Global factory instance
_factory: Optional[AgentFactory] = None


def get_factory() -> AgentFactory:
    """Get the global agent factory instance.

    Returns:
        The agent factory
    """
    global _factory
    if _factory is None:
        _factory = AgentFactory()
    return _factory


def set_factory(factory: AgentFactory):
    """Set the global agent factory instance.

    Args:
        factory: The factory to use
    """
    global _factory
    _factory = factory