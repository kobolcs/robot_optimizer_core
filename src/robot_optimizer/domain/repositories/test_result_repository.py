# src/robot_optimizer/domain/repositories/test_result_repository.py
"""Repository interface for test result storage."""
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from ..value_objects.test_result import TestResult
from ..value_objects.flakiness_stats import FlakinessStats


class TestResultRepository(ABC):
    """Repository interface for test result persistence."""
    
    @abstractmethod
    def save_result(self, result: TestResult) -> None:
        """Save a test execution result."""
        pass
    
    @abstractmethod
    def get_results_for_file(self, file_path: Path, days_back: int = 30) -> List[TestResult]:
        """Get test results for a specific file within time period."""
        pass
    
    @abstractmethod
    def get_flakiness_stats(self, file_path: Path, days_back: int = 30) -> List[FlakinessStats]:
        """Get flakiness statistics for tests in a file."""
        pass
    
    @abstractmethod
    def get_total_results_count(self) -> int:
        """Get total number of stored test results."""
        pass

