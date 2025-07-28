# src/robot_optimizer/domain/value_objects/flakiness_stats.py
"""Flakiness statistics value object."""
from datetime import datetime
from pathlib import Path

from pydantic import Field, computed_field

from ..base import ValueObject


class FlakinessStats(ValueObject):
    """Statistics about test flakiness over time."""

    test_name: str = Field(..., min_length=1)
    file_path: Path = Field(...)
    total_runs: int = Field(..., ge=0)
    failures: int = Field(..., ge=0)
    last_failure: datetime | None = Field(default=None)

    @computed_field
    @property
    def failure_rate(self) -> float:
        """Calculate failure rate as percentage."""
        if self.total_runs == 0:
            return 0.0
        return self.failures / self.total_runs

    @computed_field
    @property
    def is_flaky(self) -> bool:
        """Determine if test is considered flaky."""
        return 0 < self.failure_rate < 1.0 and self.total_runs >= 4

    @computed_field
    @property
    def severity_level(self) -> str:
        """Determine severity level based on failure rate."""
        if self.failure_rate > 0.15:
            return "ERROR"
        if self.failure_rate > 0.05:
            return "WARNING"
        return "INFO"
