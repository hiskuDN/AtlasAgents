"""Synchronous LLM-powered agent implementations."""

import json
import re
import logging
from typing import Any, Dict, Optional
from pathlib import Path

from .base import AgentRole, AgentRequest, AgentResponse
from .base_sync import SyncBaseAgent
from ..llm.model_router import ModelRouter, ModelConfig, ModelProvider
from ..llm.prompts import AgentPrompts

logger = logging.getLogger(__name__)


class SyncLLMAgent(SyncBaseAgent):
    """Synchronous LLM-powered agent."""

    def __init__(self, role: AgentRole, model_config: Optional[ModelConfig] = None):
        """Initialize the LLM agent.

        Args:
            role: Agent role
            model_config: Model configuration
        """
        super().__init__(role)
        # Set reasonable token limits based on role
        max_tokens = {
            AgentRole.PLANNER: 2000,
            AgentRole.SPEC_WRITER: 3000,
            AgentRole.CODER: 2500,
            AgentRole.REVIEWER: 1500
        }.get(role, 2000)

        self.model_config = model_config or ModelConfig(
            provider=ModelProvider.OLLAMA,
            model_name="phi4:latest",
            temperature=0.7,
            max_tokens=max_tokens
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
            try:
                artifacts = self._parse_response(llm_response, request)
            except Exception as e:
                logger.error(f"Failed to parse LLM response: {e}")
                artifacts = {'raw_response': llm_response}

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
        # Get project name and requirements
        workspace_path = Path(request.context.workspace_path)
        project_name = workspace_path.name

        # Read requirements.yaml for actual project requirements
        requirements_content = ""
        req_file = workspace_path / "requirements.yaml"
        if req_file.exists():
            try:
                import yaml
                with open(req_file, 'r') as f:
                    req_data = yaml.safe_load(f)
                    if 'requirements' in req_data:
                        requirements_content = "\n".join(f"- {req}" for req in req_data['requirements'])
                    if 'description' in req_data:
                        requirements_content = f"{req_data['description']}\n\nRequirements:\n{requirements_content}"
                    logger.debug(f"Loaded requirements from {req_file}: {len(requirements_content)} chars")
            except Exception as e:
                logger.warning(f"Failed to parse YAML from {req_file}: {e}")
                requirements_content = req_file.read_text()
        else:
            logger.warning(f"Requirements file not found: {req_file}")

        # Base context with actual project name
        prompt_args = {
            'project_name': project_name,
            'workspace_path': request.context.workspace_path,
            'stage': request.context.stage,
            'context': requirements_content or request.prompt
        }

        # Add role-specific context
        if self.role == AgentRole.PLANNER:
            prompt_args['requirements'] = requirements_content or request.prompt

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

            # Check if there's review feedback (iteration mode)
            review_path = Path(request.context.workspace_path) / "docs" / "review.md"
            if review_path.exists():
                review_content = review_path.read_text()
                # Check if this review contains issues to fix
                if any(term in review_content.lower() for term in ['needs_work', 'needs work', 'major_issues', 'major issues', 'required changes']):
                    prompt_args['review_feedback'] = review_content
                    # Modify the task to focus on fixing review issues
                    prompt_args['task_title'] = 'Fix Review Issues'
                    prompt_args['task_description'] = 'Address all issues identified in the code review and implement the required changes.'
                else:
                    task = request.context.artifacts.get('current_task', {})
                    prompt_args['task_title'] = task.get('title', 'Implementation Task')
                    prompt_args['task_description'] = task.get('description', request.prompt)
            else:
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
            # Since we simplified the prompt, just store the spec
            artifacts['spec.md'] = llm_response.strip()
            artifacts['summary'] = 'Generated technical specification'

            # Create simple default tasks based on spec content
            tasks = [
                {
                    'id': 'task-1',
                    'title': 'Implementation',
                    'description': 'Implement based on specification',
                    'priority': 'high'
                }
            ]
            artifacts['tasks.json'] = json.dumps(tasks, indent=2)
            artifacts['tasks'] = tasks

        elif self.role == AgentRole.CODER:
            # Parse the response to extract file paths and code
            files_created = {}

            # First, clean up the response to remove markdown formatting
            # This helps when LLM outputs "### Creating file: index.html"
            cleaned_response = llm_response.replace('###', '').replace('##', '').replace('#', '')
            cleaned_response = cleaned_response.replace('**', '').replace('*', '')

            # Look for patterns like "Creating file: path/to/file.ext" or "File: path/to/file.ext"
            # followed by code blocks
            # Updated pattern to be more flexible with spacing and punctuation
            pattern = r'(?:Creating file|File|Creating|Modifying)[\s:]*([a-zA-Z0-9_\-/.]+\.\w+).*?```[\w]*\n(.*?)```'
            matches = re.findall(pattern, cleaned_response, re.DOTALL | re.IGNORECASE)

            if matches:
                for filepath, code in matches:
                    # Clean up the filepath - remove any remaining special chars
                    filepath = filepath.strip().strip(':').strip()
                    # Ensure we only get the actual filename, not any surrounding text
                    # In case there's still extra text, extract just the filename part
                    import os
                    filepath = os.path.basename(filepath) if '/' not in filepath else filepath
                    files_created[filepath] = code.strip()
            else:
                # Fallback: try to extract any code blocks
                code_blocks = re.findall(r'```[\w]*\n(.*?)```', llm_response, re.DOTALL)
                if code_blocks:
                    # If we have code but no explicit paths, create default files based on content
                    for i, code in enumerate(code_blocks):
                        # Try to guess the file type from the code
                        if '<html' in code.lower() or '<!doctype' in code.lower():
                            filename = 'index.html' if i == 0 else f'file_{i}.html'
                        elif 'function' in code or 'const' in code or 'let' in code or 'var' in code:
                            filename = 'script.js' if i == 0 else f'script_{i}.js'
                        elif 'body' in code or 'color:' in code or '{' in code:
                            filename = 'styles.css' if 'css' in llm_response.lower() else f'file_{i}.css'
                        else:
                            filename = f'file_{i}.txt'
                        files_created[filename] = code.strip()

            artifacts['code_changes'] = files_created
            artifacts['summary'] = f'Created {len(files_created)} files'
            artifacts['description'] = llm_response

        elif self.role == AgentRole.REVIEWER:
            artifacts['review.md'] = llm_response

            # Parse the structured assessment from the review
            assessment_lower = llm_response.lower()

            # Look for the Overall Assessment section
            if 'overall assessment' in assessment_lower:
                # Extract the assessment value
                if 'approved' in assessment_lower:
                    artifacts['approval_status'] = 'approved'
                elif 'major_issues' in assessment_lower or 'major issues' in assessment_lower:
                    artifacts['approval_status'] = 'major_issues'
                elif 'needs_work' in assessment_lower or 'needs work' in assessment_lower:
                    artifacts['approval_status'] = 'needs_work'
                else:
                    artifacts['approval_status'] = 'pending'
            else:
                # Fallback to simple keyword search
                if 'approved' in assessment_lower and 'not approved' not in assessment_lower:
                    artifacts['approval_status'] = 'approved'
                elif 'needs work' in assessment_lower or 'needs_work' in assessment_lower:
                    artifacts['approval_status'] = 'needs_work'
                else:
                    artifacts['approval_status'] = 'pending'

            # Extract issues count for summary
            critical_count = assessment_lower.count('[critical]')
            major_count = assessment_lower.count('[major]')
            minor_count = assessment_lower.count('[minor]')

            issues_summary = []
            if critical_count > 0:
                issues_summary.append(f"{critical_count} critical")
            if major_count > 0:
                issues_summary.append(f"{major_count} major")
            if minor_count > 0:
                issues_summary.append(f"{minor_count} minor")

            if issues_summary:
                artifacts['summary'] = f"Review complete: {', '.join(issues_summary)} issues found"
            else:
                artifacts['summary'] = f"Review complete: {artifacts['approval_status']}"

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