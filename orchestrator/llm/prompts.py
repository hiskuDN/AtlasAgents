"""Agent prompts for different roles."""

from typing import Dict, Any


class AgentPrompts:
    """Manages prompts for different agent roles."""

    SYSTEM_PROMPTS = {
        "planner": """You are a senior technical architect creating an implementation plan for building an application.
Your role is to analyze the project requirements and create a clear plan for developing the specified application.
Focus on the technical approach, architecture, and implementation strategy for the actual application described in the requirements.
Output should be in markdown format with clear sections.""",

        "spec_writer": """You are a technical specification writer.
Your role is to take high-level plans and create detailed technical specifications.
Include API designs, data models, architecture diagrams (as ASCII art), and acceptance criteria.
Also create a structured list of implementation tasks in JSON format.""",

        "coder": """You are an expert programmer implementing features based on specifications.
Your role is to write clean, maintainable code following best practices.
Focus on one task at a time, ensuring proper error handling and documentation.
Describe the changes you're making and which files are affected.""",

        "reviewer": """You are a senior code reviewer conducting a thorough code review.
Your role is to review code changes for quality, correctness, security, and best practices.
Identify issues, provide constructive feedback, and determine if the code is ready for production.
Verify that the implementation meets all specifications and requirements."""
    }

    TASK_PROMPTS = {
        "planner": """
Create an implementation plan for building the following application:

Project: {project_name}

Requirements:
{requirements}

Additional Context:
{context}

Please provide a plan for BUILDING THIS SPECIFIC APPLICATION with:
1. Overview of the technical architecture
2. Core components needed (e.g., UI, business logic, data handling)
3. Technology choices and rationale
4. Development approach and phases
5. Key features to implement

Focus on planning the actual application development, NOT project management.
Format your response as a markdown document.
""",

        "spec_writer": """
Based on the following plan, create a technical specification for implementing the application.

Project: {project_name}
Plan:
{plan_content}

Additional Context:
{context}

Please provide a concise technical specification with:
1. File structure (what files will be created)
2. Key components and their responsibilities
3. Implementation approach for core functionality
4. User interface design overview
5. Main implementation steps

Focus on the actual application implementation details.
Keep the response focused and under 1500 words.
Format as markdown with clear sections.
""",

        "coder": """
Implement the following task based on the specifications.

Project: {project_name}
Task: {task_title}
Task Description: {task_description}

Specification:
{spec_content}

{review_feedback}

Workspace Path: {workspace_path}

Please implement the complete solution. For each file you create or modify:
1. Clearly state the filename (e.g., "Creating file: index.html")
2. Follow immediately with the complete file contents in a markdown code block

Example format:
Creating file: index.html
```html
<!DOCTYPE html>
<html>
...
</html>
```

Creating file: script.js
```javascript
// JavaScript code here
```

Provide the COMPLETE implementation for all necessary files.
""",

        "reviewer": """
Review the following code implementation for quality and correctness.

Project: {project_name}
Specification:
{spec_content}

Files to Review:
{changes}

Please provide a structured review with the following format:

# Code Review

## Overall Assessment
State one of: APPROVED, NEEDS_WORK, or MAJOR_ISSUES

## Issues Found
List each issue with severity [Critical/Major/Minor]:
- [Severity] File:Line - Description of issue

## Required Changes
For NEEDS_WORK or MAJOR_ISSUES, list specific changes needed:
- File: path/to/file.ext
  - Line X: Specific change required
  - Line Y: Another change required

## Code Quality
- Structure and Organization: [Good/Fair/Poor]
- Readability: [Good/Fair/Poor]
- Error Handling: [Good/Fair/Poor]
- Best Practices: [Good/Fair/Poor]

## Specifications Compliance
- Does the code meet all requirements? [Yes/No]
- If no, what's missing?

## Recommendations
Optional improvements that would enhance the code.

Make the assessment clear and actionable.
"""
    }

    @classmethod
    def get_system_prompt(cls, role) -> str:
        """Get system prompt for a role.

        Args:
            role: Agent role (AgentRole enum or string)

        Returns:
            System prompt string
        """
        # Handle both AgentRole enum and string
        role_str = role.value if hasattr(role, 'value') else str(role)
        return cls.SYSTEM_PROMPTS.get(role_str, "You are a helpful assistant.")

    @classmethod
    def get_task_prompt(cls, role, **kwargs) -> str:
        """Get task prompt for a role.

        Args:
            role: Agent role (AgentRole enum or string)
            **kwargs: Variables to format into prompt

        Returns:
            Formatted task prompt
        """
        # Handle both AgentRole enum and string
        role_str = role.value if hasattr(role, 'value') else str(role)
        template = cls.TASK_PROMPTS.get(role_str, "Complete the following task: {task}")

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
            'changes': 'No changes provided',
            'review_feedback': ''  # Empty by default, filled when in revision mode
        }

        # Merge defaults with provided kwargs
        format_args = {**defaults, **kwargs}

        try:
            return template.format(**format_args)
        except KeyError as e:
            # If a key is missing, return template with error note
            return f"{template}\n\n[Error: Missing variable {e} in prompt template]"