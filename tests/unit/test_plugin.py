# tests/unit/test_plugin.py
"""Unit tests for the secure plugin system."""

from __future__ import annotations

import ast
import hashlib
import logging
import sys
from pathlib import Path

import pytest

from robot_optimizer_core.exceptions import PluginError
from robot_optimizer_core.infrastructure.plugins.manager import (
    Plugin,
    PluginMetadata,
    PluginRegistry,
    PluginSecurityValidator,
    SecurityVisitor,
    ValidatedPluginManager,
    get_plugin_registry,
)


class _MinimalPlugin(Plugin):
    """Concrete Plugin subclass used only in test helpers."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata("minimal", "1.0.0", "Minimal test plugin", "Test")

    def activate(self) -> None:
        self.is_active = True

    def deactivate(self) -> None:
        self.is_active = False


@pytest.mark.unit
class TestPluginRegistry:
    def test_register_and_get(self) -> None:
        registry = PluginRegistry()
        registry.register("minimal", _MinimalPlugin)
        assert registry.get("minimal") is _MinimalPlugin

    def test_get_missing_returns_none(self) -> None:
        assert PluginRegistry().get("nonexistent") is None

    def test_list_empty(self) -> None:
        assert PluginRegistry().list() == []

    def test_list_registered_names(self) -> None:
        registry = PluginRegistry()
        registry.register("a", _MinimalPlugin)
        registry.register("b", _MinimalPlugin)
        assert sorted(registry.list()) == ["a", "b"]

    def test_unregister_removes_entry(self) -> None:
        registry = PluginRegistry()
        registry.register("minimal", _MinimalPlugin)
        registry.unregister("minimal")
        assert registry.get("minimal") is None
        assert "minimal" not in registry.list()

    def test_unregister_missing_is_noop(self) -> None:
        registry = PluginRegistry()
        registry.unregister("does_not_exist")  # must not raise


@pytest.mark.unit
class TestPluginInterface:
    def test_activate_sets_is_active(self) -> None:
        plugin = _MinimalPlugin()
        assert plugin.is_active is False
        plugin.activate()
        assert plugin.is_active is True

    def test_deactivate_clears_is_active(self) -> None:
        plugin = _MinimalPlugin()
        plugin.activate()
        plugin.deactivate()
        assert plugin.is_active is False

    def test_metadata_fields(self) -> None:
        meta = _MinimalPlugin().metadata
        assert meta.name == "minimal"
        assert meta.version == "1.0.0"
        assert meta.description == "Minimal test plugin"
        assert meta.author == "Test"

    def test_registry_stored_on_init(self) -> None:
        registry = PluginRegistry()
        plugin = _MinimalPlugin(registry=registry)
        assert plugin.registry is registry

    def test_abstract_class_not_instantiable(self) -> None:
        with pytest.raises(TypeError):
            Plugin()  # type: ignore[abstract]


@pytest.mark.unit
class TestSecurityVisitor:
    def _visit(self, code: str) -> SecurityVisitor:
        tree = ast.parse(code)
        visitor = SecurityVisitor()
        visitor.visit(tree)
        return visitor

    def test_forbidden_import_flagged(self) -> None:
        visitor = self._visit("import os")
        assert any("os" in v for v in visitor.violations)

    def test_forbidden_from_import_flagged(self) -> None:
        visitor = self._visit("from subprocess import run")
        assert any("subprocess" in v for v in visitor.violations)

    def test_allowed_import_accepted(self) -> None:
        assert self._visit("import pathlib").violations == []

    def test_allowed_from_import_accepted(self) -> None:
        assert self._visit("from typing import Any").violations == []

    def test_allowed_from_robot_optimizer_core(self) -> None:
        assert self._visit("from robot_optimizer_core import Plugin").violations == []

    def test_eval_call_flagged(self) -> None:
        visitor = self._visit("eval('1+1')")
        assert any("eval" in v for v in visitor.violations)

    def test_exec_call_flagged(self) -> None:
        visitor = self._visit("exec('x=1')")
        assert any("exec" in v for v in visitor.violations)

    def test_open_call_flagged(self) -> None:
        visitor = self._visit("open('file.txt')")
        assert any("open" in v for v in visitor.violations)

    def test_os_module_usage_flagged(self) -> None:
        visitor = self._visit("os.getcwd()")
        assert any("os" in v for v in visitor.violations)

    def test_subprocess_usage_flagged(self) -> None:
        visitor = self._visit("subprocess.run(['ls'])")
        assert any("subprocess" in v for v in visitor.violations)

    def test_forbidden_attribute_globals_flagged(self) -> None:
        visitor = self._visit("x = obj.__globals__")
        assert any("__globals__" in v for v in visitor.violations)

    def test_forbidden_attribute_dict_flagged(self) -> None:
        visitor = self._visit("x = obj.__dict__")
        assert any("__dict__" in v for v in visitor.violations)

    def test_getattr_with_dangerous_attr_flagged(self) -> None:
        visitor = self._visit("getattr(obj, '__dict__')")
        assert any("__dict__" in v for v in visitor.violations)

    def test_getattr_with_globals_flagged(self) -> None:
        visitor = self._visit("getattr(obj, '__globals__')")
        assert any("__globals__" in v for v in visitor.violations)

    def test_setattr_with_dangerous_attr_flagged(self) -> None:
        visitor = self._visit("setattr(obj, '__dict__', {})")
        assert any("__dict__" in v for v in visitor.violations)

    def test_getattr_with_non_literal_attr_flagged(self) -> None:
        visitor = self._visit("getattr(obj, attr_name)")
        assert any("non-literal" in v for v in visitor.violations)

    def test_forbidden_attribute_class_flagged(self) -> None:
        visitor = self._visit("x = obj.__class__")
        assert any("__class__" in v for v in visitor.violations)

    def test_forbidden_attribute_bases_flagged(self) -> None:
        visitor = self._visit("x = obj.__bases__")
        assert any("__bases__" in v for v in visitor.violations)

    def test_getattr_with_safe_attr_accepted(self) -> None:
        assert self._visit("getattr(obj, 'name')").violations == []

    def test_clean_code_has_no_violations(self) -> None:
        code = """
