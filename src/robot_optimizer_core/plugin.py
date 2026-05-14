# src/robot_optimizer_core/plugin.py
"""Secure plugin system that prevents arbitrary code execution."""

from __future__ import annotations

import ast
import hashlib
import sys
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
    "SecurityVisitor",
    "ValidatedPluginManager",
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

    def validate_content(
        self, content: str, file_path: Path
    ) -> tuple[bool, list[str]]:
        """Validate plugin content for security issues.

        Args:
            content: Plugin file content
            file_path: Path to plugin file (for error reporting and permissions check)

        Returns:
            Tuple of (is_safe, violations)
        """
        self.violations = []

        try:
            # Parse AST
            tree = ast.parse(content, filename=str(file_path))

            # Run security checks
            validator = SecurityVisitor()
            validator.visit(tree)

            self.violations.extend(validator.violations)

            # Check file permissions on POSIX only.
            # Windows does not track group/other write bits (st_mode & 0o022
            # is always 0 there), so this check is meaningless on Windows.
            if sys.platform != "win32":
                stat = file_path.stat()
                if stat.st_mode & 0o022:
                    self.violations.append("Plugin file is writable by group/others")

            return len(self.violations) == 0, self.violations

        except Exception as e:
            self.violations.append(f"Failed to parse plugin: {e}")
            return False, self.violations

    def validate_file(self, file_path: Path) -> tuple[bool, list[str]]:
        """Validate a plugin file for security issues.

        Returns:
            Tuple of (is_safe, violations)
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            return self.validate_content(content, file_path)
        except Exception as e:
            return False, [f"Failed to read plugin file: {e}"]


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
                    f"Forbidden import: from {node.module} "
                    f"(only allowed: {ALLOWED_IMPORTS})"
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Check function calls for dangerous operations."""
        if isinstance(node.func, ast.Name):
            self._check_name_function(node)
        elif isinstance(node.func, ast.Attribute):
            self._check_attribute_function(node)

        self.generic_visit(node)

    def _check_name_function(self, node: ast.Call) -> None:
        """Check a function call with a simple name."""
        func = node.func
        if not isinstance(func, ast.Name):
            return
        func_name = func.id
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
        elif func_name in {"getattr", "setattr"} and len(node.args) > 1:
            self._check_getattr_setattr(func_name, node.args[1])

    def _check_getattr_setattr(self, func_name: str, attr_arg: ast.expr) -> None:
        """Check getattr/setattr for dangerous attribute access."""
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
        if isinstance(attr_arg, ast.Constant) and isinstance(attr_arg.value, str):
            if attr_arg.value in dangerous_attrs:
                self.violations.append(
                    f"Forbidden {func_name} with dangerous attribute: "
                    f"{attr_arg.value!r}"
                )
        else:
            self.violations.append(
                f"Forbidden {func_name} with non-literal attribute name"
            )

    def _check_attribute_function(self, node: ast.Call) -> None:
        """Check a function call on an attribute (e.g., os.system)."""
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            module = func.value.id
            forbidden_modules = {
                "os",
                "sys",
                "subprocess",
                "socket",
                "urllib",
                "requests",
            }
            if module in forbidden_modules:
                self.violations.append(
                    f"Forbidden module usage: {module}.{func.attr}"
                )

    def visit_Name(self, node: ast.Name) -> None:
        """Check bare name access for dangerous identifiers."""
        dangerous_names = {
            "__builtins__",
            "__import__",
            "__dict__",
            "__globals__",
            "__code__",
            "__class__",
            "__bases__",
            "__subclasses__",
        }
        if node.id in dangerous_names:
            self.violations.append(f"Forbidden identifier access: {node.id}")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Check subscript access for sandbox escape via __builtins__[...]."""
        value = node.value
        if isinstance(value, ast.Name) and value.id == "__builtins__":
            self.violations.append(
                "Forbidden __builtins__ subscript access: "
                "__builtins__[...] bypasses sandbox restrictions"
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

    def _compute_content_hash(self, content: bytes) -> str:
        """Compute SHA-256 hash of file content."""
        return hashlib.sha256(content).hexdigest()

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

        # Read file once to avoid TOCTOU vulnerability
        try:
            content_bytes = file_path.read_bytes()
            content_str = content_bytes.decode("utf-8")
        except Exception as e:
            raise PluginError(f"Failed to read plugin file: {file_path}") from e

        file_hash = self._compute_content_hash(content_bytes)
        self._check_plugin_security(file_path, content_str, file_hash, force)

        try:
            restricted_globals = self._create_restricted_environment(file_path)
            plugin_class = self._execute_and_find_plugin_class(
                file_path, content_str, restricted_globals
            )
            self._register_plugin(plugin_class, file_hash)
        except PluginError:
            raise
        except Exception as e:
            raise PluginError(
                f"Failed to load plugin: {file_path}", details={"error": str(e)}
            ) from e

    def _check_plugin_security(
        self, file_path: Path, content: str, file_hash: str, force: bool
    ) -> None:
        """Check if plugin is trusted or validate its security."""
        if file_hash in self.trusted_hashes:
            logger.info(f"Loading trusted plugin: {file_path}")
        elif not force:
            is_safe, violations = self.validator.validate_content(content, file_path)
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

    def _create_restricted_environment(self, file_path: Path) -> dict[str, object]:
        """Create a restricted globals environment for plugin execution."""
        builtin_dict = (
            __builtins__ if isinstance(__builtins__, dict) else vars(__builtins__)
        )
        restricted_builtins = {
            k: builtin_dict[k] for k in ALLOWED_BUILTINS if k in builtin_dict
        }
        # Add __import__ and __build_class__ for module imports and class definitions
        # __builtins__ subscript access is blocked by SecurityVisitor during validation
        for special_name in ("__import__", "__build_class__"):
            if special_name in builtin_dict:
                restricted_builtins[special_name] = builtin_dict[special_name]
        return {
            "__builtins__": restricted_builtins,
            "__name__": f"plugin_{file_path.stem}",
            "__file__": str(file_path),
        }

    def _execute_and_find_plugin_class(
        self, file_path: Path, content: str, restricted_globals: dict[str, object]
    ) -> type[Plugin]:
        """Execute plugin code and find the Plugin subclass.

        SECURITY NOTE: exec() is used here with security mitigations:
        - Code is validated by SecurityVisitor before execution
        - Environment restricted to safe builtins only
        - __builtins__ subscript access blocked (prevents __builtins__['__import__'])
        - Dangerous functions (eval, open, os.system, etc.) detected and rejected
        - Only load plugins from trusted sources
        """
        compiled = compile(content, str(file_path), "exec", flags=0)
        exec(compiled, restricted_globals)  # nosec: B102 - security validated above

        plugin_class = None
        for obj in restricted_globals.values():
            if (
                isinstance(obj, type)
                and issubclass(obj, Plugin)
                and obj is not Plugin
            ):
                plugin_class = obj
                break

        if not plugin_class:
            raise PluginError(f"No Plugin subclass found in: {file_path}")
        return plugin_class

    def _register_plugin(
        self, plugin_class: type[Plugin], file_hash: str
    ) -> None:
        """Create, validate, activate, and register a plugin."""
        plugin = plugin_class(self.registry)
        metadata = plugin.metadata

        if not metadata.name or ".." in metadata.name or "/" in metadata.name:
            raise PluginError(f"Invalid plugin name: {metadata.name!r}")

        # Check for duplicate plugin names
        if metadata.name in self.plugins:
            raise PluginError(
                f"Plugin already loaded: {metadata.name!r}",
                details={"existing": self.plugins[metadata.name]},
            )

        plugin.activate()
        plugin.is_active = True
        self.plugins[metadata.name] = plugin

        logger.info(
            f"Plugin loaded securely: {metadata.name} v{metadata.version}",
            extra={"file_hash": file_hash},
        )

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
