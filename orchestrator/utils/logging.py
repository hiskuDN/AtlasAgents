"""Structured logging configuration for AtlasAgents."""

import sys
import logging
from pathlib import Path
from typing import Any, Dict, Optional
import structlog
from structlog.types import Processor
from datetime import datetime
import json


def add_timestamp(_, __, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add timestamp to log entries."""
    event_dict["timestamp"] = datetime.utcnow().isoformat()
    return event_dict


def add_project_context(_, __, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Add project context to logs if available."""
    # This will be populated from thread-local storage when available
    context = structlog.contextvars.get_contextvars()
    if "project_id" in context:
        event_dict["project_id"] = context["project_id"]
    if "project_name" in context:
        event_dict["project_name"] = context["project_name"]
    if "job_id" in context:
        event_dict["job_id"] = context["job_id"]
    return event_dict


def censor_sensitive(_, __, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Censor sensitive information in logs."""
    sensitive_keys = ["api_key", "token", "password", "secret", "bot_token"]

    def censor_dict(d: Dict) -> Dict:
        result = {}
        for key, value in d.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                result[key] = "***REDACTED***"
            elif isinstance(value, dict):
                result[key] = censor_dict(value)
            else:
                result[key] = value
        return result

    return censor_dict(event_dict)


class LogManager:
    """Manages logging configuration for AtlasAgents."""

    def __init__(self, log_dir: Optional[Path] = None, log_level: str = "INFO"):
        self.log_dir = log_dir or Path.home() / ".atlas" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_level = getattr(logging, log_level.upper())
        self._configure_structlog()
        self._configure_standard_logging()

    def _configure_structlog(self):
        """Configure structlog with processors."""
        processors: list[Processor] = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            add_timestamp,
            add_project_context,
            censor_sensitive,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
        ]

        # Add appropriate renderer based on environment
        if sys.stderr.isatty():
            # Console output with colors
            processors.append(structlog.dev.ConsoleRenderer())
        else:
            # JSON output for production/logging
            processors.append(structlog.processors.JSONRenderer())

        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

    def _configure_standard_logging(self):
        """Configure standard logging to work with structlog."""
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=self.log_level,
        )

        # Add file handler for persistent logs
        file_handler = logging.FileHandler(
            self.log_dir / f"atlas_{datetime.now().strftime('%Y%m%d')}.log"
        )
        file_handler.setLevel(self.log_level)

        # JSON formatter for file logs
        file_handler.setFormatter(
            logging.Formatter('%(message)s')
        )

        logging.getLogger().addHandler(file_handler)

    def get_logger(self, name: str) -> structlog.BoundLogger:
        """Get a logger instance."""
        return structlog.get_logger(name)

    def set_context(self, **kwargs):
        """Set context variables for all loggers."""
        structlog.contextvars.bind_contextvars(**kwargs)

    def clear_context(self):
        """Clear context variables."""
        structlog.contextvars.clear_contextvars()


# Global log manager instance
_log_manager: Optional[LogManager] = None


def setup_logging(log_dir: Optional[Path] = None, log_level: str = "INFO") -> LogManager:
    """Setup logging for the application."""
    global _log_manager
    if _log_manager is None:
        _log_manager = LogManager(log_dir, log_level)
    return _log_manager


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a logger instance."""
    if _log_manager is None:
        setup_logging()
    return _log_manager.get_logger(name)