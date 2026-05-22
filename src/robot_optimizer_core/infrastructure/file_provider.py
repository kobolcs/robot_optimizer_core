# src/robot_optimizer_core/infrastructure/file_provider.py
"""File I/O abstraction and providers for testability.

This module defines the FileProvider interface and implementations,
allowing easy substitution of file sources (disk, memory, S3, etc.)
without changing analysis code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

__all__ = ["DiskFileProvider", "FileProvider", "InMemoryFileProvider"]


class FileProvider(Protocol):
    """Protocol for file content providers.

    Implementations can load files from disk, memory, remote sources, etc.
    """

    def load(self, file_path: Path) -> str:
        """Load file content.

        Args:
            file_path: Path to the file.

        Returns:
            File content as string.

        Raises:
            FileNotFoundError: If file does not exist.
            IOError: If file cannot be read.
        """
        ...

    def exists(self, file_path: Path) -> bool:
        """Check if file exists.

        Args:
            file_path: Path to check.

        Returns:
            True if file exists, False otherwise.
        """
        ...


class DiskFileProvider:
    """Load files from disk (default behavior)."""

    def load(self, file_path: Path) -> str:
        """Load file from disk."""
        path = Path(file_path) if not isinstance(file_path, Path) else file_path
        return path.read_text(encoding="utf-8")

    def exists(self, file_path: Path) -> bool:
        """Check if file exists on disk."""
        path = Path(file_path) if not isinstance(file_path, Path) else file_path
        return path.exists()


class InMemoryFileProvider:
    """Load files from an in-memory dictionary (for testing)."""

    def __init__(self, files: dict[str, str] | None = None) -> None:
        """Initialize with a dictionary of file paths to content.

        Args:
            files: Dictionary mapping file path (as string) to file content.
        """
        self.files: dict[str, str] = {}
        if files:
            for path, content in files.items():
                # Normalize paths to string for consistent lookup
                self.files[str(Path(path))] = content

    def load(self, file_path: Path) -> str:
        """Load file from memory.

        Args:
            file_path: Path to file.

        Returns:
            File content.

        Raises:
            FileNotFoundError: If file not in dictionary.
        """
        normalized = str(Path(file_path))
        if normalized not in self.files:
            raise FileNotFoundError(f"File not in memory: {file_path}")
        return self.files[normalized]

    def exists(self, file_path: Path) -> bool:
        """Check if file exists in memory."""
        normalized = str(Path(file_path))
        return normalized in self.files

    def add(self, file_path: str | Path, content: str) -> None:
        """Add a file to the in-memory provider.

        Args:
            file_path: Path to file.
            content: File content.
        """
        normalized = str(Path(file_path))
        self.files[normalized] = content

    def clear(self) -> None:
        """Clear all in-memory files."""
        self.files.clear()
