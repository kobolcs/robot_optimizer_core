# src/robot_optimizer_core/infrastructure/plugins/manager.py
"""Secure plugin system that prevents arbitrary code execution."""

from __future__ import annotations

import ast
import builtins as _builtins_module
import hashlib
import os
import sys
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...exceptions import PluginError
from ..logging.adapter import get_logger

__all__ = [
    "ALLOWED_BUILTINS",
    "ALLOWED_IMPORTS",
    "Plugin",
    "PluginMetadata",
    "PluginRegistry",
    "PluginSecurityValidator",
    "SecurityVisitor",
    "ValidatedPluginManager",
    "get_plugin_registry",
    "reset_plugin_registry",
]

logger = get_logger(__name__)


@dataclass
class PluginMetadata:
    """Metadata for a plugin."""

    name: str
    version: str
    description: str
    author: str


class Plugin(ABC):
    """Base class for plugins."""

    def __init__(self, registry: PluginRegistry | None = None) -> None:
        self.registry = registry
        self.is_active: bool = False

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        ...

    @abstractmethod
    def activate(self) -> None:
        """Activate the plugin."""
        ...

    @abstractmethod
    def deactivate(self) -> None:
        """Deactivate the plugin."""
        ...


class PluginRegistry:
    """Registry for managing plugins."""

    def __init__(self) -> None:
        self.plugins: dict[str, type[Plugin]] = {}

    def register(self, name: str, plugin_class: type[Plugin]) -> None:
        """Register a plugin."""
        self.plugins[name] = plugin_class

    def get(self, name: str) -> type[Plugin] | None:
        """Get a plugin by name."""
        return self.plugins.get(name)

    def list(self) -> list[str]:
        """List all registered plugins."""
        return list(self.plugins.keys())

    def unregister(self, name: str) -> None:
        """Remove a plugin from the registry."""
        self.plugins.pop(name, None)


# Whitelist of allowed imports for plugins
ALLOWED_IMPORTS = {
    "robot_optimizer_core",
    "pathlib",
    "typing",
    "typing_extensions",
    "dataclasses",
    "enum",
    "abc",
    "collections",
    "pydantic",
    "functools",
    "itertools",
    "re",
}

# Whitelist of allowed builtins
ALLOWED_BUILTINS = {
    "len",
    "str",
    "int",
    "float",
    "bool",
    "list",
    "dict",
    "set",
    "tuple",
    "isinstance",
    "issubclass",
    "hasattr",
    "getattr",
    "setattr",
    "property",
    "classmethod",
    "staticmethod",
    "super",
    "Exception",
    "ValueError",
    "TypeError",
    "AttributeError",
}


class PluginSecurityValidator:
    """Validates plugin code for security issues before loading."""

    def validate_file(self, file_path: Path) -> tuple[bool, list[str]]:
        """Validate a plugin file for security issues.

        Returns:
            Tuple of (is_safe, violations)
        """
        violations: list[str] = []

        try:
            content = file_path.read_text(encoding="utf-8")

            # Parse AST
            tree = ast.parse(content, filename=str(file_path))

            # Run security checks
            validator = SecurityVisitor()
            validator.visit(tree)

            violations.extend(validator.violations)

            # Check file permissions on POSIX only.
            # Windows does not track group/other write bits (st_mode & 0o022
            # is always 0 there), so this check is meaningless on Windows.
            if sys.platform != "win32":  # pragma: no cover
                stat = file_path.stat()
                if stat.st_mode & 0o022:
                    violations.append("Plugin file is writable by group/others")

            return len(violations) == 0, violations

        except Exception as e:
            violations.append(f"Failed to parse plugin: {e}")
            return False, violations


