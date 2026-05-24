from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from robot_optimizer_core.domain.value_objects import Finding, Severity
from robot_optimizer_core.domain.value_objects.location import Location
from robot_optimizer_core.domain.value_objects.pattern import Pattern, PatternType


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if str(item.fspath).replace("\\", "/").split("/tests/")[1].startswith("unit/"):
            item.add_marker(pytest.mark.unit)


# ---------------------------------------------------------------------------
# Shared finding factory — replaces per-file _make_finding() helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def make_finding() -> Callable[..., Finding]:
    """Return a factory that builds Finding test instances.

    All parameters are optional; defaults produce a minimal WARNING-severity
    SLEEP_IN_TEST finding at suite.robot:10.
    """
    def _factory(
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
    return _factory
