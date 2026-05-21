# tests/unit/analyzers/test_flakiness.py
"""Unit tests for FlakinessAnalyzer.

Tests cover flakiness detection, severity determination, and integration
with the test result repository.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from robot_optimizer_core.analyzers import FlakinessAnalyzer
from robot_optimizer_core.config import Settings
from robot_optimizer_core.domain.entities import TestFile
from robot_optimizer_core.domain.repositories import TestResultRepository
from robot_optimizer_core.domain.value_objects import (
    FlakinessStats,
    PatternType,
    Severity,
)
from robot_optimizer_core.exceptions import ConfigurationError, RepositoryError


@pytest.mark.unit
class TestFlakinessAnalyzer:
    """Test the FlakinessAnalyzer."""

    @pytest.fixture
    def mock_repository(self) -> Mock:
        """Create mock test result repository."""
        mock = Mock(spec=TestResultRepository)
        mock.get_flakiness_stats.return_value = []
        return mock

    @pytest.fixture
    def test_file(self) -> TestFile:
        """Create test file with flaky tests."""
        content = """*** Test Cases ***
Flaky Login Test
    [Documentation]    This test is flaky
    Open Browser    ${URL}    chrome
    Wait Until Element Is Visible    id=login    timeout=2s
    Click Button    id=login

Stable Test
    Log    Always passes

Very Flaky Test
    [Documentation]    Fails often
    ${random}=    Evaluate    random.random()
    Should Be True    ${random} > 0.7
