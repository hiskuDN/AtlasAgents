"""Main orchestrator for AtlasAgents system."""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
import json
import threading
from enum import Enum

from orchestrator.models.database import (
    Database, JobStage, AgentRole, ApprovalStatus, MessageRole
)
from orchestrator.core.state_machine import StateMachine, StateContext, StateTransition
from orchestrator.core.job_manager import JobManager, JobExecutor
from orchestrator.core.config import AtlasConfig, get_config
from orchestrator.utils.paths import PathManager, get_path_manager
from orchestrator.mcp.manager import MCPManager, SimpleMCPManager
from orchestrator.agents.factory import get_factory


logger = logging.getLogger(__name__)


class OrchestratorEvent(str, Enum):
    """Events emitted by the orchestrator."""
    PROJECT_CREATED = "project_created"
    PROJECT_SWITCHED = "project_switched"
    JOB_STARTED = "job_started"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED = "approval_rejected"
    STATE_CHANGED = "state_changed"
    CHECKPOINT_CREATED = "checkpoint_created"
    CHECKPOINT_RESTORED = "checkpoint_restored"


class EventHandler:
    """Handles orchestrator events."""

    def __init__(self):
        self.listeners: Dict[OrchestratorEvent, List[Callable]] = {}
        self._lock = threading.Lock()

    def register(self, event: OrchestratorEvent, handler: Callable):
        """Register an event handler."""
        with self._lock:
            if event not in self.listeners:
                self.listeners[event] = []
            self.listeners[event].append(handler)

    def emit(self, event: OrchestratorEvent, data: Dict[str, Any]):
        """Emit an event to all listeners."""
        with self._lock:
            handlers = self.listeners.get(event, [])

        for handler in handlers:
            try:
                handler(event, data)
            except Exception as e:
                logger.error(f"Error in event handler for {event}: {e}")


class ProjectContext:
    """Manages context for a single project."""

    def __init__(self, project_id: int, project_name: str, workspace_path: Path):
        self.project_id = project_id
        self.project_name = project_name
        self.workspace_path = workspace_path
        self.active_job_id: Optional[int] = None
        self.pending_approval_id: Optional[int] = None
        self.checkpoint_refs: List[str] = []
        self.metadata: Dict[str, Any] = {}

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "workspace_path": str(self.workspace_path),
            "active_job_id": self.active_job_id,
            "pending_approval_id": self.pending_approval_id,
            "checkpoint_refs": self.checkpoint_refs,
            "metadata": self.metadata
        }


