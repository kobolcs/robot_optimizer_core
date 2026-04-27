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

from robot_optimizer_core.domain.value_objects import TestResult


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
