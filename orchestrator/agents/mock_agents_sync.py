"""Synchronous mock agent implementations for testing."""

import json
from typing import Any, Dict

from .base import AgentRole, AgentRequest, AgentResponse
from .base_sync import SyncBaseAgent


class SyncMockPlannerAgent(SyncBaseAgent):
    """Synchronous mock planner agent that returns a predefined plan."""

    def __init__(self):
        super().__init__(AgentRole.PLANNER)

    def execute(self, request: AgentRequest) -> AgentResponse:
        """Generate a mock plan."""
        self.validate_request(request)

        plan_content = """# Implementation Plan

## Overview
This plan outlines the implementation of the requested feature.

## Objectives
1. Implement core functionality
2. Add comprehensive tests
3. Update documentation

## Approach
We'll use a phased approach:
- Phase 1: Core implementation
- Phase 2: Testing and validation
- Phase 3: Documentation and polish

## Timeline
Estimated completion: 2-3 hours

## Risks
- Potential API changes
- Integration complexity
"""

        response = AgentResponse(
            success=True,
            content=plan_content,
            artifacts={
                'plan.md': plan_content,
                'summary': 'Generated implementation plan with 3 phases'
            },
            metadata={
                'agent': self.name,
                'tokens_used': 150  # Mock token count
            }
        )
        response.complete()
        return response


class SyncMockSpecWriterAgent(SyncBaseAgent):
    """Synchronous mock spec writer agent that returns predefined specifications."""

    def __init__(self):
        super().__init__(AgentRole.SPEC_WRITER)

    def execute(self, request: AgentRequest) -> AgentResponse:
        """Generate mock specifications."""
        self.validate_request(request)

        spec_content = """# Technical Specification

## Requirements
- Feature must be performant
- Must maintain backward compatibility
- Should include comprehensive error handling

## Architecture
```
Component A --> Component B --> Output
     |              |
     v              v
  Storage       Logging
```

## API Design
- `POST /api/feature` - Create new feature
- `GET /api/feature/{id}` - Get feature details
- `PUT /api/feature/{id}` - Update feature
- `DELETE /api/feature/{id}` - Remove feature

## Data Model
```json
{
  "id": "string",
  "name": "string",
  "status": "active|inactive",
  "metadata": {}
}
```

## Testing Strategy
- Unit tests for all components
- Integration tests for API endpoints
- Performance benchmarks
"""

        tasks = [
            {
                "id": "task-1",
                "title": "Implement core data model",
                "description": "Create the base data structures",
                "priority": "high",
                "estimated_hours": 2
            },
            {
                "id": "task-2",
                "title": "Build API endpoints",
                "description": "Implement REST API",
                "priority": "high",
                "estimated_hours": 3
            },
            {
                "id": "task-3",
                "title": "Add validation logic",
                "description": "Input validation and error handling",
                "priority": "medium",
                "estimated_hours": 2
            },
            {
                "id": "task-4",
                "title": "Write tests",
                "description": "Unit and integration tests",
                "priority": "high",
                "estimated_hours": 3
            }
        ]

        response = AgentResponse(
            success=True,
            content=spec_content,
            artifacts={
                'spec.md': spec_content,
                'tasks.json': json.dumps(tasks, indent=2),
                'tasks': tasks,
                'summary': f'Generated spec with {len(tasks)} tasks'
            },
            metadata={
                'agent': self.name,
                'task_count': len(tasks),
                'tokens_used': 350
            }
        )
        response.complete()
        return response


class SyncMockCoderAgent(SyncBaseAgent):
    """Synchronous mock coder agent that returns code changes."""

    def __init__(self):
        super().__init__(AgentRole.CODER)

    def execute(self, request: AgentRequest) -> AgentResponse:
        """Generate mock code changes."""
        self.validate_request(request)

        # Get task from context if available
        task = request.context.artifacts.get('current_task', {})
        task_id = task.get('id', 'unknown')

        code_changes = {
            'created_files': [
                'src/feature/model.py',
                'src/feature/api.py',
                'tests/test_feature.py'
            ],
            'modified_files': [
                'src/main.py',
                'requirements.txt'
            ],
            'changes': [
                {
                    'file': 'src/feature/model.py',
                    'action': 'create',
                    'content': '''"""Feature model implementation."""

class Feature:
    def __init__(self, id: str, name: str):
        self.id = id
        self.name = name
        self.status = "active"

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status
        }
'''
                },
                {
                    'file': 'src/main.py',
                    'action': 'modify',
                    'hunks': [
                        {
                            'old': 'from src import app',
                            'new': 'from src import app\nfrom src.feature import api'
                        }
                    ]
                }
            ]
        }

        response = AgentResponse(
            success=True,
            content=f"Implemented task {task_id}: Created 3 files, modified 2 files",
            artifacts={
                'code_changes': code_changes,
                'summary': f'Task {task_id} implementation complete',
                'files_created': code_changes['created_files'],
                'files_modified': code_changes['modified_files']
            },
            tool_calls=[
                {
                    'tool': 'filesystem.write',
                    'args': {'path': 'src/feature/model.py'},
                    'result': 'success'
                },
                {
                    'tool': 'filesystem.edit',
                    'args': {'path': 'src/main.py'},
                    'result': 'success'
                }
            ],
            metadata={
                'agent': self.name,
                'task_id': task_id,
                'tokens_used': 500,
                'files_touched': 5
            }
        )
        response.complete()
        return response


class SyncMockReviewerAgent(SyncBaseAgent):
    """Synchronous mock reviewer agent that provides code review."""

    def __init__(self):
        super().__init__(AgentRole.REVIEWER)

    def execute(self, request: AgentRequest) -> AgentResponse:
        """Generate mock code review."""
        self.validate_request(request)

        review_content = """# Code Review

## Summary
The implementation looks good overall with minor suggestions for improvement.

## Strengths ✅
- Clean code structure
- Good error handling
- Comprehensive test coverage
- Follows project conventions

## Suggestions 🔍

### 1. Performance Optimization
**File:** `src/feature/api.py`
**Line:** 45-52
```python
# Current
for item in items:
    process(item)

# Suggested
# Use batch processing for better performance
process_batch(items)
```

### 2. Add Type Hints
**File:** `src/feature/model.py`
**Line:** 12
```python
# Current
def calculate(value):

# Suggested
def calculate(value: float) -> float:
```

### 3. Improve Error Messages
**File:** `src/feature/api.py`
**Line:** 78
Consider adding more context to error messages for easier debugging.

## Testing Coverage
- Unit tests: ✅ 95%
- Integration tests: ✅ 88%
- Edge cases: ✅ Covered

## Security Check
- No hardcoded credentials ✅
- Input validation present ✅
- SQL injection protection ✅

## Final Verdict
**APPROVED** with minor suggestions

The code is ready for merge after addressing the optional improvements.
"""

        response = AgentResponse(
            success=True,
            content=review_content,
            artifacts={
                'review.md': review_content,
                'approval_status': 'approved_with_suggestions',
                'issues_found': 3,
                'severity': 'minor',
                'test_coverage': {
                    'unit': 95,
                    'integration': 88
                }
            },
            metadata={
                'agent': self.name,
                'tokens_used': 400,
                'review_duration_seconds': 15
            }
        )
        response.complete()
        return response