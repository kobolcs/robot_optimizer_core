# tests/unit/analyzers/test_setup_teardown_internals.py
"""Coverage tests for SetupTeardownAnalyzer private text-parsing helpers.

The public analyze() method delegates to the AST parser, but the class also
contains text-based helpers (_extract_keyword_call, _classify_indented_line,
_parse_test_steps) that implement an alternative parsing path. These tests
exercise them directly to ensure the logic is correct and covered.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from robot_optimizer_core.application.analyzers import SetupTeardownAnalyzer
from robot_optimizer_core.domain.entities import TestFile


def _make_file(content: str, name: str = "test.robot") -> TestFile:
    return TestFile(
        path=Path(name),
        content=content,
        size_bytes=len(content),
        last_modified_utc=datetime.now(),
    )


@pytest.mark.unit
class TestExtractKeywordCall:
    """_extract_keyword_call strips variable-assignment prefixes."""

    def setup_method(self) -> None:
        self.a = SetupTeardownAnalyzer()

    def test_plain_keyword_unchanged(self) -> None:
        assert self.a._extract_keyword_call("Open Browser") == "Open Browser"

    def test_variable_assignment_stripped(self) -> None:
        assert self.a._extract_keyword_call("${result} =    Open Browser") == "Open Browser"

    def test_variable_assignment_no_trailing_space(self) -> None:
        result = self.a._extract_keyword_call("${x}=Keyword Name")
        assert result == "Keyword Name"

    def test_no_brace_prefix_unchanged(self) -> None:
        assert self.a._extract_keyword_call("Log    message") == "Log    message"

    def test_dollar_without_brace_unchanged(self) -> None:
        assert self.a._extract_keyword_call("$result = Keyword") == "$result = Keyword"


@pytest.mark.unit
class TestClassifyIndentedLine:
    """_classify_indented_line categorises robot test step lines."""

    def setup_method(self) -> None:
        self.a = SetupTeardownAnalyzer()

    def test_setup_line_recognised(self) -> None:
        is_setup, is_teardown, kw = self.a._classify_indented_line("[Setup]    Open Browser")
        assert is_setup is True
        assert is_teardown is False
        assert kw is None

    def test_teardown_line_recognised(self) -> None:
        is_setup, is_teardown, kw = self.a._classify_indented_line("[Teardown]    Close Browser")
        assert is_setup is False
        assert is_teardown is True
        assert kw is None

    def test_empty_bracketed_tag_is_neither(self) -> None:
        # "[Tags]" (no value) starts and ends with ] so matches the bracket filter.
        is_setup, is_teardown, kw = self.a._classify_indented_line("[Tags]")
        assert is_setup is False
        assert is_teardown is False
        assert kw is None

    def test_bracketed_tag_with_value_is_treated_as_keyword(self) -> None:
        # "[Tags]    smoke" doesn't end with ], so it falls through to keyword extraction.
        is_setup, is_teardown, kw = self.a._classify_indented_line("[Tags]    smoke")
        assert is_setup is False
        assert is_teardown is False
        assert kw is not None  # treated as a keyword call line

    def test_comment_line_is_neither(self) -> None:
        is_setup, is_teardown, kw = self.a._classify_indented_line("# a comment")
        assert is_setup is False
        assert is_teardown is False
        assert kw is None

    def test_normal_keyword_returned(self) -> None:
        is_setup, is_teardown, kw = self.a._classify_indented_line("Log    message")
        assert is_setup is False
        assert is_teardown is False
        assert kw == "Log    message"

    def test_variable_assignment_stripped_in_keyword(self) -> None:
        is_setup, is_teardown, kw = self.a._classify_indented_line("${x} =    Open Browser")
        assert kw == "Open Browser"

    def test_setup_case_insensitive(self) -> None:
        is_setup, _, _ = self.a._classify_indented_line("[setup]    Something")
        assert is_setup is True

    def test_teardown_case_insensitive(self) -> None:
        _, is_teardown, _ = self.a._classify_indented_line("[TEARDOWN]    Something")
        assert is_teardown is True


@pytest.mark.unit
class TestParseTestSteps:
    """_parse_test_steps parses robot content into structured tuples."""

    def setup_method(self) -> None:
        self.a = SetupTeardownAnalyzer()

    def test_simple_test_returns_one_tuple(self) -> None:
        content = "*** Test Cases ***\nMy Test\n    Log    hello\n"
        result = self.a._parse_test_steps(_make_file(content))
        assert len(result) == 1
        name, line, steps, has_setup, has_teardown = result[0]
        assert name == "My Test"
        assert "Log    hello" in steps
        assert has_setup is False
        assert has_teardown is False

    def test_setup_hook_detected(self) -> None:
        content = (
            "*** Test Cases ***\nMy Test\n"
            "    [Setup]    Open Browser\n"
            "    Log    done\n"
        )
        result = self.a._parse_test_steps(_make_file(content))
        assert result[0][3] is True  # has_setup

    def test_teardown_hook_detected(self) -> None:
        content = (
            "*** Test Cases ***\nMy Test\n"
            "    Log    done\n"
            "    [Teardown]    Close Browser\n"
        )
        result = self.a._parse_test_steps(_make_file(content))
        assert result[0][4] is True  # has_teardown

    def test_multiple_tests_all_returned(self) -> None:
        content = (
            "*** Test Cases ***\n"
            "Test A\n    Log    a\n\n"
            "Test B\n    Log    b\n"
        )
        result = self.a._parse_test_steps(_make_file(content))
        assert len(result) == 2
        assert result[0][0] == "Test A"
        assert result[1][0] == "Test B"

    def test_non_test_section_ignored(self) -> None:
        content = (
            "*** Settings ***\nLibrary    MyLib\n\n"
            "*** Test Cases ***\nMy Test\n    Log    hi\n\n"
            "*** Keywords ***\nMy Keyword\n    Log    kw\n"
        )
        result = self.a._parse_test_steps(_make_file(content))
        assert len(result) == 1
        assert result[0][0] == "My Test"

    def test_comment_as_test_name_skipped(self) -> None:
        content = (
            "*** Test Cases ***\n"
            "# comment\n    Log    x\n\n"
            "Real Test\n    Log    y\n"
        )
        result = self.a._parse_test_steps(_make_file(content))
        # comment becomes current_name=None so its steps are discarded
        real = [r for r in result if r[0] == "Real Test"]
        assert len(real) == 1

    def test_variable_assignment_prefix_stripped_in_steps(self) -> None:
        content = (
            "*** Test Cases ***\nMy Test\n"
            "    ${x} =    Open Browser    ${URL}\n"
            "    Log    done\n"
        )
        result = self.a._parse_test_steps(_make_file(content))
        steps = result[0][2]
        assert any("Open Browser" in s for s in steps)

    def test_empty_file_returns_empty_list(self) -> None:
        result = self.a._parse_test_steps(_make_file(""))
        assert result == []

    def test_blank_lines_skipped(self) -> None:
        content = "*** Test Cases ***\n\nMy Test\n\n    Log    hi\n\n"
        result = self.a._parse_test_steps(_make_file(content))
        assert len(result) == 1

    def test_line_number_recorded(self) -> None:
        content = "*** Test Cases ***\nMy Test\n    Log    hi\n"
        result = self.a._parse_test_steps(_make_file(content))
        _, line_num, _, _, _ = result[0]
        assert line_num == 2  # "My Test" is on line 2
