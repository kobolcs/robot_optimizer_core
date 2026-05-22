# src/robot_optimizer_core/domain/ports/file_provider.py
"""Port interface for file I/O abstraction."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class FileProvider(Protocol):
    """Interface for loading file content from any backing store."""

    def load(self, file_path: Path) -> str:
        """Return the text content of *file_path*.

        Raises:
            FileNotFoundError: If the file does not exist.
            IOError: If the file cannot be read.
        """
        ...  # pragma: no cover

    def exists(self, file_path: Path) -> bool:
        """Return ``True`` if *file_path* exists in the backing store."""
        ...  # pragma: no cover


__all__ = ["FileProvider"]
