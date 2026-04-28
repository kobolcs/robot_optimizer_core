# src/robot_optimizer/domain/repositories/robot_parser_repository.py
"""Repository interface for Robot Framework parsing."""

from abc import ABC, abstractmethod

from ..entities import TestFile
from ..value_objects.robot_ast import RobotSuite


class RobotParserRepository(ABC):
    """Repository interface for parsing Robot Framework files."""

    @abstractmethod
    def parse_suite(self, test_file: TestFile) -> RobotSuite:
        """Parse a test file into a RobotSuite."""
