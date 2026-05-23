# src/robot_optimizer_core/domain/ports/parser.py
"""Port interface for Robot Framework file parsing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..entities.test_file import TestFile
    from ..value_objects.robot_ast import RobotSuite


@runtime_checkable
class IParser(Protocol):
    """Interface for parsing a Robot Framework test file into a domain model."""

    def parse_suite(self, test_file: TestFile) -> RobotSuite:
        """Parse *test_file* and return the corresponding :class:`RobotSuite`."""
        ...  # pragma: no cover


__all__ = ["IParser"]
