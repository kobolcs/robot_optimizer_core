"""Core repository interfaces."""
from .test_result_repository import TestResultRepository
from .robot_parser_repository import RobotParserRepository

__all__ = [
    "TestResultRepository",
    "RobotParserRepository",
]
