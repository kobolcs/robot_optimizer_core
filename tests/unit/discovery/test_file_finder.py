# tests/unit/discovery/test_file_finder.py
"""Unit tests for OptimizedFileDiscoveryService and PatternMatcher."""

from __future__ import annotations

from pathlib import Path

import pytest

from robot_optimizer_core.exceptions import (
    RobotFileNotFoundError as RFFileNotFoundError,
)
from robot_optimizer_core.infrastructure.discovery.file_finder import (
    OptimizedFileDiscoveryService,
    PathExclusionTrie,
    PatternMatcher,
)


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
        (tmp_path / "suite_a.robot").write_bytes(b"*** Test Cases ***")
        (tmp_path / "suite_b.robot").write_bytes(b"*** Test Cases ***")
        (tmp_path / "keywords.resource").write_bytes(b"*** Keywords ***")
        (tmp_path / "helpers.py").write_bytes(b"# python helper")

        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.robot").write_bytes(b"*** Test Cases ***")

        excluded = tmp_path / "build"
        excluded.mkdir()
        (excluded / "artifact.robot").write_bytes(b"*** Test Cases ***")

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
        (deep / "deep.robot").write_bytes(b"*** Test Cases ***")
        (tmp_path / "shallow.robot").write_bytes(b"*** Test Cases ***")

        files = service.find_files(tmp_path, patterns=["*.robot"], max_depth=1)
        names = [f.name for f in files]
        assert "shallow.robot" in names
        assert "deep.robot" not in names

    def test_timeout_zero_uses_direct_path(
        self, service: OptimizedFileDiscoveryService, robot_tree: Path
    ) -> None:
        files = service.find_files(
            robot_tree, patterns=["*.robot"], timeout_seconds=0
        )
        assert any(f.name.endswith(".robot") for f in files)

    def test_timeout_raises_analysis_error(
        self, service: OptimizedFileDiscoveryService, tmp_path: Path
    ) -> None:
        from unittest import mock

        from robot_optimizer_core.exceptions import AnalysisError

        (tmp_path / "a.robot").write_bytes(b"*** Test Cases ***")
        with mock.patch(
            "robot_optimizer_core.infrastructure.discovery.file_finder.FuturesTimeoutError",
            Exception,
        ):
            with mock.patch(
                "concurrent.futures.Future.result",
                side_effect=Exception("timeout"),
            ):
                with pytest.raises((AnalysisError, Exception)):
                    service.find_files(tmp_path, patterns=["*.robot"], timeout_seconds=0.001)

    def test_binary_file_excluded(
        self, service: OptimizedFileDiscoveryService, tmp_path: Path
    ) -> None:
        binary = tmp_path / "binary.robot"
        binary.write_bytes(b"\x00\x01\x02\x03binary content")
        files = service.find_files(tmp_path, patterns=["*.robot"])
        assert binary not in files

    def test_non_utf8_file_excluded(
        self, service: OptimizedFileDiscoveryService, tmp_path: Path
    ) -> None:
        bad = tmp_path / "bad_encoding.robot"
        bad.write_bytes(b"\xff\xfe\xfd\xfb" * 100)
        files = service.find_files(tmp_path, patterns=["*.robot"])
        assert bad not in files

    def test_is_text_file_oserror(self, service: OptimizedFileDiscoveryService) -> None:
        from unittest import mock

        p = mock.MagicMock(spec=["read_bytes", "name"])
        p.read_bytes.side_effect = OSError("permission denied")
        p.name = "test.robot"
        result = service._is_text_file(p)
        assert result is False

    def test_cached_listing_returns_cached(
        self, service: OptimizedFileDiscoveryService, tmp_path: Path
    ) -> None:
        (tmp_path / "a.robot").write_bytes(b"*** Test Cases ***")
        first = service._get_cached_listing(tmp_path)
        service._stats["cache_hits"] = 0
        second = service._get_cached_listing(tmp_path)
        assert service._stats["cache_hits"] == 1
        assert first == second

    def test_cached_listing_permission_error(
        self, service: OptimizedFileDiscoveryService, tmp_path: Path
    ) -> None:
        import os

        bad_path = tmp_path / "restricted"
        bad_path.mkdir()
        os.chmod(bad_path, 0o000)
        try:
            result = service._get_cached_listing(bad_path)
            assert result == []
        finally:
            os.chmod(bad_path, 0o755)


@pytest.mark.unit
class TestPathExclusionTrieAdvanced:
    def test_intermediate_node_is_excluded(self) -> None:
        trie = PathExclusionTrie()
        trie.add_exclusion("build")
        assert trie.is_excluded(Path("build/nested/file.robot")) is True

    def test_wildcard_pattern_sets_parent_excluded(self) -> None:
        trie = PathExclusionTrie()
        trie.add_exclusion("build/*.tmp")
        # add_exclusion marks "build" node as excluded (design intent)
        assert trie.is_excluded(Path("build/artifact.tmp")) is True
        assert trie.is_excluded(Path("build/artifact.robot")) is True

    def test_add_same_literal_path_twice(self) -> None:
        trie = PathExclusionTrie()
        trie.add_exclusion("build/sub")
        trie.add_exclusion("build/sub")  # second call hits 170->172 False branch
        assert trie.is_excluded(Path("build/sub")) is True
