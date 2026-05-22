# tests/integration/test_parser_integration.py
"""Integration tests for RobotASTParser.

These tests verify that the parser correctly extracts test cases, keywords,
variables, imports, and documentation from real Robot Framework suite content,
and that it integrates cleanly with the TestFile entity used across the engine.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from robot_optimizer_core.domain.entities.test_file import TestFile
from robot_optimizer_core.infrastructure.parsers.robot_ast_parser import RobotASTParser


def _make_file(content: str, path: Path = Path("suite.robot")) -> TestFile:
    return TestFile.model_validate(
        {
            "path": path,
            "content": content,
            "size_bytes": len(content.encode()),
            "last_modified_utc": datetime.now(tz=UTC),
        }
    )


FULL_SUITE = """\
*** Settings ***
Documentation    Full integration suite
Library          Collections
Library          String
Resource         common.resource

*** Variables ***
${BASE_URL}    https://example.com
${TIMEOUT}     10s

*** Test Cases ***
Login Test
    [Documentation]    Verify login flow
    [Tags]    smoke    regression
    Log    Open browser
    Log    Submit form

Sleep Usage Test
    [Documentation]    Test that uses sleep (anti-pattern)
    Sleep    3s
    Log    Done

*** Keywords ***
Submit Login Form
    [Arguments]    ${username}    ${password}
    Log    ${username}
    Log    ${password}

Unused Helper Keyword
    [Documentation]    This keyword is never called
    Log    orphan
"""


@pytest.mark.integration
class TestRobotASTParserIntegration:
    """Parser produces correct structured output from real suite content."""

    def test_parse_suite_returns_result(self) -> None:
        tf = _make_file(FULL_SUITE)
        result = RobotASTParser().parse_suite(tf)
        assert result is not None

    def test_parse_extracts_test_cases(self) -> None:
        tf = _make_file(FULL_SUITE)
        result = RobotASTParser().parse_suite(tf)
        names = [tc.name for tc in result.test_cases]
        assert "Login Test" in names
        assert "Sleep Usage Test" in names

    def test_parse_extracts_keywords(self) -> None:
        tf = _make_file(FULL_SUITE)
        result = RobotASTParser().parse_suite(tf)
        names = [kw.name for kw in result.keywords]
        assert "Submit Login Form" in names
        assert "Unused Helper Keyword" in names

    def test_parse_extracts_variables(self) -> None:
        tf = _make_file(FULL_SUITE)
        result = RobotASTParser().parse_suite(tf)
        var_names = [v.name for v in result.variables]
        assert any("BASE_URL" in n for n in var_names)

    def test_parse_extracts_imports(self) -> None:
        tf = _make_file(FULL_SUITE)
        result = RobotASTParser().parse_suite(tf)
        import_names = [imp.name for imp in result.imports]
        assert any("Collections" in n for n in import_names)
        assert any("String" in n for n in import_names)

    def test_parse_suite_documentation(self) -> None:
        tf = _make_file(FULL_SUITE)
        result = RobotASTParser().parse_suite(tf)
        assert result.documentation is not None
        assert "Full integration suite" in result.documentation

    def test_parse_empty_suite(self) -> None:
        tf = _make_file("")
        result = RobotASTParser().parse_suite(tf)
        assert result is not None
        assert result.test_cases == []
        assert result.keywords == []

    def test_parse_keywords_only_suite(self) -> None:
        content = """\
*** Keywords ***
My Keyword
    [Arguments]    ${arg}
    Log    ${arg}
"""
        tf = _make_file(content)
        result = RobotASTParser().parse_suite(tf)
        assert len(result.keywords) == 1
        assert result.keywords[0].name == "My Keyword"

    def test_parse_test_case_tags(self) -> None:
        tf = _make_file(FULL_SUITE)
        result = RobotASTParser().parse_suite(tf)
        login_test = next(tc for tc in result.test_cases if tc.name == "Login Test")
        assert "smoke" in login_test.tags or "regression" in login_test.tags

    def test_parser_is_idempotent(self) -> None:
        tf = _make_file(FULL_SUITE)
        parser = RobotASTParser()
        result1 = parser.parse_suite(tf)
        result2 = parser.parse_suite(tf)
        assert [tc.name for tc in result1.test_cases] == [tc.name for tc in result2.test_cases]
        assert [kw.name for kw in result1.keywords] == [kw.name for kw in result2.keywords]


@pytest.mark.integration
class TestParserWithRealFileIntegration:
    """Parser works with actual files written to disk."""

    def test_parse_from_path_matches_from_content(self, tmp_path: Path) -> None:
        file_path = tmp_path / "suite.robot"
        file_path.write_bytes(FULL_SUITE.encode("utf-8"))

        tf_from_path = TestFile.from_path(file_path)
        tf_from_content = _make_file(FULL_SUITE, path=file_path)

        parser = RobotASTParser()
        r1 = parser.parse_suite(tf_from_path)
        r2 = parser.parse_suite(tf_from_content)

        assert [tc.name for tc in r1.test_cases] == [tc.name for tc in r2.test_cases]
        assert [kw.name for kw in r1.keywords] == [kw.name for kw in r2.keywords]
