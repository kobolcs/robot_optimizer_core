# src/robot_optimizer_core/domain/ports/cache.py
"""Port interface for analysis result caching."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path

    from ..value_objects.finding import Finding


@runtime_checkable
class IAnalysisCache(Protocol):
    """Interface for a content-addressed per-file analysis cache.

    Implementations hash file content so that unchanged files can be
    skipped during directory analysis.
    """

    def file_hash(self, path: Path) -> str:
        """Return a stable content hash for *path* (e.g. SHA-256 hex)."""
        ...  # pragma: no cover

    def get(self, path: Path, file_hash: str) -> list[Finding] | None:
        """Return cached findings for *(path, hash)*, or ``None`` on a miss."""
        ...  # pragma: no cover

    def put(self, path: Path, file_hash: str, findings: list[Finding]) -> None:
        """Store *findings* for *(path, hash)*."""
        ...  # pragma: no cover

    def flush(self) -> None:
        """Persist any pending writes to the backing store."""
        ...  # pragma: no cover

    def clear(self) -> None:
        """Remove all cached entries from the backing store."""
        ...  # pragma: no cover


__all__ = ["IAnalysisCache"]
