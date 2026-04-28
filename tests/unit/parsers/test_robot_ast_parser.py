# tests/unit/parsers/test_robot_ast_parser.py
"""Tests for RobotASTParser."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from robot_optimizer_core.domain.entities.test_file import TestFile
from robot_optimizer_core.parsers.robot_ast_parser import RobotASTParser


def _make_file(content: str, path: Path = Path("suite.robot")) -> TestFile:
    now = datetime.now(tz=UTC)
    return TestFile.model_validate(
        {
            "path": path,
            "content": content,
            "size_bytes": len(content.encode()),
            "last_modified_utc": now,
        }
    )


SIMPLE_TEST = """\
*** Test Cases ***
My Test Case
    Log    Hello World
    Sleep    1s
"""

KEYWORD_FILE = """\
*** Keywords ***
My Keyword
    [Arguments]    ${arg1}
    Log    ${arg1}
    [Return]    ${arg1}
"""

VARIABLE_FILE = """\
*** Variables ***
${MY_VAR}    hello world
${ANOTHER}    42
"""

SETTINGS_FILE = """\
*** Settings ***
Library    Collections
Resource    common.resource

*** Test Cases ***
Simple Test
    Log    done
"""

FULL_FILE = """\
*** Settings ***
Documentation    My test suite
Library    Collections
Metadata    Version    1.0

*** Variables ***
${BASE_URL}    http://localhost

*** Test Cases ***
Login Test
    [Documentation]    Tests login
    [Tags]    smoke    regression
    [Setup]    Open Browser    ${BASE_URL}
    Log    Hello
    [Teardown]    Close Browser

*** Keywords ***
Open Browser
    [Arguments]    ${url}
    Log    Opening ${url}
"""


class TestParseEmpty:
    def test_empty_content_returns_suite(self) -> None:
        suite = RobotASTParser().parse_suite(_make_file(""))
        assert suite.name == "suite"
        assert suite.test_cases == []
        assert suite.keywords == []
        assert suite.variables == []
        assert suite.imports == []


class TestParseTestCases:
    def test_extracts_test_case(self) -> None:
        suite = RobotASTParser().parse_suite(_make_file(SIMPLE_TEST))
        assert len(suite.test_cases) == 1
        assert suite.test_cases[0].name == "My Test Case"

    def test_test_case_body_calls(self) -> None:
        suite = RobotASTParser().parse_suite(_make_file(SIMPLE_TEST))
        calls = suite.test_cases[0].body_calls
        assert len(calls) >= 1
        call_names = [c.keyword_name for c in calls]
        assert "Log" in call_names

    def test_keyword_call_arguments(self) -> None:
        suite = RobotASTParser().parse_suite(_make_file(SIMPLE_TEST))
        log_call = next(
            c for c in suite.test_cases[0].body_calls if c.keyword_name == "Log"
        )
        assert "Hello World" in log_call.arguments

    def test_test_case_location(self) -> None:
        path = Path("my_suite.robot")
        suite = RobotASTParser().parse_suite(_make_file(SIMPLE_TEST, path))
        tc = suite.test_cases[0]
        assert tc.location.file_path == path
        assert tc.location.line >= 1

    def test_test_case_documentation(self) -> None:
        suite = RobotASTParser().parse_suite(_make_file(FULL_FILE))
        tc = suite.test_cases[0]
        assert tc.documentation is not None

    def test_test_case_tags(self) -> None:
        suite = RobotASTParser().parse_suite(_make_file(FULL_FILE))
        tc = suite.test_cases[0]
        assert "smoke" in tc.tags
        assert "regression" in tc.tags

    def test_test_case_setup_and_teardown(self) -> None:
        suite = RobotASTParser().parse_suite(_make_file(FULL_FILE))
        tc = suite.test_cases[0]
        assert tc.setup is not None
        assert tc.teardown is not None


class TestParseKeywords:
    def test_extracts_keyword(self) -> None:
        suite = RobotASTParser().parse_suite(_make_file(KEYWORD_FILE))
        assert len(suite.keywords) == 1
        assert suite.keywords[0].name == "My Keyword"

    def test_keyword_arguments(self) -> None:
        suite = RobotASTParser().parse_suite(_make_file(KEYWORD_FILE))
        kw = suite.keywords[0]
        assert len(kw.arguments) == 1

    def test_keyword_location(self) -> None:
        path = Path("keywords.robot")
        suite = RobotASTParser().parse_suite(_make_file(KEYWORD_FILE, path))
        assert suite.keywords[0].location.file_path == path
        assert suite.keywords[0].location.line >= 1

    def test_keyword_body_calls(self) -> None:
        suite = RobotASTParser().parse_suite(_make_file(KEYWORD_FILE))
        kw = suite.keywords[0]
        assert len(kw.body_calls) >= 1
        assert kw.body_calls[0].keyword_name == "Log"


class TestParseVariables:
    def test_extracts_variables(self) -> None:
        suite = RobotASTParser().parse_suite(_make_file(VARIABLE_FILE))
        assert len(suite.variables) == 2

    def test_variable_names(self) -> None:
        suite = RobotASTParser().parse_suite(_make_file(VARIABLE_FILE))
        names = {v.name for v in suite.variables}
        assert "${MY_VAR}" in names


class TestParseImports:
    def test_extracts_library_import(self) -> None:
        suite = RobotASTParser().parse_suite(_make_file(SETTINGS_FILE))
        lib_names = [i.name for i in suite.imports if i.import_type == "Library"]
        assert "Collections" in lib_names

    def test_extracts_resource_import(self) -> None:
        suite = RobotASTParser().parse_suite(_make_file(SETTINGS_FILE))
        res_names = [i.name for i in suite.imports if i.import_type == "Resource"]
        assert "common.resource" in res_names

    def test_import_location(self) -> None:
        suite = RobotASTParser().parse_suite(_make_file(SETTINGS_FILE))
        assert all(i.location.line >= 1 for i in suite.imports)


class TestParseSuiteMetadata:
    def test_suite_name_from_path(self) -> None:
        suite = RobotASTParser().parse_suite(
            _make_file(FULL_FILE, Path("my_suite.robot"))
        )
        assert suite.name == "my_suite"

    def test_suite_documentation(self) -> None:
        suite = RobotASTParser().parse_suite(_make_file(FULL_FILE))
        assert suite.documentation is not None
        assert suite.documentation != ""

    def test_suite_metadata(self) -> None:
        suite = RobotASTParser().parse_suite(_make_file(FULL_FILE))
        assert "Version" in suite.metadata
        assert suite.metadata["Version"] == "1.0"


class TestParseErrorFallback:
    def test_parse_error_returns_fallback_suite(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:

        def _raise(*args: object, **kwargs: object) -> object:
            raise RuntimeError("parse failed")

        monkeypatch.setattr(
            "robot_optimizer_core.parsers.robot_ast_parser.get_model", _raise
        )
        parser = RobotASTParser()
        suite = parser.parse_suite(_make_file("*** Test Cases ***"))
        assert suite.test_cases == []
        assert "Parse error" in (suite.documentation or "")
