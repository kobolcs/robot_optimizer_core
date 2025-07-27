# Update value objects module
# src/robot_optimizer/domain/value_objects/__init__.py
"""Value objects for the Robot Framework Optimizer domain."""

from .severity import Severity
from .location import Location
from .pattern import Pattern, PatternType
from .finding import Finding
from .sleep_pattern import SleepPattern
from .optimization_suggestion import OptimizationSuggestion, OptimizationType
from .test_result import TestResult
from .flakiness_stats import FlakinessStats

__all__ = [
    "Severity",
    "Location", 
    "Pattern",
    "PatternType",
    "Finding",
    "SleepPattern",
    "OptimizationSuggestion",
    "OptimizationType",
    "TestResult",
    "FlakinessStats",
]
