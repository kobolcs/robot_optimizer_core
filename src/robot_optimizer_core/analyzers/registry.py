# src/robot_optimizer_core/analyzers/registry.py
"""Analyzer registry for managing and discovering analyzers.

This module provides the registry system that tracks all available
analyzers, including built-in and plugin-provided analyzers.

Example:
    Registering and using analyzers::

        from robot_optimizer_core.analyzers import register_analyzer, get_analyzer

        # Register a custom analyzer
        register_analyzer("custom", CustomAnalyzer)

        # Get analyzer instance
        analyzer = get_analyzer("custom")

        # List all available analyzers
        analyzers = list_analyzers()
"""

from __future__ import annotations

import builtins
from importlib.metadata import EntryPoint, entry_points
from typing import TYPE_CHECKING, Any, TypeAlias, cast

from ..di import get_container
from ..exceptions import PluginError
from ..logging import get_logger
from .base import BaseAnalyzer

if TYPE_CHECKING:
    AnalyzerClass: TypeAlias = type[BaseAnalyzer]

__all__ = [
    "AnalyzerRegistry",
    "get_analyzer",
    "get_analyzer_info",
    "get_analyzer_registry",
    "list_analyzers",
    "register_analyzer",
    "reset_registry",
]

logger = get_logger(__name__)


def _iter_analyzer_entry_points() -> list[EntryPoint]:
    """Return analyzer entry points for the canonical group."""
    eps: Any = entry_points()
    if hasattr(eps, "select"):
        return cast(
            "list[EntryPoint]",
            list(eps.select(group="robot_optimizer_core.analyzers")),
        )
    return cast(
        "list[EntryPoint]",
        list(eps.get("robot_optimizer_core.analyzers", [])),
    )


class AnalyzerRegistry:
    """Registry for managing analyzers.

    This registry tracks all available analyzers and provides
    methods for registration, discovery, and instantiation.

    Attributes:
        analyzers: Dictionary of registered analyzer classes.
        instances: Cache of analyzer instances.
        default_analyzers: List of analyzer names to use by default.
    """

    __slots__ = ("analyzers", "default_analyzers", "instances")

    def __init__(self) -> None:
        """Initialize the analyzer registry."""
        self.analyzers: dict[str, AnalyzerClass] = {}
        self.instances: dict[str, BaseAnalyzer] = {}
        self.default_analyzers: list[str] = [
            "dead_code",
            "sleep_detector",
            "hardcoded_value",
            "naming_convention",
            "setup_teardown",
            "tag_consistency",
            "test_documentation",
        ]

    def register(
        self, name: str, analyzer_class: AnalyzerClass, override: bool = False
    ) -> None:
        """Register an analyzer.

        Args:
            name: Unique name for the analyzer.
            analyzer_class: The analyzer class.
            override: Whether to override existing analyzer.

        Raises:
            PluginError: If analyzer already exists and override is False.
        """
        if name in self.analyzers and not override:
            raise PluginError(
                f"Analyzer already registered: {name}",
                plugin_name=name,
                plugin_type="analyzer",
            )

        # Validate it's a proper analyzer
        if not issubclass(analyzer_class, BaseAnalyzer):
            raise PluginError(
                f"Analyzer must inherit from BaseAnalyzer: {analyzer_class}",
                plugin_name=name,
                plugin_type="analyzer",
            )

        self.analyzers[name] = analyzer_class

        # Clear cached instance if overriding
        if override and name in self.instances:
            del self.instances[name]

        logger.info(
            "Analyzer registered",
            extra={
                "name": name,
                "class": analyzer_class.__name__,
                "override": override,
            },
        )

    def get(self, name: str) -> BaseAnalyzer:
        """Get an analyzer instance.

        This method returns a cached instance if available,
        otherwise creates a new instance.

        Args:
            name: Analyzer name.

        Returns:
            Analyzer instance.

        Raises:
            PluginError: If analyzer not found.
        """
        # Return cached instance
        if name in self.instances:
            return self.instances[name]

        # Check registered analyzers (built-in or plugin-provided via register_analyzer())
        if name not in self.analyzers:
            raise PluginError(
                f"Analyzer not found: {name}",
                plugin_name=name,
                plugin_type="analyzer",
                details={"available": self.list()},
            )

        instance = self.create(name)

        # Cache instance
        self.instances[name] = instance

        return instance

    def create(self, name: str) -> BaseAnalyzer:
        """Create a fresh analyzer instance without using the cache."""
        if name not in self.analyzers:
            raise PluginError(
                f"Analyzer not found: {name}",
                plugin_name=name,
                plugin_type="analyzer",
                details={"available": self.list()},
            )

        analyzer_class = self.analyzers[name]
        container = get_container()
        if container.has_service(f"analyzer.{name}"):
            return cast("BaseAnalyzer", container.resolve(f"analyzer.{name}"))
        return analyzer_class()

    def list(self) -> list[str]:
        """List all registered analyzer names.

        Returns:
            List of analyzer names.
        """
        return sorted(self.analyzers.keys())

    def get_info(self, name: str) -> dict[str, str]:
        """Get information about an analyzer.

        Args:
            name: Analyzer name.

        Returns:
            Dictionary with analyzer information.
        """
        analyzer = self.get(name)

        return {
            "name": analyzer.name,
            "description": analyzer.description,
            "version": analyzer.version,
            "class": analyzer.__class__.__name__,
            "module": analyzer.__class__.__module__,
            "supports_auto_fix": str(analyzer.supports_auto_fix),
            "tags": ", ".join(analyzer.tags) if analyzer.tags else "",
        }

    def get_default_analyzers(self) -> builtins.list[BaseAnalyzer]:
        """Get default analyzer instances.

        Returns:
            List of default analyzer instances.
        """
        return [self.get(name) for name in self.default_analyzers]

    def set_default_analyzers(self, names: builtins.list[str]) -> None:
        """Set the default analyzers.

        Args:
            names: List of analyzer names to use by default.
        """
        # Validate all names exist
        available = set(self.list())
        invalid: set[str] = set(names) - available
        if invalid:
            raise PluginError(
                f"Invalid analyzer names: {invalid}",
                plugin_type="analyzer",
                details={"available": sorted(available)},
            )

        self.default_analyzers = names

    def clear_cache(self) -> None:
        """Clear the instance cache.

        This forces new instances to be created on next access.
        """
        self.instances.clear()

    def unregister(self, name: str) -> None:
        """Unregister an analyzer.

        Args:
            name: Analyzer name to remove.
        """
        self.analyzers.pop(name, None)
        self.instances.pop(name, None)


