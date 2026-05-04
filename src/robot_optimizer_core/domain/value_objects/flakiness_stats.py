# src/robot_optimizer/domain/value_objects/flakiness_stats.py
"""Flakiness statistics value object."""

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field

from ..base import ValueObject

FlakinessTrend = Literal["improving", "stable", "worsening", "unknown"]


class FlakinessStats(ValueObject):
    """Statistics about test flakiness over time."""

    test_name: str = Field(..., min_length=1)
    file_path: Path = Field(...)
    total_runs: int = Field(..., ge=0)
    failures: int = Field(..., ge=0)
    last_failure: datetime | None = Field(default=None)

    # Task 12: trend field — compares recent vs older failure rates
    recent_failures: int = Field(
        default=0,
        ge=0,
        description="Failures in the most recent half of the run window",
    )
    older_failures: int = Field(
        default=0,
        ge=0,
        description="Failures in the older half of the run window",
    )
    recent_runs: int = Field(
        default=0,
        ge=0,
        description="Total runs in the most recent half of the window",
    )
    older_runs: int = Field(
        default=0,
        ge=0,
        description="Total runs in the older half of the window",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def failure_rate(self) -> float:
        """Calculate failure rate as percentage."""
        if self.total_runs == 0:
            return 0.0
        return self.failures / self.total_runs

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_flaky(self) -> bool:
        """Determine if test is considered flaky."""
        return 0 < self.failure_rate < 1.0 and self.total_runs >= 4

    @computed_field  # type: ignore[prop-decorator]
    @property
    def severity_level(self) -> str:
        """Determine severity level based on failure rate."""
        if self.failure_rate > 0.15:
            return "ERROR"
        if self.failure_rate > 0.05:
            return "WARNING"
        return "INFO"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def trend(self) -> FlakinessTrend:
        """
        Classifies the flakiness trend by comparing failure rates between the recent and older run windows.
        
        If either window has fewer than 2 runs the trend is `'unknown'`. Otherwise the method computes the difference between recent and older failure rates and applies an absolute threshold of 0.05: a decrease of at least 0.05 is `'improving'`, an increase of at least 0.05 is `'worsening'`, and any change within ±0.05 is `'stable'`.
        
        Returns:
        	FlakinessTrend: `'improving'` if recent failure rate is at least 0.05 lower than older rate, `'worsening'` if recent failure rate is at least 0.05 higher than older rate, `'stable'` if the rates differ by less than 0.05, `'unknown'` if either window has fewer than 2 runs.
        """
        if self.recent_runs < 2 or self.older_runs < 2:
            return "unknown"

        recent_rate = self.recent_failures / self.recent_runs
        older_rate = self.older_failures / self.older_runs

        delta = recent_rate - older_rate
        # Use a 5% absolute threshold to avoid noise
        if delta < -0.05:
            return "improving"
        if delta > 0.05:
            return "worsening"
        return "stable"
