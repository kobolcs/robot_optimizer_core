# src/robot_optimizer_core/analyzers/base.py
"""Base analyzer class with plugin support for Robot Framework analysis.

This module provides the enhanced base analyzer that all analyzers must
inherit from, including support for the plugin system and metrics.

Example:
    Creating a custom analyzer::

        from robot_optimizer_core.analyzers import BaseAnalyzer
        from robot_optimizer_core import Finding, Pattern, Severity

        class MyAnalyzer(BaseAnalyzer):
            @property
            def name(self) -> str:
                return "my_analyzer"

            @property
            def description(self) -> str:
                return "My custom analyzer"

            def analyze(self, test_file: TestFile) -> list[Finding]:
                findings = []
                # Analysis logic here
                return findings
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeAlias, TypeVar

from ..domain.entities import TestFile
from ..domain.value_objects import Finding, Severity
from ..exceptions import AnalysisError
from ..logging import get_logger
from ..metrics import get_metrics

# Type alias for analyzer configuration values
ConfigValue: TypeAlias = str | int | float | bool | dict[str, object] | list[object] | None

# Type variable for generic config value retrieval
T = TypeVar("T")

logger = get_logger(__name__)


class BaseAnalyzer(ABC):
    """Enhanced base class for all analyzers with plugin support.

    This abstract base class defines the interface that all analyzers
    must implement. It includes hooks for metrics, logging, and error
    handling that can be extended by subclasses.

    Attributes:
        config: Analyzer-specific configuration.
        metrics_enabled: Whether to collect metrics for this analyzer.
    """

    __slots__ = ("_logger", "_metrics", "config", "metrics_enabled")

    def __init__(
        self,
        config: dict[str, ConfigValue] | None = None,
        metrics_enabled: bool = True
    ) -> None:
        """Initialize the analyzer.

        Args:
            config: Analyzer-specific configuration.
            metrics_enabled: Whether to collect metrics.
        """
        self.config = config or {}
        self.metrics_enabled = metrics_enabled
        self._metrics = get_metrics() if metrics_enabled else None
        self._logger = get_logger(
            f"{__name__}.{self.__class__.__name__}",
            {"analyzer": self.name}
        )

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the analyzer name.

        This should be a unique identifier for the analyzer.

        Returns:
            Analyzer name.
        """

    @property
    @abstractmethod
    def description(self) -> str:
        """Get the analyzer description.

        This should be a human-readable description of what
        the analyzer does.

        Returns:
            Analyzer description.
        """

    @property
    def version(self) -> str:
        """Get the analyzer version.

        Subclasses can override this to provide version information.

        Returns:
            Analyzer version (default: "1.0.0").
        """
        return "1.0.0"

    @property
    def tags(self) -> list[str]:
        """Get analyzer tags for categorization.

        Subclasses can override this to provide tags.

        Returns:
            List of tags (default: empty).
        """
        return []

    @property
    def supports_auto_fix(self) -> bool:
        """Check if analyzer supports auto-fixing.

        Subclasses that support auto-fixing should override this.

        Returns:
            True if auto-fix is supported (default: False).
        """
        return False

    @abstractmethod
    def analyze(self, test_file: TestFile) -> list[Finding]:
        """Analyze a test file and return findings.

        This is the main method that subclasses must implement.
        It should analyze the given test file and return a list
        of findings.

        Args:
            test_file: The test file to analyze.

        Returns:
            List of findings discovered.

        Raises:
            AnalysisError: If analysis fails.
        """

    def pre_analyze(self, test_file: TestFile) -> None:  # noqa: B027
        """Hook called before analysis.

        Subclasses can override this to perform setup tasks.
        This is called before analyze() and is wrapped in
        error handling.

        Args:
            test_file: The test file to be analyzed.
        """

    def post_analyze(
        self,
        test_file: TestFile,
        findings: list[Finding]
    ) -> list[Finding]:
        """Hook called after analysis.

        Subclasses can override this to perform cleanup or
        modify findings. This is called after analyze() and
        is wrapped in error handling.

        Args:
            test_file: The test file that was analyzed.
            findings: The findings from analysis.

        Returns:
            Modified findings (default: unchanged).
        """
        return findings

    def validate_config(self) -> None:  # noqa: B027
        """Validate analyzer configuration.

        Subclasses can override this to validate their specific
        configuration. This is called during initialization.

        Raises:
            ConfigurationError: If configuration is invalid.
        """

    def safe_analyze(self, test_file: TestFile) -> list[Finding]:
        """Safely analyze a file with full error handling.

        This method wraps the analyze() method with error handling,
        metrics collection, and logging. It should not be overridden
        by subclasses.

        Args:
            test_file: The test file to analyze.

        Returns:
            List of findings discovered.

        Raises:
            AnalysisError: If analysis fails.
        """
        self._logger.debug(
            "Starting analysis",
            extra={"file": str(test_file.path)}
        )

        try:
            # Pre-analysis hook
            self.pre_analyze(test_file)

            # Main analysis
            findings = self.analyze(test_file)

            # Validate findings
            validated_findings = self._validate_findings(findings, test_file)

            # Post-analysis hook
            final_findings = self.post_analyze(test_file, validated_findings)

            # Collect metrics
            if self._metrics:
                self._metrics.increment(f"analyzer.{self.name}.success")
                self._metrics.gauge(
                    f"analyzer.{self.name}.findings_count",
                    len(final_findings)
                )

            self._logger.debug(
                "Analysis complete",
                extra={
                    "file": str(test_file.path),
                    "findings_count": len(final_findings)
                }
            )

            return final_findings

        except AnalysisError:
            # Re-raise analysis errors
            if self._metrics:
                self._metrics.increment(f"analyzer.{self.name}.failure")
            raise

        except Exception as e:
            # Wrap other errors
            if self._metrics:
                self._metrics.increment(f"analyzer.{self.name}.failure")

            self._logger.error(
                f"Analysis failed: {e}",
                extra={
                    "file": str(test_file.path),
                    "error_type": type(e).__name__
                },
                exc_info=True
            )

            raise AnalysisError(
                f"Analysis failed in {self.name}: {e}",
                file_path=test_file.path,
                analyzer=self.name
            ) from e

    def _validate_findings(
        self,
        findings: list[Finding],
        test_file: TestFile
    ) -> list[Finding]:
        """Validate findings from analysis.

        This ensures all findings have correct file paths and
        valid line numbers.

        Args:
            findings: Findings to validate.
            test_file: The analyzed file.

        Returns:
            Validated findings.
        """
        validated = []

        for finding in findings:
            # Ensure file path matches
            if finding.location.file_path != test_file.path:
                self._logger.warning(
                    "Finding has incorrect file path",
                    extra={
                        "expected": str(test_file.path),
                        "actual": str(finding.location.file_path)
                    }
                )
                continue

            # Ensure line number is valid
            if finding.location.line > test_file.line_count:
                self._logger.warning(
                    "Finding has invalid line number",
                    extra={
                        "line": finding.location.line,
                        "max_line": test_file.line_count
                    }
                )
                continue

            validated.append(finding)

        return validated

    def get_config_value(
        self,
        key: str,
        default: T | None = None,
        required: bool = False
    ) -> T | ConfigValue:
        """Get a configuration value with type safety.

        Convenience method for accessing configuration with
        defaults and validation.

        Args:
            key: Configuration key.
            default: Default value if not found.
            required: Whether the key is required.

        Returns:
            Configuration value.

        Raises:
            ConfigurationError: If required key is missing.
        """
        if required and key not in self.config:
            from ..exceptions import ConfigurationError
            raise ConfigurationError(
                f"Required configuration key missing: {key}",
                config_key=f"{self.name}.{key}"
            )

        return self.config.get(key, default)

    def determine_severity_by_threshold(
        self,
        value: float,
        thresholds: dict[str, float]
    ) -> Severity:
        """Determine severity based on value and threshold mapping.

        This is a helper method to reduce duplication across analyzers
        that use threshold-based severity determination.

        Args:
            value: The numeric value to evaluate.
            thresholds: Dict mapping severity level names to threshold values.
                       Should contain 'info', 'warning', and 'error' keys.

        Returns:
            Severity level based on thresholds.

        Example:
            >>> thresholds = {'info': 1.0, 'warning': 5.0, 'error': 10.0}
            >>> self.determine_severity_by_threshold(3.0, thresholds)
            Severity.WARNING
        """
        # Check thresholds in order from highest to lowest severity
        if value >= thresholds.get("error", float("inf")):
            return Severity.ERROR
        if value >= thresholds.get("warning", float("inf")):
            return Severity.WARNING
        return Severity.INFO

    def __repr__(self) -> str:
        """Return string representation of analyzer.

        Returns:
            String representation.
        """
        return (
            f"{self.__class__.__name__}("
            f"name={self.name!r}, "
            f"version={self.version!r})"
        )
