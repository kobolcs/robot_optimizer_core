from __future__ import annotations

from collections.abc import Generator
from importlib.metadata import EntryPoint

import pytest

from robot_optimizer_core.application.analyzers import BaseAnalyzer, SleepDetector
from robot_optimizer_core.application.analyzers.registry import (
    AnalyzerRegistry,
    _iter_analyzer_entry_points,
    _register_entry_point_analyzers,
    get_analyzer,
    get_analyzer_info,
    get_analyzer_registry,
    list_analyzers,
    register_analyzer,
    reset_registry,
)
from robot_optimizer_core.domain.entities import TestFile
from robot_optimizer_core.domain.value_objects import Finding
from robot_optimizer_core.exceptions import PluginError


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


@pytest.fixture(autouse=True)
def _isolate_registry_state() -> Generator[None, None, None]:
    reset_registry()
    yield
    reset_registry()


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
        value="robot_optimizer_core.application.analyzers:SleepDetector",
        group="robot_optimizer_core.application.analyzers",
    )

    monkeypatch.setattr(
        "robot_optimizer_core.application.analyzers.registry._iter_analyzer_entry_points",
        lambda: [ep],
    )

    _register_entry_point_analyzers(registry)

    assert "external_plugin" in registry.list()
    assert isinstance(registry.create("external_plugin"), SleepDetector)


@pytest.mark.unit
class TestAnalyzerRegistryErrors:
    def test_register_duplicate_raises(self) -> None:
        registry = AnalyzerRegistry()
        registry.register("ext", ExternalAnalyzer)
        with pytest.raises(PluginError, match="already registered"):
            registry.register("ext", ExternalAnalyzer)

    def test_register_override_replaces(self) -> None:
        registry = AnalyzerRegistry()
        registry.register("ext", ExternalAnalyzer)
        registry.register("ext", ExternalAnalyzer, override=True)
        assert "ext" in registry.list()

    def test_register_override_clears_cached_instance(self) -> None:
        registry = AnalyzerRegistry()
        registry.register("ext", ExternalAnalyzer)
        _ = registry.get("ext")
        assert "ext" in registry.instances
        registry.register("ext", ExternalAnalyzer, override=True)
        assert "ext" not in registry.instances

    def test_register_not_subclass_raises(self) -> None:
        registry = AnalyzerRegistry()
        with pytest.raises(PluginError, match="must inherit from BaseAnalyzer"):
            registry.register("bad", str)  # type: ignore[arg-type]

    def test_get_not_found_raises(self) -> None:
        registry = AnalyzerRegistry()
        with pytest.raises(PluginError, match="not found"):
            registry.get("nonexistent")

    def test_create_not_found_raises(self) -> None:
        registry = AnalyzerRegistry()
        with pytest.raises(PluginError, match="not found"):
            registry.create("nonexistent")

    def test_get_default_analyzers(self) -> None:
        registry = get_analyzer_registry()
        defaults = registry.get_default_analyzers()
        assert len(defaults) > 0
        assert all(isinstance(a, BaseAnalyzer) for a in defaults)

    def test_set_default_analyzers_valid(self) -> None:
        registry = get_analyzer_registry()
        registry.set_default_analyzers(["dead_code", "flakiness"])
        assert registry.default_analyzers == ["dead_code", "flakiness"]

    def test_set_default_analyzers_invalid_raises(self) -> None:
        registry = get_analyzer_registry()
        with pytest.raises(PluginError, match="Invalid analyzer names"):
            registry.set_default_analyzers(["nonexistent_analyzer"])

    def test_clear_cache(self) -> None:
        registry = get_analyzer_registry()
        _ = registry.get("dead_code")
        assert "dead_code" in registry.instances
        registry.clear_cache()
        assert registry.instances == {}

    def test_unregister(self) -> None:
        registry = AnalyzerRegistry()
        registry.register("ext", ExternalAnalyzer)
        _ = registry.get("ext")
        registry.unregister("ext")
        assert "ext" not in registry.analyzers
        assert "ext" not in registry.instances

    def test_unregister_nonexistent_is_noop(self) -> None:
        registry = AnalyzerRegistry()
        registry.unregister("nonexistent")


@pytest.mark.unit
class TestAnalyzerRegistryModuleFunctions:
    def test_register_analyzer(self) -> None:
        register_analyzer("ext_func", ExternalAnalyzer, override=True)
        assert "ext_func" in get_analyzer_registry().list()

    def test_get_analyzer(self) -> None:
        instance = get_analyzer("dead_code")
        assert isinstance(instance, BaseAnalyzer)

    def test_list_analyzers(self) -> None:
        names = list_analyzers()
        assert "dead_code" in names
        assert isinstance(names, list)

    def test_get_analyzer_info(self) -> None:
        info = get_analyzer_info("dead_code")
        assert "name" in info
        assert "description" in info
        assert "version" in info


@pytest.mark.unit
class TestIterAnalyzerEntryPoints:
    def test_returns_list(self) -> None:
        result = _iter_analyzer_entry_points()
        assert isinstance(result, list)

    def test_old_style_entry_points(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_eps: dict[str, list[object]] = {"robot_optimizer_core.application.analyzers": []}

        monkeypatch.setattr(
            "robot_optimizer_core.application.analyzers.registry.entry_points",
            lambda: fake_eps,
        )
        result = _iter_analyzer_entry_points()
        assert result == []
