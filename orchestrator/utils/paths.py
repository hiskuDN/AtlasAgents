"""Path utilities for workspace and project management."""

import os
from pathlib import Path
from typing import Optional, Tuple


class PathManager:
    """Manages paths for workspaces, projects, and configurations."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.cwd()
        self.config_dir = Path.home() / ".atlas"
        self.workspaces_dir = self.base_dir / "workspaces"

        # Ensure directories exist
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.workspaces_dir.mkdir(parents=True, exist_ok=True)

    @property
    def global_atlas_md(self) -> Path:
        """Path to global ATLAS.md memory file."""
        return self.config_dir / "ATLAS.md"

    @property
    def settings_path(self) -> Path:
        """Path to global settings.json."""
        return self.config_dir / "settings.json"

    @property
    def history_dir(self) -> Path:
        """Path to global history directory for checkpoints."""
        history = self.config_dir / "history"
        history.mkdir(parents=True, exist_ok=True)
        return history

    def get_project_dir(self, project_name: str) -> Path:
        """Get the directory for a specific project."""
        return self.workspaces_dir / project_name

    def get_project_atlas_md(self, project_name: str) -> Path:
        """Get the project-specific ATLAS.md path."""
        return self.get_project_dir(project_name) / ".atlas" / "ATLAS.md"

    def get_project_internal_dir(self, project_name: str) -> Path:
        """Get the internal directory for a project."""
        internal = self.get_project_dir(project_name) / ".internal"
        internal.mkdir(parents=True, exist_ok=True)
        return internal

    def get_project_docs_dir(self, project_name: str) -> Path:
        """Get the docs directory for a project."""
        docs = self.get_project_dir(project_name) / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        return docs

    def get_project_src_dir(self, project_name: str) -> Path:
        """Get the src directory for a project."""
        src = self.get_project_dir(project_name) / "src"
        src.mkdir(parents=True, exist_ok=True)
        return src

    def get_project_history_dir(self, project_name: str) -> Path:
        """Get the history directory for a specific project."""
        import hashlib
        project_hash = hashlib.md5(project_name.encode()).hexdigest()[:8]
        history = self.history_dir / project_hash
        history.mkdir(parents=True, exist_ok=True)
        return history

    def resolve_workspace_path(self, project_name: str, relative_path: str) -> Tuple[Path, bool]:
        """
        Resolve a path within a project workspace and verify it's within bounds.

        Returns:
            Tuple of (resolved_path, is_safe)
        """
        project_dir = self.get_project_dir(project_name)

        # Resolve the path
        resolved = (project_dir / relative_path).resolve()

        # Check if it's within the project directory
        try:
            resolved.relative_to(project_dir.resolve())
            is_safe = True
        except ValueError:
            is_safe = False

        return resolved, is_safe

    def get_current_project(self) -> Optional[str]:
        """Get the currently active project from .atlas/current file."""
        current_file = self.config_dir / "current"
        if current_file.exists():
            return current_file.read_text().strip()
        return None

    def set_current_project(self, project_name: str) -> None:
        """Set the currently active project."""
        current_file = self.config_dir / "current"
        current_file.write_text(project_name)

    def list_projects(self) -> list[str]:
        """List all available projects."""
        if not self.workspaces_dir.exists():
            return []
        return [
            d.name for d in self.workspaces_dir.iterdir()
            if d.is_dir() and not d.name.startswith('.')
        ]

    def project_exists(self, project_name: str) -> bool:
        """Check if a project exists."""
        return self.get_project_dir(project_name).exists()

    def create_project_structure(self, project_name: str) -> None:
        """Create the full directory structure for a new project."""
        project_dir = self.get_project_dir(project_name)

        # Create main directories
        (project_dir / ".atlas").mkdir(parents=True, exist_ok=True)
        (project_dir / "docs").mkdir(parents=True, exist_ok=True)
        (project_dir / "src").mkdir(parents=True, exist_ok=True)
        (project_dir / ".internal").mkdir(parents=True, exist_ok=True)
        (project_dir / ".internal" / "diffs").mkdir(parents=True, exist_ok=True)
        (project_dir / ".internal" / "prs").mkdir(parents=True, exist_ok=True)
        (project_dir / ".internal" / "logs").mkdir(parents=True, exist_ok=True)

        # Create default files
        readme_path = project_dir / "README.md"
        if not readme_path.exists():
            readme_path.write_text(f"# {project_name}\n\nProject workspace for AtlasAgents.\n")

        requirements_path = project_dir / "requirements.yaml"
        if not requirements_path.exists():
            requirements_path.write_text(f"name: {project_name}\nversion: 0.1.0\ndescription: ''\n")

        atlas_md_path = project_dir / ".atlas" / "ATLAS.md"
        if not atlas_md_path.exists():
            atlas_md_path.write_text(f"# {project_name} Memory\n\n## Project Context\n\n## Constraints\n\n## Learnings\n")

    def update_mcp_paths(self, project_name: str, config_path: Path) -> None:
        """Update MCP config file with project-specific paths."""
        import yaml

        project_dir = self.get_project_dir(project_name)

        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}

        # Update paths in MCP transports
        if 'mcp' in config and 'transports' in config['mcp']:
            for transport in config['mcp']['transports']:
                if transport['name'] == 'filesystem':
                    transport['env']['ROOT'] = str(project_dir)
                elif transport['name'] == 'git':
                    transport['env']['REPO_PATH'] = str(project_dir)
                elif transport['name'] == 'sqlite':
                    transport['env']['SQLITE_PATH'] = str(project_dir / ".internal" / "atlas.db")

        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)


# Singleton instance
_path_manager: Optional[PathManager] = None


def get_path_manager(base_dir: Optional[Path] = None) -> PathManager:
    """Get or create the global path manager instance."""
    global _path_manager
    if _path_manager is None:
        _path_manager = PathManager(base_dir)
    return _path_manager