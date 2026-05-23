# src/robot_optimizer_core/domain/ports/plugin.py
"""Domain port contracts for the plugin extension system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

__all__ = ["Plugin", "PluginMetadata"]


@dataclass
class PluginMetadata:
    """Metadata for a plugin."""

    name: str
    version: str
    description: str
    author: str


class Plugin(ABC):
    """Abstract base class for plugins.

    The registry parameter uses ``Any`` to avoid a circular import between the
    domain layer (which owns this contract) and the infrastructure layer (which
    provides the concrete ``PluginRegistry`` implementation).
    """

    def __init__(self, registry: Any = None) -> None:
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
