# tests/unit/domain/value_objects/test_robot_ast.py
"""Tests for robot_ast value objects."""

from __future__ import annotations

from pathlib import Path

from robot_optimizer_core.domain.value_objects.location import Location
from robot_optimizer_core.domain.value_objects.robot_ast import (
    KeywordCall,
    RobotArgument,
    RobotImport,
    RobotKeyword,
    RobotSuite,
    RobotTestCase,
    RobotVariable,
)


def _loc(line: int = 1) -> Location:
    return Location(file_path=Path("suite.robot"), line=line)


def _call(name: str, args: list[str] | None = None, **kw: object) -> KeywordCall:
    return KeywordCall(keyword_name=name, arguments=args or [], location=_loc(), **kw)


class TestKeywordCall:
    def test_is_builtin_log(self) -> None:
        assert _call("log").is_builtin is True

    def test_is_builtin_set_variable(self) -> None:
        assert _call("set variable").is_builtin is True

    def test_is_builtin_false_for_custom(self) -> None:
        assert _call("My Custom Keyword").is_builtin is False

    def test_is_library_keyword_with_dot(self) -> None:
        assert _call("SeleniumLibrary.Open Browser").is_library_keyword is True

    def test_is_library_keyword_without_dot(self) -> None:
        assert _call("Open Browser").is_library_keyword is False


class TestRobotKeyword:
    def _kw(self, name: str = "My Keyword", **kw: object) -> RobotKeyword:
        return RobotKeyword(name=name, location=_loc(), **kw)

    def test_argument_names(self) -> None:
        kw = self._kw(
            arguments=[RobotArgument(name="${arg1}"), RobotArgument(name="${arg2}")]
        )
        assert kw.argument_names == ["${arg1}", "${arg2}"]

    def test_argument_names_skips_none(self) -> None:
        kw = self._kw(arguments=[RobotArgument(name=None)])
        assert kw.argument_names == []

    def test_has_documentation_true(self) -> None:
        kw = self._kw(documentation="Does something useful")
        assert kw.has_documentation is True

    def test_has_documentation_false_when_none(self) -> None:
        kw = self._kw(documentation=None)
        assert kw.has_documentation is False

    def test_has_documentation_false_when_blank(self) -> None:
        kw = self._kw(documentation="   ")
        assert kw.has_documentation is False

    def test_calls_other_keywords(self) -> None:
        kw = self._kw(body_calls=[_call("Log"), _call("Sleep")])
        assert kw.calls_other_keywords == ["Log", "Sleep"]

    def test_calls_other_keywords_empty(self) -> None:
        kw = self._kw()
        assert kw.calls_other_keywords == []


class TestRobotTestCase:
    def _tc(self, name: str = "My Test", **kw: object) -> RobotTestCase:
        return RobotTestCase(name=name, location=_loc(), **kw)

    def test_all_keyword_calls_body_only(self) -> None:
        tc = self._tc(body_calls=[_call("Log"), _call("Sleep")])
        assert len(tc.all_keyword_calls) == 2

    def test_all_keyword_calls_includes_setup(self) -> None:
        tc = self._tc(setup=_call("Open Browser"), body_calls=[_call("Log")])
        calls = tc.all_keyword_calls
        assert calls[0].keyword_name == "Open Browser"
        assert len(calls) == 2

    def test_all_keyword_calls_includes_teardown(self) -> None:
        tc = self._tc(teardown=_call("Close Browser"), body_calls=[_call("Log")])
        calls = tc.all_keyword_calls
        assert calls[-1].keyword_name == "Close Browser"

    def test_line_count_with_end_line(self) -> None:
        loc = Location(file_path=Path("s.robot"), line=5, end_line=10)
        tc = RobotTestCase(name="T", location=loc)
        assert tc.line_count == 6

    def test_line_count_estimate_without_end_line(self) -> None:
        tc = self._tc(body_calls=[_call("Log"), _call("Sleep")])
        assert tc.line_count == 4  # 2 calls + 2


class TestRobotImport:
    def test_is_library(self) -> None:
        imp = RobotImport(import_type="Library", name="Collections", location=_loc())
        assert imp.is_library is True
        assert imp.is_resource is False

    def test_is_resource(self) -> None:
        imp = RobotImport(
            import_type="Resource", name="common.resource", location=_loc()
        )
        assert imp.is_resource is True
        assert imp.is_library is False

    def test_resolved_path_for_resource(self) -> None:
        imp = RobotImport(
            import_type="Resource", name="keywords/common.resource", location=_loc()
        )
        assert imp.resolved_path == Path("keywords/common.resource")

    def test_resolved_path_none_for_variable_resource(self) -> None:
        imp = RobotImport(
            import_type="Resource", name="${RESOURCES}/common.resource", location=_loc()
        )
        assert imp.resolved_path is None

    def test_resolved_path_none_for_library(self) -> None:
        imp = RobotImport(import_type="Library", name="Collections", location=_loc())
        assert imp.resolved_path is None


class TestRobotVariable:
    def test_is_scalar(self) -> None:
        v = RobotVariable(name="${VAR}", value="x", location=_loc())
        assert v.is_scalar is True
        assert v.is_list is False
        assert v.is_dict is False

    def test_is_list(self) -> None:
        v = RobotVariable(name="@{ITEMS}", value="x", location=_loc())
        assert v.is_list is True
        assert v.is_scalar is False

    def test_is_dict(self) -> None:
        v = RobotVariable(name="&{DICT}", value="x", location=_loc())
        assert v.is_dict is True
        assert v.is_scalar is False


class TestRobotSuite:
    def _suite(self, **kw: object) -> RobotSuite:
        return RobotSuite(name="suite", source=Path("suite.robot"), **kw)

    def test_imported_libraries(self) -> None:
        suite = self._suite(
            imports=[
                RobotImport(import_type="Library", name="Collections", location=_loc()),
                RobotImport(
                    import_type="Resource", name="common.resource", location=_loc()
                ),
            ]
        )
        assert suite.imported_libraries == ["Collections"]

    def test_imported_resources(self) -> None:
        suite = self._suite(
            imports=[
                RobotImport(
                    import_type="Resource", name="common.resource", location=_loc()
                ),
                RobotImport(import_type="Library", name="Collections", location=_loc()),
            ]
        )
        assert Path("common.resource") in suite.imported_resources

    def test_keyword_names(self) -> None:
        suite = self._suite(
            keywords=[
                RobotKeyword(name="Login", location=_loc()),
                RobotKeyword(name="Logout", location=_loc()),
            ]
        )
        assert suite.keyword_names == {"Login", "Logout"}

    def test_test_names(self) -> None:
        suite = self._suite(
            test_cases=[
                RobotTestCase(name="Test A", location=_loc()),
                RobotTestCase(name="Test B", location=_loc()),
            ]
        )
        assert suite.test_names == {"Test A", "Test B"}

    def test_all_keyword_calls_from_tests_and_keywords(self) -> None:
        tc = RobotTestCase(name="T", location=_loc(), body_calls=[_call("Log")])
        kw = RobotKeyword(name="K", location=_loc(), body_calls=[_call("Sleep")])
        suite = self._suite(test_cases=[tc], keywords=[kw])
        names = [c.keyword_name for c in suite.all_keyword_calls]
        assert "Log" in names
        assert "Sleep" in names

    def test_has_documentation_true(self) -> None:
        suite = self._suite(documentation="Suite docs")
        assert suite.has_documentation is True

    def test_has_documentation_false(self) -> None:
        suite = self._suite(documentation=None)
        assert suite.has_documentation is False