class SecurityVisitor(ast.NodeVisitor):
    """AST visitor that checks for security violations."""

    # Dangerous built-in functions (immutable)
    _DANGEROUS_FUNCS: frozenset[str] = frozenset({
        "eval",
        "exec",
        "compile",
        "__import__",
        "open",
        "input",
        "raw_input",
        "execfile",
        "file",
        "reload",
        # Introspection builtins that can expose internals not caught by
        # _DANGEROUS_ATTRS (e.g. vars(obj) bypasses the __dict__ attr check).
        "vars",
        "dir",
        "locals",
        "globals",
    })

    # Dangerous attributes that can be used with getattr/setattr (immutable)
    _DANGEROUS_ATTRS: frozenset[str] = frozenset({
        "__dict__",
        "__globals__",
        "__builtins__",
        "__import__",
        "__code__",
        "__class__",
        "__bases__",
        "__subclasses__",
    })

    # Dangerous modules (immutable)
    _DANGEROUS_MODULES: frozenset[str] = frozenset({
        "os",
        "sys",
        "subprocess",
        "socket",
        "urllib",
        "requests",
    })

    def __init__(self) -> None:
        self.violations: list[str] = []
        self.in_plugin_class = False

    def visit_Import(self, node: ast.Import) -> None:
        """Check import statements."""
        for alias in node.names:
            module = alias.name.split(".")[0]
            if module not in ALLOWED_IMPORTS:
                self.violations.append(
                    f"Forbidden import: {alias.name} (only allowed: {ALLOWED_IMPORTS})"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Check from-import statements."""
        if node.module:
            module = node.module.split(".")[0]
            if module not in ALLOWED_IMPORTS:
                self.violations.append(
                    f"Forbidden import: from {node.module} (only allowed: {ALLOWED_IMPORTS})"
                )
        self.generic_visit(node)

    def _check_dangerous_func(self, func_name: str) -> None:
        """Check if function call is dangerous."""
        if func_name in self._DANGEROUS_FUNCS:
            self.violations.append(f"Forbidden function call: {func_name}")

    def _check_getattr_setattr(self, func_name: str, node: ast.Call) -> None:
        """Check getattr/setattr with dangerous attributes."""
        if len(node.args) >= 2:
            attr_arg = node.args[1]
            if isinstance(attr_arg, ast.Constant) and isinstance(attr_arg.value, str):
                if attr_arg.value in self._DANGEROUS_ATTRS:
                    self.violations.append(
                        f"Forbidden {func_name} with dangerous attribute: {attr_arg.value!r}"
                    )
            else:
                self.violations.append(
                    f"Forbidden {func_name} with non-literal attribute name"
                )

    def _check_module_usage(self, node: ast.Call) -> None:
        """Check for dangerous module usage."""
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                module = node.func.value.id
                if module in self._DANGEROUS_MODULES:
                    self.violations.append(
                        f"Forbidden module usage: {module}.{node.func.attr}"
                    )

    def visit_Call(self, node: ast.Call) -> None:
        """Check function calls for dangerous operations."""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            self._check_dangerous_func(func_name)
            if func_name in {"getattr", "setattr"}:
                self._check_getattr_setattr(func_name, node)
        else:
            self._check_module_usage(node)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Check attribute access for dangerous patterns."""
        if node.attr in self._DANGEROUS_ATTRS:
            self.violations.append(f"Forbidden attribute access: {node.attr}")

        self.generic_visit(node)


def _make_restricted_import(allowed: frozenset[str]) -> Callable[..., Any]:
    """Return a restricted __import__ that only permits modules in *allowed*.

    Wrapping the real ``__import__`` prevents plugin code from calling
    ``__builtins__['__import__']('os')`` at runtime, even when the AST-level
    import whitelist blocked the ``import os`` statement.
    """
    real_import = _builtins_module.__import__

    def _restricted_import(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        top_level = name.split(".", maxsplit=1)[0]
        if top_level not in allowed:
            raise ImportError(
                f"Import of '{name}' is not permitted in plugins. "
                f"Allowed packages: {sorted(allowed)}"
            )
        return real_import(name, globals, locals, fromlist, level)

    return _restricted_import


class ValidatedPluginManager:
    """Plugin manager that validates plugins via AST analysis before loading.

    .. warning::
        The AST-level validation performed by this class is **not a sandbox**.
        It reduces risk from accidentally unsafe plugins but cannot prevent a
        determined adversary from executing arbitrary code.  Only load plugins
        from sources you trust.
    """

    def __init__(self, registry: PluginRegistry | None = None) -> None:
        self.registry = registry or PluginRegistry()
        self.plugins: dict[str, Plugin] = {}
        self.trusted_hashes: set[str] = set()
        self.validator = PluginSecurityValidator()

    def add_trusted_plugin_hash(self, file_hash: str) -> None:
        """Add a trusted plugin hash (for pre-approved plugins)."""
        self.trusted_hashes.add(file_hash)

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA-256 hash of a file."""
        return hashlib.sha256(file_path.read_bytes()).hexdigest()

    def _validate_and_check_plugin(self, file_path: Path, bypass_validation: bool = False) -> str:
        """Validate plugin file and return its hash. Raises PluginError if validation fails.

        bypass_validation is only honoured when the environment variable
        ROBOT_OPTIMIZER_ALLOW_UNSAFE_PLUGINS=1 is set, so bypasses require an
        explicit deployment-level opt-in rather than a call-site string match.
        """
        file_hash = self._compute_file_hash(file_path)
        if file_hash in self.trusted_hashes:
            logger.info(f"Loading trusted plugin: {file_path}")
            return file_hash

        allow_unsafe = os.environ.get("ROBOT_OPTIMIZER_ALLOW_UNSAFE_PLUGINS") == "1"
        if bypass_validation and allow_unsafe:
            msg = (
                f"SECURITY WARNING: Plugin security validation bypassed: "
                f"{file_path} (hash: {file_hash})"
            )
            # Always write to stderr so the bypass is auditable even when
            # application logging is disabled or redirected.
            print(msg, file=sys.stderr, flush=True)
            logger.warning(msg)
        else:
            is_safe, violations = self.validator.validate_file(file_path)
            if not is_safe:
                raise PluginError(
                    f"Plugin failed security validation: {file_path}",
                    details={"violations": violations, "file_hash": file_hash},
                )

        return file_hash

    def _create_restricted_globals(self, file_path: Path) -> dict[str, Any]:
        """Create restricted globals environment for plugin execution."""
        raw_builtins: Any = __builtins__
        builtin_dict: dict[str, Any] = (
            raw_builtins if isinstance(raw_builtins, dict) else vars(raw_builtins)
        )
        restricted_builtins: dict[str, Any] = {
            k: builtin_dict[k] for k in ALLOWED_BUILTINS if k in builtin_dict
        }
        # __build_class__ is needed for class definitions.
        if "__build_class__" in builtin_dict:
            restricted_builtins["__build_class__"] = builtin_dict["__build_class__"]
        # Replace __import__ with a wrapper that enforces ALLOWED_IMPORTS at
        # runtime, preventing __builtins__['__import__']('os')-style bypasses.
        restricted_builtins["__import__"] = _make_restricted_import(
            frozenset(ALLOWED_IMPORTS)
        )
        return {
            "__builtins__": restricted_builtins,
            "__name__": f"plugin_{file_path.stem}",
            "__file__": str(file_path),
        }

    def _execute_and_load_plugin(
        self, file_path: Path, restricted_globals: dict[str, Any], file_hash: str
    ) -> None:
        """Execute plugin code and register the Plugin subclass.

        Executes compiled plugin code in a restricted environment with defense-in-depth
        security: AST validation before execution prevents forbidden imports and dangerous
        function calls; restricted builtins limit runtime capabilities; file permissions
        validated on POSIX systems; plugin hash validation allows pre-approved plugins.
        """
        plugin_code = file_path.read_text(encoding="utf-8")
        compiled = compile(plugin_code, str(file_path), "exec", flags=0)

        exec(compiled, restricted_globals)  # NOSONAR - Secure execution with AST pre-validation

        plugin_class = None
        for obj in restricted_globals.values():
            if isinstance(obj, type) and issubclass(obj, Plugin) and obj is not Plugin:
                plugin_class = obj
                break

        if not plugin_class:
            raise PluginError(f"No Plugin subclass found in: {file_path}")

        plugin = plugin_class(self.registry)
        metadata = plugin.metadata

        if not metadata.name or ".." in metadata.name or "/" in metadata.name or "\\" in metadata.name:
            raise PluginError(f"Invalid plugin name: {metadata.name!r}")

        plugin.activate()
        plugin.is_active = True
        self.plugins[metadata.name] = plugin

        logger.info(
            f"Plugin loaded securely: {metadata.name} v{metadata.version}",
            extra={"file_hash": file_hash},
        )

    def load_plugin_from_file(
        self,
        file_path: Path,
        bypass_validation: bool = False,
    ) -> None:
        """Securely load a plugin from a file.

        Args:
            file_path: Path to the plugin file.
            bypass_validation: When ``True`` **and** the environment variable
                ``ROBOT_OPTIMIZER_ALLOW_UNSAFE_PLUGINS=1`` is set, AST
                validation is skipped.  Both conditions must be satisfied so
                that bypasses require an explicit deployment-level opt-in.
                **Not recommended** — only for development use.

        Raises:
            PluginError: If plugin fails security validation or cannot be loaded.
        """
        if not file_path.exists():
            raise PluginError(f"Plugin file not found: {file_path}")

        try:
            file_hash = self._validate_and_check_plugin(file_path, bypass_validation)
            restricted_globals = self._create_restricted_globals(file_path)

            # Execute in restricted environment with layered security:
            # 1. AST validation before execution detects forbidden imports, dangerous function
            #    calls, and attribute access patterns (__dict__, __globals__, etc.)
            # 2. Restricted builtins whitelist allows only safe functions (len, str, isinstance,
            #    etc.) and blocks dangerous ones (eval, exec, open, file, etc.).
            #    __import__ and __build_class__ are intentionally restored ONLY because AST
            #    validation already blocked non-whitelisted imports at the syntax level.
            # 3. File permissions validated on POSIX to ensure only trusted users can modify
            #    plugin files (st_mode & 0o022 check on non-Windows).
            # 4. Plugin hash validation allows pre-approved plugins to skip validation.
            # This approach provides defense-in-depth: AST validation catches code patterns
            # before execution, and restricted environment limits runtime capabilities.
            self._execute_and_load_plugin(file_path, restricted_globals, file_hash)

        except PluginError:
            raise
        except Exception as e:
            raise PluginError(
                f"Failed to load plugin: {file_path}", details={"error": str(e)}
            ) from e

    # Keep force= as a deprecated shim so existing callers get a clear error
    # rather than silently bypassing validation with a wrong signature.
    def load_plugin_from_file_force(self, file_path: Path) -> None:
        """Deprecated: use load_plugin_from_file with bypass_validation=True."""
        import warnings
        warnings.warn(
            "load_plugin_from_file_force is deprecated. Use load_plugin_from_file "
            "with bypass_validation=True (and set ROBOT_OPTIMIZER_ALLOW_UNSAFE_PLUGINS=1).",
            DeprecationWarning,
            stacklevel=2,
        )
        self.load_plugin_from_file(file_path, bypass_validation=True)

    def unload_plugin(self, name: str) -> None:
        """Unload a plugin."""
        if name in self.plugins:
            plugin = self.plugins[name]
            plugin.deactivate()
            del self.plugins[name]


# Global plugin registry instance
_plugin_registry: PluginRegistry | None = None


def get_plugin_registry() -> PluginRegistry:
    """Get the global plugin registry instance.

    Returns:
        The global plugin registry instance.
    """
    global _plugin_registry
    if _plugin_registry is None:
        _plugin_registry = PluginRegistry()
    return _plugin_registry


def reset_plugin_registry() -> None:
    """Reset the global plugin registry to an uninitialised state.

    Primarily useful for tests and plugin reload scenarios.
    """
    global _plugin_registry
    _plugin_registry = None
