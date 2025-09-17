"""Permission system for MCP tool access control."""

from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import fnmatch
import json

from orchestrator.core.config import AtlasConfig, TrustPolicy
from orchestrator.mcp.registry import ToolMetadata, ToolCategory, ToolOperation
from orchestrator.models.database import AgentRole
from orchestrator.utils.logging import get_logger
from orchestrator.utils.exceptions import MCPToolError


logger = get_logger(__name__)


@dataclass
class PermissionCheck:
    """Result of a permission check."""
    tool_id: str
    agent: str
    allowed: bool
    reason: Optional[str] = None
    requires_approval: bool = False
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PermissionAuditEntry:
    """Audit log entry for permission checks."""
    tool_id: str
    agent: str
    allowed: bool
    reason: str
    project_id: Optional[int] = None
    job_id: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict:
        """Convert to dictionary for logging."""
        return {
            "tool_id": self.tool_id,
            "agent": self.agent,
            "allowed": self.allowed,
            "reason": self.reason,
            "project_id": self.project_id,
            "job_id": self.job_id,
            "timestamp": self.timestamp.isoformat()
        }


class PermissionManager:
    """Manages tool access permissions based on trust policies."""

    def __init__(self, config: AtlasConfig):
        self.config = config
        self.trust_policy = config.settings.trust
        self.audit_log: List[PermissionAuditEntry] = []
        self._permission_cache: Dict[Tuple[str, str], PermissionCheck] = {}

        logger.info(f"Permission manager initialized with default policy: {self.trust_policy.default}")

    def check_permission(self,
                        agent_role: str,
                        tool_id: str,
                        tool_metadata: Optional[ToolMetadata] = None,
                        project_id: Optional[int] = None,
                        job_id: Optional[int] = None) -> PermissionCheck:
        """
        Check if an agent has permission to use a tool.

        Args:
            agent_role: Role of the agent (e.g., "planner", "coder")
            tool_id: Tool identifier (e.g., "filesystem.read")
            tool_metadata: Optional tool metadata for additional checks
            project_id: Optional project ID for audit
            job_id: Optional job ID for audit

        Returns:
            PermissionCheck result
        """
        # Check cache first
        cache_key = (agent_role, tool_id)
        if cache_key in self._permission_cache:
            cached = self._permission_cache[cache_key]
            logger.debug(f"Using cached permission for {agent_role} -> {tool_id}: {cached.allowed}")
            return cached

        # Perform permission check
        result = self._evaluate_permission(agent_role, tool_id, tool_metadata)

        # Cache the result
        self._permission_cache[cache_key] = result

        # Log audit entry
        audit_entry = PermissionAuditEntry(
            tool_id=tool_id,
            agent=agent_role,
            allowed=result.allowed,
            reason=result.reason or "Permission check",
            project_id=project_id,
            job_id=job_id
        )
        self.audit_log.append(audit_entry)

        # Log the check
        if result.allowed:
            logger.info(f"Permission granted: {agent_role} -> {tool_id}",
                       agent=agent_role, tool=tool_id, allowed=True)
        else:
            logger.warning(f"Permission denied: {agent_role} -> {tool_id}: {result.reason}",
                          agent=agent_role, tool=tool_id, allowed=False, reason=result.reason)

        return result

    def _evaluate_permission(self,
                            agent_role: str,
                            tool_id: str,
                            tool_metadata: Optional[ToolMetadata]) -> PermissionCheck:
        """Evaluate permission based on trust policy."""
        # Check default policy
        if self.trust_policy.default == "allow":
            # Allow by default, but check deny list
            if self._is_explicitly_denied(agent_role, tool_id):
                return PermissionCheck(
                    tool_id=tool_id,
                    agent=agent_role,
                    allowed=False,
                    reason="Tool explicitly denied for agent"
                )
        else:  # default is "deny"
            # Deny by default, check allow list
            if not self._is_explicitly_allowed(agent_role, tool_id):
                return PermissionCheck(
                    tool_id=tool_id,
                    agent=agent_role,
                    allowed=False,
                    reason="Tool not explicitly allowed for agent"
                )

        # Check if tool requires approval
        requires_approval = self._requires_approval(tool_id, tool_metadata)

        return PermissionCheck(
            tool_id=tool_id,
            agent=agent_role,
            allowed=True,
            requires_approval=requires_approval,
            reason="Permission granted" + (" (approval required)" if requires_approval else "")
        )

    def _is_explicitly_allowed(self, agent_role: str, tool_id: str) -> bool:
        """Check if a tool is explicitly allowed for an agent."""
        allowed_patterns = self.trust_policy.allow.get(agent_role, [])

        for pattern in allowed_patterns:
            if self._match_pattern(tool_id, pattern):
                return True

        return False

    def _is_explicitly_denied(self, agent_role: str, tool_id: str) -> bool:
        """Check if a tool is explicitly denied for an agent."""
        # In current config, we don't have explicit deny lists
        # This is for future extension
        return False

    def _requires_approval(self, tool_id: str, tool_metadata: Optional[ToolMetadata]) -> bool:
        """Check if a tool requires approval."""
        # Check approval patterns in config
        for pattern in self.trust_policy.require_approval:
            if self._match_pattern(tool_id, pattern):
                return True

        # Check tool metadata
        if tool_metadata and tool_metadata.requires_approval:
            return True

        return False

    def _match_pattern(self, tool_id: str, pattern: str) -> bool:
        """
        Match a tool ID against a pattern.

        Supports:
        - Exact match: "filesystem.read"
        - Wildcard: "filesystem.*", "*.write*"
        - Category shortcuts: "fs.*" for filesystem.*
        """
        # Handle category shortcuts
        pattern = pattern.replace("fs.", "filesystem.")

        # Use fnmatch for pattern matching
        return fnmatch.fnmatch(tool_id.lower(), pattern.lower())

    def get_allowed_tools(self, agent_role: str, tools: List[ToolMetadata]) -> List[ToolMetadata]:
        """
        Filter a list of tools to only those allowed for an agent.

        Args:
            agent_role: Role of the agent
            tools: List of available tools

        Returns:
            List of allowed tools
        """
        allowed = []

        for tool in tools:
            check = self.check_permission(agent_role, tool.tool_id, tool)
            if check.allowed:
                allowed.append(tool)

        return allowed

    def get_denied_tools(self, agent_role: str, tools: List[ToolMetadata]) -> List[ToolMetadata]:
        """Get tools that are denied for an agent."""
        denied = []

        for tool in tools:
            check = self.check_permission(agent_role, tool.tool_id, tool)
            if not check.allowed:
                denied.append(tool)

        return denied

    def validate_agent_permissions(self, agent_role: str) -> Dict[str, any]:
        """
        Validate and summarize permissions for an agent role.

        Returns:
            Dictionary with permission summary
        """
        # Get allowed patterns from config
        allowed_patterns = self.trust_policy.allow.get(agent_role, [])

        # Get patterns requiring approval
        approval_patterns = self.trust_policy.require_approval

        return {
            "agent": agent_role,
            "default_policy": self.trust_policy.default,
            "allowed_patterns": allowed_patterns,
            "approval_required": approval_patterns,
            "can_read": any("read" in p or "*.read" in p for p in allowed_patterns),
            "can_write": any("write" in p or "*.write" in p for p in allowed_patterns),
            "can_execute": any("exec" in p or "run" in p for p in allowed_patterns)
        }

    def get_audit_log(self,
                     agent: Optional[str] = None,
                     tool_id: Optional[str] = None,
                     allowed: Optional[bool] = None,
                     limit: int = 100) -> List[PermissionAuditEntry]:
        """
        Get filtered audit log entries.

        Args:
            agent: Filter by agent role
            tool_id: Filter by tool ID
            allowed: Filter by allowed/denied
            limit: Maximum entries to return

        Returns:
            List of matching audit entries
        """
        filtered = self.audit_log

        if agent:
            filtered = [e for e in filtered if e.agent == agent]
        if tool_id:
            filtered = [e for e in filtered if e.tool_id == tool_id]
        if allowed is not None:
            filtered = [e for e in filtered if e.allowed == allowed]

        # Return most recent entries
        return filtered[-limit:]

    def export_audit_log(self, filepath: str):
        """Export audit log to a file."""
        with open(filepath, 'w') as f:
            entries = [entry.to_dict() for entry in self.audit_log]
            json.dump(entries, f, indent=2, default=str)
        logger.info(f"Exported {len(self.audit_log)} audit entries to {filepath}")

    def clear_cache(self):
        """Clear the permission cache."""
        self._permission_cache.clear()
        logger.debug("Permission cache cleared")

    def update_trust_policy(self, new_policy: TrustPolicy):
        """Update the trust policy and clear cache."""
        self.trust_policy = new_policy
        self.clear_cache()
        logger.info("Trust policy updated, cache cleared")


