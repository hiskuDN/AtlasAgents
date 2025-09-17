"""SQLite database management for AtlasAgents."""

import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from contextlib import contextmanager
from enum import Enum


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class JobStage(str, Enum):
    IDEA = "IDEA"
    PLAN = "PLAN"
    SPEC = "SPEC"
    CODE = "CODE"
    REVIEW = "REVIEW"
    DONE = "DONE"
    HOLD = "HOLD"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class AgentRole(str, Enum):
    PLANNER = "planner"
    SPEC_WRITER = "spec_writer"
    CODER = "coder"
    REVIEWER = "reviewer"
    PM = "pm"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REVISE = "revise"
    STOPPED = "stopped"


class MessageRole(str, Enum):
    USER = "user"
    SYSTEM = "system"
    AGENT = "agent"
    TOOL = "tool"
    ORCHESTRATOR = "orchestrator"
    TELEGRAM = "telegram"


class Database:
    """SQLite database manager for AtlasAgents."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Path.home() / ".atlas" / "atlas.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database schema."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Projects table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    workspace_path TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    current_stage TEXT DEFAULT 'IDEA',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Jobs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    stage TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    input_ref TEXT,
                    output_ref TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                )
            """)

            # Approvals table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS approvals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT,
                    actor TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (job_id) REFERENCES jobs(id)
                )
            """)

            # Messages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    meta TEXT,  -- JSON string
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                )
            """)

            # Artifacts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    type TEXT NOT NULL,
                    sha TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (job_id) REFERENCES jobs(id)
                )
            """)

            # Tool calls table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tool_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    server TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    params TEXT,  -- JSON string
                    preview TEXT,  -- JSON string
                    executed INTEGER DEFAULT 0,
                    result TEXT,  -- JSON string
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (job_id) REFERENCES jobs(id)
                )
            """)

            # Checkpoints table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    ref TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                )
            """)

            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_project ON messages(project_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_approvals_job ON approvals(job_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_job ON artifacts(job_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tool_calls_job ON tool_calls(job_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_checkpoints_project ON checkpoints(project_id)")

    # Project operations
    def create_project(self, name: str, workspace_path: str) -> int:
        """Create a new project."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO projects (name, workspace_path) VALUES (?, ?)",
                (name, workspace_path)
            )
            return cursor.lastrowid

    def get_project(self, project_id: Optional[int] = None, name: Optional[str] = None) -> Optional[Dict]:
        """Get project by ID or name."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if project_id:
                cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
            elif name:
                cursor.execute("SELECT * FROM projects WHERE name = ?", (name,))
            else:
                return None

            row = cursor.fetchone()
            return dict(row) if row else None

    def update_project_stage(self, project_id: int, stage: str) -> None:
        """Update project's current stage."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE projects SET current_stage = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (stage, project_id)
            )

    def list_projects(self) -> List[Dict]:
        """List all projects."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM projects ORDER BY updated_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def delete_project(self, project_id: int):
        """Delete a project and all its related data."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # This will cascade delete related jobs, approvals, etc.
            cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.commit()

    # Job operations
    def create_job(self, project_id: int, stage: str, agent: str) -> int:
        """Create a new job."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO jobs (project_id, stage, agent) VALUES (?, ?, ?)",
                (project_id, stage, agent)
            )
            return cursor.lastrowid

    def update_job(self, job_id: int, **kwargs) -> None:
        """Update job fields."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            fields = []
            values = []
            for key, value in kwargs.items():
                if key in ['status', 'input_ref', 'output_ref']:
                    fields.append(f"{key} = ?")
                    values.append(value)

            if fields:
                values.append(job_id)
                query = f"UPDATE jobs SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
                cursor.execute(query, values)

    def get_job(self, job_id: int) -> Optional[Dict]:
        """Get job by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_active_job(self, project_id: int) -> Optional[Dict]:
        """Get the active job for a project."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM jobs WHERE project_id = ? AND status = 'active' ORDER BY created_at DESC LIMIT 1",
                (project_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    # Approval operations
    def create_approval(self, job_id: int, status: str, reason: Optional[str] = None, actor: Optional[str] = None) -> int:
        """Create an approval record."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO approvals (job_id, status, reason, actor) VALUES (?, ?, ?, ?)",
                (job_id, status, reason, actor)
            )
            return cursor.lastrowid

    def get_pending_approvals(self, project_id: int) -> List[Dict]:
        """Get pending approvals for a project."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.*, j.stage, j.agent
                FROM approvals a
                JOIN jobs j ON a.job_id = j.id
                WHERE j.project_id = ? AND a.status = 'pending'
                ORDER BY a.created_at DESC
            """, (project_id,))
            return [dict(row) for row in cursor.fetchall()]

    # Message operations
    def add_message(self, project_id: int, role: str, content: str, meta: Optional[Dict] = None) -> int:
        """Add a message to the conversation log."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            meta_str = json.dumps(meta) if meta else None
            cursor.execute(
                "INSERT INTO messages (project_id, role, content, meta) VALUES (?, ?, ?, ?)",
                (project_id, role, content, meta_str)
            )
            return cursor.lastrowid

    def get_messages(self, project_id: int, limit: int = 100) -> List[Dict]:
        """Get messages for a project."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM messages WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
                (project_id, limit)
            )
            rows = cursor.fetchall()
            messages = []
            for row in rows:
                msg = dict(row)
                if msg.get('meta'):
                    msg['meta'] = json.loads(msg['meta'])
                messages.append(msg)
            return messages

    # Tool call operations
    def create_tool_call(self, job_id: int, server: str, tool: str, params: Dict) -> int:
        """Create a tool call record."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tool_calls (job_id, server, tool, params) VALUES (?, ?, ?, ?)",
                (job_id, server, tool, json.dumps(params))
            )
            return cursor.lastrowid

    def update_tool_call(self, tool_call_id: int, preview: Optional[Dict] = None,
                        executed: bool = False, result: Optional[Dict] = None) -> None:
        """Update tool call with preview or result."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            updates = []
            values = []

            if preview:
                updates.append("preview = ?")
                values.append(json.dumps(preview))
            if executed:
                updates.append("executed = 1")
            if result:
                updates.append("result = ?")
                values.append(json.dumps(result))

            if updates:
                values.append(tool_call_id)
                query = f"UPDATE tool_calls SET {', '.join(updates)} WHERE id = ?"
                cursor.execute(query, values)

    # Checkpoint operations
    def create_checkpoint(self, project_id: int, ref: str, stage: str) -> int:
        """Create a checkpoint."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO checkpoints (project_id, ref, stage) VALUES (?, ?, ?)",
                (project_id, ref, stage)
            )
            return cursor.lastrowid

    def get_latest_checkpoint(self, project_id: int) -> Optional[Dict]:
        """Get the latest checkpoint for a project."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM checkpoints WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                (project_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_approval(self, approval_id: int) -> Optional[Dict]:
        """Get an approval by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM approvals WHERE id = ?",
                (approval_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    # Artifact operations
    def create_artifact(self, job_id: int, path: str, artifact_type: str, sha: Optional[str] = None) -> int:
        """Create an artifact record."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO artifacts (job_id, path, type, sha) VALUES (?, ?, ?, ?)",
                (job_id, path, artifact_type, sha)
            )
            return cursor.lastrowid

    def execute_query(self, query: str) -> List[Dict]:
        """Execute a raw SQL query."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]