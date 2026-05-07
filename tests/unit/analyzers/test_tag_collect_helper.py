# tests/unit/analyzers/test_tag_collect_helper.py
"""Tests for TagConsistencyAnalyzer._collect_tag_info."""

from __future__ import annotations

import pytest

from robot_optimizer_core.analyzers.tag_consistency import TagConsistencyAnalyzer


@pytest.mark.unit
class TestCollectTagInfo:
    def setup_method(self) -> None:
        self.analyzer = TagConsistencyAnalyzer()

    def test_empty_returns_empty(self) -> None:
        assert self.analyzer._collect_tag_info([]) == []

    def test_single_test_with_tags(self) -> None:
        lines = [
            "*** Test Cases ***",
            "My Test",
            "    [Tags]    smoke  regression",
            "    Log    hi",
        ]
        result = self.analyzer._collect_tag_info(lines)
        assert len(result) == 1
        name, line_num, tags = result[0]
        assert name == "My Test"
        assert line_num == 2
        assert "smoke" in tags
        assert "regression" in tags

    def test_multiple_tests(self) -> None:
        lines = [
            "*** Test Cases ***", "Test One", "    [Tags]    a",
            "Test Two", "    [Tags]    b",
        ]
        result = self.analyzer._collect_tag_info(lines)
        assert [r[0] for r in result] == ["Test One", "Test Two"]

    def test_test_without_tags(self) -> None:
        lines = ["*** Test Cases ***", "My Test", "    Log    hi"]
        assert self.analyzer._collect_tag_info(lines)[0][2] == []

    def test_ignores_keyword_sections(self) -> None:
        lines = ["*** Keywords ***", "My KW", "    [Tags]    ignored"]
        assert self.analyzer._collect_tag_info(lines) == []
