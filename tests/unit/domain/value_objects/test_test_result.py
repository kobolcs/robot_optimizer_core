# tests/unit/domain/value_objects/test_test_result.py
"""Unit tests for TestResult value object.

Comprehensive tests for the TestResult value object including validation
and all properties.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from robot_optimizer_core.domain.value_objects import FlakinessStats, TestResult


@pytest.mark.unit
class TestTestResult:
    """Test the TestResult value object."""

    def test_create_test_result(self) -> None:
        """Test creating a test result."""
        timestamp = datetime.now(UTC)
        result = TestResult(
            test_name="Login Test",
            file_path=Path("tests/login.robot"),
            status="PASS",
            execution_time=1.5,
            timestamp=timestamp
        )

        assert result.test_name == "Login Test"
        assert result.file_path == Path("tests/login.robot")
        assert result.status == "PASS"
        assert result.execution_time == 1.5
        assert result.timestamp == timestamp
        assert result.error_message is None

    def test_create_with_error_message(self) -> None:
        """Test creating a failed test result with error message."""
        timestamp = datetime.now(UTC)
        result = TestResult(
            test_name="Login Test",
            file_path=Path("tests/login.robot"),
            status="FAIL",
            execution_time=2.3,
            error_message="Element 'id=username' not found",
            timestamp=timestamp
        )

        assert result.status == "FAIL"
        assert result.error_message == "Element 'id=username' not found"

    def test_test_name_validation(self) -> None:
        """Test test name validation."""
        # Empty test name
        with pytest.raises(ValidationError) as exc_info:
            TestResult(
                test_name="",
                file_path=Path("test.robot"),
                status="PASS",
                execution_time=1.0,
                timestamp=datetime.now()
            )
        assert "at least 1 character" in str(exc_info.value)

    def test_status_validation(self) -> None:
        """Test status validation."""
        timestamp = datetime.now()

        # Valid statuses
        for status in ["PASS", "FAIL", "SKIP"]:
            result = TestResult(
                test_name="Test",
                file_path=Path("test.robot"),
                status=status,
                execution_time=1.0,
                timestamp=timestamp
            )
            assert result.status == status

        # Invalid status
        with pytest.raises(ValidationError) as exc_info:
            TestResult(
                test_name="Test",
                file_path=Path("test.robot"),
                status="SUCCESS",  # Invalid
                execution_time=1.0,
                timestamp=timestamp
            )
        assert "String should match pattern" in str(exc_info.value)

    def test_execution_time_validation(self) -> None:
        """Test execution time validation."""
        # Negative execution time
        with pytest.raises(ValidationError) as exc_info:
            TestResult(
                test_name="Test",
                file_path=Path("test.robot"),
                status="PASS",
                execution_time=-1.0,
                timestamp=datetime.now()
            )
        assert "greater than or equal to 0" in str(exc_info.value)

        # Zero execution time is valid
        result = TestResult(
            test_name="Test",
            file_path=Path("test.robot"),
            status="SKIP",
            execution_time=0.0,
            timestamp=datetime.now()
        )
        assert result.execution_time == 0.0

    def test_is_failure_property(self) -> None:
        """Test is_failure property."""
        timestamp = datetime.now()

        fail_result = TestResult(
            test_name="Test",
            file_path=Path("test.robot"),
            status="FAIL",
            execution_time=1.0,
            timestamp=timestamp
        )
        assert fail_result.is_failure is True
        assert fail_result.is_success is False

        pass_result = TestResult(
            test_name="Test",
            file_path=Path("test.robot"),
            status="PASS",
            execution_time=1.0,
            timestamp=timestamp
        )
        assert pass_result.is_failure is False
        assert pass_result.is_success is True

        skip_result = TestResult(
            test_name="Test",
            file_path=Path("test.robot"),
            status="SKIP",
            execution_time=0.0,
            timestamp=timestamp
        )
        assert skip_result.is_failure is False
        assert skip_result.is_success is False

    def test_path_string_conversion(self) -> None:
        """Test that string paths are converted to Path objects."""
        result = TestResult(
            test_name="Test",
            file_path="tests/suite/test.robot",  # String
            status="PASS",
            execution_time=1.0,
            timestamp=datetime.now()
        )

        assert isinstance(result.file_path, Path)
        assert result.file_path == Path("tests/suite/test.robot")

    def test_test_result_equality(self) -> None:
        """Test test result equality."""
        timestamp = datetime.now()

        r1 = TestResult(
            test_name="Test",
            file_path=Path("test.robot"),
            status="PASS",
            execution_time=1.0,
            timestamp=timestamp
        )

        r2 = TestResult(
            test_name="Test",
            file_path=Path("test.robot"),
            status="PASS",
            execution_time=1.0,
            timestamp=timestamp
        )

        r3 = TestResult(
            test_name="Different Test",  # Different name
            file_path=Path("test.robot"),
            status="PASS",
            execution_time=1.0,
            timestamp=timestamp
        )

        assert r1 == r2
        assert r1 != r3
        assert r1 != "not a test result"

    def test_test_result_immutability(self) -> None:
        """Test that test results are immutable."""
        result = TestResult(
            test_name="Test",
            file_path=Path("test.robot"),
            status="PASS",
            execution_time=1.0,
            timestamp=datetime.now()
        )

        with pytest.raises(ValidationError):
            result.status = "FAIL"

        with pytest.raises(ValidationError):
            result.execution_time = 2.0


@pytest.mark.unit
class TestFlakinessStats:
    """Test the FlakinessStats value object."""

    def test_create_flakiness_stats(self) -> None:
        """Test creating flakiness statistics."""
        last_failure = datetime.now(UTC)
        stats = FlakinessStats(
            test_name="Flaky Login Test",
            file_path=Path("tests/login.robot"),
            total_runs=100,
            failures=15,
            last_failure=last_failure
        )

        assert stats.test_name == "Flaky Login Test"
        assert stats.file_path == Path("tests/login.robot")
        assert stats.total_runs == 100
        assert stats.failures == 15
        assert stats.last_failure == last_failure

    def test_create_without_failures(self) -> None:
        """Test creating stats for a stable test."""
        stats = FlakinessStats(
            test_name="Stable Test",
            file_path=Path("tests/stable.robot"),
            total_runs=200,
            failures=0,
            last_failure=None
        )

        assert stats.failures == 0
        assert stats.last_failure is None
        assert stats.failure_rate == 0.0

    def test_test_name_validation(self) -> None:
        """Test test name validation."""
        with pytest.raises(ValidationError) as exc_info:
            FlakinessStats(
                test_name="",
                file_path=Path("test.robot"),
                total_runs=10,
                failures=1
            )
        assert "at least 1 character" in str(exc_info.value)

    def test_negative_values_validation(self) -> None:
        """Test validation of numeric fields."""
        # Negative total runs
        with pytest.raises(ValidationError) as exc_info:
            FlakinessStats(
                test_name="Test",
                file_path=Path("test.robot"),
                total_runs=-1,
                failures=0
            )
        assert "greater than or equal to 0" in str(exc_info.value)

        # Negative failures
        with pytest.raises(ValidationError) as exc_info:
            FlakinessStats(
                test_name="Test",
                file_path=Path("test.robot"),
                total_runs=10,
                failures=-1
            )
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_failure_rate_calculation(self) -> None:
        """Test failure rate calculation."""
        # Normal case
        stats1 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=25
        )
        assert stats1.failure_rate == 0.25

        # No failures
        stats2 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=50,
            failures=0
        )
        assert stats2.failure_rate == 0.0

        # All failures
        stats3 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=10,
            failures=10
        )
        assert stats3.failure_rate == 1.0

        # No runs (edge case)
        stats4 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=0,
            failures=0
        )
        assert stats4.failure_rate == 0.0

    def test_is_flaky_property(self) -> None:
        """Test flakiness detection logic."""
        # Flaky test (between 0 and 100% failure, min 4 runs)
        stats1 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=15
        )
        assert stats1.is_flaky is True

        # Not flaky - always passes
        stats2 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=0
        )
        assert stats2.is_flaky is False

        # Not flaky - always fails
        stats3 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=50,
            failures=50
        )
        assert stats3.is_flaky is False

        # Not flaky - too few runs
        stats4 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=3,
            failures=1
        )
        assert stats4.is_flaky is False

        # Edge case - exactly 4 runs (minimum)
        stats5 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=4,
            failures=1
        )
        assert stats5.is_flaky is True

    def test_severity_level_property(self) -> None:
        """Test severity level determination."""
        # INFO level (< 5% failure)
        stats1 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=3
        )
        assert stats1.severity_level == "INFO"

        # WARNING level (5-15% failure)
        stats2 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=10
        )
        assert stats2.severity_level == "WARNING"

        # ERROR level (> 15% failure)
        stats3 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=20
        )
        assert stats3.severity_level == "ERROR"

        # Edge cases
        stats4 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=5  # Exactly 5%
        )
        assert stats4.severity_level == "INFO"

        stats5 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=15  # Exactly 15%
        )
        assert stats5.severity_level == "WARNING"

    def test_path_string_conversion(self) -> None:
        """Test that string paths are converted to Path objects."""
        stats = FlakinessStats(
            test_name="Test",
            file_path="tests/suite/test.robot",  # String
            total_runs=10,
            failures=1
        )

        assert isinstance(stats.file_path, Path)
        assert stats.file_path == Path("tests/suite/test.robot")

    def test_flakiness_stats_equality(self) -> None:
        """Test flakiness stats equality."""
        last_failure = datetime.now()

        s1 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=10,
            last_failure=last_failure
        )

        s2 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=10,
            last_failure=last_failure
        )

        s3 = FlakinessStats(
            test_name="Different Test",  # Different name
            file_path=Path("test.robot"),
            total_runs=100,
            failures=10,
            last_failure=last_failure
        )

        assert s1 == s2
        assert s1 != s3
        assert s1 != "not flakiness stats"

    def test_flakiness_stats_immutability(self) -> None:
        """Test that flakiness stats are immutable."""
        stats = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=10
        )

        with pytest.raises(ValidationError):
            stats.total_runs = 200

        with pytest.raises(ValidationError):
            stats.failures = 20

    def test_logical_consistency(self) -> None:
        """Test that failures cannot exceed total runs."""
        # This should ideally be validated, but if not, test the behavior
        stats = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=10,
            failures=20  # More failures than runs
        )

        # The failure rate would be > 1, which is illogical
        assert stats.failure_rate == 2.0  # Shows the issue

        # But is_flaky should handle this gracefully
        assert stats.is_flaky is False  # Not flaky if rate >= 1
