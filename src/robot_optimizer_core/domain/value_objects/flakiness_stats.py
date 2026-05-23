# src/robot_optimizer/domain/value_objects/flakiness_stats.py
"""Flakiness statistics value object."""

from datetime import datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import Field, computed_field

from ..base import ValueObject

FlakinessTrend = Literal["improving", "stable", "worsening", "unknown"]

# Minimum runs in each half-window required for trend comparison.
_MIN_WINDOW_RUNS: Final[int] = 2
# Failure rate above which a test is considered severely flaky (ERROR).
_SEVERITY_ERROR_RATE: Final[float] = 0.15
# Failure rate above which a test warrants a WARNING.
_SEVERITY_WARNING_RATE: Final[float] = 0.05
# Absolute delta threshold below which rate changes are treated as noise.
_TREND_NOISE_THRESHOLD: Final[float] = 0.05
# Minimum runs for is_flaky to trigger.
_MIN_FLAKY_RUNS: Final[int] = 4


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

    @computed_field  # type: ignore[prop-decorator]  # pydantic/mypy: computed_field+property pattern not yet suppressed by plugin
    @property
    def failure_rate(self) -> float:
        """Calculate failure rate as percentage."""
        if self.total_runs == 0:
            return 0.0
        return self.failures / self.total_runs

    @computed_field  # type: ignore[prop-decorator]  # pydantic/mypy: computed_field+property pattern not yet suppressed by plugin
    @property
    def is_flaky(self) -> bool:
        """Determine if test is considered flaky."""
        return 0 < self.failure_rate < 1.0 and self.total_runs >= _MIN_FLAKY_RUNS

    @computed_field  # type: ignore[prop-decorator]  # pydantic/mypy: computed_field+property pattern not yet suppressed by plugin
    @property
    def severity_level(self) -> str:
        """Determine severity level based on failure rate."""
        if self.failure_rate > _SEVERITY_ERROR_RATE:
            return "ERROR"
        if self.failure_rate > _SEVERITY_WARNING_RATE:
            return "WARNING"
        return "INFO"

    @computed_field  # type: ignore[prop-decorator]  # pydantic/mypy: computed_field+property pattern not yet suppressed by plugin
    @property
    def trend(self) -> FlakinessTrend:
        """Determine whether flakiness is improving, stable, or worsening.

        Compares the failure rate in the recent half of the run window against
        the older half.  Requires at least 2 runs in each window to be
        meaningful; otherwise reports 'unknown'.
        """
        if self.recent_runs < _MIN_WINDOW_RUNS or self.older_runs < _MIN_WINDOW_RUNS:
            return "unknown"

        recent_rate = self.recent_failures / self.recent_runs
        older_rate = self.older_failures / self.older_runs

        delta = recent_rate - older_rate
        if delta < -_TREND_NOISE_THRESHOLD:
            return "improving"
        if delta > _TREND_NOISE_THRESHOLD:
            return "worsening"
        return "stable"
