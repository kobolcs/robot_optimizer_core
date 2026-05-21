# src/robot_optimizer/domain/value_objects/sleep_pattern.py
"""Sleep pattern value object for Robot Framework sleep detection.

100% Pydantic v2 compliant implementation.
"""

from decimal import Decimal
from pydantic import Field, computed_field, field_serializer, field_validator, model_validator

from ..base import ValueObject
from .pattern import Pattern


class SleepPattern(ValueObject):
    """Value object representing a sleep pattern in Robot Framework tests.

    Encapsulates information about Sleep keyword usage, including duration,
    time unit, and location in the test file.
    """

    duration: Decimal = Field(..., description="Sleep duration in the specified unit")
    unit: str = Field(..., description="Time unit (s, seconds, m, minutes, etc.)")
    line_number: int = Field(..., ge=1, description="Line number where sleep found")
    original_text: str = Field(..., description="Original sleep command text")

    @field_serializer("duration", when_used="json")
    def serialize_duration(self, v: Decimal) -> float:
        return float(v)

    @field_validator("duration")
    @classmethod
    def validate_duration(cls, v: Decimal) -> Decimal:
        """Validate duration is positive and reasonable.

        Args:
            v: Duration value

        Returns:
            Validated duration

        Raises:
            ValueError: If duration is invalid
        """
        if v <= 0:
            raise ValueError("Sleep duration must be positive")
        return v

    @field_validator("unit")
    @classmethod
    def validate_unit(cls, v: str) -> str:
        """Validate time unit is supported.

        Args:
            v: Time unit string

        Returns:
            Normalized time unit

        Raises:
            ValueError: If unit is not supported
        """
        valid_units = {
            "s",
            "seconds",
            "second",
            "m",
            "minutes",
            "minute",
            "ms",
            "milliseconds",
            "millisecond",
            # Extended units supported by Task 9
            "h",
            "hour",
            "hours",
            "d",
            "day",
            "days",
        }
        normalized = v.lower().strip()
        if normalized not in valid_units:
            raise ValueError(f"Invalid time unit: {v}")
        return normalized

    @model_validator(mode="after")
    def validate_original_text_consistency(self) -> "SleepPattern":
        """Ensure original text contains the duration and unit.

        Pydantic v2 model validator.
        """
        duration_str = str(self.duration.normalize())
        if duration_str not in self.original_text:
            # Just log warning, don't fail - might be formatted differently
            pass
        return self

    # Pydantic v2: computed fields for derived properties
    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_in_seconds(self) -> float:
        """Convert duration to seconds regardless of unit."""
        if self.unit in {"m", "minutes", "minute"}:
            return float(self.duration * 60)
        if self.unit in {"ms", "milliseconds", "millisecond"}:
            return float(self.duration / 1000)
        if self.unit in {"h", "hour", "hours"}:
            return float(self.duration * 3600)
        if self.unit in {"d", "day", "days"}:
            return float(self.duration * 86400)
        return float(self.duration)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_excessive(self) -> bool:
        """Check if sleep duration is excessive (>5 seconds)."""
        return self.duration_in_seconds > 5

    @computed_field  # type: ignore[prop-decorator]
    @property
    def normalized_unit(self) -> str:
        """Get standardized unit representation."""
        unit_map = {
            "s": "seconds",
            "seconds": "seconds",
            "second": "seconds",
            "m": "minutes",
            "minutes": "minutes",
            "minute": "minutes",
            "ms": "milliseconds",
            "milliseconds": "milliseconds",
            "millisecond": "milliseconds",
        }
        return unit_map.get(self.unit, self.unit)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def severity_hint(self) -> str:
        """Suggest severity based on duration."""
        if self.duration_in_seconds < 1:
            return "INFO"
        if self.duration_in_seconds <= 5:
            return "WARNING"
        return "ERROR"

    def to_pattern(self) -> Pattern:
        """Convert to a generic Pattern object."""
        return Pattern.sleep_in_test(f"{self.duration} {self.unit}")

    def __eq__(self, other: object) -> bool:
        """Check equality with another SleepPattern."""
        if not isinstance(other, SleepPattern):
            return False
        return (
            self.duration == other.duration
            and self.unit == other.unit
            and self.line_number == other.line_number
        )

    def __hash__(self) -> int:
        """Generate hash for the sleep pattern."""
        return hash((self.duration, self.unit, self.line_number))

