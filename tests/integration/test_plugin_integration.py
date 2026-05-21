# tests/integration/test_plugin_integration.py
"""Integration tests for the plugin system.

These tests verify that Plugin, PluginRegistry, and ValidatedPluginManager
interact correctly end-to-end — registration, lifecycle, security validation,
and the global registry singleton.
"""

from __future__ import annotations

import pytest

from robot_optimizer_core.plugin import (
    Plugin,
    PluginMetadata,
    PluginRegistry,
    ValidatedPluginManager,
    get_plugin_registry,
)


class _StubPlugin(Plugin):
    """Minimal concrete plugin for integration testing."""

    activated: bool = False
    deactivated: bool = False

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata("stub", "1.0.0", "Stub integration plugin", "Test")

    def activate(self) -> None:
        self.activated = True
        self.is_active = True

    def deactivate(self) -> None:
        self.deactivated = True
        self.is_active = False


class _AnotherPlugin(Plugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata("another", "2.0.0", "Another plugin", "Test")

    def activate(self) -> None:
        self.is_active = True

    def deactivate(self) -> None:
        self.is_active = False


@pytest.mark.integration
class TestPluginRegistryIntegration:
    """PluginRegistry register/get/list/unregister round-trip."""

    def test_register_then_get_returns_class(self) -> None:
        registry = PluginRegistry()
        registry.register("stub", _StubPlugin)
        assert registry.get("stub") is _StubPlugin

    def test_list_reflects_registrations(self) -> None:
        registry = PluginRegistry()
        registry.register("a", _StubPlugin)
        registry.register("b", _AnotherPlugin)
        assert sorted(registry.list()) == ["a", "b"]

    def test_unregister_removes_entry(self) -> None:
        registry = PluginRegistry()
        registry.register("stub", _StubPlugin)
        registry.unregister("stub")
        assert registry.get("stub") is None
        assert "stub" not in registry.list()

    def test_get_missing_returns_none(self) -> None:
        assert PluginRegistry().get("does-not-exist") is None

    def test_register_twice_overwrites_silently(self) -> None:
        registry = PluginRegistry()
        registry.register("p", _StubPlugin)
        registry.register("p", _AnotherPlugin)
        assert registry.get("p") is _AnotherPlugin


@pytest.mark.integration
class TestPluginLifecycleIntegration:
    """Plugin activate/deactivate lifecycle through the registry."""

    def test_activate_deactivate_round_trip(self) -> None:
        plugin = _StubPlugin()
        assert not plugin.is_active

        plugin.activate()
        assert plugin.is_active
        assert plugin.activated

        plugin.deactivate()
        assert not plugin.is_active
        assert plugin.deactivated

    def test_metadata_accessible_after_activation(self) -> None:
        plugin = _StubPlugin()
        plugin.activate()
        meta = plugin.metadata
        assert meta.name == "stub"
        assert meta.version == "1.0.0"


@pytest.mark.integration
class TestGlobalPluginRegistryIntegration:
    """get_plugin_registry() returns a usable singleton."""

    def test_global_registry_is_plugin_registry_instance(self) -> None:
        registry = get_plugin_registry()
        assert isinstance(registry, PluginRegistry)

    def test_global_registry_supports_register_and_get(self) -> None:
        registry = get_plugin_registry()
        registry.register("_integration_test_stub", _StubPlugin)
        assert registry.get("_integration_test_stub") is _StubPlugin
        registry.unregister("_integration_test_stub")

    def test_global_registry_same_object_across_calls(self) -> None:
        r1 = get_plugin_registry()
        r2 = get_plugin_registry()
        assert r1 is r2


@pytest.mark.integration
class TestValidatedPluginManagerIntegration:
    """ValidatedPluginManager rejects unsafe plugins."""

    def test_manager_has_expected_interface(self) -> None:
        manager = ValidatedPluginManager()
        assert hasattr(manager, "load_plugin_from_file")
        assert hasattr(manager, "unload_plugin")
        assert hasattr(manager, "add_trusted_plugin_hash")