class MyClass:
    def method(self) -> None:
        result = len([1, 2, 3])
        return str(result)
"""
        assert self._visit(code).violations == []

    def test_multiple_violations_collected(self) -> None:
        code = "import os\nimport sys\neval('x')"
        visitor = self._visit(code)
        assert len(visitor.violations) >= 3


@pytest.mark.unit
class TestPluginSecurityValidator:
    def test_clean_file_passes(self, tmp_path: Path) -> None:
        plugin_file = tmp_path / "clean.py"
        plugin_file.write_bytes(b"x = 1\n")
        plugin_file.chmod(0o644)

        validator = PluginSecurityValidator()
        is_safe, violations = validator.validate_file(plugin_file)

        assert is_safe is True
        assert violations == []

    def test_forbidden_import_rejected(self, tmp_path: Path) -> None:
        plugin_file = tmp_path / "bad.py"
        plugin_file.write_bytes(b"import os\n")
        plugin_file.chmod(0o644)

        validator = PluginSecurityValidator()
        is_safe, violations = validator.validate_file(plugin_file)

        assert is_safe is False
        assert any("os" in v for v in violations)

    def test_eval_call_rejected(self, tmp_path: Path) -> None:
        plugin_file = tmp_path / "eval_plugin.py"
        plugin_file.write_bytes(b"result = eval('1+1')\n")
        plugin_file.chmod(0o644)

        validator = PluginSecurityValidator()
        is_safe, violations = validator.validate_file(plugin_file)

        assert is_safe is False
        assert any("eval" in v for v in violations)

    def test_nonexistent_file_returns_unsafe(self) -> None:
        validator = PluginSecurityValidator()
        is_safe, violations = validator.validate_file(Path("/nonexistent/plugin.py"))

        assert is_safe is False
        assert len(violations) > 0

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Windows does not support Unix group/other write permission bits",
    )
    def test_world_writable_file_rejected(self, tmp_path: Path) -> None:
        plugin_file = tmp_path / "writable.py"
        plugin_file.write_bytes(b"x = 1\n")
        plugin_file.chmod(0o666)  # world-writable

        validator = PluginSecurityValidator()
        is_safe, violations = validator.validate_file(plugin_file)

        assert is_safe is False
        assert any("writable" in v.lower() for v in violations)


@pytest.mark.unit
class TestValidatedPluginManager:
    def test_nonexistent_file_raises_plugin_error(self) -> None:
        manager = ValidatedPluginManager()
        with pytest.raises(PluginError, match="Plugin file not found"):
            manager.load_plugin_from_file(Path("/nonexistent/plugin.py"))

    def test_security_violation_raises_plugin_error(self, tmp_path: Path) -> None:
        plugin_file = tmp_path / "bad.py"
        plugin_file.write_bytes(b"import os\n")
        plugin_file.chmod(0o644)

        manager = ValidatedPluginManager()
        with pytest.raises(PluginError, match="[Ss]ecurity validation"):
            manager.load_plugin_from_file(plugin_file)

    def test_load_valid_plugin_registers_and_activates(self, tmp_path: Path) -> None:
        plugin_file = tmp_path / "valid_plugin.py"
        plugin_file.write_bytes(

                b"from robot_optimizer_core.infrastructure.plugins.manager import Plugin, PluginMetadata\n"
                b"\n"
                b"class ValidPlugin(Plugin):\n"
                b"    @property\n"
                b"    def metadata(self) -> PluginMetadata:\n"
                b'        return PluginMetadata("valid_plugin", "1.0.0", "Valid test plugin", "Test")\n'
                b"\n"
                b"    def activate(self) -> None:\n"
                b"        self.is_active = True\n"
                b"\n"
                b"    def deactivate(self) -> None:\n"
                b"        self.is_active = False\n"

        )
        plugin_file.chmod(0o644)

        manager = ValidatedPluginManager()
        manager.load_plugin_from_file(plugin_file)

        assert "valid_plugin" in manager.plugins
        assert isinstance(manager.plugins["valid_plugin"], Plugin)
        assert manager.plugins["valid_plugin"].is_active is True

    def test_no_plugin_subclass_raises_plugin_error(self, tmp_path: Path) -> None:
        plugin_file = tmp_path / "no_subclass.py"
        plugin_file.write_bytes(b"x = 1\n")
        plugin_file.chmod(0o644)

        manager = ValidatedPluginManager()
        with pytest.raises(PluginError):
            manager.load_plugin_from_file(plugin_file)

    def test_force_true_emits_warning_and_skips_validation(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        plugin_file = tmp_path / "forced.py"
        plugin_file.write_bytes(b"import os\n")  # would be rejected by validator
        plugin_file.chmod(0o644)

        monkeypatch.setenv("ROBOT_OPTIMIZER_ALLOW_UNSAFE_PLUGINS", "1")
        manager = ValidatedPluginManager()
        with caplog.at_level(logging.WARNING, logger="robot_optimizer_core.infrastructure.plugins.manager"):
            with pytest.raises(PluginError):
                manager.load_plugin_from_file(plugin_file, bypass_validation=True)

        warning_messages = [
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        ]
        assert any(
            "bypass" in msg.lower() or "security" in msg.lower()
            for msg in warning_messages
        ), f"Expected bypass warning, got: {warning_messages}"

    def test_force_true_warning_includes_path(
        self,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        plugin_file = tmp_path / "forced.py"
        plugin_file.write_bytes(b"import os\n")
        plugin_file.chmod(0o644)

        monkeypatch.setenv("ROBOT_OPTIMIZER_ALLOW_UNSAFE_PLUGINS", "1")
        manager = ValidatedPluginManager()
        with caplog.at_level(logging.WARNING, logger="robot_optimizer_core.infrastructure.plugins.manager"):
            with pytest.raises(PluginError):
                manager.load_plugin_from_file(plugin_file, bypass_validation=True)

        warning_texts = " ".join(
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        )
        assert "forced.py" in warning_texts

    def test_trusted_hash_skips_security_validation(self, tmp_path: Path) -> None:
        plugin_file = tmp_path / "trusted.py"
        plugin_file.write_bytes(b"import os\n")  # would normally be rejected
        plugin_file.chmod(0o644)

        file_hash = hashlib.sha256(plugin_file.read_bytes()).hexdigest()
        manager = ValidatedPluginManager()
        manager.add_trusted_plugin_hash(file_hash)

        # Security validation is skipped; exec still fails with no Plugin subclass.
        # The error must NOT be a "security validation" error.
        with pytest.raises(PluginError) as exc_info:
            manager.load_plugin_from_file(plugin_file)

        assert "security validation" not in str(exc_info.value).lower()

    def test_add_trusted_hash_stored(self) -> None:
        manager = ValidatedPluginManager()
        manager.add_trusted_plugin_hash("deadbeef")
        assert "deadbeef" in manager.trusted_hashes

    def test_invalid_plugin_name_raises(self, tmp_path: Path) -> None:
        # Plugin with traversal attempt in metadata name.
        plugin_file = tmp_path / "traversal.py"
        plugin_file.write_bytes(

                b"from robot_optimizer_core.infrastructure.plugins.manager import Plugin, PluginMetadata\n"
                b"\n"
                b"class TraversalPlugin(Plugin):\n"
                b"    @property\n"
                b"    def metadata(self) -> PluginMetadata:\n"
                b"        return PluginMetadata('../evil', '1.0.0', 'Bad name', 'Test')\n"
                b"\n"
                b"    def activate(self) -> None:\n"
                b"        self.is_active = True\n"
                b"\n"
                b"    def deactivate(self) -> None:\n"
                b"        self.is_active = False\n"

        )
        plugin_file.chmod(0o644)

        manager = ValidatedPluginManager()
        file_hash = hashlib.sha256(plugin_file.read_bytes()).hexdigest()
        manager.add_trusted_plugin_hash(file_hash)

        with pytest.raises(PluginError) as exc_info:
            manager.load_plugin_from_file(plugin_file)

        error_message = str(exc_info.value).lower()
        assert "name" in error_message
        assert "../evil" in error_message


@pytest.mark.unit
class TestGetPluginRegistry:
    def test_returns_registry_instance(self) -> None:
        assert isinstance(get_plugin_registry(), PluginRegistry)

    def test_returns_same_instance_on_repeated_calls(self) -> None:
        r1 = get_plugin_registry()
        r2 = get_plugin_registry()
        assert r1 is r2


@pytest.mark.unit
class TestDeprecatedForceShim:
    def test_load_plugin_from_file_force_emits_deprecation_warning(
        self, tmp_path: Path
    ) -> None:
        plugin_file = tmp_path / "shim_test.py"
        plugin_file.write_bytes(b"import os\n")
        plugin_file.chmod(0o644)

        manager = ValidatedPluginManager()
        import warnings
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with pytest.raises(PluginError):
                manager.load_plugin_from_file_force(plugin_file)

        assert any(issubclass(w.category, DeprecationWarning) for w in caught)
        assert any("deprecated" in str(w.message).lower() for w in caught)


# ---------------------------------------------------------------------------
# contribute_analyzers hook
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestContributeAnalyzers:
    """Tests for the Plugin.contribute_analyzers() → registry wiring."""

    def _make_valid_plugin_file(self, tmp_path: Path, extra_body: str = "") -> Path:
        """Write a minimal valid plugin file to *tmp_path*."""
        plugin_file = tmp_path / "contrib_plugin.py"
        plugin_file.write_bytes(
            b"from robot_optimizer_core.infrastructure.plugins.manager import Plugin, PluginMetadata\n"
            b"from robot_optimizer_core.application.analyzers.base import BaseAnalyzer\n"
            b"from robot_optimizer_core.domain.entities.test_file import TestFile\n"
            b"\n"
            b"class _ContribAnalyzer(BaseAnalyzer):\n"
            b"    @property\n"
            b"    def name(self): return 'contrib_analyzer'\n"
            b"    @property\n"
            b"    def description(self): return 'contributed'\n"
            b"    def analyze(self, test_file): return []\n"
            b"\n"
            b"class ContribPlugin(Plugin):\n"
            b"    @property\n"
            b"    def metadata(self):\n"
            b"        return PluginMetadata('contrib_plugin', '1.0.0', 'Contrib', 'Test')\n"
            b"    def activate(self): self.is_active = True\n"
            b"    def deactivate(self): self.is_active = False\n"
            + extra_body.encode()
        )
        plugin_file.chmod(0o644)
        return plugin_file

    def test_default_contribute_analyzers_returns_empty(self) -> None:
        """Plugin base class contribute_analyzers() returns [] by default."""
        plugin = _MinimalPlugin()
        assert plugin.contribute_analyzers() == []

    def test_register_contributed_analyzers_no_op_on_empty(self) -> None:
        """_register_contributed_analyzers does nothing when plugin contributes nothing."""
        manager = ValidatedPluginManager()
        plugin = _MinimalPlugin()
        plugin.activate()
        manager._register_contributed_analyzers(plugin)  # must not raise

    def test_register_contributed_analyzers_skips_non_base_analyzer(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Non-BaseAnalyzer types contributed by a plugin are skipped with a warning."""
        _MANAGER_LOGGER = "robot_optimizer_core.infrastructure.plugins.manager"

        class _BadPlugin(_MinimalPlugin):
            def contribute_analyzers(self) -> list:
                return [object]  # not a BaseAnalyzer

        manager = ValidatedPluginManager()
        plugin = _BadPlugin()
        plugin.activate()
        with caplog.at_level(logging.WARNING, logger=_MANAGER_LOGGER):
            manager._register_contributed_analyzers(plugin)
        assert any("non-BaseAnalyzer" in r.message for r in caplog.records)

    def test_register_contributed_analyzers_logs_on_exception(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """If contribute_analyzers() raises, a warning is logged and execution continues."""
        _MANAGER_LOGGER = "robot_optimizer_core.infrastructure.plugins.manager"

        class _ExplodingPlugin(_MinimalPlugin):
            def contribute_analyzers(self) -> list:
                raise RuntimeError("boom")

        manager = ValidatedPluginManager()
        plugin = _ExplodingPlugin()
        plugin.activate()
        with caplog.at_level(logging.WARNING, logger=_MANAGER_LOGGER):
            manager._register_contributed_analyzers(plugin)  # must not propagate
        assert any("boom" in r.message for r in caplog.records)

    def test_register_contributed_analyzers_success_path(self) -> None:
        """A valid BaseAnalyzer contributed by a plugin is registered in the registry."""
        from robot_optimizer_core.application.analyzers.base import BaseAnalyzer
        from robot_optimizer_core.domain.entities.test_file import TestFile as TF

        class _ContribAnalyzer(BaseAnalyzer):
            @property
            def name(self) -> str:
                return "_contrib_test_analyzer"

            @property
            def description(self) -> str:
                return "contributed by test plugin"

            def analyze(self, test_file: TF) -> list:
                return []

        class _ContribPlugin(_MinimalPlugin):
            def contribute_analyzers(self) -> list:
                return [_ContribAnalyzer]

        manager = ValidatedPluginManager()
        plugin = _ContribPlugin()
        plugin.activate()
        manager._register_contributed_analyzers(plugin)

        from robot_optimizer_core.application.analyzers.registry import (
            get_analyzer_registry,
        )
        registry = get_analyzer_registry()
        assert "_contrib_test_analyzer" in registry.list()

    def test_register_contributed_analyzers_registry_failure_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """If the registry cannot be accessed, a warning is logged and execution continues."""
        from unittest.mock import patch
        _MANAGER_LOGGER = "robot_optimizer_core.infrastructure.plugins.manager"

        from robot_optimizer_core.application.analyzers.base import BaseAnalyzer
        from robot_optimizer_core.domain.entities.test_file import TestFile as TF

        class _GoodAnalyzer(BaseAnalyzer):
            @property
            def name(self) -> str:
                return "_good_contrib"

            @property
            def description(self) -> str:
                return "good"

            def analyze(self, test_file: TF) -> list:
                return []

        class _GoodPlugin(_MinimalPlugin):
            def contribute_analyzers(self) -> list:
                return [_GoodAnalyzer]

        manager = ValidatedPluginManager()
        plugin = _GoodPlugin()
        plugin.activate()

        with patch(
            "robot_optimizer_core.application.analyzers.registry.get_analyzer_registry",
            side_effect=RuntimeError("registry unavailable"),
        ), caplog.at_level(logging.WARNING, logger=_MANAGER_LOGGER):
            manager._register_contributed_analyzers(plugin)  # must not propagate

        assert any("registry" in r.message.lower() for r in caplog.records)
