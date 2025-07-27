# src/robot_optimizer_core/discovery/file_finder.py
"""File discovery service for finding Robot Framework test files.

This module provides the service for discovering test files in a directory
structure, with support for patterns and exclusions.

Example:
    Finding test files::
    
        from robot_optimizer_core.discovery import FileDiscoveryService
        from pathlib import Path
        
        discovery = FileDiscoveryService()
        files = discovery.find_files(
            root_path=Path("tests/"),
            patterns=["*.robot", "*.resource"],
            recursive=True
        )
        
        for file in files:
            print(f"Found: {file}")
"""
from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TypeGuard, Protocol, runtime_checkable

from ..config import get_settings
from ..exceptions import FileNotFoundError as RFFileNotFoundError
from ..logging import get_logger
from ..metrics import get_metrics


@runtime_checkable
class AnalyzableFile(Protocol):
    """Protocol for files that can be analyzed."""
    
    def exists(self) -> bool: ...
    def is_file(self) -> bool: ...
    def stat(self) -> os.stat_result: ...
    def __str__(self) -> str: ...


@dataclass(slots=True)
class FileStats:
    """Statistics about discovered files."""
    total_files: int = 0
    total_size_bytes: int = 0
    excluded_files: int = 0
    invalid_files: int = 0
    
    @property
    def total_size_mb(self) -> float:
        """Get total size in megabytes."""
        return self.total_size_bytes / (1024 * 1024)


