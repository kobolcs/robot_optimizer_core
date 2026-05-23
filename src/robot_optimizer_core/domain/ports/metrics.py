# src/robot_optimizer_core/domain/ports/metrics.py
"""Port interface for metrics collection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from contextlib import AbstractContextManager


@runtime_checkable
class IMetrics(Protocol):
    """Minimal interface required by domain and application code for metrics recording."""

    def increment(
        self, metric: str, value: int = 1, tags: dict[str, str] | None = None
    ) -> None:
        """Increment a counter metric."""
        ...  # pragma: no cover

    def gauge(
        self, metric: str, value: float, tags: dict[str, str] | None = None
    ) -> None:
        """Set a gauge metric."""
        ...  # pragma: no cover

    def timing(
        self, metric: str, value: float, tags: dict[str, str] | None = None
    ) -> None:
        """Record a timing metric."""
        ...  # pragma: no cover

    def timer(
        self, metric: str, tags: dict[str, str] | None = None
    ) -> AbstractContextManager[None]:
        """Return a context manager that records elapsed time."""
        ...  # pragma: no cover

    def get_metrics(self) -> dict[str, Any]:
        """Return a snapshot of all collected metrics."""
        ...  # pragma: no cover

    def reset(self) -> None:
        """Clear all collected metrics."""
        ...  # pragma: no cover


__all__ = ["IMetrics"]
