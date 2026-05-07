# tests/unit/analyzers/test_dead_code_decomposition.py
"""Tests for the decomposed AST walking methods."""

from __future__ import annotations

import pytest

from robot_optimizer_core.analyzers.dead_code import DeadCodeAnalyzer


@pytest.mark.unit
class TestDeadCodeWalkDecomposition:
    def setup_method(self) -> None:
        self.analyzer = DeadCodeAnalyzer()

    def test_walk_body_ignores_none(self) -> None:
        calls: list[str] = []
        self.analyzer._walk_body(None, calls)  # type: ignore[arg-type]
        assert calls == []

    def test_walk_body_ignores_integer(self) -> None:
        calls: list[str] = []
        self.analyzer._walk_body(42, calls)  # type: ignore[arg-type]
        assert calls == []

    def test_resolve_no_keyword_attr(self) -> None:
        class FakeItem:
            pass
        assert self.analyzer._resolve_keyword_call_name(FakeItem()) is None

    def test_resolve_run_keyword(self) -> None:
        class FakeItem:
            keyword = "Run Keyword"
            args = ("My Target",)
        assert self.analyzer._resolve_keyword_call_name(FakeItem()) == "Run Keyword My Target"

    def test_resolve_run_keywords(self) -> None:
        class FakeItem:
            keyword = "Run Keywords"
            args = ("KW One", "KW Two")
        assert self.analyzer._resolve_keyword_call_name(FakeItem()) == "Run Keywords KW One KW Two"

    def test_resolve_plain_keyword(self) -> None:
        class FakeItem:
            keyword = "My Keyword"
            args = ()
        assert self.analyzer._resolve_keyword_call_name(FakeItem()) == "My Keyword"

    def test_iter_nested_bodies_body(self) -> None:
        class FakeItem:
            body = [1, 2]
        assert [1, 2] in list(self.analyzer._iter_nested_bodies(FakeItem()))

    def test_iter_nested_bodies_empty(self) -> None:
        class FakeItem:
            pass
        assert list(self.analyzer._iter_nested_bodies(FakeItem())) == []
