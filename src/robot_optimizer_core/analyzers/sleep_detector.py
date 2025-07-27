# src/robot_optimizer_core/analyzers/sleep_detector.py
"""Sleep pattern detector for Robot Framework tests."""
import re
from decimal import Decimal
from typing import List

from .base_analyzer import BaseAnalyzer
from ..domain.entities import TestFile
from ..domain.value_objects import Finding, Pattern, Severity, Location, SleepPattern


class SleepDetector(BaseAnalyzer):
    """Detects sleep usage in Robot Framework tests."""
    
    @property
    def name(self) -> str:
        return "Sleep Pattern Detector"
    
    @property
    def description(self) -> str:
        return "Finds Sleep keyword usage that makes tests slow and fragile"
    
    def __init__(self):
        # Pattern to match Sleep keyword usage
        self.sleep_pattern = re.compile(
            r'^\s*Sleep\s+(\d+(?:\.\d+)?)\s*(s|seconds?|m|minutes?|ms|milliseconds?)?',
            re.IGNORECASE
        )
    
    def analyze(self, test_file: TestFile) -> List[Finding]:
        """Find all sleep patterns in the test file."""
        findings = []
        lines = test_file.content.splitlines()
        
        for line_num, line in enumerate(lines, 1):
            match = self.sleep_pattern.match(line)
            if match:
                duration_str = match.group(1)
                unit = match.group(2) or 's'  # Default to seconds
                
                try:
                    duration = Decimal(duration_str)
                    
                    sleep = SleepPattern(
                        duration=duration,
                        unit=unit.lower(),
                        line_number=line_num,
                        original_text=line.strip()
                    )
                    
                    # Determine severity based on duration
                    if sleep.duration_in_seconds < 1:
                        severity = Severity.INFO
                    elif sleep.duration_in_seconds < 5:
                        severity = Severity.WARNING
                    else:
                        severity = Severity.ERROR
                    
                    pattern = Pattern.sleep_in_test(f"{duration} {unit}")
                    
                    finding = Finding.create(
                        pattern=pattern,
                        severity=severity,
                        location=Location(file_path=test_file.path, line=line_num),
                        message=f"Sleep {duration} {unit} makes tests slow and fragile",
                        duration=str(duration),
                        unit=unit,
                        duration_seconds=sleep.duration_in_seconds
                    )
                    findings.append(finding)
                    
                except (ValueError, Decimal.InvalidOperation):
                    # Skip invalid sleep patterns
                    pass
        
        return findings
