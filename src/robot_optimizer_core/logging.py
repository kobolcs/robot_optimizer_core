# src/robot_optimizer_core/logging.py
"""Structured logging configuration for Robot Framework Optimizer Core.

This module provides a structured logging system that can be extended
by the Pro version. It uses Python's logging module with JSON formatting
for machine-readable logs.

Example:
    Basic logging usage::
    
        from robot_optimizer_core import get_logger
        
        logger = get_logger(__name__)
        logger.info("Analysis started", extra={"file": "test.robot"})
        logger.error("Analysis failed", extra={"error": str(e)})
"""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

from .metrics import get_metrics

# Context variable for logging context
logging_context: ContextVar[dict[str, Any]] = ContextVar('logging_context', default={})


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging.
    
    Formats log records as JSON for easy parsing and analysis.
    Includes timestamp, level, logger name, message, and any extra fields.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON.
        
        Args:
            record: The log record to format.
            
        Returns:
            JSON-formatted log entry.
        """
        # Base log entry
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Add context from context variable
        if context := logging_context.get():
            log_entry["context"] = context

        # Add extra fields
        extra_fields = {
            k: v for k, v in record.__dict__.items()
            if k not in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "pathname", "process", "processName", "relativeCreated",
                "thread", "threadName", "exc_info", "exc_text", "stack_info"
            }
        }
        if extra_fields:
            log_entry["extra"] = extra_fields

        return json.dumps(log_entry, default=str)


class MetricsHandler(logging.Handler):
    """Log handler that collects metrics about logging.
    
    This handler tracks logging metrics for monitoring purposes,
    respecting GDPR by not storing personal information.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record and update metrics.
        
        Args:
            record: The log record to emit.
        """
        metrics = get_metrics()

        # Track log levels
        metrics.increment("logs.total")
        metrics.increment(f"logs.{record.levelname.lower()}")

        # Track errors by module (no personal data)
        if record.levelno >= logging.ERROR:
            module_name = record.name.split(".")[-1]  # Last part only
            metrics.increment(f"logs.errors.{module_name}")


class LoggerAdapter(logging.LoggerAdapter):
    """Adapter that adds context to all log messages.
    
    This adapter allows adding persistent context that will be
    included in all log messages.
    """

    __slots__ = ('_context', 'extra', 'logger')

    def __init__(self, logger: logging.Logger, extra: dict[str, Any]) -> None:
        """Initialize the adapter.
        
        Args:
            logger: The underlying logger.
            extra: Context to add to all messages.
        """
        super().__init__(logger, extra)
        self._context = extra.copy()

    def add_context(self, **kwargs: Any) -> None:
        """Add context that will be included in all future log messages.
        
        Args:
            **kwargs: Context key-value pairs.
        """
        self._context |= kwargs  # Dictionary merge operator
        self.extra = self._context.copy()

    def remove_context(self, *keys: str) -> None:
        """Remove context keys.
        
        Args:
            *keys: Context keys to remove.
        """
        for key in keys:
            self._context.pop(key, None)
        self.extra = self._context.copy()

    def with_context(self, **kwargs: Any) -> LoggerAdapter:
        """Create a new adapter with additional context.
        
        Args:
            **kwargs: Additional context.
            
        Returns:
            New adapter with combined context.
        """
        new_context = self._context | kwargs  # Dictionary merge
        return LoggerAdapter(self.logger, new_context)


# Global logging configuration
_root_logger_configured = False


def configure_logging(
    level: str | int = logging.INFO,
    format_json: bool = True,
    log_file: Path | None = None,
    enable_metrics: bool = True,
    extra_handlers: list[logging.Handler] | None = None
) -> None:
    """Configure the logging system.
    
    This function sets up the logging system with structured formatting
    and optional metrics collection. It can be called multiple times
    to reconfigure logging.
    
    Args:
        level: Logging level (name or constant).
        format_json: Whether to use JSON formatting.
        log_file: Optional file to write logs to.
        enable_metrics: Whether to enable metrics collection.
        extra_handlers: Additional handlers to add.
        
    Example:
        >>> configure_logging(
        ...     level="DEBUG",
        ...     format_json=True,
        ...     log_file=Path("optimizer.log")
        ... )
    """
    global _root_logger_configured

    # Configure root logger for the package
    root_logger = logging.getLogger("robot_optimizer_core")
    root_logger.setLevel(level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    if format_json:
        console_handler.setFormatter(StructuredFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
        )
    root_logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        if format_json:
            file_handler.setFormatter(StructuredFormatter())
        else:
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
            )
        root_logger.addHandler(file_handler)

    # Metrics handler
    if enable_metrics:
        metrics_handler = MetricsHandler()
        metrics_handler.setLevel(logging.WARNING)  # Only track warnings and above
        root_logger.addHandler(metrics_handler)

    # Extra handlers
    if extra_handlers:
        for handler in extra_handlers:
            root_logger.addHandler(handler)

    _root_logger_configured = True


@cache
def get_logger(
    name: str,
    context: dict[str, Any] | None = None
) -> LoggerAdapter:
    """Get a logger with optional context.
    
    This function returns a logger adapter that can include persistent
    context in all log messages. The logger is cached for efficiency
    using functools.cache (Python 3.9+).
    
    Args:
        name: Logger name (usually __name__).
        context: Optional context to include in all messages.
        
    Returns:
        Logger adapter with context support.
        
    Example:
        >>> logger = get_logger(__name__, {"component": "analyzer"})
        >>> logger.info("Starting analysis", extra={"file": "test.robot"})
    """
    # Auto-configure if not done yet
    if not _root_logger_configured:
        configure_logging()

    # Create new logger
    logger = logging.getLogger(name)
    adapter = LoggerAdapter(logger, context or {})

    return adapter


def log_analysis_start(
    file_path: Path,
    analyzer: str,
    logger: LoggerAdapter | None = None
) -> None:
    """Log the start of file analysis.
    
    Convenience function for consistent analysis logging.
    
    Args:
        file_path: Path to file being analyzed.
        analyzer: Name of the analyzer.
        logger: Logger to use (default: module logger).
    """
    if logger is None:
        logger = get_logger(__name__)

    logger.info(
        "Starting analysis",
        extra={
            "event": "analysis_start",
            "file": str(file_path),
            "analyzer": analyzer,
            "file_size": file_path.stat().st_size if file_path.exists() else 0
        }
    )


def log_analysis_complete(
    file_path: Path,
    analyzer: str,
    findings_count: int,
    duration_seconds: float,
    logger: LoggerAdapter | None = None
) -> None:
    """Log the completion of file analysis.
    
    Convenience function for consistent analysis logging.
    
    Args:
        file_path: Path to file that was analyzed.
        analyzer: Name of the analyzer.
        findings_count: Number of findings discovered.
        duration_seconds: Analysis duration.
        logger: Logger to use (default: module logger).
    """
    if logger is None:
        logger = get_logger(__name__)

    logger.info(
        "Analysis complete",
        extra={
            "event": "analysis_complete",
            "file": str(file_path),
            "analyzer": analyzer,
            "findings_count": findings_count,
            "duration_seconds": duration_seconds
        }
    )


def log_error(
    error: Exception,
    context: dict[str, Any],
    logger: LoggerAdapter | None = None
) -> None:
    """Log an error with context.
    
    Convenience function for consistent error logging.
    
    Args:
        error: The exception that occurred.
        context: Additional context about the error.
        logger: Logger to use (default: module logger).
    """
    if logger is None:
        logger = get_logger(__name__)

    logger.error(
        f"{type(error).__name__}: {error!s}",
        extra={
            "event": "error",
            "error_type": type(error).__name__,
            **context
        },
        exc_info=True
    )
