# src/robot_optimizer_core/analyzers/flakiness.py
"""Basic flakiness analyzer for Robot Framework tests."""
from typing import List

from .base_analyzer import BaseAnalyzer
from ..domain.entities import TestFile
from ..domain.value_objects import Finding, Pattern, PatternType, Severity, Location
from ..domain.repositories import TestResultRepository


class FlakinessAnalyzer(BaseAnalyzer):
    """Basic analyzer for detecting flaky tests.
    
    This Core version provides basic flakiness detection.
    The Pro version adds trend analysis and root cause detection.
    """
    
    def __init__(self, test_result_repository: TestResultRepository):
        self.test_result_repository = test_result_repository
    
    @property
    def name(self) -> str:
        return "Flakiness Analyzer"
    
    @property
    def description(self) -> str:
        return "Detects tests that fail intermittently"
    
    def analyze(self, test_file: TestFile) -> List[Finding]:
        """Analyze test file for flaky tests."""
        findings = []
        
        # Get flakiness statistics
        stats_list = self.test_result_repository.get_flakiness_stats(
            test_file.path, days_back=30
        )
        
        for stats in stats_list:
            if stats.is_flaky and stats.failure_rate > 0.05:
                severity = self._determine_severity(stats.failure_rate)
                
                pattern = Pattern(
                    type=PatternType.INEFFICIENT_WAIT,
                    name="Flaky Test",
                    description=f"Test '{stats.test_name}' fails inconsistently",
                    recommendation="Add explicit waits or fix race conditions",
                    auto_fixable=False
                )
                
                finding = Finding.create(
                    pattern=pattern,
                    severity=severity,
                    location=Location(file_path=test_file.path, line=1),
                    message=f"Flaky test: {stats.failure_rate:.1%} failure rate",
                    test_name=stats.test_name,
                    failure_rate=stats.failure_rate,
                    total_runs=stats.total_runs
                )
                findings.append(finding)
        
        return findings
    
    def _determine_severity(self, failure_rate: float) -> Severity:
        """Determine severity based on failure rate."""
        if failure_rate > 0.15:
            return Severity.ERROR
        elif failure_rate > 0.05:
            return Severity.WARNING
        else:
            return Severity.INFO