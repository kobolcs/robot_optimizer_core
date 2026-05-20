# tests/unit/domain/value_objects/test_sleep_pattern.py
"""Unit tests for SleepPattern value object.

Comprehensive tests for the SleepPattern value object including validation,
computed properties, and edge cases.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from robot_optimizer_core.domain.value_objects import Pattern, SleepPattern


@pytest.mark.unit
class TestSleepPattern:
    """Test the SleepPattern value object."""

    def test_create_basic_sleep_pattern(self) -> None:
        """Test creating a basic sleep pattern."""
        pattern = SleepPattern(
            duration=Decimal("5"),
            unit="s",
            line_number=10,
            original_text="Sleep    5 s",
        )

        assert pattern.duration == Decimal("5")
        assert pattern.unit == "s"
        assert pattern.line_number == 10
        assert pattern.original_text == "Sleep    5 s"

    def test_duration_validation(self) -> None:
        """Test duration validation rules."""
        # Zero duration
        with pytest.raises(ValidationError) as exc_info:
            SleepPattern(
                duration=Decimal("0"),
                unit="s",
                line_number=10,
                original_text="Sleep    0 s",
            )
        assert "must be positive" in str(exc_info.value)

        # Negative duration
        with pytest.raises(ValidationError) as exc_info:
            SleepPattern(
                duration=Decimal("-5"),
                unit="s",
                line_number=10,
                original_text="Sleep    -5 s",
            )
        assert "must be positive" in str(exc_info.value)

        # Excessive duration (> 1 hour)
        with pytest.raises(ValidationError) as exc_info:
            SleepPattern(
                duration=Decimal("3601"),
                unit="s",
                line_number=10,
                original_text="Sleep    3601 s",
            )
        assert "unreasonably long" in str(exc_info.value)

    def test_unit_validation(self) -> None:
        """Test time unit validation."""
        # Valid units - seconds
        for unit in ["s", "seconds", "second"]:
            pattern = SleepPattern(
                duration=Decimal("1"),
                unit=unit,
                line_number=1,
                original_text=f"Sleep    1 {unit}",
            )
            assert pattern.unit == unit.lower()

        # Valid units - minutes
        for unit in ["m", "minutes", "minute"]:
            pattern = SleepPattern(
                duration=Decimal("1"),
                unit=unit,
                line_number=1,
                original_text=f"Sleep    1 {unit}",
            )
            assert pattern.unit == unit.lower()

        # Valid units - milliseconds
        for unit in ["ms", "milliseconds", "millisecond"]:
            pattern = SleepPattern(
                duration=Decimal("100"),
                unit=unit,
                line_number=1,
                original_text=f"Sleep    100 {unit}",
            )
            assert pattern.unit == unit.lower()

        # Invalid unit
        with pytest.raises(ValidationError) as exc_info:
            SleepPattern(
                duration=Decimal("1"),
                unit="lightyears",
                line_number=1,
                original_text="Sleep    1 lightyears",
            )
        assert "Invalid time unit" in str(exc_info.value)

    def test_line_number_validation(self) -> None:
        """Test line number validation."""
        # Zero line number
        with pytest.raises(ValidationError) as exc_info:
            SleepPattern(
                duration=Decimal("1"),
                unit="s",
                line_number=0,
                original_text="Sleep    1 s",
            )
        assert "greater than or equal to 1" in str(exc_info.value)

        # Negative line number
        with pytest.raises(ValidationError):
            SleepPattern(
                duration=Decimal("1"),
                unit="s",
                line_number=-1,
                original_text="Sleep    1 s",
            )

    def test_duration_in_seconds_conversion(self) -> None:
        """Test converting duration to seconds."""
        # Seconds
        pattern_s = SleepPattern(
            duration=Decimal("5.5"),
            unit="s",
            line_number=1,
            original_text="Sleep    5.5 s",
        )
        assert pattern_s.duration_in_seconds == pytest.approx(5.5)

        # Minutes
        pattern_m = SleepPattern(
            duration=Decimal("2"), unit="m", line_number=1, original_text="Sleep    2 m"
        )
        assert pattern_m.duration_in_seconds == pytest.approx(120.0)

        # Milliseconds
        pattern_ms = SleepPattern(
            duration=Decimal("500"),
            unit="ms",
            line_number=1,
            original_text="Sleep    500 ms",
        )
        assert pattern_ms.duration_in_seconds == pytest.approx(0.5)

        # Different unit variations
        pattern_seconds = SleepPattern(
            duration=Decimal("3"),
            unit="seconds",
            line_number=1,
            original_text="Sleep    3 seconds",
        )
        assert pattern_seconds.duration_in_seconds == pytest.approx(3.0)

    def test_is_excessive_property(self) -> None:
        """Test the is_excessive property (> 5 seconds)."""
        # Not excessive
        pattern1 = SleepPattern(
            duration=Decimal("3"), unit="s", line_number=1, original_text="Sleep    3 s"
        )
        assert pattern1.is_excessive is False

        # Exactly 5 seconds - not excessive
        pattern2 = SleepPattern(
            duration=Decimal("5"), unit="s", line_number=1, original_text="Sleep    5 s"
        )
        assert pattern2.is_excessive is False

        # Excessive
        pattern3 = SleepPattern(
            duration=Decimal("10"),
            unit="s",
            line_number=1,
            original_text="Sleep    10 s",
        )
        assert pattern3.is_excessive is True

        # Excessive in minutes
        pattern4 = SleepPattern(
            duration=Decimal("1"), unit="m", line_number=1, original_text="Sleep    1 m"
        )
        assert pattern4.is_excessive is True

    def test_normalized_unit_property(self) -> None:
        """Test unit normalization."""
        # Seconds variants
        assert (
            SleepPattern(
                duration=Decimal("1"),
                unit="s",
                line_number=1,
                original_text="Sleep 1 s",
            ).normalized_unit
            == "seconds"
        )

        assert (
            SleepPattern(
                duration=Decimal("1"),
                unit="second",
                line_number=1,
                original_text="Sleep 1 second",
            ).normalized_unit
            == "seconds"
        )

        # Minutes variants
        assert (
            SleepPattern(
                duration=Decimal("1"),
                unit="m",
                line_number=1,
                original_text="Sleep 1 m",
            ).normalized_unit
            == "minutes"
        )

        assert (
            SleepPattern(
                duration=Decimal("1"),
                unit="minute",
                line_number=1,
                original_text="Sleep 1 minute",
            ).normalized_unit
            == "minutes"
        )

        # Milliseconds variants
        assert (
            SleepPattern(
                duration=Decimal("100"),
                unit="ms",
                line_number=1,
                original_text="Sleep 100 ms",
            ).normalized_unit
            == "milliseconds"
        )

        assert (
            SleepPattern(
                duration=Decimal("100"),
                unit="millisecond",
                line_number=1,
                original_text="Sleep 100 millisecond",
            ).normalized_unit
            == "milliseconds"
        )

    def test_severity_hint_property(self) -> None:
        """Test severity hint based on duration."""
        # INFO level (< 1 second)
        pattern1 = SleepPattern(
            duration=Decimal("0.5"),
            unit="s",
            line_number=1,
            original_text="Sleep    0.5 s",
        )
        assert pattern1.severity_hint == "INFO"

        # WARNING level (1-5 seconds)
        pattern2 = SleepPattern(
            duration=Decimal("3"), unit="s", line_number=1, original_text="Sleep    3 s"
        )
        assert pattern2.severity_hint == "WARNING"

        # ERROR level (> 5 seconds)
        pattern3 = SleepPattern(
            duration=Decimal("10"),
            unit="s",
            line_number=1,
            original_text="Sleep    10 s",
        )
        assert pattern3.severity_hint == "ERROR"

        # Edge cases
        pattern4 = SleepPattern(
            duration=Decimal("1"), unit="s", line_number=1, original_text="Sleep    1 s"
        )
        assert pattern4.severity_hint == "WARNING"

        pattern5 = SleepPattern(
            duration=Decimal("5"), unit="s", line_number=1, original_text="Sleep    5 s"
        )
        assert pattern5.severity_hint == "WARNING"

    def test_to_pattern_conversion(self) -> None:
        """Test converting to generic Pattern object."""
        sleep_pattern = SleepPattern(
            duration=Decimal("2.5"),
            unit="s",
            line_number=42,
            original_text="Sleep    2.5 s",
        )

        pattern = sleep_pattern.to_pattern()

        assert isinstance(pattern, Pattern)
        assert pattern.type.name == "SLEEP_IN_TEST"
        assert "2.5 s" in pattern.description

    def test_sleep_pattern_equality(self) -> None:
        """Test equality comparison."""
        p1 = SleepPattern(
            duration=Decimal("5"),
            unit="s",
            line_number=10,
            original_text="Sleep    5 s",
        )

        p2 = SleepPattern(
            duration=Decimal("5"),
            unit="s",
            line_number=10,
            original_text="Sleep    5 s",
        )

        p3 = SleepPattern(
            duration=Decimal("10"),  # Different duration
            unit="s",
            line_number=10,
            original_text="Sleep    10 s",
        )

        p4 = SleepPattern(
            duration=Decimal("5"),
            unit="m",  # Different unit
            line_number=10,
            original_text="Sleep    5 m",
        )

        p5 = SleepPattern(
            duration=Decimal("5"),
            unit="s",
            line_number=20,  # Different line
            original_text="Sleep    5 s",
        )

        # Same values
        assert p1 == p2
        assert hash(p1) == hash(p2)

        # Different values
        assert p1 != p3
        assert p1 != p4
        assert p1 != p5
        assert hash(p1) != hash(p3)

        # Different type
        assert p1 != "not a sleep pattern"
        assert p1 != 5

    def test_model_dump_json_mode(self) -> None:
        """Test model_dump with JSON mode includes computed fields."""
        pattern = SleepPattern(
            duration=Decimal("3.75"),
            unit="s",
            line_number=10,
            original_text="Sleep    3.75 s",
        )

        # Normal mode
        normal_data = pattern.model_dump()
        assert isinstance(normal_data["duration"], Decimal)

        # JSON mode
        json_data = pattern.model_dump(mode="json")

        # Decimal converted to float
        assert isinstance(json_data["duration"], float)
        assert json_data["duration"] == pytest.approx(3.75)

        # Computed fields included
        assert json_data["duration_in_seconds"] == pytest.approx(3.75)
        assert json_data["is_excessive"] is False
        assert json_data["normalized_unit"] == "seconds"
        assert json_data["severity_hint"] == "WARNING"

    def test_sleep_pattern_immutability(self) -> None:
        """Test that sleep patterns are immutable."""
        pattern = SleepPattern(
            duration=Decimal("5"),
            unit="s",
            line_number=10,
            original_text="Sleep    5 s",
        )

        with pytest.raises(ValidationError):
            pattern.duration = Decimal("10")

        with pytest.raises(ValidationError):
            pattern.unit = "m"

        with pytest.raises(ValidationError):
            pattern.line_number = 20

    def test_case_insensitive_units(self) -> None:
        """Test that units are case-insensitive."""
        pattern1 = SleepPattern(
            duration=Decimal("1"),
            unit="S",  # Uppercase
            line_number=1,
            original_text="Sleep    1 S",
        )
        assert pattern1.unit == "s"

        pattern2 = SleepPattern(
            duration=Decimal("1"),
            unit="SECONDS",  # Uppercase
            line_number=1,
            original_text="Sleep    1 SECONDS",
        )
        assert pattern2.unit == "seconds"

    def test_duration_in_seconds_hours(self) -> None:
        pattern = SleepPattern(duration=Decimal("1"), unit="h", line_number=1, original_text="Sleep    1h")
        assert pattern.duration_in_seconds == pytest.approx(3600.0)

    def test_duration_in_seconds_days(self) -> None:
        pattern = SleepPattern(duration=Decimal("1"), unit="d", line_number=1, original_text="Sleep    1d")
        assert pattern.duration_in_seconds == pytest.approx(86400.0)