"""
        return TestFile(
            path=Path("tests/flaky.robot"),
            content=content,
            size_bytes=len(content),
            last_modified_utc=datetime.now(),
        )

    def test_create_analyzer_with_repository(self, mock_repository: Mock) -> None:
        """Test creating analyzer with provided repository."""
        analyzer = FlakinessAnalyzer(test_result_repository=mock_repository)

        assert analyzer.name == "flakiness"
        assert analyzer.description == "Detects tests that fail intermittently"
        assert analyzer.tags == ["stability", "reliability", "test-quality"]
        assert not analyzer.supports_auto_fix
        assert analyzer._repository == mock_repository

    def test_create_analyzer_from_container(self, mock_repository: Mock) -> None:
        """Test creating analyzer without repository returns None repo (Task 11)."""
        # Without a repository, construction succeeds but _repository is None
        analyzer = FlakinessAnalyzer()
        assert analyzer._repository is None

    def test_configuration_options(self, mock_repository: Mock) -> None:
        """Test analyzer configuration."""
        config = {
            "days_back": 60,
            "failure_threshold": 0.1,
            "min_runs": 10,
            "severity_thresholds": {"info": 0.1, "warning": 0.2, "error": 0.4},
        }

        analyzer = FlakinessAnalyzer(
            test_result_repository=mock_repository, config=config
        )

        assert analyzer._days_back == 60
        assert analyzer._failure_threshold == pytest.approx(0.1)
        assert analyzer._min_runs == 10
        assert analyzer._severity_thresholds["warning"] == pytest.approx(0.2)

    def test_analyze_no_flaky_tests(
        self, mock_repository: Mock, test_file: TestFile
    ) -> None:
        """Test analysis when no tests are flaky."""
        # All tests are stable
        mock_repository.get_flakiness_stats.return_value = [
            FlakinessStats(
                test_name="Stable Test",
                file_path=test_file.path,
                total_runs=100,
                failures=0,
            )
        ]

        analyzer = FlakinessAnalyzer(test_result_repository=mock_repository)
        findings = analyzer.analyze(test_file)

        assert len(findings) == 0
        mock_repository.get_flakiness_stats.assert_called_once_with(
            test_file.path, days_back=30
        )

    def test_analyze_flaky_tests(
        self, mock_repository: Mock, test_file: TestFile
    ) -> None:
        """Test analysis with flaky tests."""
        now = datetime.now()

        mock_repository.get_flakiness_stats.return_value = [
            # Flaky test (15% failure rate)
            FlakinessStats(
                test_name="Flaky Login Test",
                file_path=test_file.path,
                total_runs=100,
                failures=15,
                last_failure=now - timedelta(hours=2),
            ),
            # Very flaky test (50% failure rate)
            FlakinessStats(
                test_name="Very Flaky Test",
                file_path=test_file.path,
                total_runs=50,
                failures=25,
                last_failure=now - timedelta(days=1),
            ),
            # Stable test
            FlakinessStats(
                test_name="Stable Test",
                file_path=test_file.path,
                total_runs=200,
                failures=0,
            ),
            # Always fails (not flaky)
            FlakinessStats(
                test_name="Broken Test",
                file_path=test_file.path,
                total_runs=20,
                failures=20,
            ),
        ]

        analyzer = FlakinessAnalyzer(test_result_repository=mock_repository)
        findings = analyzer.analyze(test_file)

        # Should find 2 flaky tests
        assert len(findings) == 2

        # Check first finding (Flaky Login Test)
        finding1 = next(
            f for f in findings if "Flaky Login Test" in f.context["test_name"]
        )
        assert finding1.severity == Severity.WARNING
        assert finding1.context["failure_rate"] == pytest.approx(0.15)
        assert finding1.context["total_runs"] == 100
        assert finding1.context["failures"] == 15
        assert finding1.location.line == 2  # Found in file
        assert "15.0% failure rate" in finding1.message
        assert "3.8 hours wasted" in finding1.message  # 15 * 0.25 hours

        # Check second finding (Very Flaky Test)
        finding2 = next(
            f for f in findings if "Very Flaky Test" in f.context["test_name"]
        )
        assert finding2.severity == Severity.ERROR  # High failure rate
        assert finding2.context["failure_rate"] == pytest.approx(0.5)
        assert finding2.location.line == 11  # Found in file
        assert "50.0% failure rate" in finding2.message

    def test_is_flaky_logic(self, mock_repository: Mock) -> None:
        """Test flakiness detection logic."""
        analyzer = FlakinessAnalyzer(test_result_repository=mock_repository)

        # Too few runs
        stats1 = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=3, failures=1
        )
        assert not analyzer._is_flaky(stats1)

        # Always passes
        stats2 = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=100, failures=0
        )
        assert not analyzer._is_flaky(stats2)

        # Always fails
        stats3 = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=50, failures=50
        )
        assert not analyzer._is_flaky(stats3)

        # Flaky - meets all criteria
        stats4 = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=100, failures=10
        )
        assert analyzer._is_flaky(stats4)

        # Below threshold
        stats5 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=1000,
            failures=2,  # 0.2% < 5% threshold
        )
        assert not analyzer._is_flaky(stats5)

    def test_severity_determination(self, mock_repository: Mock) -> None:
        """Test severity level determination."""
        analyzer = FlakinessAnalyzer(test_result_repository=mock_repository)

        # Default thresholds: info=5%, warning=15%, error=30%
        assert analyzer._determine_severity(0.03) == Severity.INFO
        assert analyzer._determine_severity(0.05) == Severity.INFO
        assert analyzer._determine_severity(0.10) == Severity.WARNING
        assert analyzer._determine_severity(0.15) == Severity.WARNING
        # 0.25 is above info (0.05) but below error (0.30), so WARNING
        assert analyzer._determine_severity(0.25) == Severity.WARNING
        assert analyzer._determine_severity(0.50) == Severity.ERROR

    def test_custom_severity_thresholds(self, mock_repository: Mock) -> None:
        """Test custom severity thresholds."""
        config = {"severity_thresholds": {"info": 0.01, "warning": 0.05, "error": 0.10}}

        analyzer = FlakinessAnalyzer(
            test_result_repository=mock_repository, config=config
        )

        assert analyzer._determine_severity(0.005) == Severity.INFO
        assert analyzer._determine_severity(0.02) == Severity.WARNING
        assert analyzer._determine_severity(0.08) == Severity.WARNING
        assert analyzer._determine_severity(0.15) == Severity.ERROR

    def test_recommendations(self, mock_repository: Mock) -> None:
        """Test recommendation generation."""
        analyzer = FlakinessAnalyzer(test_result_repository=mock_repository)

        stats = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=100, failures=10
        )

        # Very high failure rate
        recommendation = analyzer._get_recommendation(
            stats.model_copy(update={"failures": 60})
        )
        assert "fails more often than passes" in recommendation

        # High failure rate
        recommendation = analyzer._get_recommendation(
            stats.model_copy(update={"failures": 25})
        )
        assert "timing issues" in recommendation

        # Moderate failure rate
        recommendation = analyzer._get_recommendation(
            stats.model_copy(update={"failures": 12})
        )
        assert "race conditions" in recommendation

        # Low failure rate
        recommendation = analyzer._get_recommendation(
            stats.model_copy(update={"failures": 7})
        )
        assert "wait conditions" in recommendation

    def test_flakiness_categorization(
        self, mock_repository: Mock, test_file: TestFile
    ) -> None:
        """Test categorizing flakiness types."""
        analyzer = FlakinessAnalyzer(test_result_repository=mock_repository)

        # UI test
        ui_stats = FlakinessStats(
            test_name="Click Button Test",
            file_path=test_file.path,
            total_runs=100,
            failures=20,
        )
        assert analyzer._categorize_flakiness(ui_stats, test_file) == "ui_timing"

        # API test
        api_stats = FlakinessStats(
            test_name="API Request Test",
            file_path=test_file.path,
            total_runs=100,
            failures=15,
        )
        assert analyzer._categorize_flakiness(api_stats, test_file) == "api_timing"

        # Database test
        db_stats = FlakinessStats(
            test_name="Database Query Test",
            file_path=test_file.path,
            total_runs=100,
            failures=10,
        )
        assert analyzer._categorize_flakiness(db_stats, test_file) == "database_timing"

        # File operation
        file_stats = FlakinessStats(
            test_name="File Upload Test",
            file_path=test_file.path,
            total_runs=100,
            failures=8,
        )
        assert analyzer._categorize_flakiness(file_stats, test_file) == "file_operation"

        # High failure rate - logic issue
        logic_stats = FlakinessStats(
            test_name="Complex Logic Test",
            file_path=test_file.path,
            total_runs=100,
            failures=60,
        )
        assert analyzer._categorize_flakiness(logic_stats, test_file) == "logic_issue"

        # Default
        other_stats = FlakinessStats(
            test_name="Other Test",
            file_path=test_file.path,
            total_runs=100,
            failures=12,
        )
        assert analyzer._categorize_flakiness(other_stats, test_file) == "timing_issue"

    def test_find_test_line(self, mock_repository: Mock, test_file: TestFile) -> None:
        """Test finding test location in file."""
        analyzer = FlakinessAnalyzer(test_result_repository=mock_repository)

        # Found tests
        assert analyzer._find_test_line(test_file, "Flaky Login Test") == 2
        assert analyzer._find_test_line(test_file, "Stable Test") == 8
        assert analyzer._find_test_line(test_file, "Very Flaky Test") == 11

        # Not found
        assert analyzer._find_test_line(test_file, "Non-existent Test") is None

    def test_repository_error_handling(
        self, mock_repository: Mock, test_file: TestFile
    ) -> None:
        """Test handling repository errors gracefully."""
        mock_repository.get_flakiness_stats.side_effect = Exception("Database error")

        analyzer = FlakinessAnalyzer(test_result_repository=mock_repository)
        findings = analyzer.analyze(test_file)

        # Should return empty list on error
        assert findings == []

    def test_validate_config(self, mock_repository: Mock) -> None:
        """Test configuration validation."""
        # Invalid days_back
        with pytest.raises(ConfigurationError) as exc_info:
            analyzer = FlakinessAnalyzer(
                test_result_repository=mock_repository, config={"days_back": 0}
            )
            analyzer.validate_config()
        assert "days_back must be at least 1" in str(exc_info.value)

        # Invalid failure_threshold
        with pytest.raises(ConfigurationError) as exc_info:
            analyzer = FlakinessAnalyzer(
                test_result_repository=mock_repository,
                config={"failure_threshold": 1.5},
            )
            analyzer.validate_config()
        assert "failure_threshold must be between 0 and 1" in str(exc_info.value)

        # Invalid min_runs
        with pytest.raises(ConfigurationError) as exc_info:
            analyzer = FlakinessAnalyzer(
                test_result_repository=mock_repository, config={"min_runs": 1}
            )
            analyzer.validate_config()
        assert "min_runs must be at least 2" in str(exc_info.value)

        # Missing severity threshold
        with pytest.raises(ConfigurationError) as exc_info:
            analyzer = FlakinessAnalyzer(
                test_result_repository=mock_repository,
                config={"severity_thresholds": {"info": 0.1, "warning": 0.2}},
            )
            analyzer.validate_config()
        assert "Missing severity threshold: error" in str(exc_info.value)

        # Invalid severity threshold value
        with pytest.raises(ConfigurationError) as exc_info:
            analyzer = FlakinessAnalyzer(
                test_result_repository=mock_repository,
                config={
                    "severity_thresholds": {"info": 0.1, "warning": -0.1, "error": 0.3}
                },
            )
            analyzer.validate_config()
        assert "must be between 0 and 1" in str(exc_info.value)

    def test_settings_integration(self, mock_repository: Mock) -> None:
        """Test integration with global settings."""
        # Default uses settings
        analyzer = FlakinessAnalyzer(test_result_repository=mock_repository)

        settings = Settings()
        assert analyzer._failure_threshold == settings.flakiness_threshold
        assert analyzer._min_runs == settings.flakiness_min_runs

    def test_pattern_type(self, mock_repository: Mock, test_file: TestFile) -> None:
        """Test that findings use correct pattern type."""
        mock_repository.get_flakiness_stats.return_value = [
            FlakinessStats(
                test_name="Flaky Test",
                file_path=test_file.path,
                total_runs=100,
                failures=10,
                last_failure=datetime.now(),
            )
        ]

        analyzer = FlakinessAnalyzer(test_result_repository=mock_repository)
        findings = analyzer.analyze(test_file)

        assert len(findings) == 1
        assert findings[0].pattern.type == PatternType.INEFFICIENT_WAIT
        assert not findings[0].pattern.auto_fixable

    def test_analyze_without_repository_returns_empty(
        self, test_file: TestFile
    ) -> None:
        """FlakinessAnalyzer with no repository returns empty findings."""
        from robot_optimizer_core.di import reset_container

        reset_container()
        analyzer = FlakinessAnalyzer()
        findings = analyzer.analyze(test_file)
        assert findings == []

    def test_repository_error_raises_gracefully(
        self, mock_repository: Mock, test_file: TestFile
    ) -> None:
        """RepositoryError is caught and empty list returned."""
        mock_repository.get_flakiness_stats.side_effect = RepositoryError("DB down")
        analyzer = FlakinessAnalyzer(test_result_repository=mock_repository)
        findings = analyzer.analyze(test_file)
        assert findings == []

    def test_finding_message_includes_trend(
        self, mock_repository: Mock, test_file: TestFile
    ) -> None:
        """Trend info is included in the finding message when available."""
        mock_repository.get_flakiness_stats.return_value = [
            FlakinessStats(
                test_name="Flaky Login Test",
                file_path=test_file.path,
                total_runs=50,
                failures=10,
                # Force "worsening" trend: recent rate >> older rate
                recent_runs=10,
                older_runs=10,
                recent_failures=8,
                older_failures=1,
                last_failure=datetime.now(),
            )
        ]
        analyzer = FlakinessAnalyzer(test_result_repository=mock_repository)
        findings = analyzer.analyze(test_file)
        assert len(findings) == 1
        assert "worsening" in findings[0].message

    def test_find_test_line_leaves_test_section(
        self, mock_repository: Mock
    ) -> None:
        """_find_test_line correctly resets in_test_cases when leaving the section."""
        content = (
            "*** Test Cases ***\nMy Test\n    Log    ok\n\n"
            "*** Keywords ***\nKeyword Helper\n    Log    kw\n"
        )
        kw_file = TestFile(
            path=Path("kw.robot"),
            content=content,
            size_bytes=len(content),
            last_modified_utc=datetime.now(),
        )
        analyzer = FlakinessAnalyzer(test_result_repository=mock_repository)
        # "Keyword Helper" appears after *** Keywords ***, not in test cases
        result = analyzer._find_test_line(kw_file, "Keyword Helper")
        assert result is None
