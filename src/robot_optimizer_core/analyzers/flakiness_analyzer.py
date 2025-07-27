# src/robot_optimizer/domain/services/flakiness_analyzer.py
"""Domain service for flakiness analysis."""
from typing import List

from ..entities import TestFile
from ..value_objects import Pattern, PatternType, Finding, Location, Severity
from ..value_objects.flakiness_stats import FlakinessStats
from ..repositories import TestResultRepository


class FlakinessAnalyzer:
    """Domain service for analyzing test flakiness."""
    
    def __init__(self, test_result_repository: TestResultRepository):
        self.test_result_repository = test_result_repository
    
    def analyze_flakiness(self, test_file: TestFile, days_back: int = 30) -> List[Finding]:
        """Analyze flakiness for tests in the given file."""
        flakiness_stats = self.test_result_repository.get_flakiness_stats(
            test_file.path, days_back
        )
        
        return self._create_findings_from_stats(flakiness_stats, test_file)
    
    def _create_findings_from_stats(self, stats_list: List[FlakinessStats], test_file: TestFile) -> List[Finding]:
        """Create Finding objects from flakiness statistics."""
        findings = []
        
        for stats in stats_list:
            if stats.is_flaky and stats.failure_rate > 0.05:  # More than 5% failure rate
                severity = self._determine_severity(stats.failure_rate)
                
                pattern = Pattern(
                    type=PatternType.INEFFICIENT_WAIT,
                    name="Flaky Test",
                    description=f"Test '{stats.test_name}' fails inconsistently",
                    recommendation="Investigate timing issues, add explicit waits, or fix race conditions",
                    auto_fixable=False
                )
                
                finding = Finding.create(
                    pattern=pattern,
                    severity=severity,
                    location=Location(
                        file_path=test_file.path,
                        line=1  # Don't know exact line in simple mode
                    ),
                    message=f"Flaky test: {stats.failure_rate:.1%} failure rate "
                           f"({stats.failures}/{stats.total_runs} runs)",
                    test_name=stats.test_name,
                    failure_rate=stats.failure_rate,
                    total_runs=stats.total_runs,
                    failures=stats.failures,
                    time_wasted_hours=stats.failures * 0.25  # 15 min per failure investigation
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
