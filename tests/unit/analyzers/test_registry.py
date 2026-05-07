from __future__ import annotations

from importlib.metadata import EntryPoint

import pytest

from robot_optimizer_core.analyzers import BaseAnalyzer, SleepDetector
from robot_optimizer_core.analyzers.registry import (
    AnalyzerRegistry,
    _register_entry_point_analyzers,
    get_analyzer_registry,
    reset_registry,
)
from robot_optimizer_core.domain.entities import TestFile
from robot_optimizer_core.domain.value_objects import Finding


@pytest.fixture(autouse=True)
def _reset_analyzer_registry() -> None:
    """Reset the analyzer registry before each test to avoid cross-test pollution."""
    reset_registry()


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


_ALL_BUILTINS = {
    "dead_code",
    "sleep_detector",
    "flakiness",
    "hardcoded_value",
    "naming_convention",
    "setup_teardown",
    "tag_consistency",
    "test_documentation",
}


@pytest.mark.unit
def test_reset_registry_creates_fresh_instance() -> None:
    r1 = get_analyzer_registry()
    reset_registry()
    r2 = get_analyzer_registry()
    assert r1 is not r2


@pytest.mark.unit
def test_get_analyzer_registry_stable_without_reset() -> None:
    r1 = get_analyzer_registry()
    r2 = get_analyzer_registry()
    assert r1 is r2


@pytest.mark.unit
def test_reset_registry_rebuilds_all_builtins() -> None:
    reset_registry()
    registry = get_analyzer_registry()
    missing = _ALL_BUILTINS - set(registry.list())
    assert not missing, f"Missing after reset: {missing}"


@pytest.mark.unit
def test_reset_registry_removes_custom_analyzer() -> None:
    registry = get_analyzer_registry()
    registry.register("_temp_probe", ExternalAnalyzer, override=True)
    assert "_temp_probe" in registry.list()
    reset_registry()
    assert "_temp_probe" not in get_analyzer_registry().list()


@pytest.mark.unit
def test_register_entry_point_analyzers_loads_canonical_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