# Global registry instance
_analyzer_registry: AnalyzerRegistry | None = None


def get_analyzer_registry() -> AnalyzerRegistry:
    """Get the global analyzer registry.

    Returns:
        The global analyzer registry instance.
    """
    global _analyzer_registry
    if _analyzer_registry is None:
        _analyzer_registry = AnalyzerRegistry()
        _register_built_in_analyzers(_analyzer_registry)
        _register_entry_point_analyzers(_analyzer_registry)
    return _analyzer_registry


def reset_registry() -> None:
    """Reset the global analyzer registry to an uninitialized state.

    Primarily useful for tests and plugin reload scenarios.
    """
    global _analyzer_registry
    _analyzer_registry = None


def _register_built_in_analyzers(registry: AnalyzerRegistry) -> None:
    """Register built-in analyzers.

    Args:
        registry: The analyzer registry.
    """
    # Import here to avoid circular imports
    from .dead_code import DeadCodeAnalyzer
    from .flakiness import FlakinessAnalyzer
    from .hardcoded_value import HardcodedValueAnalyzer
    from .naming_convention import NamingConventionAnalyzer
    from .setup_teardown import SetupTeardownAnalyzer
    from .sleep_detector import SleepDetectorAnalyzer
    from .tag_consistency import TagConsistencyAnalyzer
    from .test_documentation import TestDocumentationAnalyzer

    registry.register("dead_code", DeadCodeAnalyzer)
    registry.register("sleep_detector", SleepDetectorAnalyzer)
    registry.register("flakiness", FlakinessAnalyzer)
    registry.register("hardcoded_value", HardcodedValueAnalyzer)
    registry.register("naming_convention", NamingConventionAnalyzer)
    registry.register("setup_teardown", SetupTeardownAnalyzer)
    registry.register("tag_consistency", TagConsistencyAnalyzer)
    registry.register("test_documentation", TestDocumentationAnalyzer)

    logger.debug("Built-in analyzers registered")


def _register_entry_point_analyzers(registry: AnalyzerRegistry) -> None:
    """Register third-party analyzers from Python entry points."""
    for ep in _iter_analyzer_entry_points():
        try:
            analyzer_class = ep.load()
            registry.register(ep.name, analyzer_class, override=True)
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.warning(
                "Failed to load analyzer entry point",
                extra={
                    "entry_point": getattr(ep, "name", "<unknown>"),
                    "error": str(exc),
                },
            )


# Public API functions
def register_analyzer(
    name: str, analyzer_class: AnalyzerClass, override: bool = False
) -> None:
    """Register an analyzer in the global registry.

    Args:
        name: Unique name for the analyzer.
        analyzer_class: The analyzer class.
        override: Whether to override existing analyzer.

    Example:
        >>> register_analyzer("custom", CustomAnalyzer)
    """
    registry = get_analyzer_registry()
    registry.register(name, analyzer_class, override)


def get_analyzer(name: str) -> BaseAnalyzer:
    """Get an analyzer instance from the global registry.

    Args:
        name: Analyzer name.

    Returns:
        Analyzer instance.

    Example:
        >>> analyzer = get_analyzer("dead_code")
    """
    registry = get_analyzer_registry()
    return registry.get(name)


def list_analyzers() -> list[str]:
    """List all available analyzer names.

    Returns:
        List of analyzer names.

    Example:
        >>> analyzers = list_analyzers()
        >>> print(analyzers)
        ['dead_code', 'flakiness', 'sleep_detector']
    """
    registry = get_analyzer_registry()
    return registry.list()


def get_analyzer_info(name: str) -> dict[str, str]:
    """Get information about an analyzer.

    Args:
        name: Analyzer name.

    Returns:
        Dictionary with analyzer information.

    Example:
        >>> info = get_analyzer_info("dead_code")
        >>> print(info["description"])
    """
    registry = get_analyzer_registry()
    return registry.get_info(name)
