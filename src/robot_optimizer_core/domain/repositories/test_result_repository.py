# src/robot_optimizer_core/domain/repositories/test_result_repository.py
"""Repository interface for test result storage."""

from abc import ABC, abstractmethod
from pathlib import Path

from ..value_objects.flakiness_stats import FlakinessStats
from ..value_objects.test_result import TestResult


class TestResultRepository(ABC):
    """Repository interface for test result persistence."""

    @abstractmethod
    def save_result(self, result: TestResult) -> None:
        """Save a test execution result."""

    @abstractmethod
    def get_results_for_file(
        self, file_path: Path, days_back: int = 30
    ) -> list[TestResult]:
        """Get test results for a specific file within time period."""

    @abstractmethod
    def get_flakiness_stats(
        self, file_path: Path, days_back: int = 30
    ) -> list[FlakinessStats]:
        """Get flakiness statistics for tests in a file."""

    @abstractmethod
    def get_total_results_count(self) -> int:
        """Get total number of stored test results."""
