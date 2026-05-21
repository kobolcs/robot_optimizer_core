# tests/unit/analyzers/test_dead_code_strategies.py
"""Tests for _ASTDeadCodeStrategy, _RegexDeadCodeStrategy, and strategy selection."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import pytest

from robot_optimizer_core.analyzers.dead_code import (
    DeadCodeAnalyzer,
    _ASTDeadCodeStrategy,
    _RegexDeadCodeStrategy,
)
from robot_optimizer_core.domain.entities import TestFile

_SIMPLE_ROBOT = """\
*** Test Cases ***
My Test
    Used Keyword

*** Keywords ***
Used Keyword
    No Operation

Unused Keyword
    No Operation
"""

_DUPLICATE_ROBOT = """\
*** Keywords ***
My Keyword
    No Operation

My Keyword
    Log    duplicate
"""


def _make_file(content: str, path: str = "suite.robot") -> TestFile:
    return TestFile(
        path=Path(path),
        content=content,
        size_bytes=len(content),
        last_modified_utc=datetime.now(UTC),
    )


@pytest.mark.unit
class TestASTStrategy:
    def setup_method(self) -> None:
        self.strategy = _ASTDeadCodeStrategy()

    def test_extract_returns_four_tuple(self) -> None:
        keywords, calls, display_names, candidates = self.strategy.extract(
            _make_file(_SIMPLE_ROBOT)
        )
        assert isinstance(keywords, dict)
        assert isinstance(calls, set)
        assert isinstance(display_names, dict)
        assert isinstance(candidates, list)

    def test_detects_keyword_definitions(self) -> None:
        keywords, _, display_names, _ = self.strategy.extract(_make_file(_SIMPLE_ROBOT))
        assert "used keyword" in keywords
        assert "unused keyword" in keywords
        assert display_names["used keyword"] == "Used Keyword"

    def test_resolves_calls(self) -> None:
        _, calls, _, _ = self.strategy.extract(_make_file(_SIMPLE_ROBOT))
        assert "used keyword" in calls
        assert "unused keyword" not in calls

    def test_detects_duplicate_definitions(self) -> None:
        keywords, _, _, _ = self.strategy.extract(_make_file(_DUPLICATE_ROBOT))
        assert len(keywords["my keyword"]) == 2

    def test_raises_on_unparseable_content(self) -> None:
        with mock.patch(
            "robot_optimizer_core.analyzers.dead_code._ASTDeadCodeStrategy.extract",
            side_effect=Exception("parse failure"),
        ), pytest.raises(Exception, match="parse failure"):
            self.strategy.extract(_make_file("not robot content"))

    def test_raw_candidates_include_call_names(self) -> None:
        _, _, _, candidates = self.strategy.extract(_make_file(_SIMPLE_ROBOT))
        assert any("Used Keyword" in c for c in candidates)


@pytest.mark.unit
class TestRegexStrategy:
    def setup_method(self) -> None:
        self.strategy = _RegexDeadCodeStrategy()

    def test_extract_returns_four_tuple(self) -> None:
        keywords, calls, display_names, candidates = self.strategy.extract(
            _make_file(_SIMPLE_ROBOT)
        )
        assert isinstance(keywords, dict)
        assert isinstance(calls, set)
        assert isinstance(display_names, dict)
        assert isinstance(candidates, list)

    def test_detects_keyword_definitions(self) -> None:
        keywords, _, display_names, _ = self.strategy.extract(_make_file(_SIMPLE_ROBOT))
        assert "used keyword" in keywords
        assert "unused keyword" in keywords
        assert display_names["used keyword"] == "Used Keyword"

    def test_resolves_calls(self) -> None:
        _, calls, _, _ = self.strategy.extract(_make_file(_SIMPLE_ROBOT))
        assert "used keyword" in calls
        assert "unused keyword" not in calls

    def test_detects_duplicate_definitions(self) -> None:
        keywords, _, _, _ = self.strategy.extract(_make_file(_DUPLICATE_ROBOT))
        assert len(keywords["my keyword"]) == 2

    def test_handles_empty_content(self) -> None:
        keywords, calls, _, _ = self.strategy.extract(_make_file(""))
        assert keywords == {}
        assert calls == set()

    def test_skips_comment_lines(self) -> None:
        content = """\
*** Keywords ***
# This is a comment
Real Keyword
    No Operation
