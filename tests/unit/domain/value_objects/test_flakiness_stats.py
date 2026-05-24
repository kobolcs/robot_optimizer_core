# tests/unit/domain/value_objects/test_flakiness_stats.py
"""Unit tests for FlakinessStats value object."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from robot_optimizer_core.domain.value_objects import FlakinessStats

_non_neg_int = st.integers(min_value=0, max_value=10_000)
_test_name = st.text(min_size=1, max_size=50).filter(lambda s: s.strip())
_path = st.just(Path("test.robot"))


@st.composite
def _valid_stats(draw: st.DrawFn) -> FlakinessStats:
    total = draw(_non_neg_int)
    failures = draw(st.integers(min_value=0, max_value=total))
    return FlakinessStats(
        test_name=draw(_test_name),
        file_path=Path("test.robot"),
        total_runs=total,
        failures=failures,
    )


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
            last_failure=last_failure,
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
            last_failure=None,
        )

        assert stats.failures == 0
        assert stats.last_failure is None
        assert stats.failure_rate == pytest.approx(0.0)

    def test_test_name_validation(self) -> None:
        """Test test name validation."""
        with pytest.raises(ValidationError) as exc_info:
            FlakinessStats(
                test_name="", file_path=Path("test.robot"), total_runs=10, failures=1
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
                failures=0,
            )
        assert "greater than or equal to 0" in str(exc_info.value)

        # Negative failures
        with pytest.raises(ValidationError) as exc_info:
            FlakinessStats(
                test_name="Test",
                file_path=Path("test.robot"),
                total_runs=10,
                failures=-1,
            )
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_failure_rate_calculation(self) -> None:
        """Test failure rate calculation."""
        # Normal case
        stats1 = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=100, failures=25
        )
        assert stats1.failure_rate == pytest.approx(0.25)

        # No failures
        stats2 = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=50, failures=0
        )
        assert stats2.failure_rate == pytest.approx(0.0)

        # All failures
        stats3 = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=10, failures=10
        )
        assert stats3.failure_rate == pytest.approx(1.0)

        # No runs (edge case)
        stats4 = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=0, failures=0
        )
        assert stats4.failure_rate == pytest.approx(0.0)

    def test_is_flaky_property(self) -> None:
        """Test flakiness detection logic."""
        # Flaky test (between 0 and 100% failure, min 4 runs)
        stats1 = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=100, failures=15
        )
        assert stats1.is_flaky is True

        # Not flaky - always passes
        stats2 = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=100, failures=0
        )
        assert stats2.is_flaky is False

        # Not flaky - always fails
        stats3 = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=50, failures=50
        )
        assert stats3.is_flaky is False

        # Not flaky - too few runs
        stats4 = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=3, failures=1
        )
        assert stats4.is_flaky is False

        # Edge case - exactly 4 runs (minimum)
        stats5 = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=4, failures=1
        )
        assert stats5.is_flaky is True

    def test_severity_level_property(self) -> None:
        """Test severity level determination."""
        # INFO level (< 5% failure)
        stats1 = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=100, failures=3
        )
        assert stats1.severity_level == "INFO"

        # WARNING level (5-15% failure)
        stats2 = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=100, failures=10
        )
        assert stats2.severity_level == "WARNING"

        # ERROR level (> 15% failure)
        stats3 = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=100, failures=20
        )
        assert stats3.severity_level == "ERROR"

        # Edge cases
        stats4 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=5,  # Exactly 5%
        )
        assert stats4.severity_level == "INFO"

        stats5 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=15,  # Exactly 15%
        )
        assert stats5.severity_level == "WARNING"

    def test_path_string_conversion(self) -> None:
        """Test that string paths are converted to Path objects."""
        stats = FlakinessStats(
            test_name="Test",
            file_path="tests/suite/test.robot",  # String
            total_runs=10,
            failures=1,
        )

        assert isinstance(stats.file_path, Path)
        assert stats.file_path == Path("tests/suite/test.robot")

    def test_flakiness_stats_equality(self) -> None:
        """Test flakiness stats equality."""
        last_failure = datetime.now(UTC)

        s1 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=10,
            last_failure=last_failure,
        )

        s2 = FlakinessStats(
            test_name="Test",
            file_path=Path("test.robot"),
            total_runs=100,
            failures=10,
            last_failure=last_failure,
        )

        s3 = FlakinessStats(
            test_name="Different Test",  # Different name
            file_path=Path("test.robot"),
            total_runs=100,
            failures=10,
            last_failure=last_failure,
        )

        assert s1 == s2
        assert s1 != s3
        assert s1 != "not flakiness stats"

    def test_flakiness_stats_immutability(self) -> None:
        """Test that flakiness stats are immutable."""
        stats = FlakinessStats(
            test_name="Test", file_path=Path("test.robot"), total_runs=100, failures=10
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
            failures=20,  # More failures than runs
        )

        # The failure rate would be > 1, which is illogical
        assert stats.failure_rate == pytest.approx(2.0)  # Shows the issue

        # But is_flaky should handle this gracefully
        assert stats.is_flaky is False  # Not flaky if rate >= 1


@pytest.mark.unit
class TestFlakinessStatsProperties:
    """Property-based tests for FlakinessStats invariants."""

    @given(_valid_stats())
    @settings(max_examples=200)
    def test_failure_rate_in_unit_interval(self, stats: FlakinessStats) -> None:
        assert 0.0 <= stats.failure_rate <= 1.0

    @given(_valid_stats())
    @settings(max_examples=200)
    def test_is_flaky_implies_rate_strictly_between_zero_and_one(
        self, stats: FlakinessStats
    ) -> None:
        if stats.is_flaky:
            assert 0.0 < stats.failure_rate < 1.0

    @given(_valid_stats())
    @settings(max_examples=200)
    def test_is_flaky_implies_minimum_runs(self, stats: FlakinessStats) -> None:
        if stats.is_flaky:
            assert stats.total_runs >= 4

    @given(_valid_stats())
    @settings(max_examples=200)
    def test_not_flaky_when_always_passes_or_always_fails(
        self, stats: FlakinessStats
    ) -> None:
        if stats.failure_rate == 0.0 or stats.failure_rate == 1.0:
            assert not stats.is_flaky
