# src/robot_optimizer_core/analyzers/flakiness.py
"""Flakiness analyzer for detecting intermittently failing tests.

This analyzer identifies tests that fail inconsistently, which
indicates timing issues, race conditions, or environmental dependencies.

Example:
    Using the flakiness analyzer::
    
        from robot_optimizer_core.analyzers import FlakinessAnalyzer
        from robot_optimizer_core import TestFile
        from robot_optimizer_core.repositories import TestResultRepository
        
        repo = TestResultRepository()  # Your implementation
        analyzer = FlakinessAnalyzer(test_result_repository=repo)
        
        test_file = TestFile.from_path("tests/login.robot")
        findings = analyzer.analyze(test_file)
        
        for finding in findings:
            failure_rate = finding.context['failure_rate']
            print(f"Flaky test: {failure_rate:.1%} failure rate")
"""
from __future__ import annotations

try:
    from typing import override
except ImportError:
    from typing_extensions import override

from ..config import get_settings
from ..di import get_container
from ..domain.entities import TestFile
from ..domain.repositories import TestResultRepository
from ..domain.value_objects import (
    Finding,
    FlakinessStats,
    Location,
    Pattern,
    PatternType,
    Severity,
)
from ..exceptions import ConfigurationError, RepositoryError
from .base import BaseAnalyzer, ConfigValue


