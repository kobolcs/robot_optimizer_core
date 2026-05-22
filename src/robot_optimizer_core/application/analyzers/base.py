# src/robot_optimizer_core/application/analyzers/base.py
"""Base analyzer class with metrics integration and plugin support.

All built-in and third-party analyzers must subclass :class:`BaseAnalyzer` and
implement :meth:`~BaseAnalyzer.analyze`. The base class handles metrics
recording, error wrapping, finding validation, and lifecycle hooks
(``pre_analyze`` / ``post_analyze``) so that individual analyzers stay focused
on their detection logic.

Example:
    Implementing a minimal custom analyzer::

        from robot_optimizer_core.application.analyzers import BaseAnalyzer
        from robot_optimizer_core.domain.entities import TestFile
        from robot_optimizer_core.domain.value_objects import Finding

        class MyAnalyzer(BaseAnalyzer):
            @property
            def name(self) -> str:
                return "my_analyzer"

            @property
            def description(self) -> str:
                return "My custom analysis rules"

            def analyze(self, test_file: TestFile) -> list[Finding]:
                return []  # detection logic here
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import (
    TYPE_CHECKING,
    ClassVar,
    Protocol,
    TypeAlias,
    TypeVar,
    runtime_checkable,
)

from ...domain.entities import TestFile
from ...domain.value_objects import Finding, Severity
from ...exceptions import AnalysisError
from ...infrastructure.logging.adapter import get_logger
from ...infrastructure.metrics.collector import MetricsCollector, get_metrics

if TYPE_CHECKING:
    from collections.abc import Sequence

# Type alias for analyzer configuration values
__all__ = ["BaseAnalyzer", "ConfigValue", "SuiteAwareAnalyzer"]

ConfigValue: TypeAlias = (
    str | int | float | bool | dict[str, object] | list[object] | None
)

T = TypeVar("T")  # kept for any remaining generic use in subclasses


@runtime_checkable
class SuiteAwareAnalyzer(Protocol):
    """Protocol for analyzers that support cross-file suite-level analysis.

    Analyzers that implement this protocol receive the full list of
    :class:`~robot_optimizer_core.domain.entities.TestFile` objects in
    a suite, enabling cross-file detection (e.g. unused keywords that are
    only called from other files).

    Third-party analyzers can participate in :func:`analyze_suite` by
    implementing this method alongside :class:`BaseAnalyzer`.
    """

    def analyze_suite(self, files: Sequence[TestFile]) -> list[Finding]:
        """Analyze an entire suite of test files as a single unit.

        Args:
            files: All test files that belong to the suite.

        Returns:
            List of findings discovered across the suite.
        """
        ...

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
        self, config: dict[str, ConfigValue] | None = None, metrics_enabled: bool = True
    ) -> None:
        """Initialize the analyzer.

        Args:
            config: Analyzer-specific configuration.
            metrics_enabled: Whether to collect metrics.
        """
        self.config = config or {}
        self.metrics_enabled = metrics_enabled
        # Resolved lazily on first safe_analyze call
        self._metrics: MetricsCollector | None = None
        self._logger = get_logger(
            f"{__name__}.{self.__class__.__name__}", {"analyzer": self.name}
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

    #: Set to True on subclasses that require an external repository to be
    #: injected (e.g. TestResultRepository). The default API reads this at
    #: the class level before instantiation to skip such analyzers.
    requires_external_repo: ClassVar[bool] = False

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

    def pre_analyze(self, _test_file: TestFile) -> None:  # noqa: B027
        """Hook called before analysis.

        Subclasses can override this to perform setup tasks.
        This is called before analyze() and is wrapped in
        error handling.

        Args:
            _test_file: The test file to be analyzed.
        """

    def post_analyze(
        self, _test_file: TestFile, findings: list[Finding]
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
        self._logger.debug("Starting analysis", extra={"file": str(test_file.path)})

        try:
            if self.metrics_enabled and self._metrics is None:
                self._metrics = get_metrics()

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
                    f"analyzer.{self.name}.findings_count", len(final_findings)
                )

            self._logger.debug(
                "Analysis complete",
                extra={
                    "file": str(test_file.path),
                    "findings_count": len(final_findings),
                },
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
                extra={"file": str(test_file.path), "error_type": type(e).__name__},
                exc_info=True,
            )

            raise AnalysisError(
                f"Analysis failed in {self.name}: {e}",
                file_path=test_file.path,
                analyzer=self.name,
            ) from e

    def _validate_findings(
        self, findings: list[Finding], test_file: TestFile
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
        dropped = 0

        for finding in findings:
            # Normalise both paths to absolute before comparing so that a
            # finding constructed with an absolute path is not wrongly dropped
            # when test_file.path is relative (or vice-versa).
            if finding.location.file_path.resolve() != test_file.path.resolve():
                dropped += 1
                self._logger.warning(
                    "Dropping finding: file path mismatch",
                    extra={
                        "expected": str(test_file.path),
                        "actual": str(finding.location.file_path),
                        "finding_message": finding.message,
                    },
                )
                continue

            # Ensure line number is valid
            if finding.location.line > test_file.line_count:
                dropped += 1
                self._logger.warning(
                    "Dropping finding: line number out of range",
                    extra={
                        "line": finding.location.line,
                        "max_line": test_file.line_count,
                        "finding_message": finding.message,
                    },
                )
                continue

            validated.append(finding)

        if dropped:
            self._logger.warning(
                "Dropped invalid findings",
                extra={
                    "dropped": dropped,
                    "kept": len(validated),
                    "total": len(findings),
                    "file": str(test_file.path),
                },
            )
            if self._metrics:
                self._metrics.increment(
                    f"analyzer.{self.name}.findings_dropped", dropped
                )

        return validated

    def get_config_value(
        self, key: str, default: ConfigValue = None, required: bool = False
    ) -> ConfigValue:
        """Get a configuration value.

        Returns whatever is stored in ``self.config[key]``, which may be any
        ``ConfigValue`` type regardless of the type of *default*.  Callers that
        need type guarantees should use the typed helpers
        :meth:`get_bool_config`, :meth:`get_int_config`, etc., which validate
        the stored value at runtime.

        Args:
            key: Configuration key.
            default: Default value when the key is absent.
            required: When ``True``, raise ``ConfigurationError`` if the key is
                missing instead of returning *default*.

        Returns:
            The stored ``ConfigValue``, or *default* when the key is absent.

        Raises:
            ConfigurationError: If *required* is ``True`` and the key is missing.
        """
        if required and key not in self.config:
            from ...exceptions import ConfigurationError

            raise ConfigurationError(
                f"Required configuration key missing: {key}",
                config_key=f"{self.name}.{key}",
            )

        return self.config.get(key, default)

    def get_bool_config(self, key: str, default: bool) -> bool:
        """Get a boolean configuration value, raising ConfigurationError on type mismatch."""
        val = self.get_config_value(key, default)
        if not isinstance(val, bool):
            from ...exceptions import ConfigurationError
            raise ConfigurationError(
                f"Config key '{key}' must be a bool, got {type(val).__name__}",
                config_key=f"{self.name}.{key}",
                provided_value=val,
            )
        return val

    def get_int_config(self, key: str, default: int) -> int:
        """Get an integer configuration value, raising ConfigurationError on type mismatch."""
        val = self.get_config_value(key, default)
        if not isinstance(val, int) or isinstance(val, bool):
            from ...exceptions import ConfigurationError
            raise ConfigurationError(
                f"Config key '{key}' must be an int, got {type(val).__name__}",
                config_key=f"{self.name}.{key}",
                provided_value=val,
            )
        return val

    def get_float_config(self, key: str, default: float) -> float:
        """Get a float configuration value, raising ConfigurationError on type mismatch."""
        val = self.get_config_value(key, default)
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            from ...exceptions import ConfigurationError
            raise ConfigurationError(
                f"Config key '{key}' must be a float, got {type(val).__name__}",
                config_key=f"{self.name}.{key}",
                provided_value=val,
            )
        return float(val)

    def get_list_config(self, key: str, default: list[object]) -> list[object]:
        """Get a list configuration value, raising ConfigurationError on type mismatch."""
        val = self.get_config_value(key, default)
        if not isinstance(val, list):
            from ...exceptions import ConfigurationError
            raise ConfigurationError(
                f"Config key '{key}' must be a list, got {type(val).__name__}",
                config_key=f"{self.name}.{key}",
                provided_value=val,
            )
        return val

    def determine_severity_by_threshold(
        self, value: float, thresholds: dict[str, float]
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
            f"{self.__class__.__name__}(name={self.name!r}, version={self.version!r})"
        )
