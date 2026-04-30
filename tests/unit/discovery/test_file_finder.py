# tests/unit/discovery/test_file_finder.py
"""Unit tests for OptimizedFileDiscoveryService and PatternMatcher."""

from __future__ import annotations

from pathlib import Path

import pytest

from robot_optimizer_core.discovery.file_finder import (
    OptimizedFileDiscoveryService,
    PathExclusionTrie,
    PatternMatcher,
)
from robot_optimizer_core.exceptions import RobotFileNotFoundError as RFFileNotFoundError


@pytest.mark.unit
class TestPatternMatcher:
    def test_simple_extension_match(self) -> None:
        matcher = PatternMatcher.from_patterns(["*.robot"])
        assert matcher.matches("test_suite.robot") is True
        assert matcher.matches("test_suite.py") is False

    def test_multiple_extensions(self) -> None:
        matcher = PatternMatcher.from_patterns(["*.robot", "*.resource"])
        assert matcher.matches("keywords.resource") is True
        assert matcher.matches("suite.robot") is True
        assert matcher.matches("conftest.py") is False

    def test_exact_filename_match(self) -> None:
        matcher = PatternMatcher.from_patterns(["conftest.robot"])
        assert matcher.matches("conftest.robot") is True
        assert matcher.matches("other.robot") is False

    def test_glob_pattern(self) -> None:
        matcher = PatternMatcher.from_patterns(["test_*.robot"])
        assert matcher.matches("test_login.robot") is True
        assert matcher.matches("login.robot") is False

    def test_case_insensitive(self) -> None:
        matcher = PatternMatcher.from_patterns(["*.robot"])
        assert matcher.matches("Suite.ROBOT") is True
        assert matcher.matches("Suite.Robot") is True

    def test_no_patterns_matches_nothing(self) -> None:
        matcher = PatternMatcher.from_patterns([])
        assert matcher.matches("anything.robot") is False


@pytest.mark.unit
class TestPathExclusionTrie:
    def test_excludes_simple_directory(self) -> None:
        trie = PathExclusionTrie()
        trie.add_exclusion("build")
        assert trie.is_excluded(Path("build")) is True

    def test_non_excluded_path(self) -> None:
        trie = PathExclusionTrie()
        trie.add_exclusion("build")
        assert trie.is_excluded(Path("src")) is False

    def test_pattern_exclusion(self) -> None:
        trie = PathExclusionTrie()
        trie.add_exclusion("**/__pycache__")
        # Pattern nodes match at the component level
        assert trie.is_excluded(Path("__pycache__")) is True

    def test_empty_trie_excludes_nothing(self) -> None:
        trie = PathExclusionTrie()
        assert trie.is_excluded(Path("anything")) is False

    def test_glob_star_star_does_not_exclude_unrelated_paths(self) -> None:
        """Adding **/__pycache__ must not exclude all other paths (regression)."""
        trie = PathExclusionTrie()
        trie.add_exclusion("**/__pycache__")
        # __pycache__ at any depth should be excluded
        assert trie.is_excluded(Path("__pycache__")) is True
        assert trie.is_excluded(Path("src/__pycache__")) is True
        # Unrelated paths must NOT be excluded
        assert trie.is_excluded(Path("src")) is False
        assert trie.is_excluded(Path("tests")) is False

    def test_multiple_glob_patterns_independent(self) -> None:
        """Multiple **-patterns each exclude only their own component."""
        trie = PathExclusionTrie()
        trie.add_exclusion("**/__pycache__")
        trie.add_exclusion("**/node_modules")
        assert trie.is_excluded(Path("__pycache__")) is True
        assert trie.is_excluded(Path("node_modules")) is True
        assert trie.is_excluded(Path("src")) is False

    def test_hidden_file_pattern(self) -> None:
        """**/.*  must match hidden files/dirs but not regular ones."""
        trie = PathExclusionTrie()
        trie.add_exclusion("**/.*")
        assert trie.is_excluded(Path(".hidden")) is True
        assert trie.is_excluded(Path(".venv")) is True
        assert trie.is_excluded(Path("src")) is False


@pytest.mark.unit
class TestOptimizedFileDiscoveryService:
    @pytest.fixture
    def service(self) -> OptimizedFileDiscoveryService:
        return OptimizedFileDiscoveryService()

    @pytest.fixture
    def robot_tree(self, tmp_path: Path) -> Path:
        """Create a tree of robot files for discovery tests."""
        (tmp_path / "suite_a.robot").write_text("*** Test Cases ***")
        (tmp_path / "suite_b.robot").write_text("*** Test Cases ***")
        (tmp_path / "keywords.resource").write_text("*** Keywords ***")
        (tmp_path / "helpers.py").write_text("# python helper")

        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.robot").write_text("*** Test Cases ***")

        excluded = tmp_path / "build"
        excluded.mkdir()
        (excluded / "artifact.robot").write_text("*** Test Cases ***")

        return tmp_path

    def test_finds_robot_files(
        self, service: OptimizedFileDiscoveryService, robot_tree: Path
    ) -> None:
        files = service.find_files(robot_tree, patterns=["*.robot", "*.resource"])
        names = [f.name for f in files]
        assert "suite_a.robot" in names
        assert "suite_b.robot" in names
        assert "keywords.resource" in names

    def test_ignores_non_matching_files(
        self, service: OptimizedFileDiscoveryService, robot_tree: Path
    ) -> None:
        files = service.find_files(robot_tree, patterns=["*.robot"])
        assert not any(f.suffix == ".py" for f in files)

    def test_recursive_discovery(
        self, service: OptimizedFileDiscoveryService, robot_tree: Path
    ) -> None:
        files = service.find_files(robot_tree, patterns=["*.robot"])
        names = [f.name for f in files]
        assert "nested.robot" in names

    def test_non_recursive_skips_subdirs(
        self, service: OptimizedFileDiscoveryService, robot_tree: Path
    ) -> None:
        files = service.find_files(robot_tree, patterns=["*.robot"], recursive=False)
        assert not any(f.parent != robot_tree for f in files)

    def test_exclude_patterns(
        self, service: OptimizedFileDiscoveryService, robot_tree: Path
    ) -> None:
        files = service.find_files(
            robot_tree,
            patterns=["*.robot"],
            exclude_patterns=["build"],
        )
        assert not any("build" in str(f) for f in files)

    def test_result_is_sorted(
        self, service: OptimizedFileDiscoveryService, robot_tree: Path
    ) -> None:
        files = service.find_files(robot_tree, patterns=["*.robot"])
        assert files == sorted(files)

    def test_nonexistent_root_raises(
        self, service: OptimizedFileDiscoveryService
    ) -> None:
        with pytest.raises(RFFileNotFoundError):
            service.find_files(Path("/nonexistent/path/xyz"))

    def test_empty_directory_returns_empty(
        self, service: OptimizedFileDiscoveryService, tmp_path: Path
    ) -> None:
        assert service.find_files(tmp_path, patterns=["*.robot"]) == []

    def test_max_depth_limits_recursion(
        self, service: OptimizedFileDiscoveryService, tmp_path: Path
    ) -> None:
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / "deep.robot").write_text("*** Test Cases ***")
        (tmp_path / "shallow.robot").write_text("*** Test Cases ***")

        files = service.find_files(tmp_path, patterns=["*.robot"], max_depth=1)
        names = [f.name for f in files]
        assert "shallow.robot" in names
        assert "deep.robot" not in names
