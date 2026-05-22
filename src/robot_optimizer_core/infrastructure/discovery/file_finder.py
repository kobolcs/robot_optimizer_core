# src/robot_optimizer_core/infrastructure/discovery/file_finder.py
"""Optimized file discovery with linear time complexity.

This module provides ``OptimizedFileDiscoveryService``, the main file-discovery
component of the analysis engine. Discovery is O(n) relative to the total number
of files on disk, using pre-compiled pattern matching and an exclusion trie.

A configurable ``timeout_seconds`` guard prevents discovery from hanging
indefinitely on broken symlinks, network mounts, or slow file-systems.

Example:
    Finding all Robot Framework files under a directory::

        from robot_optimizer_core.infrastructure.discovery import OptimizedFileDiscoveryService

        service = OptimizedFileDiscoveryService()
        files = service.find_files(root_path=Path("tests/"), timeout_seconds=30)
        print(f"Found {len(files)} files")
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from pathlib import Path

from ...exceptions import AnalysisError
from ...exceptions import RobotFileNotFoundError as RFFileNotFoundError
from ..config import Settings
from ..logging.adapter import get_logger

logger = get_logger(__name__)


__all__ = [
    "OptimizedFileDiscoveryService",
    "PathExclusionTrie",
    "PatternMatcher",
]


@dataclass
class PatternMatcher:
    """Optimized pattern matcher using pre-compiled patterns and tries.

    Classifies each glob pattern on construction into one of three buckets:
    exact-name set lookups (O(1)), extension suffix checks (O(1)), or
    compiled regex fallbacks for complex globs.

    Attributes:
        patterns: Compiled regex patterns for complex globs.
        exact_matches: Lower-cased set of literal filenames.
        extensions: Lower-cased set of file extensions (e.g. ``".robot"``).
    """

    patterns: list[re.Pattern[str]] = field(default_factory=list)
    exact_matches: set[str] = field(default_factory=set)
    extensions: set[str] = field(default_factory=set)

    @classmethod
    def from_patterns(cls, patterns: list[str]) -> PatternMatcher:
        """Build an optimized matcher from a list of glob patterns.

        Args:
            patterns: Glob patterns such as ``["*.robot", "*.resource"]``.

        Returns:
            A ``PatternMatcher`` with patterns pre-compiled for fast lookup.
        """
        matcher = cls()

        for pattern in patterns:
            if (
                pattern.startswith("*.")
                and "*" not in pattern[2:]
                and "?" not in pattern[2:]
            ):
                matcher.extensions.add(pattern[1:].lower())  # Store ".robot"
            elif "*" not in pattern and "?" not in pattern:
                matcher.exact_matches.add(pattern.lower())
            else:
                regex_pattern = fnmatch.translate(pattern)
                matcher.patterns.append(re.compile(regex_pattern, re.IGNORECASE))

        return matcher

    def matches(self, filename: str) -> bool:
        """Return ``True`` when *filename* matches at least one pattern.

        Uses O(1) set/extension checks before falling back to regex, so the
        common ``*.robot`` / ``*.resource`` cases never hit the regex engine.

        Args:
            filename: Bare filename (no directory component) to test.

        Returns:
            ``True`` if the filename matches any registered pattern.
        """
        filename_lower = filename.lower()

        if filename_lower in self.exact_matches:
            return True

        for ext in self.extensions:
            if filename_lower.endswith(ext):
                return True

        for pattern in self.patterns:
            if pattern.match(filename):
                return True

        return False


@dataclass
class PathExclusionTrie:
    """Trie structure for efficient path exclusion checking.

    Patterns containing ``**`` are handled separately via per-component fnmatch
    matching so that patterns like ``**/.*`` or ``**/__pycache__/**`` correctly
    match only the intended path components instead of marking the trie root as
    excluded (which would exclude everything).

    Attributes:
        root: Root node of the exclusion trie.
    """

    class TrieNode:
        def __init__(self) -> None:
            self.children: dict[str, PathExclusionTrie.TrieNode] = {}
            self.is_excluded = False
            self.is_pattern = False
            self.pattern: re.Pattern[str] | None = None

    root: TrieNode = field(default_factory=TrieNode)
    # Per-component patterns compiled from ** glob patterns (init=False keeps
    # them out of the dataclass constructor signature).
    _component_patterns: list[re.Pattern[str]] = field(default_factory=list, init=False)

    def add_exclusion(self, pattern: str) -> None:
        """Add exclusion pattern to trie.

        Patterns containing ``**`` are decomposed into their non-wildcard
        segments and stored as per-component match patterns.  All other
        patterns are inserted into the prefix trie as before.
        """
        if "**" in pattern:
            # Extract the meaningful (non-**) components and compile each one
            # as an fnmatch pattern so they can be matched against individual
            # path parts at query time.
            for part in pattern.split("/"):
                if part and part != "**":
                    self._component_patterns.append(
                        re.compile(fnmatch.translate(part), re.IGNORECASE)
                    )
            return

        parts = pattern.split("/")
        node = self.root

        for part in parts:
            if "*" in part or "?" in part:
                # Pattern node
                node.is_pattern = True
                node.pattern = re.compile(fnmatch.translate(part))
                break
            # Literal node
            if part not in node.children:
                node.children[part] = PathExclusionTrie.TrieNode()
            node = node.children[part]

        node.is_excluded = True

    def _check_component_patterns(self, parts: tuple[str, ...]) -> bool:
        """Check if any path component matches a component pattern."""
        if not self._component_patterns:
            return False
        for part in parts:
            for cpat in self._component_patterns:
                if cpat.match(part):
                    return True
        return False

    def _find_next_node(
        self, node: TrieNode, part: str
    ) -> tuple[TrieNode | None, bool]:
        """Find the next node for a path part.

        Returns (next_node, found). If not found, returns (None, False).
        """
        # Check exact match
        if part in node.children:
            return node.children[part], True

        # Check for pattern children
        for child_name, child_node in node.children.items():
            if "*" in child_name or "?" in child_name:
                pat = re.compile(fnmatch.translate(child_name))
                if pat.match(part):
                    return child_node, True

        return None, False

    def is_excluded(self, path: Path) -> bool:
        """Check if path is excluded - O(d) where d is directory depth."""
        parts = path.parts

        # Fast component-pattern check for ** patterns
        if self._check_component_patterns(parts):
            return True

        node = self.root

        for part in parts:
            # Check if current node excludes
            if node.is_excluded:
                return True

            # Check pattern matching
            if node.is_pattern and node.pattern:
                if node.pattern.match(part):
                    return True

            # Find next node
            next_node, found = self._find_next_node(node, part)
            if found:
                assert next_node is not None
                node = next_node
            else:
                return False

        return node.is_excluded


class OptimizedFileDiscoveryService:
    """File discovery with O(n) complexity relative to total files on disk.

    Uses pre-compiled pattern matchers and an exclusion trie to avoid the
    O(n*m) cost of naïve glob-per-pattern approaches. A ``timeout_seconds``
    guard in :meth:`find_files` prevents the process from hanging on network
    mounts or broken symlinks.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the discovery service.

        Args:
            settings: Configuration settings. Defaults to the global settings
                instance when not provided.
        """
        self.settings = settings or Settings()
        self.logger = get_logger(__name__)

        self._include_matcher: PatternMatcher = PatternMatcher()
        self._exclude_trie: PathExclusionTrie = PathExclusionTrie()
        self._dir_cache: dict[Path, list[Path]] = {}
        self._stats = {
            "files_checked": 0,
            "dirs_checked": 0,
            "cache_hits": 0,
            "pattern_checks": 0,
        }

    def find_files(
        self,
        root_path: Path,
        patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        recursive: bool = True,
        max_depth: int = 20,
        timeout_seconds: float = 60.0,
    ) -> list[Path]:
        """Discover matching files under *root_path* with timeout protection.

        Args:
            root_path: Directory to search. Must exist.
            patterns: Glob patterns to include (e.g. ``["*.robot"]``). Defaults
                to ``Settings.file_patterns`` when ``None``.
            exclude_patterns: Glob patterns to exclude. Defaults to
                ``Settings.exclude_patterns`` when both this and *patterns* are
                ``None``; defaults to ``[]`` when *patterns* is given explicitly
                so that caller-specified includes are not silently filtered.
            recursive: When ``False``, only the top-level directory is searched.
            max_depth: Maximum directory depth to descend into. Prevents
                runaway recursion in deeply nested trees.
            timeout_seconds: Wall-clock seconds before discovery is aborted with
                :class:`~robot_optimizer_core.exceptions.AnalysisError`.
                Protects against hangs on network mounts and broken symlinks.
                Set to ``0`` to disable the timeout (not recommended).

        Returns:
            Sorted list of matching file paths.

        Raises:
            RobotFileNotFoundError: If *root_path* does not exist.
            AnalysisError: If discovery does not complete within
                *timeout_seconds*.
        """
        self._stats = {
            "files_checked": 0,
            "dirs_checked": 0,
            "cache_hits": 0,
            "pattern_checks": 0,
        }
        self._dir_cache.clear()

        root_path = Path(root_path).resolve()
        if not root_path.exists():
            raise RFFileNotFoundError(root_path)

        patterns = patterns or self.settings.file_patterns
        self._include_matcher = PatternMatcher.from_patterns(patterns)

        exclude_patterns = (
            exclude_patterns
            if exclude_patterns is not None
            else ([] if patterns is not None else self.settings.exclude_patterns)
        )
        self._exclude_trie = PathExclusionTrie()
        for pattern in exclude_patterns:
            self._exclude_trie.add_exclusion(pattern)

        if timeout_seconds > 0:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    lambda: sorted(
                        self._discover_optimized(
                            root_path, root_path, recursive, max_depth, 0
                        )
                    )
                )
                try:
                    files = future.result(timeout=timeout_seconds)
                except FuturesTimeoutError:
                    future.cancel()
                    raise AnalysisError(
                        f"File discovery timed out after {timeout_seconds}s. "
                        "Check for network mounts or broken symlinks under "
                        f"{root_path}",
                        file_path=root_path,
                    ) from None
        else:
            files = sorted(
                self._discover_optimized(root_path, root_path, recursive, max_depth, 0)
            )

        self.logger.info(
            "Optimized discovery complete",
            extra={"files_found": len(files), "stats": self._stats},
        )

        return files

    def _discover_optimized(
        self,
        current_path: Path,
        root_path: Path,
        recursive: bool,
        max_depth: int,
        current_depth: int,
    ) -> Iterator[Path]:
        """Yield matching files under *current_path* with early termination.

        Args:
            current_path: Directory currently being scanned.
            root_path: Original root passed to :meth:`find_files`; used for
                computing relative paths for exclusion checks.
            recursive: Whether to descend into subdirectories.
            max_depth: Maximum recursion depth relative to *root_path*.
            current_depth: Current recursion depth (caller-managed).

        Yields:
            Matching file paths.
        """
        # Check depth limit
        if current_depth > max_depth:
            return

        # Early termination for excluded directories - O(d) where d is depth
        if self._exclude_trie.is_excluded(current_path.relative_to(root_path)):
            return

        self._stats["dirs_checked"] += 1

        # Get directory listing with caching
        entries = self._get_cached_listing(current_path)

        # Process entries - O(e) where e is entries in directory
        for entry in entries:
            # Skip if excluded - O(d) check
            if self._exclude_trie.is_excluded(entry.relative_to(root_path)):
                continue

            if entry.is_file():
                self._stats["files_checked"] += 1
                self._stats["pattern_checks"] += 1

                # Check pattern match - O(1) for most patterns
                if self._include_matcher.matches(entry.name) and self._is_text_file(
                    entry
                ):
                    yield entry

            elif entry.is_dir() and recursive:
                # Recurse into subdirectory
                yield from self._discover_optimized(
                    entry, root_path, recursive, max_depth, current_depth + 1
                )

    def _is_text_file(self, path: Path) -> bool:
        """Return ``False`` for binary or high-control-byte files that cannot be parsed.

        Reads up to 4 096 bytes and rejects the file if it contains a null byte
        (binary indicator) or more than 5 % non-printable control characters.

        Args:
            path: File to inspect.

        Returns:
            ``True`` when the file appears to be valid UTF-8 text.
        """
        try:
            sample = path.read_bytes()[:4096]
        except OSError:
            return False

        if b"\x00" in sample:
            return False

        try:
            text = sample.decode("utf-8")
        except UnicodeDecodeError:
            return False

        # Reject files that are mostly non-printable control bytes.
        control_chars = sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\r\t")
        return control_chars <= max(1, len(text) // 20)

    def _get_cached_listing(self, path: Path) -> list[Path]:
        """Return a directory listing, using an in-memory cache to avoid re-reading.

        Args:
            path: Directory to list.

        Returns:
            Children of *path*. Returns ``[]`` on permission or I/O errors.
        """
        if path in self._dir_cache:
            self._stats["cache_hits"] += 1
            return self._dir_cache[path]

        try:
            entries = list(path.iterdir())
            self._dir_cache[path] = entries
            return entries
        except (PermissionError, OSError):
            return []
