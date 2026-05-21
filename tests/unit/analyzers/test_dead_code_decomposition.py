# tests/unit/analyzers/test_dead_code_decomposition.py
"""Tests for the decomposed AST walking methods on _ASTDeadCodeStrategy."""

from __future__ import annotations

import pytest

from robot_optimizer_core.analyzers.dead_code import (
    DeadCodeAnalyzer,
    _ASTDeadCodeStrategy,
)


@pytest.mark.unit
class TestDeadCodeWalkDecomposition:
    def setup_method(self) -> None:
        self.strategy = _ASTDeadCodeStrategy()

    def test_walk_body_ignores_none(self) -> None:
        calls: list[str] = []
        self.strategy._walk_body(None, calls)  # type: ignore[arg-type]
        assert calls == []

    def test_walk_body_ignores_integer(self) -> None:
        calls: list[str] = []
        self.strategy._walk_body(42, calls)  # type: ignore[arg-type]
        assert calls == []

    def test_resolve_no_keyword_attr(self) -> None:
        class FakeItem:
            pass
        assert self.strategy._resolve_keyword_call_name(FakeItem()) is None

    def test_resolve_run_keyword(self) -> None:
        class FakeItem:
            keyword = "Run Keyword"
            args = ("My Target",)
        assert self.strategy._resolve_keyword_call_name(FakeItem()) == "Run Keyword My Target"

    def test_resolve_run_keywords(self) -> None:
        class FakeItem:
            keyword = "Run Keywords"
            args = ("KW One", "KW Two")
        assert self.strategy._resolve_keyword_call_name(FakeItem()) == "Run Keywords KW One KW Two"

    def test_resolve_plain_keyword(self) -> None:
        class FakeItem:
            keyword = "My Keyword"
            args = ()
        assert self.strategy._resolve_keyword_call_name(FakeItem()) == "My Keyword"

    def test_iter_nested_bodies_body(self) -> None:
        class FakeItem:
            body = [1, 2]
        assert [1, 2] in list(self.strategy._iter_nested_bodies(FakeItem()))

    def test_iter_nested_bodies_empty(self) -> None:
        class FakeItem:
            pass
        assert list(self.strategy._iter_nested_bodies(FakeItem())) == []

    def test_iter_nested_bodies_try_linked_list(self) -> None:
        """Test that Try nodes are walked via .next linked list (RF 7.1+)."""
        class FakeTryNode:
            type = "TRY"
            body = ["try_body"]
            next = None
            finalbody = None

        class FakeExceptNode:
            type = "TRY"
            body = ["except_body"]
            next = None
            finalbody = None

        class FakeFinallyNode:
            type = "TRY"
            body = ["finally_body"]
            next = None
            finalbody = ["finalbody_content"]

        # Link them together: TRY -> EXCEPT -> FINALLY
        try_node = FakeTryNode()
        except_node = FakeExceptNode()
        finally_node = FakeFinallyNode()
        try_node.next = except_node
        except_node.next = finally_node

        # Collect all yielded bodies
        bodies = list(self.strategy._iter_nested_bodies(try_node))
        # Should yield: try body, except body, finally body, finalbody
        assert ["try_body"] in bodies
        assert ["except_body"] in bodies
        assert ["finally_body"] in bodies
        assert ["finalbody_content"] in bodies

    def test_analyzer_uses_ast_strategy_by_default(self) -> None:
        """DeadCodeAnalyzer._ast_strategy is an _ASTDeadCodeStrategy instance."""
        analyzer = DeadCodeAnalyzer()
        assert isinstance(analyzer._ast_strategy, _ASTDeadCodeStrategy)
