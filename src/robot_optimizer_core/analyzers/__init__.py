# src/robot_optimizer_core/analyzers/__init__.py
"""Analyzers for Robot Framework test suite optimization.

This package contains the analyzer framework and built-in analyzers
for detecting various issues in Robot Framework test suites.

Built-in analyzers:
    - DeadCodeAnalyzer: Finds unused keywords and duplicates
    - SleepDetector: Detects sleep usage that makes tests slow
    - FlakinessAnalyzer: Identifies intermittently failing tests

Example:
    Using analyzers directly::

        from robot_optimizer_core.analyzers import DeadCodeAnalyzer
        from robot_optimizer_core import TestFile

        analyzer = DeadCodeAnalyzer()
        test_file = TestFile.from_path("tests/login.robot")
        findings = analyzer.analyze(test_file)

    Using the registry::

        from robot_optimizer_core.analyzers import get_analyzer, list_analyzers

        # List available analyzers
        print(list_analyzers())

        # Get analyzer by name
        analyzer = get_analyzer("dead_code")
"""
from __future__ import annotations

# Base classes
from .base import BaseAnalyzer

# Built-in analyzers
from .dead_code import DeadCodeAnalyzer
from .flakiness import FlakinessAnalyzer

# Registry
from .registry import (
    AnalyzerRegistry,
    get_analyzer,
    get_analyzer_info,
    get_analyzer_registry,
    list_analyzers,
    register_analyzer,
)
from .sleep_detector import SleepDetector

__all__ = [
    # Base
    "BaseAnalyzer",

    # Registry
    "AnalyzerRegistry",
    "register_analyzer",
    "get_analyzer",
    "list_analyzers",
    "get_analyzer_info",
    "get_analyzer_registry",

    # Built-in analyzers
    "DeadCodeAnalyzer",
    "SleepDetector",
    "FlakinessAnalyzer",
]