class Orchestrator:
    """Main orchestrator that coordinates all components."""

    def __init__(self, config: Optional[AtlasConfig] = None,
                 db_path: Optional[Path] = None,
                 use_mock_mcp: bool = True):
        # Configuration
        self.config = config or get_config()
        self.path_manager = get_path_manager()

        # Database
        self.db = Database(db_path)

        # MCP Manager (use mock for testing)
        if use_mock_mcp:
            self.mcp_manager = SimpleMCPManager(self.config)
        else:
            self.mcp_manager = MCPManager(self.config, self.path_manager, self.db)
            self.mcp_manager.set_database(self.db)

        # Core components
        self.state_machine = StateMachine(self.db)
        # Use agent factory instead of simple function
        agent_factory = get_factory()
        self.job_executor = JobExecutor(self.db, agent_factory)
        self.job_manager = JobManager(self.db, self.state_machine, self.job_executor)

        # Event system
        self.events = EventHandler()

        # Project management
        self.current_project_id: Optional[int] = None
        self.project_contexts: Dict[int, ProjectContext] = {}

        # Register internal event handlers
        self._register_internal_handlers()

        # Start job manager
        self.job_manager.start()

        # Load current project if exists
        self._load_current_project()

        logger.info("Orchestrator initialized")

    def _register_internal_handlers(self):
        """Register internal event handlers."""
        self.events.register(OrchestratorEvent.JOB_COMPLETED, self._on_job_completed)
        self.events.register(OrchestratorEvent.APPROVAL_GRANTED, self._on_approval_granted)
        self.events.register(OrchestratorEvent.STATE_CHANGED, self._on_state_changed)

    def set_agent_factory(self, use_llm: bool = False):
        """Update the agent factory.

        Args:
            use_llm: Whether to use LLM agents
        """
        from orchestrator.agents.factory import AgentFactory
        agent_factory = AgentFactory(use_llm=use_llm)
        self.job_executor.agent_factory = agent_factory
        logger.info(f"Agent factory updated: use_llm={use_llm}")

    def _on_job_completed(self, event: OrchestratorEvent, data: Dict):
        """Handle job completion."""
        job_id = data.get("job_id")
        project_id = data.get("project_id")

        logger.info(f"Job {job_id} completed for project {project_id}")

        # Check if approval is needed
        context = self.state_machine.get_context(project_id)
        if StateTransition.requires_approval(context.current_stage):
            self.request_approval(project_id, job_id)

    def _on_approval_granted(self, event: OrchestratorEvent, data: Dict):
        """Handle approval granted."""
        project_id = data.get("project_id")
        next_stage = data.get("next_stage")

        if next_stage:
            # Transition to next stage
            success, error = self.state_machine.transition(project_id, JobStage(next_stage))
            if success:
                # Start next job
                self.job_manager.enqueue_job(project_id)

    def _on_state_changed(self, event: OrchestratorEvent, data: Dict):
        """Handle state change."""
        project_id = data.get("project_id")
        new_stage = data.get("new_stage")

        logger.info(f"Project {project_id} transitioned to {new_stage}")

        # Update project context
        if project_id in self.project_contexts:
            self.db.update_project_stage(project_id, new_stage)

    def _load_current_project(self):
        """Load the current project from persistent storage."""
        current_name = self.path_manager.get_current_project()
        if current_name:
            # Find project in database
            project = self.db.get_project(name=current_name)
            if project:
                # Set as current without emitting events
                self.current_project_id = project['id']
                context = ProjectContext(
                    project_id=project['id'],
                    project_name=project['name'],
                    workspace_path=Path(project['workspace_path'])
                )
                self.project_contexts[project['id']] = context
                # Restart MCP manager for the project
                if hasattr(self.mcp_manager, 'set_project'):
                    self.mcp_manager.set_project(project['name'], Path(project['workspace_path']))
                logger.info(f"Loaded current project: {current_name}")

    # Project Management

    def create_project(self, name: str) -> int:
        """Create a new project."""
        # Check if project already exists
        existing = self.db.get_project(name=name)
        if existing:
            raise ValueError(f"Project '{name}' already exists")

        # Create project structure
        self.path_manager.create_project_structure(name)
        workspace_path = self.path_manager.get_project_dir(name)

        # Create database entry
        project_id = self.db.create_project(name, str(workspace_path))

        # Initialize project context
        context = ProjectContext(project_id, name, workspace_path)
        self.project_contexts[project_id] = context

        # Initialize state machine for project
        self.state_machine.initialize_project(project_id)

        # Emit event
        self.events.emit(OrchestratorEvent.PROJECT_CREATED, {
            "project_id": project_id,
            "project_name": name,
            "workspace_path": str(workspace_path)
        })

        logger.info(f"Created project '{name}' with ID {project_id}")
        return project_id

    def switch_project(self, name: str) -> bool:
        """Switch to a different project."""
        project = self.db.get_project(name=name)
        if not project:
            logger.error(f"Project '{name}' not found")
            return False

        self.current_project_id = project['id']
        self.path_manager.set_current_project(name)

        # Update MCP paths for the project
        config_path = Path.cwd() / "atlas.config.yaml"
        self.path_manager.update_mcp_paths(name, config_path)

        # Restart MCP manager with new project context
        self.mcp_manager.restart_for_project(name)

        # Load or create project context
        if project['id'] not in self.project_contexts:
            context = ProjectContext(
                project['id'],
                name,
                Path(project['workspace_path'])
            )
            self.project_contexts[project['id']] = context

        # Emit event
        self.events.emit(OrchestratorEvent.PROJECT_SWITCHED, {
            "project_id": project['id'],
            "project_name": name
        })

        logger.info(f"Switched to project '{name}'")
        return True

    def get_current_project(self) -> Optional[ProjectContext]:
        """Get the current project context."""
        if self.current_project_id:
            return self.project_contexts.get(self.current_project_id)
        return None

    def delete_project(self, project_name: str):
        """Delete a project by name."""
        project = self.db.get_project(name=project_name)
        if not project:
            raise ValueError(f"Project '{project_name}' not found")

        project_id = project['id']
        self.db.delete_project(project_id)

        # Also remove workspace directory
        path_manager = get_path_manager()
        project_dir = path_manager.get_project_dir(project_name)
        if project_dir.exists():
            import shutil
            shutil.rmtree(project_dir)

        # If it was the current project, clear it
        current_project = self.path_manager.get_current_project()
        if current_project == project_name:
            self.current_project_id = None
            # Remove from project contexts
            if project_id in self.project_contexts:
                del self.project_contexts[project_id]
            # Clear current project file
            current_file = self.path_manager.config_dir / "current"
            if current_file.exists():
                current_file.unlink()

    # Job Management

    def run_stage(self, stage: Optional[str] = None) -> Optional[int]:
        """Run a specific stage or continue from current stage."""
        if not self.current_project_id:
            logger.error("No project selected")
            return None

        context = self.state_machine.get_context(self.current_project_id)

        # Parse stage if provided
        target_stage = None
        if stage:
            try:
                target_stage = JobStage(stage.upper())
            except ValueError:
                logger.error(f"Invalid stage: {stage}")
                return None

            # Check if transition is valid
            if target_stage != context.current_stage:
                success, error = self.state_machine.transition(
                    self.current_project_id,
                    target_stage
                )
                if not success:
                    logger.error(f"Cannot transition to {stage}: {error}")
                    return None

        # Enqueue job
        job_id = self.job_manager.enqueue_job(self.current_project_id, target_stage)

        if job_id:
            # Update project context
            project_context = self.project_contexts[self.current_project_id]
            project_context.active_job_id = job_id

            # Emit event
            self.events.emit(OrchestratorEvent.JOB_STARTED, {
                "project_id": self.current_project_id,
                "job_id": job_id,
                "stage": context.current_stage.value
            })

        return job_id

    # Approval Management

    def request_approval(self, project_id: int, job_id: int) -> int:
        """Request approval for a job."""
        # Get job details
        job = self.db.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Get preview data (artifacts, diffs, etc.)
        preview_data = self._get_preview_data(job_id)

        # Create approval request in state machine
        approval_id = self.state_machine.request_approval(
            project_id, job_id, preview_data
        )

        # Update project context
        if project_id in self.project_contexts:
            self.project_contexts[project_id].pending_approval_id = approval_id

        # Emit event (will trigger Telegram notification)
        self.events.emit(OrchestratorEvent.APPROVAL_REQUESTED, {
            "project_id": project_id,
            "job_id": job_id,
            "approval_id": approval_id,
            "stage": job['stage'],
            "preview": preview_data
        })

        logger.info(f"Requested approval {approval_id} for job {job_id}")
        return approval_id

    def handle_approval(self, approval_id: int, decision: str, actor: str,
                       reason: Optional[str] = None) -> bool:
        """Handle an approval decision."""
        # Find the approval and associated job in the database
        approval = self.db.get_approval(approval_id=approval_id)
        if not approval:
            logger.error(f"Approval {approval_id} not found")
            return False

        # Get the job to find the project
        job = self.db.get_job(approval['job_id'])
        if not job:
            logger.error(f"Job {approval['job_id']} not found for approval {approval_id}")
            return False

        project_id = job['project_id']

        # Convert decision to enum
        try:
            status = ApprovalStatus(decision.lower())
        except ValueError:
            logger.error(f"Invalid approval decision: {decision}")
            return False

        # Handle in state machine
        success, next_stage = self.state_machine.handle_approval(
            project_id, approval_id, status, actor, reason
        )

        if success:
            # Clear pending approval
            self.project_contexts[project_id].pending_approval_id = None

            # Emit appropriate event
            if status == ApprovalStatus.APPROVED:
                self.events.emit(OrchestratorEvent.APPROVAL_GRANTED, {
                    "project_id": project_id,
                    "approval_id": approval_id,
                    "actor": actor,
                    "next_stage": next_stage.value if next_stage else None
                })
            else:
                self.events.emit(OrchestratorEvent.APPROVAL_REJECTED, {
                    "project_id": project_id,
                    "approval_id": approval_id,
                    "actor": actor,
                    "reason": reason
                })

        return success

    def _get_preview_data(self, job_id: int) -> Dict:
        """Get preview data for a job."""
        # This will be expanded when we implement MCP tools
        # For now, return basic artifact information
        artifacts = []
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM artifacts WHERE job_id = ?",
                (job_id,)
            )
            for row in cursor.fetchall():
                artifacts.append(dict(row))

        return {
            "artifacts": artifacts,
            "timestamp": datetime.now().isoformat()
        }

    # Status and Monitoring

    def get_status(self) -> Dict:
        """Get overall orchestrator status."""
        if not self.current_project_id:
            return {
                "status": "no_project",
                "message": "No project selected"
            }

        # Get project status from state machine
        project_status = self.state_machine.get_status(self.current_project_id)

        # Get job queue status
        queue_status = self.job_manager.get_queue_status()

        # Get project context
        context = self.project_contexts.get(self.current_project_id)

        return {
            "project": project_status,
            "queue": queue_status,
            "context": context.to_dict() if context else None
        }

    def list_projects(self) -> List[Dict]:
        """List all projects."""
        return self.db.list_projects()

    # Lifecycle

    def shutdown(self):
        """Shutdown the orchestrator."""
        logger.info("Shutting down orchestrator")

        # Stop job manager
        self.job_manager.stop()

        # Stop MCP manager
        self.mcp_manager.stop()

        # Save any pending state
        for context in self.project_contexts.values():
            self.db.add_message(
                project_id=context.project_id,
                role=MessageRole.ORCHESTRATOR.value,
                content="Orchestrator shutdown",
                meta={"context": context.to_dict()}
            )

        logger.info("Orchestrator shutdown complete")