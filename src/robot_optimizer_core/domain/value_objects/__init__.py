# src/robot_optimizer_core/domain/value_objects/__init__.py
"""Core value objects for Robot Framework Optimizer.

These immutable objects represent core concepts in the domain.
"""

from .finding import Finding
from .flakiness_stats import FlakinessStats
from .location import Location
from .pattern import Pattern, PatternType
from .remediation import RemediationHint
from .results import AnalysisMeta, FileAnalysisResult
from .severity import Severity
from .sleep_pattern import SleepPattern
from .test_result import TestResult

__all__ = [
    "AnalysisMeta",
    "FileAnalysisResult",
    "Finding",
    "FlakinessStats",
    "Location",
    "Pattern",
    "PatternType",
    "RemediationHint",
    "Severity",
    "SleepPattern",
    "TestResult",
]
