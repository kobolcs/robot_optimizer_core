# tests/unit/helpers.py
"""Shared factory helpers for unit tests.

Import these instead of defining local _make_finding / _make_pattern in each file.

Constants
---------
_SIMPLE_ROBOT   Minimal valid .robot file bytes — use wherever a file exists but
                content does not matter for the test assertion.
"""

from __future__ import annotations

from pathlib import Path

from robot_optimizer_core.domain.value_objects import Finding, Severity
from robot_optimizer_core.domain.value_objects.location import Location
from robot_optimizer_core.domain.value_objects.pattern import Pattern, PatternType

# Minimal valid Robot Framework content.  Use this instead of hardcoding the
# bytes in each test so that format changes require a single-line fix here.
_SIMPLE_ROBOT: bytes = b"*** Test Cases ***\nT\n    Log    ok\n"


def make_pattern(
    pattern_type: PatternType = PatternType.SLEEP_IN_TEST,
    name: str = "Sleep in Test Case",
    description: str = "Sleep detected",
    recommendation: str = "Use explicit wait",
) -> Pattern:
    return Pattern(
        type=pattern_type,
        name=name,
        description=description,
        recommendation=recommendation,
    )


def make_finding(
    file_path: Path = Path("suite.robot"),
    line: int = 10,
    severity: Severity = Severity.WARNING,
    pattern_type: PatternType = PatternType.SLEEP_IN_TEST,
    message: str = "Use explicit wait",
    pattern_name: str = "Sleep in Test Case",
    pattern_description: str = "Sleep detected",
    pattern_recommendation: str = "Use explicit wait",
) -> Finding:
    pattern = Pattern(
        type=pattern_type,
        name=pattern_name,
        description=pattern_description,
        recommendation=pattern_recommendation,
    )
    return Finding.create(
        pattern=pattern,
        severity=severity,
        location=Location(file_path=file_path, line=line),
        message=message,
    )
