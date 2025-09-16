"""Job management system for orchestrating agent tasks."""

import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from dataclasses import dataclass, field
import logging
from queue import Queue, PriorityQueue
import threading

from orchestrator.models.database import Database, JobStage, AgentRole
from orchestrator.core.state_machine import StateMachine, StateContext


logger = logging.getLogger(__name__)


@dataclass(order=True)
class JobTask:
    """Represents a task in the job queue."""
    priority: int
    project_id: int = field(compare=False)
    stage: JobStage = field(compare=False)
    agent: AgentRole = field(compare=False)
    job_id: Optional[int] = field(compare=False, default=None)
    retry_count: int = field(compare=False, default=0)
    max_retries: int = field(compare=False, default=3)
    metadata: Dict[str, Any] = field(compare=False, default_factory=dict)


class JobExecutor:
    """Executes individual jobs with an agent."""

    def __init__(self, db: Database, agent_factory: Optional[Callable] = None):
        self.db = db
        self.agent_factory = agent_factory
        self._running_jobs: Dict[int, threading.Thread] = {}

    def execute(self, task: JobTask) -> Dict[str, Any]:
        """
        Execute a job task.

        Returns:
            Result dictionary with status and output
        """
        logger.info(f"Executing job {task.job_id} for project {task.project_id}")

        try:
            # Update job status
            self.db.update_job(task.job_id, status="running")

            # Get input artifacts for the agent
            input_data = self._prepare_input(task)

            # Execute with the appropriate agent
            if self.agent_factory:
                agent = self.agent_factory(task.agent)
                result = agent.execute(input_data)
            else:
                # Mock execution for testing
                result = self._mock_execute(task, input_data)

            # Store output artifacts
            output_refs = self._store_outputs(task, result)

            # Update job with results
            self.db.update_job(
                task.job_id,
                status="completed",
                output_ref=json.dumps(output_refs)
            )

            logger.info(f"Job {task.job_id} completed successfully")
            return {
                "status": "success",
                "output_refs": output_refs,
                "result": result
            }

        except Exception as e:
            logger.error(f"Job {task.job_id} failed: {str(e)}")
            self.db.update_job(task.job_id, status="failed")

            return {
                "status": "failed",
                "error": str(e)
            }

    def _prepare_input(self, task: JobTask) -> Dict[str, Any]:
        """Prepare input data for an agent based on the stage."""
        project = self.db.get_project(project_id=task.project_id)
        project_dir = Path(project['workspace_path'])

        input_data = {
            "project_id": task.project_id,
            "project_name": project['name'],
            "workspace_path": str(project_dir),
            "stage": task.stage.value,
        }

        # Add stage-specific inputs
        if task.stage == JobStage.PLAN:
            # Planner needs README, requirements, and ATLAS.md
            input_data["files"] = {
                "readme": str(project_dir / "README.md"),
                "requirements": str(project_dir / "requirements.yaml"),
                "atlas_md": str(project_dir / ".atlas" / "ATLAS.md")
            }

        elif task.stage == JobStage.SPEC:
            # Spec writer needs plan.md
            input_data["files"] = {
                "plan": str(project_dir / "docs" / "plan.md")
            }

        elif task.stage == JobStage.CODE:
            # Coder needs spec.md and tasks.json
            input_data["files"] = {
                "spec": str(project_dir / "docs" / "spec.md"),
                "tasks": str(project_dir / "docs" / "tasks.json")
            }

        elif task.stage == JobStage.REVIEW:
            # Reviewer needs diff and spec.md
            input_data["files"] = {
                "spec": str(project_dir / "docs" / "spec.md"),
                "diff": str(project_dir / ".internal" / "diffs" / "latest.diff")
            }

        return input_data

    def _store_outputs(self, task: JobTask, result: Dict) -> Dict[str, str]:
        """Store agent outputs as artifacts."""
        project = self.db.get_project(project_id=task.project_id)
        project_dir = Path(project['workspace_path'])

        output_refs = {}

        # Store stage-specific outputs
        if task.stage == JobStage.PLAN and "plan" in result:
            plan_path = project_dir / "docs" / "plan.md"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(result["plan"])
            output_refs["plan"] = str(plan_path)

            self.db.create_artifact(
                job_id=task.job_id,
                path=str(plan_path),
                artifact_type="document"
            )

        elif task.stage == JobStage.SPEC:
            if "spec" in result:
                spec_path = project_dir / "docs" / "spec.md"
                spec_path.write_text(result["spec"])
                output_refs["spec"] = str(spec_path)

                self.db.create_artifact(
                    job_id=task.job_id,
                    path=str(spec_path),
                    artifact_type="document"
                )

            if "tasks" in result:
                tasks_path = project_dir / "docs" / "tasks.json"
                tasks_path.write_text(json.dumps(result["tasks"], indent=2))
                output_refs["tasks"] = str(tasks_path)

                self.db.create_artifact(
                    job_id=task.job_id,
                    path=str(tasks_path),
                    artifact_type="data"
                )

        return output_refs

    def _mock_execute(self, task: JobTask, input_data: Dict) -> Dict:
        """Mock execution for testing."""
        import time
        time.sleep(1)  # Simulate work

        if task.stage == JobStage.PLAN:
            return {
                "plan": f"# Plan for {input_data['project_name']}\n\n## Overview\nMocked plan content\n"
            }
        elif task.stage == JobStage.SPEC:
            return {
                "spec": f"# Specification\n\nMocked spec content\n",
                "tasks": {
                    "tasks": [
                        {
                            "id": "task-1",
                            "title": "Mock task",
                            "files": ["src/main.py"],
                            "acceptance": ["Tests pass"]
                        }
                    ]
                }
            }

        return {"status": "mocked"}