class FileDiscoveryService:
    """Service for discovering Robot Framework test files.
    
    This service handles file discovery with pattern matching,
    exclusions, and size limits. It's designed to be efficient
    for large directory structures.
    
    Attributes:
        logger: Logger instance.
        metrics: Metrics collector.
        settings: Configuration settings.
    """
    
    __slots__ = ('settings', 'logger', 'metrics', '_stats')
    
    def __init__(
        self,
        settings: Settings | None = None
    ) -> None:
        """Initialize the file discovery service.
        
        Args:
            settings: Configuration settings (default: global settings).
        """
        self.settings = settings or get_settings()
        self.logger = get_logger(__name__)
        self.metrics = get_metrics()
        self._stats = FileStats()
    
    def find_files(
        self,
        root_path: Path,
        patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        recursive: bool = True,
        follow_symlinks: bool = False,
        max_depth: int | None = None
    ) -> list[Path]:
        """Find all matching files in a directory.
        
        Args:
            root_path: Root directory to search.
            patterns: File patterns to match (default: from settings).
            exclude_patterns: Patterns to exclude (default: from settings).
            recursive: Whether to search subdirectories.
            follow_symlinks: Whether to follow symbolic links.
            max_depth: Maximum directory depth (None = unlimited).
            
        Returns:
            List of matching file paths.
            
        Raises:
            FileNotFoundError: If root path doesn't exist.
        """
        # Reset stats
        self._stats = FileStats()
        
        # Validate root path
        if not root_path.exists():
            raise RFFileNotFoundError(root_path)
        
        # Use default patterns if not provided
        patterns = patterns or self.settings.file_patterns
        exclude_patterns = exclude_patterns or self.settings.exclude_patterns
        
        self.logger.info(
            "Starting file discovery",
            extra={
                "root": str(root_path),
                "patterns": patterns,
                "recursive": recursive
            }
        )
        
        # Collect files
        with self.metrics.timer("discovery.duration"):
            files = list(self._discover_files(
                root_path,
                patterns,
                exclude_patterns,
                recursive,
                follow_symlinks,
                max_depth
            ))
        
        # Sort for consistent ordering
        files.sort()
        
        self.logger.info(
            "File discovery complete",
            extra={
                "root": str(root_path),
                "files_found": len(files),
                "stats": {
                    "total_size_mb": self._stats.total_size_mb,
                    "excluded": self._stats.excluded_files,
                    "invalid": self._stats.invalid_files
                }
            }
        )
        
        self.metrics.gauge("discovery.files_found", len(files))
        self.metrics.gauge("discovery.total_size_mb", self._stats.total_size_mb)
        
        return files
    
    def _discover_files(
        self,
        root_path: Path,
        patterns: list[str],
        exclude_patterns: list[str],
        recursive: bool,
        follow_symlinks: bool,
        max_depth: int | None,
        current_depth: int = 0
    ) -> Iterator[Path]:
        """Discover files matching patterns.
        
        Args:
            root_path: Root directory.
            patterns: Include patterns.
            exclude_patterns: Exclude patterns.
            recursive: Whether to recurse.
            follow_symlinks: Whether to follow links.
            max_depth: Maximum depth.
            current_depth: Current recursion depth.
            
        Yields:
            Matching file paths.
        """
        try:
            entries = list(root_path.iterdir())
        except PermissionError:
            self.logger.warning(
                f"Permission denied accessing: {root_path}",
                extra={"path": str(root_path)}
            )
            return
        except Exception as e:
            self.logger.error(
                f"Error accessing directory: {root_path}",
                extra={"path": str(root_path), "error": str(e)}
            )
            return
        
        for entry in entries:
            # Handle symlinks
            if entry.is_symlink() and not follow_symlinks:
                continue
            
            # Check exclusions first
            if self._should_exclude(entry, exclude_patterns):
                self.logger.debug(
                    f"Excluded: {entry}",
                    extra={"path": str(entry)}
                )
                self._stats.excluded_files += 1
                continue
            
            # Process files
            if entry.is_file():
                if self._matches_patterns(entry, patterns):
                    if self._is_valid_file(entry):
                        self._stats.total_files += 1
                        if stat := self._safe_stat(entry):
                            self._stats.total_size_bytes += stat.st_size
                        yield entry
                    else:
                        self._stats.invalid_files += 1
                        self.logger.debug(
                            f"Skipped invalid file: {entry}",
                            extra={"path": str(entry)}
                        )
            
            # Process directories
            elif entry.is_dir() and recursive:
                # Check depth limit
                if max_depth is not None and current_depth >= max_depth:
                    continue
                
                # Recurse into subdirectory
                yield from self._discover_files(
                    entry,
                    patterns,
                    exclude_patterns,
                    recursive,
                    follow_symlinks,
                    max_depth,
                    current_depth + 1
                )
    
    def _matches_patterns(self, path: Path, patterns: list[str]) -> bool:
        """Check if file matches any of the patterns.
        
        Args:
            path: File path to check.
            patterns: List of patterns.
            
        Returns:
            True if file matches any pattern.
        """
        name = path.name
        
        for pattern in patterns:
            # Standard match
            if fnmatch.fnmatch(name, pattern):
                return True
            
            # Case-insensitive match
            if fnmatch.fnmatch(name.lower(), pattern.lower()):
                return True
        
        return False
    
    def _should_exclude(self, path: Path, exclude_patterns: list[str]) -> bool:
        """Check if path should be excluded.
        
        Args:
            path: Path to check.
            exclude_patterns: List of exclusion patterns.
            
        Returns:
            True if path should be excluded.
        """
        # Convert to string for pattern matching
        path_str = str(path)
        
        for pattern in exclude_patterns:
            # Check against full path
            if fnmatch.fnmatch(path_str, pattern):
                return True
            
            # Check against relative path parts
            if any(fnmatch.fnmatch(part, pattern) for part in path.parts):
                return True
            
            # Special handling for directory patterns
            if path.is_dir() and pattern.endswith("/"):
                dir_pattern = pattern.rstrip("/")
                if fnmatch.fnmatch(path.name, dir_pattern):
                    return True
        
        return False
    
    def _is_valid_file(self, path: Path) -> bool:
        """Check if file is valid for analysis.
        
        Args:
            path: File path to check.
            
        Returns:
            True if file is valid.
        """
        # Check file size
        if stat := self._safe_stat(path):
            max_size = self.settings.max_file_size_bytes
            
            if stat.st_size > max_size:
                self.logger.warning(
                    f"File too large: {path} ({stat.st_size} bytes)",
                    extra={
                        "path": str(path),
                        "size": stat.st_size,
                        "max_size": max_size
                    }
                )
                return False
        
        # Check if file is readable
        if not os.access(path, os.R_OK):
            self.logger.warning(
                f"File not readable: {path}",
                extra={"path": str(path)}
            )
            return False
        
        # Quick content check - ensure it's a text file
        if not self._is_text_file(path):
            return False
        
        return True
    
    def _safe_stat(self, path: Path) -> os.stat_result | None:
        """Safely get file stats.
        
        Args:
            path: File path.
            
        Returns:
            File stats or None if error.
        """
        try:
            return path.stat()
        except Exception as e:
            self.logger.error(
                f"Error getting file stats: {path}",
                extra={"path": str(path), "error": str(e)}
            )
            return None
    
    def _is_text_file(self, path: Path) -> bool:
        """Check if file is a text file.
        
        Args:
            path: File path to check.
            
        Returns:
            True if file appears to be text.
        """
        try:
            with open(path, 'rb') as f:
                # Read first 1KB
                chunk = f.read(1024)
                
                # Check for null bytes (binary file)
                if b'\x00' in chunk:
                    self.logger.debug(
                        f"Binary file detected: {path}",
                        extra={"path": str(path)}
                    )
                    return False
                
                # Try to decode as UTF-8
                try:
                    chunk.decode('utf-8')
                except UnicodeDecodeError:
                    # Try other encodings
                    for encoding in ['latin-1', 'utf-16']:
                        try:
                            chunk.decode(encoding)
                            break
                        except UnicodeDecodeError:
                            continue
                    else:
                        self.logger.debug(
                            f"Unable to decode file: {path}",
                            extra={"path": str(path)}
                        )
                        return False
            
            return True
            
        except Exception as e:
            self.logger.error(
                f"Error checking file content: {path}",
                extra={"path": str(path), "error": str(e)}
            )
            return False
    
    def count_files(
        self,
        root_path: Path,
        patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        recursive: bool = True
    ) -> int:
        """Count matching files without loading them.
        
        This is more efficient than len(find_files()) for large directories.
        
        Args:
            root_path: Root directory to search.
            patterns: File patterns to match.
            exclude_patterns: Patterns to exclude.
            recursive: Whether to search subdirectories.
            
        Returns:
            Number of matching files.
        """
        return sum(
            1 for _ in self._discover_files(
                root_path,
                patterns or self.settings.file_patterns,
                exclude_patterns or self.settings.exclude_patterns,
                recursive,
                follow_symlinks=False,
                max_depth=None
            )
        )
    
    def estimate_analysis_time(
        self,
        file_count: int,
        avg_file_size_kb: float = 10.0,
        analyzers_count: int = 3
    ) -> float:
        """Estimate analysis time for given number of files.
        
        This is a rough estimate based on typical performance.
        
        Args:
            file_count: Number of files to analyze.
            avg_file_size_kb: Average file size in KB.
            analyzers_count: Number of analyzers to run.
            
        Returns:
            Estimated time in seconds.
        """
        # Base estimates (very rough)
        time_per_file_base = 0.1  # 100ms base overhead
        time_per_kb = 0.01  # 10ms per KB
        time_per_analyzer = 0.05  # 50ms per analyzer
        
        time_per_file = (
            time_per_file_base +
            (avg_file_size_kb * time_per_kb) +
            (analyzers_count * time_per_analyzer)
        )
        
        return file_count * time_per_file


def is_robot_file(path: Path) -> TypeGuard[Path]:
    """Type guard to check if path is a Robot Framework file.
    
    Args:
        path: Path to check.
        
    Returns:
        True if path is a .robot or .resource file.
    """
    return path.suffix.lower() in {'.robot', '.resource'}


def get_file_stats(files: list[Path]) -> FileStats:
    """Get statistics about a list of files.
    
    Args:
        files: List of file paths.
        
    Returns:
        File statistics.
    """
    stats = FileStats(total_files=len(files))
    
    for file in files:
        if file.exists():
            stats.total_size_bytes += file.stat().st_size
    
    return stats