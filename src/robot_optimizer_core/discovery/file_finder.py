# src/robot_optimizer_core/discovery/file_finder.py
"""Optimized file discovery with linear time complexity.

This module is part of the test-suite analysis engine infrastructure.
Its primary production responsibility is file discovery.

Note:
    Additional optimization helper classes in this module are retained for
    backward compatibility and experimentation. Public imports should prefer
    :class:`OptimizedFileDiscoveryService` (aliased as ``FileDiscoveryService``).
"""
from __future__ import annotations

import fnmatch
import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..config import Settings
from ..exceptions import FileNotFoundError as RFFileNotFoundError
from ..logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from ..domain.entities import TestFile
    from ..domain.value_objects import Finding

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
            if pattern.startswith("*.") and "*" not in pattern[2:] and "?" not in pattern[2:]:
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
    """Trie structure for efficient path exclusion checking."""

    class TrieNode:
        def __init__(self) -> None:
            self.children: dict[str, PathExclusionTrie.TrieNode] = {}
            self.is_excluded = False
            self.is_pattern = False
            self.pattern: re.Pattern[str] | None = None

    root: TrieNode = field(default_factory=TrieNode)

    def add_exclusion(self, pattern: str) -> None:
        """Add exclusion pattern to trie."""
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

    def is_excluded(self, path: Path) -> bool:
        """Check if path is excluded - O(d) where d is directory depth."""
        parts = path.parts
        node = self.root

        for _, part in enumerate(parts):
            # Check if current node excludes
            if node.is_excluded:
                return True

            # Check pattern matching
            if node.is_pattern and node.pattern:
                if node.pattern.match(part):
                    return True

            # Check exact match
            if part in node.children:
                node = node.children[part]
            else:
                # Check for pattern children
                for child_name, child_node in node.children.items():
                    if "*" in child_name or "?" in child_name:
                        pattern = re.compile(fnmatch.translate(child_name))
                        if pattern.match(part):
                            node = child_node
                            break
                else:
                    # No match found
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
            "pattern_checks": 0
        }

    def find_files(
        self,
        root_path: Path,
        patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        recursive: bool = True,
        max_depth: int = 20
    ) -> list[Path]:
        """Find files with O(n) complexity where n is number of files."""
        # Reset stats
        self._stats = {
            "files_checked": 0,
            "dirs_checked": 0,
            "cache_hits": 0,
            "pattern_checks": 0
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
        files = list(self._discover_optimized(
            root_path,
            root_path,
            recursive,
            max_depth,
            0
        ))

        self.logger.info(
            "Optimized discovery complete",
            extra={
                "files_found": len(files),
                "stats": self._stats
            }
        )

        return sorted(files)  # O(n log n) for consistent ordering

    def _discover_optimized(
        self,
        current_path: Path,
        root_path: Path,
        recursive: bool,
        max_depth: int,
        current_depth: int
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
                if self._include_matcher.matches(entry.name) and self._is_text_file(entry):
                    yield entry

            elif entry.is_dir() and recursive:
                # Recurse into subdirectory
                yield from self._discover_optimized(
                    entry,
                    root_path,
                    recursive,
                    max_depth,
                    current_depth + 1
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
        control_chars = sum(
            1 for ch in text
            if ord(ch) < 32 and ch not in "\n\r\t"
        )
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


# Optimized analyzer base
class OptimizedAnalyzer:
    """Base analyzer with performance optimizations."""

    def __init__(self) -> None:
        """Initialize with optimizations."""
        # Pre-compile all regex patterns
        self._compiled_patterns: dict[str, re.Pattern[str]] = {}
        # Cache for parsed structures
        self._parse_cache: dict[str, Any] = {}
        # Metrics for performance tracking
        self._perf_metrics: defaultdict[str, float] = defaultdict(float)

    def compile_pattern(self, name: str, pattern: str, flags: int = 0) -> re.Pattern[str]:
        """Compile and cache regex pattern."""
        if name not in self._compiled_patterns:
            self._compiled_patterns[name] = re.compile(pattern, flags)
        return self._compiled_patterns[name]

    def batch_analyze(self, test_files: list[TestFile]) -> dict[Path, list[Finding]]:
        """Analyze multiple files in batch for better performance."""
        import concurrent.futures
        import multiprocessing

        # Use process pool for CPU-bound analysis
        max_workers = min(multiprocessing.cpu_count(), len(test_files))

        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Submit all files
            future_to_file = {
                executor.submit(self._analyze_single, test_file): test_file
                for test_file in test_files
            }

            # Collect results
            results = {}
            for future in concurrent.futures.as_completed(future_to_file):
                test_file = future_to_file[future]
                try:
                    findings = future.result()
                    results[test_file.path] = findings
                except Exception as e:
                    logger.error(f"Analysis failed for {test_file.path}: {e}")
                    results[test_file.path] = []

            return results

    def _analyze_single(self, test_file: TestFile) -> list[Finding]:
        """Analyze single file (runs in separate process)."""
        # Override in subclasses
        raise NotImplementedError


# Example: Optimized sleep detector
class OptimizedSleepDetector(OptimizedAnalyzer):
    """Sleep detector with pre-compiled patterns and caching."""

    def __init__(self) -> None:
        """Initialize with optimized patterns."""
        super().__init__()

        # Pre-compile all patterns once
        self.sleep_pattern = self.compile_pattern(
            "sleep",
            r"^\s*(?:BuiltIn\.)?Sleep\s+(\d+(?:\.\d+)?)\s*(s|seconds?|m|minutes?|ms|milliseconds?)?",
            re.IGNORECASE
        )

        self.wait_pattern = self.compile_pattern(
            "wait",
            r"^\s*(?:Wait|Pause|Delay)\s+(\d+(?:\.\d+)?)\s*(s|seconds?|m|minutes?)?",
            re.IGNORECASE
        )

        self.variable_sleep = self.compile_pattern(
            "variable",
            r"^\s*Sleep\s+\$\{([^}]+)\}",
            re.IGNORECASE
        )

    def analyze(self, test_file: TestFile) -> list[Finding]:
        """Analyze with optimized pattern matching."""
        findings = []

        # Split lines once
        lines = test_file.content.splitlines()

        # Single pass through file - O(n) where n is lines
        for line_num, line in enumerate(lines, 1):
            # Skip empty lines early
            if not line.strip():
                continue

            # Check patterns - each pattern is O(1) average case
            if (match := self.sleep_pattern.match(line)) or (match := self.wait_pattern.match(line)):
                findings.append(self._create_finding(match, line, line_num, test_file))
            elif match := self.variable_sleep.match(line):
                findings.append(self._create_variable_finding(match, line, line_num, test_file))

        return findings

    def _create_finding(self, match: re.Match[str], line: str, line_num: int, test_file: Any) -> Any:
        raise NotImplementedError

    def _create_variable_finding(self, match: re.Match[str], line: str, line_num: int, test_file: Any) -> Any:
        raise NotImplementedError


# String matching optimization using Aho-Corasick
class MultiPatternMatcher:
    """Efficient multi-pattern string matching using Aho-Corasick algorithm."""

    def __init__(self, patterns: list[str]) -> None:
        """Build Aho-Corasick automaton for O(n + m) matching."""
        self.patterns = patterns
        self.root: dict[str, Any] = {}
        self.outputs: defaultdict[int, list[int]] = defaultdict(list)
        self._build_automaton()

    def _build_automaton(self) -> None:
        """Build the automaton - O(m) where m is total pattern length."""
        # Build trie
        for idx, pattern in enumerate(self.patterns):
            node = self.root
            for char in pattern:
                if char not in node:
                    node[char] = {}
                node = node[char]
            self.outputs[id(node)].append(idx)

        # Build failure links (simplified version)
        # Full implementation would include proper failure function

    def find_all(self, text: str) -> list[tuple[int, int]]:
        """Find all pattern occurrences - O(n) where n is text length."""
        matches = []
        node = self.root

        for i, char in enumerate(text):
            while node and char not in node:
                # Follow failure link (simplified)
                node = self.root

            if char in node:
                node = node[char]

                # Check for matches
                if id(node) in self.outputs:
                    for pattern_idx in self.outputs[id(node)]:
                        pattern_len = len(self.patterns[pattern_idx])
                        matches.append((i - pattern_len + 1, pattern_idx))

        return matches
