# src/robot_optimizer_core/domain/ports/plugin.py
"""Domain port contracts for the plugin extension system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = ["IPluginRegistry", "Plugin", "PluginMetadata"]


@dataclass
class PluginMetadata:
    """Metadata for a plugin."""

    name: str
    version: str
    description: str
    author: str


@runtime_checkable
class IPluginRegistry(Protocol):
    """Minimal interface a Plugin needs from its registry.

    Keeping this in the domain layer avoids a circular import between
    ``domain.ports.plugin`` and the infrastructure ``PluginRegistry``
    implementation that used to require ``Any``.
    """

    def register(self, name: str, plugin_class: type) -> None:
        """Register a plugin class under *name*."""
        ...  # pragma: no cover

    def list(self) -> list[str]:
        """Return all registered plugin names."""
        ...  # pragma: no cover


class Plugin(ABC):
    """Abstract base class for plugins."""

    def __init__(self, registry: IPluginRegistry | None = None) -> None:
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

    def contribute_analyzers(self) -> list[type]:
        """Return analyzer classes this plugin wants to register.

        Override in subclasses to contribute custom analyzers to the registry
        during plugin activation.  The returned types must be
        ``BaseAnalyzer`` subclasses; the infrastructure layer validates this
        before registering.

        Returns:
            List of analyzer classes (default: empty — no contribution).
        """
        return []
