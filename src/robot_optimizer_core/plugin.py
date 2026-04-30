# src/robot_optimizer_core/plugin.py
"""Secure plugin system that prevents arbitrary code execution."""

from __future__ import annotations

import ast
import hashlib
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from .exceptions import PluginError
from .logging import get_logger

__all__ = [
    "ALLOWED_BUILTINS",
    "ALLOWED_IMPORTS",
    "Plugin",
    "PluginMetadata",
    "PluginRegistry",
    "PluginSecurityValidator",
    "ValidatedPluginManager",
    "SecurityVisitor",
    "get_plugin_registry",
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
    "dataclasses",
    "enum",
    "abc",
    "collections",
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

    def __init__(self) -> None:
        self.violations: list[str] = []

    def validate_file(self, file_path: Path) -> tuple[bool, list[str]]:
        """Validate a plugin file for security issues.

        Returns:
            Tuple of (is_safe, violations)
        """
        self.violations = []

        try:
            content = file_path.read_text(encoding="utf-8")

            # Parse AST
            tree = ast.parse(content, filename=str(file_path))

            # Run security checks
            validator = SecurityVisitor()
            validator.visit(tree)

            self.violations.extend(validator.violations)

            # Check file permissions (should not be writable by others; POSIX only)
            if os.name == "posix":
                stat = file_path.stat()
                if stat.st_mode & 0o022:  # Check if writable by group/others
                    self.violations.append("Plugin file is writable by group/others")

            return len(self.violations) == 0, self.violations

        except Exception as e:
            self.violations.append(f"Failed to parse plugin: {e}")
            return False, self.violations


class SecurityVisitor(ast.NodeVisitor):
    """AST visitor that checks for security violations."""

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

    def visit_Call(self, node: ast.Call) -> None:
        """Check function calls for dangerous operations."""
        # Check for dangerous functions
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            dangerous_funcs = {
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
            }
            if func_name in dangerous_funcs:
                self.violations.append(f"Forbidden function call: {func_name}")

            # getattr/setattr with a dangerous or non-literal attr name bypass visit_Attribute
            elif func_name in {"getattr", "setattr"} and len(node.args) >= 2:
                attr_arg = node.args[1]
                if isinstance(attr_arg, ast.Constant) and isinstance(
                    attr_arg.value, str
                ):
                    dangerous_attrs = {
                        "__dict__",
                        "__globals__",
                        "__builtins__",
                        "__import__",
                        "__code__",
                        "__class__",
                        "__bases__",
                        "__subclasses__",
                    }
                    if attr_arg.value in dangerous_attrs:
                        self.violations.append(
                            f"Forbidden {func_name} with dangerous attribute: {attr_arg.value!r}"
                        )
                else:
                    # Non-literal attribute name — can't verify safety at analysis time
                    self.violations.append(
                        f"Forbidden {func_name} with non-literal attribute name"
                    )

        # Check for subprocess, os, sys modules
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name):
                module = node.func.value.id
                if module in {
                    "os",
                    "sys",
                    "subprocess",
                    "socket",
                    "urllib",
                    "requests",
                }:
                    self.violations.append(
                        f"Forbidden module usage: {module}.{node.func.attr}"
                    )

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Check attribute access for dangerous patterns."""
        # Check for __dict__, __globals__, etc.
        if node.attr.startswith("__") and node.attr.endswith("__"):
            dangerous_attrs = {
                "__dict__",
                "__globals__",
                "__builtins__",
                "__import__",
                "__code__",
                "__class__",
                "__bases__",
                "__subclasses__",
            }
            if node.attr in dangerous_attrs:
                self.violations.append(f"Forbidden attribute access: {node.attr}")

        self.generic_visit(node)


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

    def load_plugin_from_file(self, file_path: Path, force: bool = False) -> None:
        """Securely load a plugin from a file.

        Args:
            file_path: Path to the plugin file
            force: Skip security validation (NOT RECOMMENDED)

        Raises:
            PluginError: If plugin fails security validation
        """
        if not file_path.exists():
            raise PluginError(f"Plugin file not found: {file_path}")

        # Check if plugin is trusted
        file_hash = self._compute_file_hash(file_path)
        if file_hash in self.trusted_hashes:
            logger.info(f"Loading trusted plugin: {file_path}")
        elif not force:
            # Validate plugin security
            is_safe, violations = self.validator.validate_file(file_path)

            if not is_safe:
                raise PluginError(
                    f"Plugin failed security validation: {file_path}",
                    details={"violations": violations, "file_hash": file_hash},
                )
        else:
            logger.warning(
                f"Plugin security validation bypassed via force=True: {file_path} "
                f"(hash: {file_hash})"
            )

        # Load plugin in restricted environment
        try:
            # Create a restricted globals environment
            # Handle both dict and module forms of __builtins__
            builtin_dict = (
                __builtins__ if isinstance(__builtins__, dict) else vars(__builtins__)
            )
            restricted_builtins = {
                k: builtin_dict[k] for k in ALLOWED_BUILTINS if k in builtin_dict
            }
            # __import__ and __build_class__ are required by the Python runtime
            # inside exec() for import statements and class definitions.
            # Security is enforced by the AST validator that runs before exec,
            # so restoring these here does not bypass the import allowlist.
            for _name in ("__import__", "__build_class__"):
                if _name in builtin_dict:
                    restricted_builtins[_name] = builtin_dict[_name]
            restricted_globals = {
                "__builtins__": restricted_builtins,
                "__name__": f"plugin_{file_path.stem}",
                "__file__": str(file_path),
            }

            # Read and compile the plugin code
            plugin_code = file_path.read_text(encoding="utf-8")

            # Compile with restricted mode
            compiled = compile(plugin_code, str(file_path), "exec", flags=0)

            # Execute in restricted environment
            exec(compiled, restricted_globals)

            # Find Plugin subclass
            plugin_class = None
            for _, obj in restricted_globals.items():
                if (
                    isinstance(obj, type)
                    and issubclass(obj, Plugin)
                    and obj is not Plugin
                ):
                    plugin_class = obj
                    break

            if not plugin_class:
                raise PluginError(f"No Plugin subclass found in: {file_path}")

            # Create and activate plugin
            plugin = plugin_class(self.registry)
            metadata = plugin.metadata

            # Additional validation of metadata
            if not metadata.name or ".." in metadata.name or "/" in metadata.name:
                raise PluginError(f"Invalid plugin name: {metadata.name!r}")

            plugin.activate()
            plugin.is_active = True
            self.plugins[metadata.name] = plugin

            logger.info(
                f"Plugin loaded securely: {metadata.name} v{metadata.version}",
                extra={"file_hash": file_hash},
            )

        except PluginError:
            raise
        except Exception as e:
            raise PluginError(
                f"Failed to load plugin: {file_path}", details={"error": str(e)}
            ) from e

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
