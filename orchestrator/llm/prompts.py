"""Agent prompts for different roles."""

from typing import Dict, Any
from ..agents.base import AgentRole


class AgentPrompts:
    """Manages prompts for different agent roles."""

    SYSTEM_PROMPTS = {
        AgentRole.PLANNER: """You are a senior technical architect creating implementation plans.
Your role is to analyze requirements and create clear, actionable plans.
Focus on practical implementation steps, identifying risks, and suggesting approaches.
Output should be in markdown format with clear sections.""",

        AgentRole.SPEC_WRITER: """You are a technical specification writer.
Your role is to take high-level plans and create detailed technical specifications.
Include API designs, data models, architecture diagrams (as ASCII art), and acceptance criteria.
Also create a structured list of implementation tasks in JSON format.""",

        AgentRole.CODER: """You are an expert programmer implementing features based on specifications.
Your role is to write clean, maintainable code following best practices.
Focus on one task at a time, ensuring proper error handling and documentation.
Describe the changes you're making and which files are affected.""",

        AgentRole.REVIEWER: """You are a senior code reviewer.
Your role is to review code changes for quality, security, and best practices.
Provide constructive feedback, identify potential issues, and suggest improvements.
Also verify that the implementation meets the specifications."""
    }

    TASK_PROMPTS = {
        AgentRole.PLANNER: """
Given the following project context and requirements, create an implementation plan.

Project: {project_name}
Workspace: {workspace_path}
Current Stage: {stage}

Requirements:
{requirements}

Additional Context:
{context}

Please provide:
1. An overview of the implementation approach
2. Key objectives and goals
3. Phases or milestones
4. Potential risks and mitigation strategies
5. Estimated timeline

Format your response as a markdown document with clear sections.
""",

        AgentRole.SPEC_WRITER: """
Based on the following plan, create detailed technical specifications.

Project: {project_name}
Plan:
{plan_content}

Additional Context:
{context}

Please provide:
1. Technical requirements
2. Architecture design (include ASCII diagrams if helpful)
3. API specifications (if applicable)
4. Data models and schemas
5. Implementation tasks as a JSON array with this structure:
   [{{"id": "task-1", "title": "...", "description": "...", "priority": "high|medium|low", "estimated_hours": N}}]

Create two outputs:
1. A markdown specification document
2. A JSON tasks list

Start with the markdown spec, then provide the JSON tasks after a separator line "---TASKS---".
""",

        AgentRole.CODER: """
Implement the following task based on the specifications.

Project: {project_name}
Task: {task_title}
Task Description: {task_description}

Specification:
{spec_content}

Workspace Path: {workspace_path}

Please:
1. Analyze the task requirements
2. Identify which files need to be created or modified
3. Implement the solution
4. Describe the changes you're making

Format your response as:
1. Brief summary of what you're implementing
2. List of files being created/modified
3. The actual code changes
4. Any additional notes or considerations

Use markdown code blocks for code snippets.
""",

        AgentRole.REVIEWER: """
Review the following code changes for quality and correctness.

Project: {project_name}
Specification:
{spec_content}

Code Changes:
{changes}

Please provide:
1. Overall assessment (approved/needs-work)
2. Code quality review (structure, readability, maintainability)
3. Security considerations
4. Performance considerations
5. Specific suggestions for improvement
6. Verification that specifications are met

Format as a markdown document with clear sections.
"""
    }

    @classmethod
    def get_system_prompt(cls, role: AgentRole) -> str:
        """Get system prompt for a role.

        Args:
            role: Agent role

        Returns:
            System prompt string
        """
        return cls.SYSTEM_PROMPTS.get(role, "You are a helpful assistant.")

    @classmethod
    def get_task_prompt(cls, role: AgentRole, **kwargs) -> str:
        """Get task prompt for a role.

        Args:
            role: Agent role
            **kwargs: Variables to format into prompt

        Returns:
            Formatted task prompt
        """
        template = cls.TASK_PROMPTS.get(role, "Complete the following task: {task}")

        # Provide defaults for common variables
        defaults = {
            'project_name': 'Unknown Project',
            'workspace_path': '/workspace',
            'stage': 'unknown',
            'requirements': 'No specific requirements provided',
            'context': '',
            'plan_content': '',
            'spec_content': '',
            'task_title': 'Task',
            'task_description': 'No description provided',
            'changes': 'No changes provided'
        }

        # Merge defaults with provided kwargs
        format_args = {**defaults, **kwargs}

        try:
            return template.format(**format_args)
        except KeyError as e:
            # If a key is missing, return template with error note
            return f"{template}\n\n[Error: Missing variable {e} in prompt template]"