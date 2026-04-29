from __future__ import annotations

from importlib.metadata import EntryPoint

import pytest

from robot_optimizer_core.analyzers import BaseAnalyzer, SleepDetector
from robot_optimizer_core.analyzers.registry import (
    AnalyzerRegistry,
    _register_entry_point_analyzers,
)
from robot_optimizer_core.domain.entities import TestFile
from robot_optimizer_core.domain.value_objects import Finding


class ExternalAnalyzer(BaseAnalyzer):
    @property
    def name(self) -> str:
        return "external"

    @property
    def description(self) -> str:
        return "external analyzer"

    def analyze(self, test_file: TestFile) -> list[Finding]:
        return []


@pytest.mark.unit
def test_registry_create_returns_fresh_instances() -> None:
    registry = AnalyzerRegistry()
    registry.register("external", ExternalAnalyzer)

    first = registry.create("external")
    second = registry.create("external")

    assert first is not second


@pytest.mark.unit
def test_register_entry_point_analyzers_loads_canonical_group(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = AnalyzerRegistry()

    ep = EntryPoint(
        name="external_plugin",
        value="robot_optimizer_core.analyzers:SleepDetector",
        group="robot_optimizer_core.analyzers",
    )

    monkeypatch.setattr(
        "robot_optimizer_core.analyzers.registry._iter_analyzer_entry_points",
        lambda: [ep],
    )

    _register_entry_point_analyzers(registry)

    assert "external_plugin" in registry.list()
    assert isinstance(registry.create("external_plugin"), SleepDetector)
