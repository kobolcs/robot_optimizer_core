# src/robot_optimizer_core/exceptions.py
"""Custom exception hierarchy for Robot Framework Optimizer Core.

All exceptions in this package inherit from :class:`RobotOptimizerError`,
making it easy to catch every optimizer-related error with a single clause.
The hierarchy is:

.. code-block:: text

    RobotOptimizerError
    ├── AnalysisError
    │   ├── ParsingError
    │   └── RobotFileNotFoundError
    ├── ConfigurationError
    ├── PluginError
    ├── RepositoryError
    └── ValidationError

Example:
    Catching analysis errors with file context::

        from robot_optimizer_core import analyze_file, AnalysisError

        try:
            findings = analyze_file("test.robot")
        except AnalysisError as e:
            print(f"Analysis failed: {e}")
            print(f"File: {e.file_path}")
            print(f"Details: {e.details}")
"""

from __future__ import annotations

import dataclasses
import sys
from enum import StrEnum
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from pathlib import Path

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

E = TypeVar("E", bound="RobotOptimizerError")

# Stable machine-readable error codes
ERROR_ANALYSIS_FAILED = "ANALYSIS_FAILED"
ERROR_FILE_NOT_FOUND = "FILE_NOT_FOUND"
ERROR_PARSE_ERROR = "PARSE_ERROR"
ERROR_PLUGIN_LOAD_FAILED = "PLUGIN_LOAD_FAILED"
ERROR_CONFIG_INVALID = "CONFIG_INVALID"
ERROR_VALIDATION_FAILED = "VALIDATION_FAILED"
ERROR_REPOSITORY_FAILED = "REPOSITORY_FAILED"


class ErrorCategory(StrEnum):
    """Broad category for machine-readable error routing.

    Attributes:
        INPUT: Bad path, invalid argument — caller must fix.
        ANALYSIS: Analyzer-internal failure — may be retryable.
        PARSE: Robot Framework syntax error — permanent.
        CONFIG: Settings or environment problem — caller must fix.
        PLUGIN: Plugin load or runtime failure — may be retryable.
        INTERNAL: Bug in the optimizer itself — report upstream.
    """

    INPUT = "input"
    ANALYSIS = "analysis"
    PARSE = "parse"
    CONFIG = "config"
    PLUGIN = "plugin"
    INTERNAL = "internal"


@dataclasses.dataclass(frozen=True, slots=True)
class StructuredError:
    """Machine-readable error payload attached to every exception as ``.structured``.

    Attributes:
        code: One of the ``ERROR_*`` string constants.
        category: Broad error category for routing/alerting.
        retryable: Whether the operation is worth retrying as-is.
        file_path: The file involved, if applicable.
        analyzer: The analyzer that failed, if applicable.
        hint: One-sentence user-facing suggestion for resolving the error.
    """

    code: str
    category: ErrorCategory
    retryable: bool
    file_path: Path | None = None
    analyzer: str | None = None
    hint: str | None = None


__all__ = [
    "ERROR_ANALYSIS_FAILED",
    "ERROR_CONFIG_INVALID",
    "ERROR_FILE_NOT_FOUND",
    "ERROR_PARSE_ERROR",
    "ERROR_PLUGIN_LOAD_FAILED",
    "ERROR_REPOSITORY_FAILED",
    "ERROR_VALIDATION_FAILED",
    "AnalysisError",
    "ConfigurationError",
    "ErrorCategory",
    "ParsingError",
    "PluginError",
    "RepositoryError",
    "RobotFileNotFoundError",
    "RobotOptimizerError",
    "StructuredError",
    "ValidationError",
]


