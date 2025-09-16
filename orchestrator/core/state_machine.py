"""State machine for AtlasAgents orchestration."""

from enum import Enum
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from datetime import datetime
import logging

from orchestrator.models.database import Database, JobStage, AgentRole, ApprovalStatus


logger = logging.getLogger(__name__)


class StateTransition:
    """Defines valid state transitions and their rules."""

    # Define valid transitions: from_state -> [allowed_to_states]
    TRANSITIONS: Dict[JobStage, List[JobStage]] = {
        JobStage.IDEA: [JobStage.PLAN, JobStage.STOPPED],
        JobStage.PLAN: [JobStage.SPEC, JobStage.HOLD, JobStage.STOPPED, JobStage.ERROR],
        JobStage.SPEC: [JobStage.CODE, JobStage.PLAN, JobStage.HOLD, JobStage.STOPPED, JobStage.ERROR],
        JobStage.CODE: [JobStage.REVIEW, JobStage.SPEC, JobStage.HOLD, JobStage.STOPPED, JobStage.ERROR],
        JobStage.REVIEW: [JobStage.DONE, JobStage.CODE, JobStage.HOLD, JobStage.STOPPED, JobStage.ERROR],
        JobStage.DONE: [],  # Terminal state
        JobStage.HOLD: [JobStage.PLAN, JobStage.SPEC, JobStage.CODE, JobStage.REVIEW, JobStage.STOPPED],
        JobStage.STOPPED: [],  # Terminal state
        JobStage.ERROR: [JobStage.PLAN, JobStage.SPEC, JobStage.CODE, JobStage.REVIEW, JobStage.STOPPED]
    }

    # Define which agent is responsible for each stage
    STAGE_AGENTS: Dict[JobStage, AgentRole] = {
        JobStage.PLAN: AgentRole.PLANNER,
        JobStage.SPEC: AgentRole.SPEC_WRITER,
        JobStage.CODE: AgentRole.CODER,
        JobStage.REVIEW: AgentRole.REVIEWER,
    }

    # Stages that require approval before proceeding
    APPROVAL_REQUIRED: Set[JobStage] = {
        JobStage.PLAN, JobStage.SPEC, JobStage.CODE, JobStage.REVIEW
    }

    @classmethod
    def is_valid_transition(cls, from_stage: JobStage, to_stage: JobStage) -> bool:
        """Check if a transition is valid."""
        allowed = cls.TRANSITIONS.get(from_stage, [])
        return to_stage in allowed

    @classmethod
    def get_agent_for_stage(cls, stage: JobStage) -> Optional[AgentRole]:
        """Get the agent responsible for a stage."""
        return cls.STAGE_AGENTS.get(stage)

    @classmethod
    def requires_approval(cls, stage: JobStage) -> bool:
        """Check if a stage requires approval."""
        return stage in cls.APPROVAL_REQUIRED

    @classmethod
    def is_terminal(cls, stage: JobStage) -> bool:
        """Check if a stage is terminal."""
        return stage in [JobStage.DONE, JobStage.STOPPED]


@dataclass
class StateContext:
    """Context for state machine operations."""
    project_id: int
    current_stage: JobStage
    job_id: Optional[int] = None
    pending_approval_id: Optional[int] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict] = None


