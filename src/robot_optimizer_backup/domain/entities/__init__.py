# src/robot_optimizer/domain/entities/__init__.py
"""Domain entities for the Robot Framework Optimizer.

100% Pydantic v2 compliant implementations.
"""

from .test_file import TestFile
from .analysis import Analysis

__all__ = [
    "TestFile",
    "Analysis",
]
