# tests/unit/analyzers/test_base_lazy_metrics.py
"""Tests that BaseAnalyzer uses injected IMetrics."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from robot_optimizer_core.application.analyzers.base import BaseAnalyzer
from robot_optimizer_core.domain.entities import TestFile
from robot_optimizer_core.domain.ports.metrics import IMetrics
from robot_optimizer_core.domain.value_objects import Finding


class _MinimalAnalyzer(BaseAnalyzer):
    @property
    def name(self) -> str:
        return "_minimal"

    @property
    def description(self) -> str:
        return "minimal"

    def analyze(self, _test_file: TestFile) -> list[Finding]:
        return []


def _make_file(tmp_path: Path) -> TestFile:
    f = tmp_path / "t.robot"
    f.write_bytes(b"*** Test Cases ***\nT\n    Log    hi\n")
    return TestFile.from_path(f)


@pytest.mark.unit
class TestBaseAnalyzerMetricsInjection:
    def test_construction_without_metrics_leaves_none(self) -> None:
        analyzer = _MinimalAnalyzer()
        assert analyzer._metrics is None

    def test_construction_with_metrics_stores_instance(self) -> None:
        mock_metrics: IMetrics = MagicMock(spec=IMetrics)
        analyzer = _MinimalAnalyzer(metrics=mock_metrics)
        assert analyzer._metrics is mock_metrics

    def test_safe_analyze_without_metrics_does_not_raise(self, tmp_path: Path) -> None:
        analyzer = _MinimalAnalyzer()
        result = analyzer.safe_analyze(_make_file(tmp_path))
        assert result == []

    def test_safe_analyze_calls_increment_on_success(self, tmp_path: Path) -> None:
        mock_metrics: IMetrics = MagicMock(spec=IMetrics)
        analyzer = _MinimalAnalyzer(metrics=mock_metrics)
        analyzer.safe_analyze(_make_file(tmp_path))
        mock_metrics.increment.assert_called_with("analyzer._minimal.success")

    def test_safe_analyze_calls_gauge_with_findings_count(self, tmp_path: Path) -> None:
        mock_metrics: IMetrics = MagicMock(spec=IMetrics)
        analyzer = _MinimalAnalyzer(metrics=mock_metrics)
        analyzer.safe_analyze(_make_file(tmp_path))
        mock_metrics.gauge.assert_called_with("analyzer._minimal.findings_count", 0)