class StateMachine:
    """Main state machine for orchestrating agent workflow."""

    def __init__(self, db: Database):
        self.db = db
        self.contexts: Dict[int, StateContext] = {}  # project_id -> context

    def initialize_project(self, project_id: int) -> StateContext:
        """Initialize state machine for a project."""
        project = self.db.get_project(project_id=project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        stage = JobStage(project.get('current_stage', JobStage.IDEA.value))
        context = StateContext(
            project_id=project_id,
            current_stage=stage
        )
        self.contexts[project_id] = context

        logger.info(f"Initialized state machine for project {project_id} at stage {stage}")
        return context

    def get_context(self, project_id: int) -> StateContext:
        """Get or create context for a project."""
        if project_id not in self.contexts:
            return self.initialize_project(project_id)
        return self.contexts[project_id]

    def transition(self, project_id: int, to_stage: JobStage,
                  reason: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """
        Attempt to transition to a new stage.

        Returns:
            (success, error_message)
        """
        context = self.get_context(project_id)

        # Check if transition is valid
        if not StateTransition.is_valid_transition(context.current_stage, to_stage):
            error = f"Invalid transition from {context.current_stage} to {to_stage}"
            logger.warning(error)
            return False, error

        # Check if current stage has pending approvals
        if context.pending_approval_id:
            approvals = self.db.get_pending_approvals(project_id)
            if approvals:
                error = "Cannot transition with pending approvals"
                logger.warning(error)
                return False, error

        # Update context and database
        old_stage = context.current_stage
        context.current_stage = to_stage
        self.db.update_project_stage(project_id, to_stage.value)

        # Log the transition
        self.db.add_message(
            project_id=project_id,
            role="orchestrator",
            content=f"Transitioned from {old_stage} to {to_stage}",
            meta={"reason": reason} if reason else None
        )

        logger.info(f"Project {project_id} transitioned from {old_stage} to {to_stage}")
        return True, None

    def start_stage(self, project_id: int) -> Optional[int]:
        """
        Start work on the current stage.

        Returns:
            job_id if created, None if stage cannot be started
        """
        context = self.get_context(project_id)

        # Check if stage is terminal
        if StateTransition.is_terminal(context.current_stage):
            logger.warning(f"Cannot start work on terminal stage {context.current_stage}")
            return None

        # Check if stage needs an agent
        agent = StateTransition.get_agent_for_stage(context.current_stage)
        if not agent:
            logger.warning(f"No agent defined for stage {context.current_stage}")
            return None

        # Create a new job
        job_id = self.db.create_job(
            project_id=project_id,
            stage=context.current_stage.value,
            agent=agent.value
        )

        context.job_id = job_id

        self.db.add_message(
            project_id=project_id,
            role="orchestrator",
            content=f"Started {context.current_stage} stage with {agent.value}",
            meta={"job_id": job_id}
        )

        logger.info(f"Started job {job_id} for project {project_id} at stage {context.current_stage}")
        return job_id

    def request_approval(self, project_id: int, job_id: int,
                        preview_data: Dict) -> int:
        """
        Request approval for a job's output.

        Returns:
            approval_id
        """
        context = self.get_context(project_id)

        # Create approval record
        approval_id = self.db.create_approval(
            job_id=job_id,
            status=ApprovalStatus.PENDING.value
        )

        context.pending_approval_id = approval_id

        self.db.add_message(
            project_id=project_id,
            role="orchestrator",
            content=f"Requesting approval for {context.current_stage} stage",
            meta={
                "job_id": job_id,
                "approval_id": approval_id,
                "preview": preview_data
            }
        )

        logger.info(f"Created approval request {approval_id} for job {job_id}")
        return approval_id

    def handle_approval(self, project_id: int, approval_id: int,
                       status: ApprovalStatus, actor: str,
                       reason: Optional[str] = None) -> Tuple[bool, Optional[JobStage]]:
        """
        Handle an approval decision.

        Returns:
            (success, next_stage) - next_stage is set if auto-transition should happen
        """
        context = self.get_context(project_id)

        # Update approval record
        self.db.create_approval(
            job_id=context.job_id,
            status=status.value,
            actor=actor,
            reason=reason
        )

        # Clear pending approval
        context.pending_approval_id = None

        # Handle based on status
        if status == ApprovalStatus.APPROVED:
            # Determine next stage
            next_stage = self._get_next_stage(context.current_stage)

            self.db.add_message(
                project_id=project_id,
                role="orchestrator",
                content=f"Approval granted for {context.current_stage} stage",
                meta={
                    "approval_id": approval_id,
                    "actor": actor,
                    "next_stage": next_stage.value if next_stage else None
                }
            )

            # Mark job as completed
            if context.job_id:
                self.db.update_job(context.job_id, status="completed")

            logger.info(f"Approval {approval_id} granted by {actor}")
            return True, next_stage

        elif status == ApprovalStatus.REVISE:
            # Stay in current stage for revision
            self.db.add_message(
                project_id=project_id,
                role="orchestrator",
                content=f"Revision requested for {context.current_stage} stage",
                meta={
                    "approval_id": approval_id,
                    "actor": actor,
                    "reason": reason
                }
            )

            logger.info(f"Approval {approval_id} requires revision")
            return True, None

        elif status == ApprovalStatus.STOPPED:
            # Transition to STOPPED state
            self.transition(project_id, JobStage.STOPPED, reason=f"Stopped by {actor}")

            logger.info(f"Approval {approval_id} stopped the workflow")
            return True, JobStage.STOPPED

        return False, None

    def _get_next_stage(self, current: JobStage) -> Optional[JobStage]:
        """Get the natural next stage in the workflow."""
        stage_order = [
            JobStage.IDEA,
            JobStage.PLAN,
            JobStage.SPEC,
            JobStage.CODE,
            JobStage.REVIEW,
            JobStage.DONE
        ]

        try:
            current_idx = stage_order.index(current)
            if current_idx < len(stage_order) - 1:
                return stage_order[current_idx + 1]
        except ValueError:
            pass

        return None

    def handle_error(self, project_id: int, error_message: str) -> None:
        """Handle an error in the workflow."""
        context = self.get_context(project_id)

        # Transition to ERROR state
        self.transition(project_id, JobStage.ERROR, reason=error_message)
        context.error_message = error_message

        # Mark job as failed
        if context.job_id:
            self.db.update_job(context.job_id, status="failed")

        self.db.add_message(
            project_id=project_id,
            role="orchestrator",
            content=f"Error in {context.current_stage} stage: {error_message}",
            meta={"job_id": context.job_id}
        )

        logger.error(f"Error in project {project_id}: {error_message}")

    def get_status(self, project_id: int) -> Dict:
        """Get current status of a project."""
        context = self.get_context(project_id)
        project = self.db.get_project(project_id=project_id)

        # Get active job
        active_job = None
        if context.job_id:
            active_job = self.db.get_job(context.job_id)

        # Get pending approvals
        pending_approvals = self.db.get_pending_approvals(project_id)

        # Get latest checkpoint
        checkpoint = self.db.get_latest_checkpoint(project_id)

        return {
            "project": project,
            "current_stage": context.current_stage.value,
            "is_terminal": StateTransition.is_terminal(context.current_stage),
            "active_job": active_job,
            "pending_approvals": pending_approvals,
            "latest_checkpoint": checkpoint,
            "error": context.error_message,
            "can_transitions": [
                s.value for s in StateTransition.TRANSITIONS.get(context.current_stage, [])
            ]
        }