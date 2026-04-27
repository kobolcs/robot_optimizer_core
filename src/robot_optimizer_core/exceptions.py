# src/robot_optimizer_core/exceptions.py
"""Custom exception hierarchy for Robot Framework Optimizer Core.

This module defines the exception hierarchy used throughout the Core package.
All exceptions inherit from RobotOptimizerError for easy catching.

Example:
    Catching specific exceptions::
    
        from robot_optimizer_core import analyze_file, AnalysisError
        
        try:
            findings = analyze_file("test.robot")
        except AnalysisError as e:
            print(f"Analysis failed: {e}")
            print(f"File: {e.file_path}")
            print(f"Details: {e.details}")
"""
from __future__ import annotations

from pathlib import Path
from typing import TypeVar

try:
    from typing import override
except ImportError:
    from typing_extensions import override

E = TypeVar("E", bound="RobotOptimizerError")


class RobotOptimizerError(Exception):
    """Base exception for all Robot Framework Optimizer errors.
    
    All custom exceptions in this package inherit from this class,
    making it easy to catch all optimizer-related errors.
    
    Attributes:
        message: Human-readable error message.
        details: Additional error details as key-value pairs.
    """

    __slots__ = ("details", "message")

    def __init__(
        self,
        message: str,
        details: dict[str, object] | None = None
    ) -> None:
        """Initialize the exception.
        
        Args:
            message: Human-readable error message.
            details: Additional error details.
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    @override
    def __str__(self) -> str:
        """Return string representation of the error.

        Returns:
            Error message with details if available.
        """
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message


class AnalysisError(RobotOptimizerError):
    """Raised when analysis of a test file fails.
    
    This exception indicates that the analysis process encountered
    an error while processing a specific file.
    
    Attributes:
        file_path: Path to the file that caused the error.
        analyzer: Name of the analyzer that failed (if applicable).
    """

    __slots__ = ("analyzer", "file_path")

    def __init__(
        self,
        message: str,
        file_path: Path | None = None,
        analyzer: str | None = None,
        details: dict[str, object] | None = None
    ) -> None:
        """Initialize the analysis error.
        
        Args:
            message: Error description.
            file_path: Path to the problematic file.
            analyzer: Name of the analyzer that failed.
            details: Additional error details.
        """
        super().__init__(message, details)
        self.file_path = file_path
        self.analyzer = analyzer


class ParsingError(AnalysisError):
    """Raised when parsing a Robot Framework file fails.
    
    This is a specific type of AnalysisError that occurs during
    the parsing phase of analysis.
    
    Attributes:
        line_number: Line number where parsing failed (if known).
        column: Column number where parsing failed (if known).
    """

    __slots__ = ("column", "line_number")

    def __init__(
        self,
        message: str,
        file_path: Path,
        line_number: int | None = None,
        column: int | None = None,
        details: dict[str, object] | None = None
    ) -> None:
        """Initialize the parsing error.
        
        Args:
            message: Error description.
            file_path: Path to the file being parsed.
            line_number: Line where error occurred.
            column: Column where error occurred.
            details: Additional error details.
        """
        super().__init__(message, file_path, details=details)
        self.line_number = line_number
        self.column = column


class ConfigurationError(RobotOptimizerError):
    """Raised when configuration is invalid or missing.
    
    This exception indicates problems with settings, environment
    variables, or configuration files.
    
    Attributes:
        config_key: The configuration key that caused the error.
        provided_value: The invalid value that was provided.
    """

    __slots__ = ("config_key", "provided_value")

    def __init__(
        self,
        message: str,
        config_key: str | None = None,
        provided_value: object = None,
        details: dict[str, object] | None = None
    ) -> None:
        """Initialize the configuration error.
        
        Args:
            message: Error description.
            config_key: Configuration key that failed.
            provided_value: The invalid value.
            details: Additional error details.
        """
        super().__init__(message, details)
        self.config_key = config_key
        self.provided_value = provided_value


class PluginError(RobotOptimizerError):
    """Raised when plugin loading or execution fails.
    
    This exception covers errors in the plugin system, including
    loading, registration, and execution failures.
    
    Attributes:
        plugin_name: Name of the plugin that caused the error.
        plugin_type: Type of plugin (e.g., 'analyzer', 'parser').
    """

    __slots__ = ("plugin_name", "plugin_type")

    def __init__(
        self,
        message: str,
        plugin_name: str | None = None,
        plugin_type: str | None = None,
        details: dict[str, object] | None = None
    ) -> None:
        """Initialize the plugin error.
        
        Args:
            message: Error description.
            plugin_name: Name of the problematic plugin.
            plugin_type: Type of the plugin.
            details: Additional error details.
        """
        super().__init__(message, details)
        self.plugin_name = plugin_name
        self.plugin_type = plugin_type


class ValidationError(RobotOptimizerError):
    """Raised when data validation fails.
    
    This exception is used when domain objects or configurations
    fail validation rules.
    
    Attributes:
        field_name: Name of the field that failed validation.
        invalid_value: The value that failed validation.
        validation_rule: Description of the validation rule.
    """

    __slots__ = ("field_name", "invalid_value", "validation_rule")

    def __init__(
        self,
        message: str,
        field_name: str | None = None,
        invalid_value: object = None,
        validation_rule: str | None = None,
        details: dict[str, object] | None = None
    ) -> None:
        """Initialize the validation error.
        
        Args:
            message: Error description.
            field_name: Field that failed validation.
            invalid_value: The invalid value.
            validation_rule: Rule that was violated.
            details: Additional error details.
        """
        super().__init__(message, details)
        self.field_name = field_name
        self.invalid_value = invalid_value
        self.validation_rule = validation_rule


class FileNotFoundError(AnalysisError):
    """Raised when a required file cannot be found.
    
    This is a specific type of AnalysisError for missing files.
    """

    def __init__(
        self,
        file_path: Path,
        details: dict[str, object] | None = None
    ) -> None:
        """Initialize the file not found error.
        
        Args:
            file_path: Path to the missing file.
            details: Additional error details.
        """
        message = f"File not found: {file_path}"
        super().__init__(message, file_path, details=details)


class RepositoryError(RobotOptimizerError):
    """Raised when repository operations fail.
    
    This exception indicates problems with data persistence or retrieval.
    
    Attributes:
        repository_name: Name of the repository that failed.
        operation: The operation that failed (e.g., 'save', 'load').
    """

    __slots__ = ("operation", "repository_name")

    def __init__(
        self,
        message: str,
        repository_name: str | None = None,
        operation: str | None = None,
        details: dict[str, object] | None = None
    ) -> None:
        """Initialize the repository error.
        
        Args:
            message: Error description.
            repository_name: Repository that failed.
            operation: Operation that failed.
            details: Additional error details.
        """
        super().__init__(message, details)
        self.repository_name = repository_name
        self.operation = operation


def create_error(
    error_class: type[E],
    message: str,
    **kwargs: object
) -> E:
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