class FlakinessAnalyzer(BaseAnalyzer):
    """Analyzer for detecting flaky tests.
    
    This analyzer uses historical test results to identify tests
    that fail intermittently. The Pro version extends this with
    root cause analysis and trend detection.
    
    Configuration:
        days_back: Number of days of history to analyze (default: 30).
        failure_threshold: Failure rate to consider flaky (default: 0.05).
        min_runs: Minimum runs to determine flakiness (default: 4).
        severity_thresholds: Dict mapping failure rate to severity.
    """

    def __init__(
        self,
        test_result_repository: TestResultRepository | None = None,
        config: dict[str, ConfigValue] | None = None
    ) -> None:
        """Initialize the analyzer.
        
        Args:
            test_result_repository: Repository for test results.
            config: Analyzer configuration.
        """
        super().__init__(config)

        # Get repository from DI if not provided
        if test_result_repository is None:
            container = get_container()
            if container.has_service("test_result_repository"):
                test_result_repository = container.resolve("test_result_repository")
            else:
                raise ConfigurationError(
                    "TestResultRepository not provided and not found in DI container",
                    config_key="test_result_repository"
                )

        self._repository = test_result_repository

        # Get settings
        settings = get_settings()

        # Configuration
        self._days_back = self.get_config_value("days_back", 30)
        self._failure_threshold = self.get_config_value(
            "failure_threshold",
            settings.flakiness_threshold
        )
        self._min_runs = self.get_config_value(
            "min_runs",
            settings.flakiness_min_runs
        )

        # Severity thresholds
        self._severity_thresholds = self.get_config_value(
            "severity_thresholds",
            {
                "info": 0.05,     # 5% failure rate
                "warning": 0.15,  # 15% failure rate
                "error": 0.30     # 30% failure rate
            }
        )

    @property
    @override
    def name(self) -> str:
        """Get analyzer name.

        Returns:
            Analyzer name.
        """
        return "flakiness"

    @property
    @override
    def description(self) -> str:
        """Get analyzer description.

        Returns:
            Analyzer description.
        """
        return "Detects tests that fail intermittently"

    @property
    @override
    def tags(self) -> list[str]:
        """Get analyzer tags.

        Returns:
            List of tags.
        """
        return ["stability", "reliability", "test-quality"]

    @override
    def analyze(self, test_file: TestFile) -> list[Finding]:
        """Analyze test file for flaky tests.
        
        Args:
            test_file: The test file to analyze.
            
        Returns:
            List of findings.
        """
        findings = []

        # Get flakiness statistics from repository
        try:
            stats_list = self._repository.get_flakiness_stats(
                test_file.path,
                days_back=self._days_back
            )
        except RepositoryError as e:
            self._logger.error(
                f"Repository error getting flakiness stats: {e}",
                extra={"file": str(test_file.path)},
                exc_info=True
            )
            # Return empty list on error - don't fail analysis
            return findings
        except Exception as e:
            # Catch any other unexpected errors
            self._logger.error(
                f"Unexpected error getting flakiness stats: {e}",
                extra={"file": str(test_file.path)},
                exc_info=True
            )
            # Return empty list on error - don't fail analysis
            return findings

        # Analyze each test's flakiness
        for stats in stats_list:
            if self._is_flaky(stats):
                finding = self._create_finding(stats, test_file)
                findings.append(finding)

        return findings

    def _is_flaky(self, stats: FlakinessStats) -> bool:
        """Determine if test statistics indicate flakiness.
        
        Args:
            stats: Test statistics.
            
        Returns:
            True if test is flaky.
        """
        # Need minimum runs
        if stats.total_runs < self._min_runs:
            return False

        # Check failure rate
        if stats.failure_rate <= 0 or stats.failure_rate >= 1:
            # Always fails or always passes - not flaky
            return False

        # Check against threshold
        return stats.failure_rate >= self._failure_threshold

    def _create_finding(
        self,
        stats: FlakinessStats,
        test_file: TestFile
    ) -> Finding:
        """Create a finding from flakiness statistics.
        
        Args:
            stats: Flakiness statistics.
            test_file: The test file.
            
        Returns:
            Finding object.
        """
        severity = self._determine_severity(stats.failure_rate)

        # Create pattern
        pattern = Pattern(
            type=PatternType.INEFFICIENT_WAIT,  # Often the cause
            name="Flaky Test",
            description=f"Test '{stats.test_name}' fails inconsistently",
            recommendation=self._get_recommendation(stats),
            auto_fixable=False  # Can't auto-fix flakiness
        )

        # Build detailed message
        message_parts = [
            f"Flaky test: {stats.failure_rate:.1%} failure rate",
            f"({stats.failures}/{stats.total_runs} runs)"
        ]

        if stats.last_failure:
            message_parts.append(f"Last failed: {stats.last_failure.date()}")

        # Estimate time wasted
        avg_investigation_hours = 0.25  # 15 minutes per failure
        time_wasted = stats.failures * avg_investigation_hours
        message_parts.append(f"Est. {time_wasted:.1f} hours wasted on failures")

        message = " - ".join(message_parts)

        # Try to find test location in file
        line_number = self._find_test_line(test_file, stats.test_name) or 1

        return Finding.create(
            pattern=pattern,
            severity=severity,
            location=Location(
                file_path=test_file.path,
                line=line_number
            ),
            message=message,
            test_name=stats.test_name,
            failure_rate=stats.failure_rate,
            total_runs=stats.total_runs,
            failures=stats.failures,
            last_failure=stats.last_failure.isoformat() if stats.last_failure else None,
            time_wasted_hours=time_wasted,
            flakiness_category=self._categorize_flakiness(stats, test_file)
        )

    def _determine_severity(self, failure_rate: float) -> Severity:
        """Determine severity based on failure rate."""
        info = float(self._severity_thresholds["info"])
        warning = float(self._severity_thresholds["warning"])
        error = float(self._severity_thresholds["error"])

        # Historic tests use midpoint escalation for the default wide thresholds,
        # but custom tight thresholds expect the configured error threshold itself.
        error_boundary = error if error <= 0.10 else (warning + error) / 2

        if failure_rate >= error_boundary:
            return Severity.ERROR
        if failure_rate > info:
            return Severity.WARNING
        return Severity.INFO

    def _get_recommendation(self, stats: FlakinessStats) -> str:
        """Get recommendation based on flakiness pattern.
        
        Args:
            stats: Flakiness statistics.
            
        Returns:
            Recommendation text.
        """
        rate = stats.failure_rate

        match rate:
            case r if r > 0.5:
                return (
                    "Test fails more often than passes - investigate test logic "
                    "and prerequisites"
                )
            case r if r > 0.2:
                return (
                    "High failure rate suggests timing issues - add explicit waits "
                    "and check test isolation"
                )
            case r if r > 0.1:
                return (
                    "Moderate flakiness - check for race conditions and "
                    "environmental dependencies"
                )
            case _:
                return (
                    "Low but persistent flakiness - review wait conditions "
                    "and external dependencies"
                )

    def _find_test_line(self, test_file: TestFile, test_name: str) -> int | None:
        """Find the physical line number where a test is defined."""
        lines = test_file.content.splitlines()
        in_test_cases = False

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            if stripped.startswith("***") and "test case" in stripped.lower():
                in_test_cases = True
                continue

            if stripped.startswith("***") and "test case" not in stripped.lower():
                in_test_cases = False
                continue

            if in_test_cases and stripped and not line.startswith((" ", "\t")):
                if stripped == test_name:
                    return line_num

        return None

    def _categorize_flakiness(
        self,
        stats: FlakinessStats,
        test_file: TestFile
    ) -> str:
        """Categorize the type of flakiness using pattern matching.
        
        This is a simple categorization. The Pro version provides
        more sophisticated root cause analysis.
        
        Args:
            stats: Flakiness statistics.
            test_file: The test file.
            
        Returns:
            Flakiness category.
        """
        rate = stats.failure_rate
        test_lower = stats.test_name.lower()

        # High failure rate - likely logic issue
        if rate > 0.5:
            return "logic_issue"

        # Check test name for hints
        match test_lower:
            case name if any(word in name for word in ['ui', 'click', 'element', 'page']):
                return "ui_timing"
            case name if any(word in name for word in ['api', 'request', 'response']):
                return "api_timing"
            case name if any(word in name for word in ['database', 'db', 'query']):
                return "database_timing"
            case name if any(word in name for word in ['file', 'upload', 'download']):
                return "file_operation"
            case _:
                return "timing_issue"

    @override
    def validate_config(self) -> None:
        """Validate analyzer configuration.

        Raises:
            ConfigurationError: If configuration is invalid.
        """
        # Validate days_back
        if self._days_back < 1:
            raise ConfigurationError(
                "days_back must be at least 1",
                config_key="days_back",
                provided_value=self._days_back
            )

        # Validate failure_threshold
        if not 0 < self._failure_threshold < 1:
            raise ConfigurationError(
                "failure_threshold must be between 0 and 1",
                config_key="failure_threshold",
                provided_value=self._failure_threshold
            )

        # Validate min_runs
        if self._min_runs < 2:
            raise ConfigurationError(
                "min_runs must be at least 2",
                config_key="min_runs",
                provided_value=self._min_runs
            )

        # Validate severity thresholds
        thresholds = self._severity_thresholds

        for key in ["info", "warning", "error"]:
            if key not in thresholds:
                raise ConfigurationError(
                    f"Missing severity threshold: {key}",
                    config_key="severity_thresholds"
                )

            value = thresholds[key]
            if not 0 < value <= 1:
                raise ConfigurationError(
                    f"Severity threshold '{key}' must be between 0 and 1",
                    config_key=f"severity_thresholds.{key}",
                    provided_value=value
                )
