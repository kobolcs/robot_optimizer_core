# src/robot_optimizer_core/domain/ports/repository.py
"""Port interfaces for persistence repositories."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..value_objects.flakiness_stats import FlakinessStats
from ..value_objects.test_result import TestResult


class ITestResultRepository(ABC):
    """Abstract interface for test-result persistence."""

    @abstractmethod
    def save_result(self, result: TestResult) -> None:
        """Persist a single test execution result."""

    @abstractmethod
    def get_results_for_file(
        self, file_path: Path, days_back: int = 30
    ) -> list[TestResult]:
        """Return all results for *file_path* recorded within the last *days_back* days."""

    @abstractmethod
    def get_flakiness_stats(
        self, file_path: Path, days_back: int = 30
    ) -> list[FlakinessStats]:
        """Return flakiness statistics for tests in *file_path*."""

    @abstractmethod
    def get_total_results_count(self) -> int:
        """Return the total number of stored test results."""


class ITestFileRepository(ABC):
    """Abstract interface for test-file discovery and retrieval."""

    @abstractmethod
    def find_files(self, directory: Path) -> list[Path]:
        """Return all test file paths found under *directory*."""

    @abstractmethod
    def get_content(self, file_path: Path) -> str:
        """Return the text content of *file_path*."""


__all__ = ["ITestFileRepository", "ITestResultRepository"]