class JobManager:
    """Manages job queue and execution."""

    def __init__(self, db: Database, state_machine: StateMachine,
                 executor: Optional[JobExecutor] = None):
        self.db = db
        self.state_machine = state_machine
        self.executor = executor or JobExecutor(db)

        # Priority queue for jobs (lower number = higher priority)
        self.job_queue: PriorityQueue = PriorityQueue()

        # Track active jobs per project
        self.active_jobs: Dict[int, JobTask] = {}

        # Worker thread
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

    def start(self):
        """Start the job manager worker."""
        if self._worker_thread and self._worker_thread.is_alive():
            logger.warning("Job manager already running")
            return

        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        logger.info("Job manager started")

    def stop(self):
        """Stop the job manager worker."""
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        logger.info("Job manager stopped")

    def _worker_loop(self):
        """Main worker loop for processing jobs."""
        while not self._stop_event.is_set():
            try:
                # Get next job with timeout to allow checking stop event
                task = self.job_queue.get(timeout=1)

                # Check if project already has an active job
                if task.project_id in self.active_jobs:
                    # Re-queue with lower priority
                    task.priority += 10
                    self.job_queue.put(task)
                    continue

                # Mark as active
                self.active_jobs[task.project_id] = task

                # Execute the job
                try:
                    result = self.executor.execute(task)

                    # Handle result
                    if result["status"] == "success":
                        self._handle_success(task, result)
                    else:
                        self._handle_failure(task, result)

                finally:
                    # Remove from active jobs
                    self.active_jobs.pop(task.project_id, None)

            except:
                # Queue is empty, continue
                continue

    def _handle_success(self, task: JobTask, result: Dict):
        """Handle successful job completion."""
        logger.info(f"Job {task.job_id} succeeded")

        # Check if stage requires approval
        if task.stage in [JobStage.PLAN, JobStage.SPEC, JobStage.CODE, JobStage.REVIEW]:
            # Request approval (this would trigger Telegram notification)
            self.state_machine.request_approval(
                project_id=task.project_id,
                job_id=task.job_id,
                preview_data=result.get("output_refs", {})
            )
        else:
            # Auto-transition to next stage
            next_stage = self._get_next_stage(task.stage)
            if next_stage:
                self.state_machine.transition(task.project_id, next_stage)
                self.enqueue_job(task.project_id, next_stage)

    def _handle_failure(self, task: JobTask, result: Dict):
        """Handle job failure."""
        logger.error(f"Job {task.job_id} failed: {result.get('error')}")

        # Retry logic
        if task.retry_count < task.max_retries:
            task.retry_count += 1
            task.priority += 5  # Lower priority for retries
            logger.info(f"Retrying job {task.job_id} (attempt {task.retry_count})")
            self.job_queue.put(task)
        else:
            # Max retries exceeded
            self.state_machine.handle_error(
                task.project_id,
                f"Job failed after {task.max_retries} retries: {result.get('error')}"
            )

    def _get_next_stage(self, current: JobStage) -> Optional[JobStage]:
        """Get next stage in workflow."""
        stage_map = {
            JobStage.IDEA: JobStage.PLAN,
            JobStage.PLAN: JobStage.SPEC,
            JobStage.SPEC: JobStage.CODE,
            JobStage.CODE: JobStage.REVIEW,
            JobStage.REVIEW: JobStage.DONE
        }
        return stage_map.get(current)

    def enqueue_job(self, project_id: int, stage: Optional[JobStage] = None,
                   priority: int = 5) -> Optional[int]:
        """
        Enqueue a job for execution.

        Returns:
            job_id if created
        """
        # Get current stage if not specified
        context = self.state_machine.get_context(project_id)
        if not stage:
            stage = context.current_stage

        # Get agent for stage
        agent = self.state_machine.StateTransition.get_agent_for_stage(stage)
        if not agent:
            logger.error(f"No agent for stage {stage}")
            return None

        # Create job in database
        job_id = self.state_machine.start_stage(project_id)
        if not job_id:
            return None

        # Create task and enqueue
        task = JobTask(
            priority=priority,
            project_id=project_id,
            stage=stage,
            agent=agent,
            job_id=job_id
        )

        self.job_queue.put(task)
        logger.info(f"Enqueued job {job_id} for project {project_id} at stage {stage}")

        return job_id

    def get_queue_status(self) -> Dict:
        """Get current queue status."""
        return {
            "queue_size": self.job_queue.qsize(),
            "active_jobs": len(self.active_jobs),
            "active_projects": list(self.active_jobs.keys()),
            "worker_alive": self._worker_thread.is_alive() if self._worker_thread else False
        }