"""
        keywords, _, _, _ = self.strategy.extract(_make_file(content))
        assert "real keyword" in keywords
        assert "# this is a comment" not in keywords

    def test_skips_numeric_keyword_names(self) -> None:
        content = """\
*** Keywords ***
123 Not A Keyword
    No Operation
"""
        keywords, _, _, _ = self.strategy.extract(_make_file(content))
        assert keywords == {}


@pytest.mark.unit
class TestStrategyConsistency:
    """Both strategies must produce equivalent output for valid Robot files."""

    def _results(self, content: str) -> tuple[tuple, tuple]:
        tf = _make_file(content)
        ast_kw, ast_calls, ast_disp, _ = _ASTDeadCodeStrategy().extract(tf)
        rx_kw, rx_calls, rx_disp, _ = _RegexDeadCodeStrategy().extract(tf)
        return (ast_kw, ast_calls, ast_disp), (rx_kw, rx_calls, rx_disp)

    def test_same_keyword_names(self) -> None:
        (ast_kw, _, _), (rx_kw, _, _) = self._results(_SIMPLE_ROBOT)
        assert set(ast_kw) == set(rx_kw)

    def test_same_calls(self) -> None:
        (_, ast_calls, _), (_, rx_calls, _) = self._results(_SIMPLE_ROBOT)
        assert ast_calls == rx_calls

    def test_same_display_names(self) -> None:
        (_, _, ast_disp), (_, _, rx_disp) = self._results(_SIMPLE_ROBOT)
        assert ast_disp == rx_disp

    def test_same_duplicate_line_count(self) -> None:
        (ast_kw, _, _), (rx_kw, _, _) = self._results(_DUPLICATE_ROBOT)
        assert len(ast_kw["my keyword"]) == len(rx_kw["my keyword"])


@pytest.mark.unit
class TestStrategySelection:
    """DeadCodeAnalyzer picks AST first, falls back to regex on parse failure."""

    def _make_analyzer(self) -> DeadCodeAnalyzer:
        return DeadCodeAnalyzer()

    def test_ast_strategy_is_used_by_default(self) -> None:
        analyzer = self._make_analyzer()
        tf = _make_file(_SIMPLE_ROBOT)
        with mock.patch.object(
            analyzer._ast_strategy, "extract", wraps=analyzer._ast_strategy.extract
        ) as ast_spy:
            analyzer._extract_keywords_and_calls(tf)
        ast_spy.assert_called_once_with(tf)

    def test_regex_strategy_used_when_ast_fails(self) -> None:
        analyzer = self._make_analyzer()
        tf = _make_file(_SIMPLE_ROBOT)
        with mock.patch.object(
            analyzer._ast_strategy, "extract", side_effect=RuntimeError("bad parse")
        ), mock.patch.object(
            analyzer._regex_strategy, "extract", wraps=analyzer._regex_strategy.extract
        ) as rx_spy:
            analyzer._extract_keywords_and_calls(tf)
        rx_spy.assert_called_once_with(tf)

    def test_regex_strategy_not_used_when_ast_succeeds(self) -> None:
        analyzer = self._make_analyzer()
        tf = _make_file(_SIMPLE_ROBOT)
        with mock.patch.object(
            analyzer._regex_strategy, "extract", wraps=analyzer._regex_strategy.extract
        ) as rx_spy:
            analyzer._extract_keywords_and_calls(tf)
        rx_spy.assert_not_called()

    def test_fallback_result_is_used_for_analysis(self) -> None:
        """End-to-end: analyzer still produces findings when AST parse fails."""
        analyzer = self._make_analyzer()
        tf = _make_file(_SIMPLE_ROBOT)
        with mock.patch.object(
            analyzer._ast_strategy, "extract", side_effect=RuntimeError("bad parse")
        ):
            findings = analyzer.analyze(tf)
        unused = [f for f in findings if "never used" in f.message]
        assert len(unused) == 1
        assert "Unused Keyword" in unused[0].message

    def test_ast_strategy_is_ast_instance(self) -> None:
        analyzer = self._make_analyzer()
        assert isinstance(analyzer._ast_strategy, _ASTDeadCodeStrategy)

    def test_regex_strategy_is_regex_instance(self) -> None:
        analyzer = self._make_analyzer()
        assert isinstance(analyzer._regex_strategy, _RegexDeadCodeStrategy)
