# tests/contracts/test_plugin_contract.py
"""Plugin contract tests — pin the interface exposed to external plugin authors.

Plugin authors depend on these contracts. A failure here means an incompatible
change that would silently break third-party plugins without a major version bump.
"""

from __future__ import annotations

import inspect

import pytest

from robot_optimizer_core.infrastructure.plugins.manager import (
    Plugin,
    PluginMetadata,
    PluginRegistry,
    ValidatedPluginManager,
    get_plugin_registry,
)


class _MinimalPlugin(Plugin):
    """Minimal compliant plugin — exactly what an external author would write."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="minimal",
            version="1.0.0",
            description="Minimal test plugin",
            author="Test",
        )

    def activate(self) -> None:
        self.is_active = True

    def deactivate(self) -> None:
        self.is_active = False


@pytest.mark.contract
class TestPluginBaseClassContract:
    """Plugin base class interface is stable for external subclassers."""

    def test_plugin_has_is_active_attribute(self) -> None:
        p = _MinimalPlugin()
        assert hasattr(p, "is_active")
        assert p.is_active is False

    def test_plugin_has_metadata_property(self) -> None:
        p = _MinimalPlugin()
        assert hasattr(p, "metadata")

    def test_plugin_has_activate_method(self) -> None:
        assert callable(getattr(Plugin, "activate", None))

    def test_plugin_has_deactivate_method(self) -> None:
        assert callable(getattr(Plugin, "deactivate", None))

    def test_activate_sets_is_active(self) -> None:
        p = _MinimalPlugin()
        p.activate()
        assert p.is_active is True

    def test_deactivate_clears_is_active(self) -> None:
        p = _MinimalPlugin()
        p.activate()
        p.deactivate()
        assert p.is_active is False


@pytest.mark.contract
class TestPluginMetadataContract:
    """PluginMetadata field names are stable."""

    def test_metadata_has_name(self) -> None:
        m = PluginMetadata(name="x", version="1.0", description="d", author="a")
        assert m.name == "x"

    def test_metadata_has_version(self) -> None:
        m = PluginMetadata(name="x", version="1.0", description="d", author="a")
        assert m.version == "1.0"

    def test_metadata_has_description(self) -> None:
        m = PluginMetadata(name="x", version="1.0", description="d", author="a")
        assert m.description == "d"

    def test_metadata_has_author(self) -> None:
        m = PluginMetadata(name="x", version="1.0", description="d", author="a")
        assert m.author == "a"

    def test_metadata_constructor_positional_order(self) -> None:
        # Positional construction must remain stable — external code may use it.
        m = PluginMetadata("myname", "2.0.0", "My description", "Author Name")
        assert m.name == "myname"
        assert m.version == "2.0.0"


@pytest.mark.contract
class TestPluginRegistryContract:
    """PluginRegistry public interface is stable."""

    def test_registry_has_register_method(self) -> None:
        assert callable(getattr(PluginRegistry, "register", None))

    def test_registry_has_get_method(self) -> None:
        assert callable(getattr(PluginRegistry, "get", None))

    def test_registry_has_list_method(self) -> None:
        assert callable(getattr(PluginRegistry, "list", None))

    def test_registry_has_unregister_method(self) -> None:
        assert callable(getattr(PluginRegistry, "unregister", None))

    def test_register_then_get_roundtrip(self) -> None:
        r = PluginRegistry()
        r.register("minimal", _MinimalPlugin)
        assert r.get("minimal") is _MinimalPlugin

    def test_get_missing_returns_none(self) -> None:
        assert PluginRegistry().get("not-registered") is None

    def test_list_returns_registered_names(self) -> None:
        r = PluginRegistry()
        r.register("a", _MinimalPlugin)
        assert "a" in r.list()

    def test_unregister_removes_entry(self) -> None:
        r = PluginRegistry()
        r.register("x", _MinimalPlugin)
        r.unregister("x")
        assert r.get("x") is None

    def test_register_signature_stable(self) -> None:
        sig = inspect.signature(PluginRegistry.register)
        params = list(sig.parameters.keys())
        assert "name" in params
        assert "plugin_class" in params


@pytest.mark.contract
class TestGlobalRegistryContract:
    """get_plugin_registry() returns the same singleton object."""

    def test_returns_plugin_registry_instance(self) -> None:
        assert isinstance(get_plugin_registry(), PluginRegistry)

    def test_same_object_across_calls(self) -> None:
        assert get_plugin_registry() is get_plugin_registry()


@pytest.mark.contract
class TestValidatedPluginManagerContract:
    """ValidatedPluginManager public interface is stable."""

    def test_manager_has_load_plugin_from_file(self) -> None:
        assert callable(getattr(ValidatedPluginManager, "load_plugin_from_file", None))

    def test_manager_has_unload_plugin(self) -> None:
        assert callable(getattr(ValidatedPluginManager, "unload_plugin", None))

    def test_manager_has_add_trusted_plugin_hash(self) -> None:
        assert callable(getattr(ValidatedPluginManager, "add_trusted_plugin_hash", None))

    def test_manager_constructor_accepts_optional_registry(self) -> None:
        sig = inspect.signature(ValidatedPluginManager.__init__)
        assert "registry" in sig.parameters
        assert sig.parameters["registry"].default is None
