# src/robot_optimizer_core/discovery/file_finder.py
"""Optimized file discovery with linear time complexity.

This module is part of the test-suite analysis engine infrastructure.
Its primary production responsibility is file discovery.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings
from ..exceptions import RobotFileNotFoundError as RFFileNotFoundError
from ..logging import get_logger

logger = get_logger(__name__)


__all__ = [
    "OptimizedFileDiscoveryService",
    "PathExclusionTrie",
    "PatternMatcher",
]


@dataclass
class PatternMatcher:
    """Optimized pattern matcher using pre-compiled patterns and tries."""

    # Pre-compiled patterns for better performance
    patterns: list[re.Pattern[str]] = field(default_factory=list)
    # Trie structure for exact matches
    exact_matches: set[str] = field(default_factory=set)
    # Suffix tree for extension matching
    extensions: set[str] = field(default_factory=set)

    @classmethod
    def from_patterns(cls, patterns: list[str]) -> PatternMatcher:
        """Create optimized matcher from patterns."""
        matcher = cls()

        for pattern in patterns:
            # Check if it's a simple extension pattern
            if (
                pattern.startswith("*.")
                and "*" not in pattern[2:]
                and "?" not in pattern[2:]
            ):
                # Simple extension - use set lookup O(1)
                matcher.extensions.add(pattern[1:].lower())  # Store ".robot"
            elif "*" not in pattern and "?" not in pattern:
                # Exact match - use set lookup O(1)
                matcher.exact_matches.add(pattern.lower())
            else:
                # Complex pattern - compile regex (still needed for some cases)
                regex_pattern = fnmatch.translate(pattern)
                matcher.patterns.append(re.compile(regex_pattern, re.IGNORECASE))

        return matcher

    def matches(self, filename: str) -> bool:
        """Check if filename matches any pattern - O(1) for most cases."""
        filename_lower = filename.lower()

        # Check exact matches first - O(1)
        if filename_lower in self.exact_matches:
            return True

        # Check extensions - O(1)
        for ext in self.extensions:
            if filename_lower.endswith(ext):
                return True

        # Fall back to regex for complex patterns - O(m) where m is number of complex patterns
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
    """File discovery with O(n) complexity instead of O(n*m)."""

    def __init__(self, settings: Settings | None = None):
        """Initialize optimized discovery service."""
        self.settings = settings or Settings()
        self.logger = get_logger(__name__)

        # Pre-compile patterns for O(1) matching (reset to real values in find_files)
        self._include_matcher: PatternMatcher = PatternMatcher()
        self._exclude_trie: PathExclusionTrie = PathExclusionTrie()

        # Cache for directory listings
        self._dir_cache: dict[Path, list[Path]] = {}

        # Statistics
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
    ) -> list[Path]:
        """Find files with O(n) complexity where n is number of files."""
        # Reset stats
        self._stats = {
            "files_checked": 0,
            "dirs_checked": 0,
            "cache_hits": 0,
            "pattern_checks": 0,
        }
        self._dir_cache.clear()

        # Validate and resolve root
        root_path = Path(root_path).resolve()
        if not root_path.exists():
            raise RFFileNotFoundError(root_path)

        # Build optimized matchers - O(p) where p is number of patterns
        patterns = patterns or self.settings.file_patterns
        self._include_matcher = PatternMatcher.from_patterns(patterns)

        # If callers provide explicit include patterns, don't unexpectedly apply
        # global default excludes unless they also provide explicit excludes.
        exclude_patterns = (
            exclude_patterns
            if exclude_patterns is not None
            else ([] if patterns is not None else self.settings.exclude_patterns)
        )
        self._exclude_trie = PathExclusionTrie()
        for pattern in exclude_patterns:
            self._exclude_trie.add_exclusion(pattern)

        # Collect files - O(n) where n is total files
        files = list(
            self._discover_optimized(root_path, root_path, recursive, max_depth, 0)
        )

        self.logger.info(
            "Optimized discovery complete",
            extra={"files_found": len(files), "stats": self._stats},
        )

        return sorted(files)  # O(n log n) for consistent ordering

    def _discover_optimized(
        self,
        current_path: Path,
        root_path: Path,
        recursive: bool,
        max_depth: int,
        current_depth: int,
    ) -> Iterator[Path]:
        """Optimized discovery with caching and early termination."""
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
        """Return False for binary/control-byte files that cannot be analyzed."""
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
        """Get directory listing with caching."""
        if path in self._dir_cache:
            self._stats["cache_hits"] += 1
            return self._dir_cache[path]

        try:
            entries = list(path.iterdir())
            self._dir_cache[path] = entries
            return entries
        except (PermissionError, OSError):
            return []
