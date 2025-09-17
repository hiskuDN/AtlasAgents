"""Synchronous LLM-powered agent implementations."""

import json
import re
from typing import Any, Dict, Optional
from pathlib import Path

from .base import AgentRole, AgentRequest, AgentResponse
from .base_sync import SyncBaseAgent
from ..llm.model_router import ModelRouter, ModelConfig, ModelProvider
from ..llm.prompts import AgentPrompts


class SyncLLMAgent(SyncBaseAgent):
    """Synchronous LLM-powered agent."""

    def __init__(self, role: AgentRole, model_config: Optional[ModelConfig] = None):
        """Initialize the LLM agent.

        Args:
            role: Agent role
            model_config: Model configuration
        """
        super().__init__(role)
        self.model_config = model_config or ModelConfig(
            provider=ModelProvider.OLLAMA,
            model_name="phi4:latest",
            temperature=0.7
        )
        self.model_router = ModelRouter()

    def execute(self, request: AgentRequest) -> AgentResponse:
        """Execute the agent task using LLM synchronously.

        Args:
            request: Agent request

        Returns:
            Agent response
        """
        try:
            # Synchronous validation
            if not request.context:
                raise ValueError("Request must include context")
            if not request.prompt:
                raise ValueError("Request must include prompt")

            # Get prompts
            system_prompt = AgentPrompts.get_system_prompt(self.role)
            task_prompt = self._build_task_prompt(request)

            # Generate response synchronously
            llm_response = self.model_router.generate(
                prompt=task_prompt,
                model_config=self.model_config,
                system_prompt=system_prompt
            )

            # Parse and structure the response
            artifacts = self._parse_response(llm_response, request)

            response = AgentResponse(
                success=True,
                content=llm_response,
                artifacts=artifacts,
                metadata={
                    'agent': self.name,
                    'model': self.model_config.model_name,
                    'provider': self.model_config.provider.value
                }
            )
            response.complete()
            return response

        except Exception as e:
            response = AgentResponse(
                success=False,
                content="",
                error=str(e),
                metadata={'agent': self.name}
            )
            response.complete()
            return response

    def _build_task_prompt(self, request: AgentRequest) -> str:
        """Build task prompt from request.

        Args:
            request: Agent request

        Returns:
            Formatted prompt
        """
        # Base context
        prompt_args = {
            'project_name': f"Project {request.context.project_id}",
            'workspace_path': request.context.workspace_path,
            'stage': request.context.stage,
            'context': request.prompt
        }

        # Add role-specific context
        if self.role == AgentRole.PLANNER:
            prompt_args['requirements'] = request.prompt

        elif self.role == AgentRole.SPEC_WRITER:
            # Add plan content if available
            plan_path = Path(request.context.workspace_path) / "docs" / "plan.md"
            if plan_path.exists():
                prompt_args['plan_content'] = plan_path.read_text()
            else:
                prompt_args['plan_content'] = request.context.artifacts.get('plan', '')

        elif self.role == AgentRole.CODER:
            # Add spec and task info
            spec_path = Path(request.context.workspace_path) / "docs" / "spec.md"
            if spec_path.exists():
                prompt_args['spec_content'] = spec_path.read_text()
            else:
                prompt_args['spec_content'] = request.context.artifacts.get('spec', '')

            task = request.context.artifacts.get('current_task', {})
            prompt_args['task_title'] = task.get('title', 'Implementation Task')
            prompt_args['task_description'] = task.get('description', request.prompt)

        elif self.role == AgentRole.REVIEWER:
            # Add spec and changes
            spec_path = Path(request.context.workspace_path) / "docs" / "spec.md"
            if spec_path.exists():
                prompt_args['spec_content'] = spec_path.read_text()

            prompt_args['changes'] = request.context.artifacts.get('changes', 'No changes provided')

        return AgentPrompts.get_task_prompt(self.role, **prompt_args)

    def _parse_response(self, llm_response: str, request: AgentRequest) -> Dict[str, Any]:
        """Parse LLM response into artifacts.

        Args:
            llm_response: Raw LLM response
            request: Original request

        Returns:
            Artifacts dictionary
        """
        artifacts = {}

        if self.role == AgentRole.PLANNER:
            artifacts['plan.md'] = llm_response
            artifacts['summary'] = 'Generated implementation plan'

        elif self.role == AgentRole.SPEC_WRITER:
            # Split spec and tasks if separator exists
            if '---TASKS---' in llm_response:
                parts = llm_response.split('---TASKS---')
                spec_content = parts[0].strip()
                tasks_content = parts[1].strip() if len(parts) > 1 else '[]'
            else:
                spec_content = llm_response
                tasks_content = '[]'

            artifacts['spec.md'] = spec_content

            # Try to parse JSON tasks
            try:
                # Extract JSON from the tasks content
                json_match = re.search(r'\[.*\]', tasks_content, re.DOTALL)
                if json_match:
                    tasks = json.loads(json_match.group())
                else:
                    tasks = []
            except Exception as e:
                tasks = []

            artifacts['tasks.json'] = json.dumps(tasks, indent=2)
            artifacts['tasks'] = tasks
            artifacts['summary'] = f'Generated spec with {len(tasks)} tasks'

        elif self.role == AgentRole.CODER:
            # Extract code blocks
            code_blocks = re.findall(r'```[\w]*\n(.*?)```', llm_response, re.DOTALL)

            artifacts['code_changes'] = {
                'description': llm_response,
                'code_blocks': code_blocks
            }
            artifacts['summary'] = 'Implementation complete'

        elif self.role == AgentRole.REVIEWER:
            artifacts['review.md'] = llm_response

            # Try to extract approval status
            if 'approved' in llm_response.lower():
                artifacts['approval_status'] = 'approved'
            elif 'needs-work' in llm_response.lower() or 'needs work' in llm_response.lower():
                artifacts['approval_status'] = 'needs_work'
            else:
                artifacts['approval_status'] = 'pending'

            artifacts['summary'] = f'Review complete - {artifacts["approval_status"]}'

        return artifacts


class SyncLLMPlannerAgent(SyncLLMAgent):
    """Synchronous LLM-powered planner agent."""

    def __init__(self, model_config: Optional[ModelConfig] = None):
        super().__init__(AgentRole.PLANNER, model_config)


class SyncLLMSpecWriterAgent(SyncLLMAgent):
    """Synchronous LLM-powered spec writer agent."""

    def __init__(self, model_config: Optional[ModelConfig] = None):
        super().__init__(AgentRole.SPEC_WRITER, model_config)


class SyncLLMCoderAgent(SyncLLMAgent):
    """Synchronous LLM-powered coder agent."""

    def __init__(self, model_config: Optional[ModelConfig] = None):
        super().__init__(AgentRole.CODER, model_config)


class SyncLLMReviewerAgent(SyncLLMAgent):
    """Synchronous LLM-powered reviewer agent."""

    def __init__(self, model_config: Optional[ModelConfig] = None):
        super().__init__(AgentRole.REVIEWER, model_config)