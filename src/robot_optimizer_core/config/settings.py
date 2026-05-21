# src/robot_optimizer_core/config/settings.py
"""Configuration settings for Robot Framework Optimizer Core.

This module provides the settings system with validation and
environment variable support. Settings can be extended by the
Pro version with additional configuration options.

Example:
    Using settings::

        from robot_optimizer_core import get_settings

        settings = get_settings()
        print(settings.max_file_size_mb)

        # Override with environment variables
        # ROBOT_OPTIMIZER_MAX_FILE_SIZE_MB=20
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from ..exceptions import ConfigurationError

SettingsSourceCallable = PydanticBaseSettingsSource

_logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Configuration settings for Robot Framework Optimizer Core.

    Settings can be configured through:
    - Default values
    - Environment variables (ROBOT_OPTIMIZER_ prefix)
    - Configuration files (Pro feature)
    - Direct instantiation

    Attributes:
        max_file_size_mb: Maximum file size to analyze in MB.
        file_patterns: File patterns to include in analysis.
        exclude_patterns: File patterns to exclude from analysis.
        max_line_length: Maximum recommended line length.
        max_test_case_lines: Maximum lines for a test case.
        max_keyword_complexity: Maximum cyclomatic complexity.
        enable_metrics: Whether to enable metrics collection.
        log_level: Logging level.
        plugins_enabled: Whether to enable plugin loading.
        plugin_dirs: Directories to search for plugins.
    """

    # File handling
    max_file_size_mb: float = Field(
        default=10.0, description="Maximum file size to analyze in MB", ge=0.1, le=100.0
    )

    file_patterns: list[str] = Field(
        default=["*.robot", "*.resource"],
        description="File patterns to include in analysis",
    )

    exclude_patterns: list[str] = Field(
        default=[
            "**/.*",  # Hidden files
            "**/__pycache__/**",
            "**/node_modules/**",
            "**/venv/**",
            "**/.venv/**",
            "**/env/**",
            "**/.env/**",
            "**/build/**",
            "**/dist/**",
        ],
        description="File patterns to exclude from analysis",
    )

    # Analysis settings
    max_line_length: int = Field(
        default=120, description="Maximum recommended line length", ge=80, le=200
    )

    max_test_case_lines: int = Field(
        default=50, description="Maximum lines for a test case", ge=20, le=200
    )

    max_keyword_complexity: int = Field(
        default=10,
        description="Maximum cyclomatic complexity for keywords",
        ge=5,
        le=50,
    )

    # Sleep detection
    max_acceptable_sleep_seconds: float = Field(
        default=1.0,
        description="Maximum acceptable sleep duration in seconds",
        ge=0.1,
        le=10.0,
    )

    # Flakiness detection
    flakiness_threshold: float = Field(
        default=0.05,
        description="Failure rate threshold for flaky test detection",
        ge=0.01,
        le=0.5,
    )

    flakiness_min_runs: int = Field(
        default=4, description="Minimum test runs to determine flakiness", ge=3, le=100
    )

    # System settings
    enable_metrics: bool = Field(
        default=True, description="Whether to enable metrics collection"
    )

    enable_telemetry: bool = Field(
        default=False,
        description=(
            "Opt-in telemetry for premium conversion tracking. "
            "No PII is collected. No network calls are made by the free edition. "
            "Set ROBOT_OPTIMIZER_ENABLE_TELEMETRY=1 to enable."
        ),
    )

    log_level: str = Field(
        default="INFO",
        description="Logging level",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    )

    log_format_json: bool = Field(
        default=False, description="Whether to use JSON log formatting"
    )

    # Plugin settings
    plugins_enabled: bool = Field(
        default=True, description="Whether to enable plugin loading"
    )

    plugin_dirs: list[Path] = Field(
        default_factory=list, description="Directories to search for plugins"
    )

    trusted_analyzer_packages: list[str] = Field(
        default_factory=list,
        description=(
            "Allowlist of distribution package names whose entry-point analyzers "
            "are trusted to load automatically.  When empty (the default) all "
            "installed entry-point analyzers are loaded with a security warning. "
            "Set to a non-empty list to restrict loading to specific packages "
            '(e.g. ["robot-framework-optimizer-core"]).'
        ),
    )

    # Pro version extension point
    custom_settings: dict[str, Any] = Field(
        default_factory=dict, description="Custom settings for extensions"
    )

    # Per-analyzer configuration
    analyzer_config: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Per-analyzer configuration overrides. "
            "Keys are analyzer names; values are dicts passed to each analyzer "
            "at instantiation.  Example: "
            '{"sleep_detector": {"max_acceptable_sleep_seconds": 0.5}}'
        ),
    )

    model_config = SettingsConfigDict(
        env_prefix="ROBOT_OPTIMIZER_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",  # Raise on unknown fields to surface typos and misconfigured keys
    )

    def model_post_init(self, __context: Any) -> None:
        """Run cross-field validation immediately after Pydantic construction.

        Pydantic validates individual field constraints during ``__init__``,
        but cross-field rules (e.g. pattern overlap) are checked here so that
        invalid ``Settings(...)`` calls raise :class:`ConfigurationError` at
        construction time rather than at first use.

        Args:
            __context: Pydantic internal context (passed by the framework).

        Raises:
            ConfigurationError: If any cross-field validation rule is violated.
        """
        self.validate_settings()

    @field_validator("file_patterns", "exclude_patterns")
    @classmethod
    def validate_patterns(cls, v: list[str]) -> list[str]:
        """Validate file patterns.

        Args:
            v: List of patterns.

        Returns:
            Validated patterns.

        Raises:
            ValueError: If patterns are invalid.
        """
        if not v:
            raise ValueError("At least one pattern must be specified")

        # Ensure patterns are strings
        return [str(p) for p in v]

    @field_validator("plugin_dirs")
    @classmethod
    def validate_plugin_dirs(cls, v: list[str | Path]) -> list[Path]:
        """Validate and convert plugin directories to Path objects.

        Args:
            v: List of directory paths.

        Returns:
            List of Path objects.
        """
        paths = []
        for p in v:
            path = Path(p)
            if not path.exists():
                _logger.warning("Plugin directory does not exist and will be ignored: %s", path)
                continue
            if not path.is_dir():
                raise ValueError(f"Plugin path is not a directory: {path}")
            paths.append(path)
        return paths

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level.

        Args:
            v: Log level string.

        Returns:
            Uppercase log level.
        """
        return v.upper()

    def get_custom_setting(
        self, key: str, default: Any = None, setting_type: type | None = None
    ) -> Any:
        """Get a custom setting with type validation.

        This method is designed for Pro version extensions to
        safely access custom settings.

        Args:
            key: Setting key.
            default: Default value if not found.
            setting_type: Expected type for validation.

        Returns:
            Setting value.

        Raises:
            ConfigurationError: If type validation fails.
        """
        value = self.custom_settings.get(key, default)

        if setting_type and value is not None:
            if not isinstance(value, setting_type):
                raise ConfigurationError(
                    f"Invalid type for setting '{key}'",
                    config_key=key,
                    provided_value=value,
                    details={
                        "expected_type": setting_type.__name__,
                        "actual_type": type(value).__name__,
                    },
                )

        return value

    def set_custom_setting(self, key: str, value: Any) -> None:
        """Set a custom setting.

        Args:
            key: Setting key.
            value: Setting value.
        """
        self.custom_settings[key] = value

    def validate_settings(self) -> None:
        """Perform additional validation.

        This method can be overridden by Pro version to add
        custom validation logic.

        Raises:
            ConfigurationError: If validation fails.
        """
        # Validate patterns don't conflict
        pattern_overlap = set(self.file_patterns) & set(self.exclude_patterns)
        if pattern_overlap:
            raise ConfigurationError(
                "File patterns overlap with exclude patterns",
                config_key="patterns",
                provided_value=list(pattern_overlap),
            )

    @property
    def max_file_size_bytes(self) -> int:
        """Get maximum file size in bytes.

        Returns:
            Maximum file size in bytes.
        """
        return int(self.max_file_size_mb * 1024 * 1024)

    def to_dict(self) -> dict[str, Any]:
        """Convert settings to dictionary.

        Returns:
            Dictionary of settings.
        """
        return self.model_dump()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: SettingsSourceCallable,
        env_settings: SettingsSourceCallable,
        dotenv_settings: SettingsSourceCallable,
        file_secret_settings: SettingsSourceCallable,
    ) -> tuple[SettingsSourceCallable, ...]:
        """Customize settings sources for priority.

        Priority order:
        1. Init arguments
        2. Environment variables
        3. .env file (dotenv)
        4. File secrets
        5. Defaults

        Args:
            settings_cls: Settings class.
            init_settings: Init settings source.
            env_settings: Environment settings source.
            dotenv_settings: Dotenv file settings source.
            file_secret_settings: File settings source.

        Returns:
            Tuple of settings sources.
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get the global settings instance.

    Returns:
        The global settings instance.

    Example:
        >>> settings = get_settings()
        >>> print(settings.max_file_size_mb)
    """
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.validate_settings()
    return _settings


def configure_settings(**kwargs: Any) -> Settings:
    """Configure global settings with overrides.

    Args:
        **kwargs: Setting overrides.

    Returns:
        Updated settings instance.

    Example:
        >>> settings = configure_settings(
        ...     max_file_size_mb=20,
        ...     log_level="DEBUG"
        ... )
    """
    global _settings
    _settings = Settings(**kwargs)
    _settings.validate_settings()
    return _settings


def reset_settings() -> None:
    """Reset settings to defaults.

    This is mainly useful for testing.
    """
    global _settings
    _settings = None
