# tests/unit/analyzers/test_base_lazy_metrics.py
"""Tests that BaseAnalyzer resolves metrics lazily."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from robot_optimizer_core.analyzers.base import BaseAnalyzer
from robot_optimizer_core.domain.entities import TestFile
from robot_optimizer_core.domain.value_objects import Finding


class _MinimalAnalyzer(BaseAnalyzer):
    @property
    def name(self) -> str:
        return "_minimal"

    @property
    def description(self) -> str:
        return "minimal"

    def analyze(self, test_file: TestFile) -> list[Finding]:
        return []


def _make_file(tmp_path: Path) -> TestFile:
    f = tmp_path / "t.robot"
    f.write_bytes(b"*** Test Cases ***\nT\n    Log    hi\n")
    return TestFile.from_path(f)


@pytest.mark.unit
class TestBaseAnalyzerLazyMetrics:
    def test_construction_does_not_call_get_metrics(self) -> None:
        with patch("robot_optimizer_core.analyzers.base.get_metrics") as mock:
            _MinimalAnalyzer()
            mock.assert_not_called()

    def test_metrics_resolved_on_first_safe_analyze(self, tmp_path: Path) -> None:
        analyzer = _MinimalAnalyzer()
        assert analyzer._metrics is None
        analyzer.safe_analyze(_make_file(tmp_path))
        assert analyzer._metrics is not None

    def test_metrics_disabled_never_resolved(self, tmp_path: Path) -> None:
        with patch("robot_optimizer_core.analyzers.base.get_metrics") as mock:
            analyzer = _MinimalAnalyzer(metrics_enabled=False)
            analyzer.safe_analyze(_make_file(tmp_path))
            mock.assert_not_called()
        assert analyzer._metrics is None