class PermissionEnforcer:
    """Enforces permissions for tool execution."""

    def __init__(self, permission_manager: PermissionManager):
        self.permission_manager = permission_manager
        self.blocked_calls: List[Dict] = []

    def enforce(self,
               agent_role: str,
               tool_id: str,
               tool_metadata: Optional[ToolMetadata] = None,
               project_id: Optional[int] = None,
               job_id: Optional[int] = None) -> Tuple[bool, Optional[str]]:
        """
        Enforce permission for a tool call.

        Args:
            agent_role: Role requesting the tool
            tool_id: Tool being requested
            tool_metadata: Optional tool metadata
            project_id: Optional project ID
            job_id: Optional job ID

        Returns:
            (allowed, error_message)
        """
        # Check permission
        check = self.permission_manager.check_permission(
            agent_role, tool_id, tool_metadata, project_id, job_id
        )

        if not check.allowed:
            # Log blocked call
            self.blocked_calls.append({
                "agent": agent_role,
                "tool_id": tool_id,
                "reason": check.reason,
                "timestamp": datetime.utcnow().isoformat(),
                "project_id": project_id,
                "job_id": job_id
            })

            error_msg = f"Permission denied for {agent_role} to use {tool_id}: {check.reason}"
            return False, error_msg

        # Check if approval is required
        if check.requires_approval:
            # This will be handled by the approval system
            logger.info(f"Tool {tool_id} requires approval for {agent_role}")

        return True, None

    def get_blocked_calls(self, limit: int = 100) -> List[Dict]:
        """Get recent blocked tool calls."""
        return self.blocked_calls[-limit:]

    def clear_blocked_calls(self):
        """Clear the blocked calls log."""
        self.blocked_calls.clear()