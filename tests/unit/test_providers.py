# tests/unit/test_providers.py
"""Unit tests for file I/O providers."""

from __future__ import annotations

from pathlib import Path

import pytest

from robot_optimizer_core.providers import DiskFileProvider, InMemoryFileProvider


@pytest.mark.unit
class TestDiskFileProvider:
    def test_load_reads_file_content(self, tmp_path: Path) -> None:
        f = tmp_path / "a.robot"
        f.write_text("hello", encoding="utf-8")
        provider = DiskFileProvider()
        assert provider.load(f) == "hello"

    def test_load_accepts_string_path(self, tmp_path: Path) -> None:
        f = tmp_path / "b.robot"
        f.write_text("world", encoding="utf-8")
        provider = DiskFileProvider()
        assert provider.load(str(f)) == "world"

    def test_load_raises_for_missing_file(self, tmp_path: Path) -> None:
        provider = DiskFileProvider()
        with pytest.raises(FileNotFoundError):
            provider.load(tmp_path / "nonexistent.robot")

    def test_exists_true_for_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "c.robot"
        f.write_text("x", encoding="utf-8")
        provider = DiskFileProvider()
        assert provider.exists(f) is True

    def test_exists_false_for_missing_file(self, tmp_path: Path) -> None:
        provider = DiskFileProvider()
        assert provider.exists(Path("/no/such/file.robot")) is False

    def test_exists_accepts_string_path(self, tmp_path: Path) -> None:
        f = tmp_path / "d.robot"
        f.write_text("x", encoding="utf-8")
        provider = DiskFileProvider()
        assert provider.exists(str(f)) is True


@pytest.mark.unit
class TestInMemoryFileProvider:
    def test_load_returns_content(self) -> None:
        provider = InMemoryFileProvider({"test.robot": "content"})
        assert provider.load(Path("test.robot")) == "content"

    def test_load_raises_for_missing_file(self) -> None:
        provider = InMemoryFileProvider()
        with pytest.raises(FileNotFoundError, match="not in memory"):
            provider.load(Path("missing.robot"))

    def test_exists_true_for_added_file(self) -> None:
        provider = InMemoryFileProvider({"a.robot": "x"})
        assert provider.exists(Path("a.robot")) is True

    def test_exists_false_for_missing(self) -> None:
        provider = InMemoryFileProvider()
        assert provider.exists(Path("nope.robot")) is False

    def test_add_stores_file(self) -> None:
        provider = InMemoryFileProvider()
        provider.add("new.robot", "new content")
        assert provider.load(Path("new.robot")) == "new content"

    def test_add_accepts_path_object(self) -> None:
        provider = InMemoryFileProvider()
        provider.add(Path("path_obj.robot"), "data")
        assert provider.exists(Path("path_obj.robot")) is True

    def test_clear_removes_all_files(self) -> None:
        provider = InMemoryFileProvider({"a.robot": "a", "b.robot": "b"})
        provider.clear()
        assert provider.exists(Path("a.robot")) is False
        assert provider.files == {}

    def test_init_with_none_files(self) -> None:
        provider = InMemoryFileProvider(None)
        assert provider.files == {}

    def test_init_with_multiple_files(self) -> None:
        provider = InMemoryFileProvider({"a.robot": "x", "b.robot": "y"})
        assert provider.exists(Path("a.robot")) is True
        assert provider.exists(Path("b.robot")) is True