class RobotOptimizerError(Exception):
    """Base exception for all Robot Framework Optimizer errors.

    All custom exceptions in this package inherit from this class,
    making it easy to catch all optimizer-related errors.

    Attributes:
        message: Human-readable error message.
        details: Additional error details as key-value pairs.
        error_code: Stable machine-readable error code (never None).
    """

    __slots__ = ("details", "error_code", "message")

    # Subclasses override these to customise the structured payload.
    _default_error_code: str = ERROR_ANALYSIS_FAILED
    _default_category: ErrorCategory = ErrorCategory.INTERNAL
    _default_retryable: bool = False

    def __init__(
        self,
        message: str,
        details: dict[str, object] | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.error_code = error_code or self._default_error_code

    @override
    def __str__(self) -> str:
        base = f"[{self.error_code}] {self.message}"
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{base} ({details_str})"
        return base

    @property
    def structured(self) -> StructuredError:
        """Machine-readable error payload for routing and alerting."""
        return StructuredError(
            code=self.error_code,
            category=self._default_category,
            retryable=self._default_retryable,
        )


class AnalysisError(RobotOptimizerError):
    """Raised when analysis of a test file fails.

    Attributes:
        file_path: Path to the file that caused the error.
        analyzer: Name of the analyzer that failed (if applicable).
    """

    __slots__ = ("analyzer", "file_path")

    _default_error_code = ERROR_ANALYSIS_FAILED
    _default_category = ErrorCategory.ANALYSIS
    _default_retryable = True

    def __init__(
        self,
        message: str,
        file_path: Path | None = None,
        analyzer: str | None = None,
        details: dict[str, object] | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message, details, error_code=error_code)
        self.file_path = file_path
        self.analyzer = analyzer

    @property
    def structured(self) -> StructuredError:
        return StructuredError(
            code=self.error_code,
            category=self._default_category,
            retryable=self._default_retryable,
            file_path=self.file_path,
            analyzer=self.analyzer,
        )


class ParsingError(AnalysisError):
    """Raised when parsing a Robot Framework file fails.

    Attributes:
        line_number: Line number where parsing failed (if known).
        column: Column number where parsing failed (if known).
    """

    __slots__ = ("column", "line_number")

    _default_error_code = ERROR_PARSE_ERROR
    _default_category = ErrorCategory.PARSE
    _default_retryable = False

    def __init__(
        self,
        message: str,
        file_path: Path,
        line_number: int | None = None,
        column: int | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message, file_path, details=details)
        self.line_number = line_number
        self.column = column


class ConfigurationError(RobotOptimizerError):
    """Raised when configuration is invalid or missing.

    Attributes:
        config_key: The configuration key that caused the error.
        provided_value: The invalid value that was provided.
    """

    __slots__ = ("config_key", "provided_value")

    _default_error_code = ERROR_CONFIG_INVALID
    _default_category = ErrorCategory.CONFIG
    _default_retryable = False

    def __init__(
        self,
        message: str,
        config_key: str | None = None,
        provided_value: object = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.config_key = config_key
        self.provided_value = provided_value


class PluginError(RobotOptimizerError):
    """Raised when plugin loading or execution fails.

    Attributes:
        plugin_name: Name of the plugin that caused the error.
        plugin_type: Type of plugin (e.g., 'analyzer', 'parser').
    """

    __slots__ = ("plugin_name", "plugin_type")

    _default_error_code = ERROR_PLUGIN_LOAD_FAILED
    _default_category = ErrorCategory.PLUGIN
    _default_retryable = True

    def __init__(
        self,
        message: str,
        plugin_name: str | None = None,
        plugin_type: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.plugin_name = plugin_name
        self.plugin_type = plugin_type


class ValidationError(RobotOptimizerError):
    """Raised when data validation fails.

    Attributes:
        field_name: Name of the field that failed validation.
        invalid_value: The value that failed validation.
        validation_rule: Description of the validation rule.
    """

    __slots__ = ("field_name", "invalid_value", "validation_rule")

    _default_error_code = ERROR_VALIDATION_FAILED
    _default_category = ErrorCategory.INPUT
    _default_retryable = False

    def __init__(
        self,
        message: str,
        field_name: str | None = None,
        invalid_value: object = None,
        validation_rule: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.field_name = field_name
        self.invalid_value = invalid_value
        self.validation_rule = validation_rule


class RobotFileNotFoundError(AnalysisError):
    """Raised when a required file cannot be found."""

    _default_error_code = ERROR_FILE_NOT_FOUND
    _default_category = ErrorCategory.INPUT
    _default_retryable = False

    def __init__(
        self, file_path: Path, details: dict[str, object] | None = None
    ) -> None:
        message = f"File not found: {file_path}"
        super().__init__(message, file_path, details=details, error_code=ERROR_FILE_NOT_FOUND)


class RepositoryError(RobotOptimizerError):
    """Raised when repository operations fail.

    Attributes:
        repository_name: Name of the repository that failed.
        operation: The operation that failed (e.g., 'save', 'load').
    """

    __slots__ = ("operation", "repository_name")

    _default_error_code = ERROR_REPOSITORY_FAILED
    _default_category = ErrorCategory.INTERNAL
    _default_retryable = True

    def __init__(
        self,
        message: str,
        repository_name: str | None = None,
        operation: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message, details)
        self.repository_name = repository_name
        self.operation = operation


def create_error(error_class: type[E], message: str, **kwargs: Any) -> E:
    """Factory function to create errors with consistent formatting.

    Args:
        error_class: The error class to instantiate.
        message: Error message.
        **kwargs: Additional arguments for the error class.

    Returns:
        An instance of the specified error class.

    Example:
        >>> error = create_error(
        ...     AnalysisError,
        ...     "Failed to analyze file",
        ...     file_path=Path("test.robot"),
        ...     analyzer="DeadCodeAnalyzer"
        ... )
    """
    return error_class(message, **kwargs)
