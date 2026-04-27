# src/robot_optimizer/domain/value_objects/test_result.py
"""Test result value object."""
from datetime import datetime
from pathlib import Path

from pydantic import Field

from ..base import ValueObject


class TestResult(ValueObject):
    """Represents a single test execution result."""

    test_name: str = Field(..., min_length=1)
    file_path: Path = Field(...)
    status: str = Field(..., pattern=r"^(PASS|FAIL|SKIP)$")  # Fixed: regex → pattern
    execution_time: float = Field(..., ge=0)
    error_message: str | None = Field(default=None)
    timestamp: datetime = Field(...)

    @property
    def is_failure(self) -> bool:
        """Check if this result represents a test failure."""
        return self.status == "FAIL"

    @property
    def is_success(self) -> bool:
        """Check if this result represents a test success."""
        return self.status == "PASS"
