# src/robot_optimizer_core/domain/ports/analyzer_registry.py
"""Port interface for the analyzer registry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..ports.analyzer import IAnalyzer


@runtime_checkable
class IAnalyzerRegistry(Protocol):
    """Minimal interface the application layer needs from the analyzer registry.

    The concrete ``AnalyzerRegistry`` in ``application.analyzers.registry``
    satisfies this protocol structurally.
    """

    def list(self) -> list[str]:
        """Return sorted list of registered analyzer names."""
        ...  # pragma: no cover

    def get_info(self, name: str) -> dict[str, Any]:
        """Return metadata dict for the named analyzer."""
        ...  # pragma: no cover

    def create(self, name: str) -> IAnalyzer:
        """Create a fresh instance of the named analyzer."""
        ...  # pragma: no cover

    @property
    def analyzers(self) -> dict[str, Any]:
        """Mapping of name → analyzer class for all registered analyzers."""
        ...  # pragma: no cover


__all__ = ["IAnalyzerRegistry"]
