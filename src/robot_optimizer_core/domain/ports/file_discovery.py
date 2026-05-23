# src/robot_optimizer_core/domain/ports/file_discovery.py
"""Port interface for file discovery."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class IFileDiscovery(Protocol):
    """Interface for discovering Robot Framework files under a root path."""

    def find_files(
        self,
        root_path: Path,
        patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        recursive: bool = True,
    ) -> list[Path]:
        """Return all files under *root_path* that match *patterns*.

        Args:
            root_path: Directory to search.
            patterns: Glob patterns to include (e.g. ``["*.robot"]``).
            exclude_patterns: Glob patterns to exclude.
            recursive: Whether to descend into sub-directories.

        Returns:
            Sorted list of matching :class:`~pathlib.Path` objects.
        """
        ...  # pragma: no cover


__all__ = ["IFileDiscovery"]
