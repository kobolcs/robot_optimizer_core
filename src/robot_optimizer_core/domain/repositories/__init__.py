# src/robot_optimizer_core/domain/repositories/__init__.py
"""Core repository interfaces.

These define contracts for data access that can be implemented
by infrastructure layers.
"""

from .robot_parser_repository import RobotParserRepository
from .test_result_repository import TestResultRepository

__all__ = [
    "RobotParserRepository",
    "TestResultRepository",
]
