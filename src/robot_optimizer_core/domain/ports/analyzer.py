# src/robot_optimizer_core/domain/ports/analyzer.py
"""Port interfaces for analysis."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ..entities.test_file import TestFile
from ..value_objects.finding import Finding


@runtime_checkable
class IAnalyzer(Protocol):
    """Interface for a single-file analyzer."""

    @property
    def name(self) -> str:
        """Unique analyzer identifier."""
        ...  # pragma: no cover

    @property
    def description(self) -> str:
        """Human-readable description of what the analyzer detects."""
        ...  # pragma: no cover

    def analyze(self, test_file: TestFile) -> list[Finding]:
        """Analyze *test_file* and return a list of findings."""
        ...  # pragma: no cover


@runtime_checkable
class ISuiteAnalyzer(Protocol):
    """Interface for cross-file suite-level analysis."""

    def analyze_suite(self, files: Sequence[TestFile]) -> list[Finding]:
        """Analyze an entire suite and return findings that span multiple files."""
        ...  # pragma: no cover


__all__ = ["IAnalyzer", "ISuiteAnalyzer"]
