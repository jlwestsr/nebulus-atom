"""Structured logging configuration for Nebulus Swarm."""

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any, Dict, Optional

# Context variable for correlation ID (traces work across minions)
correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str:
    """Get current correlation ID or generate a new one."""
    cid = correlation_id.get()
    if cid is None:
        cid = str(uuid.uuid4())[:8]
        correlation_id.set(cid)
    return cid


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID for the current context."""
    correlation_id.set(cid)


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def __init__(self, include_extras: bool = True):
        """Initialize formatter.

        Args:
            include_extras: Include extra fields from log records.
        """
        super().__init__()
        self.include_extras = include_extras
        self._skip_fields = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "exc_info",
            "exc_text",
            "thread",
            "threadName",
            "taskName",
            "message",
        }

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }

        # Add location info for errors
        if record.levelno >= logging.ERROR:
            log_data["location"] = {
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName,
            }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields from the record
        if self.include_extras:
            for key, value in record.__dict__.items():
                if key not in self._skip_fields and not key.startswith("_"):
                    try:
                        # Ensure value is JSON serializable
                        json.dumps(value)
                        log_data[key] = value
                    except (TypeError, ValueError):
                        log_data[key] = str(value)

        return json.dumps(log_data, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable console formatter with colors."""

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record for console output."""
        color = self.COLORS.get(record.levelname, "")
        cid = get_correlation_id()

        timestamp = datetime.now().strftime("%H:%M:%S")
        level = record.levelname[0]  # First letter only

        # Format: [HH:MM:SS] L [cid] logger: message
        msg = f"{color}[{timestamp}] {level}{self.RESET} [{cid}] {record.name}: {record.getMessage()}"

        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)

        return msg


def configure_logging(
    level: str = "INFO",
    json_output: bool = False,
    log_file: Optional[str] = None,
) -> None:
    """Configure logging for the swarm.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_output: Use JSON format for stdout (for production).
        log_file: Optional file path for JSON logs.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    if json_output:
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(ConsoleFormatter())
    root_logger.addHandler(console_handler)

    # File handler (always JSON for machine parsing)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("docker").setLevel(logging.WARNING)
    logging.getLogger("github").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    Args:
        name: Logger name (typically __name__).

    Returns:
        Configured logger instance.
    """
    return logging.getLogger(name)


class LogContext:
    """Context manager for adding extra fields to log records."""

    def __init__(self, **kwargs: Any):
        """Initialize with extra fields to add to logs.

        Args:
            **kwargs: Extra fields to include in log records.
        """
        self.extras = kwargs
        self._old_factory = None

    def __enter__(self):
        """Add extra fields to log records."""
        old_factory = logging.getLogRecordFactory()
        extras = self.extras

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            for key, value in extras.items():
                setattr(record, key, value)
            return record

        self._old_factory = old_factory
        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore original log record factory."""
        if self._old_factory:
            logging.setLogRecordFactory(self._old_factory)
        return False


# Convenience function for minion logging
def minion_logger(minion_id: str, repo: str, issue: int) -> logging.Logger:
    """Get a logger configured for a specific minion.

    Args:
        minion_id: The minion's unique identifier.
        repo: Repository being worked on.
        issue: Issue number being addressed.

    Returns:
        Logger with minion context.
    """
    logger = get_logger(f"minion.{minion_id}")

    # Create a filter that adds minion context
    class MinionFilter(logging.Filter):
        def filter(self, record):
            record.minion_id = minion_id
            record.repo = repo
            record.issue = issue
            return True

    # Remove existing minion filters and add new one
    for f in logger.filters[:]:
        if isinstance(f, MinionFilter):
            logger.removeFilter(f)
    logger.addFilter(MinionFilter())

    return logger


# Auto-configure from environment on import
_log_level = os.environ.get("LOG_LEVEL", "INFO")
_json_output = os.environ.get("LOG_FORMAT", "").lower() == "json"
_log_file = os.environ.get("LOG_FILE")

configure_logging(level=_log_level, json_output=_json_output, log_file=_log_file)
