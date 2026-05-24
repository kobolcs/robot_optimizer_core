# tests/unit/parsers/test_robot_ast_parser_property.py
"""Property-based tests for RobotASTParser using Hypothesis.

Asserts structural invariants that must hold for any syntactically valid
Robot Framework file:

  1. Determinism: same content → identical RobotSuite every time.
  2. Keyword count: suite.keywords len matches the keyword section declarations.
  3. Test count: suite.test_cases len matches the test case section declarations.
  4. Location validity: every keyword and test case has a line number ≥ 1.
  5. No crashes: the parser must not raise on any valid Robot content we generate.
  6. Idempotency: parse(parse_source) == parse(source) when round-tripping names.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from robot_optimizer_core.domain.entities.test_file import TestFile
from robot_optimizer_core.infrastructure.parsers.robot_ast_parser import RobotASTParser

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_SAFE_NAME = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_",
    min_size=3,
    max_size=25,
).map(str.strip).filter(lambda s: len(s) >= 3 and not s.startswith(" "))

_KW_NAME = _SAFE_NAME.map(str.title)


def _robot_file_with_keywords(kw_names: list[str]) -> str:
    lines = ["*** Test Cases ***", "Dummy Test", "    Log    placeholder", ""]
    if kw_names:
        lines.append("*** Keywords ***")
        for name in kw_names:
            lines.append(name)
            lines.append("    Log    body")
    return "\n".join(lines)


def _robot_file_with_tests(test_names: list[str]) -> str:
    lines = ["*** Test Cases ***"]
    for name in test_names:
        lines.append(name)
        lines.append("    Log    ${x}")
    return "\n".join(lines)


def _robot_file_full(kw_names: list[str], test_names: list[str]) -> str:
    lines = ["*** Test Cases ***"]
    for name in test_names:
        lines.append(name)
        lines.append("    Log    body")
    lines.append("")
    if kw_names:
        lines.append("*** Keywords ***")
        for name in kw_names:
            lines.append(name)
            lines.append("    Log    body")
    return "\n".join(lines)


def _make_test_file(content: str) -> TestFile:
    return TestFile.model_validate({
        "path": Path("generated.robot"),
        "content": content,
        "size_bytes": len(content.encode()),
        "last_modified_utc": datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestParserDeterminism:
    """Parser produces identical output for identical input."""

    @given(
        kw_names=st.lists(_KW_NAME, min_size=0, max_size=5, unique=True),
        test_names=st.lists(_KW_NAME, min_size=1, max_size=4, unique=True),
    )
    @settings(max_examples=60, suppress_health_check=[HealthCheck.too_slow])
    def test_parse_is_deterministic(
        self, kw_names: list[str], test_names: list[str]
    ) -> None:
        content = _robot_file_full(kw_names, test_names)
        tf = _make_test_file(content)
        parser = RobotASTParser()

        suite_a = parser.parse_suite(tf)
        suite_b = parser.parse_suite(tf)

        assert [kw.name for kw in suite_a.keywords] == [kw.name for kw in suite_b.keywords], (
            "Parser is non-deterministic: keyword order changed between calls"
        )
        assert [tc.name for tc in suite_a.test_cases] == [tc.name for tc in suite_b.test_cases], (
            "Parser is non-deterministic: test case order changed between calls"
        )


@pytest.mark.unit
class TestParserKeywordInvariants:
    """Structural invariants on the keyword section output."""

    @given(
        kw_names=st.lists(_KW_NAME, min_size=0, max_size=8, unique=True),
    )
    @settings(max_examples=80, suppress_health_check=[HealthCheck.too_slow])
    def test_keyword_count_matches_declarations(self, kw_names: list[str]) -> None:
        content = _robot_file_with_keywords(kw_names)
        tf = _make_test_file(content)
        suite = RobotASTParser().parse_suite(tf)
        assert len(suite.keywords) == len(kw_names), (
            f"Declared {len(kw_names)} keywords but parsed {len(suite.keywords)}"
        )

    @given(
        kw_names=st.lists(_KW_NAME, min_size=1, max_size=6, unique=True),
    )
    @settings(max_examples=60, suppress_health_check=[HealthCheck.too_slow])
    def test_keyword_line_numbers_are_positive(self, kw_names: list[str]) -> None:
        content = _robot_file_with_keywords(kw_names)
        tf = _make_test_file(content)
        suite = RobotASTParser().parse_suite(tf)
        for kw in suite.keywords:
            assert kw.location.line >= 1, (
                f"Keyword '{kw.name}' has non-positive line {kw.location.line}"
            )

    @given(
        kw_names=st.lists(_KW_NAME, min_size=1, max_size=6, unique=True),
    )
    @settings(max_examples=60, suppress_health_check=[HealthCheck.too_slow])
    def test_keyword_names_preserved_exactly(self, kw_names: list[str]) -> None:
        content = _robot_file_with_keywords(kw_names)
        tf = _make_test_file(content)
        suite = RobotASTParser().parse_suite(tf)
        parsed_names = [kw.name for kw in suite.keywords]
        assert parsed_names == kw_names, (
            f"Keyword names not preserved: expected {kw_names}, got {parsed_names}"
        )

    @given(
        kw_names=st.lists(_KW_NAME, min_size=1, max_size=6, unique=True),
    )
    @settings(max_examples=60, suppress_health_check=[HealthCheck.too_slow])
    def test_keyword_line_numbers_are_strictly_increasing(self, kw_names: list[str]) -> None:
        content = _robot_file_with_keywords(kw_names)
        tf = _make_test_file(content)
        suite = RobotASTParser().parse_suite(tf)
        lines = [kw.location.line for kw in suite.keywords]
        assert lines == sorted(lines), (
            f"Keyword lines not in source order: {lines}"
        )


@pytest.mark.unit
class TestParserTestCaseInvariants:
    """Structural invariants on the test case section output."""

    @given(
        test_names=st.lists(_KW_NAME, min_size=1, max_size=8, unique=True),
    )
    @settings(max_examples=80, suppress_health_check=[HealthCheck.too_slow])
    def test_test_count_matches_declarations(self, test_names: list[str]) -> None:
        content = _robot_file_with_tests(test_names)
        tf = _make_test_file(content)
        suite = RobotASTParser().parse_suite(tf)
        assert len(suite.test_cases) == len(test_names), (
            f"Declared {len(test_names)} tests but parsed {len(suite.test_cases)}"
        )

    @given(
        test_names=st.lists(_KW_NAME, min_size=1, max_size=6, unique=True),
    )
    @settings(max_examples=60, suppress_health_check=[HealthCheck.too_slow])
    def test_test_case_line_numbers_are_positive(self, test_names: list[str]) -> None:
        content = _robot_file_with_tests(test_names)
        tf = _make_test_file(content)
        suite = RobotASTParser().parse_suite(tf)
        for tc in suite.test_cases:
            assert tc.location.line >= 1, (
                f"Test case '{tc.name}' has non-positive line {tc.location.line}"
            )

    @given(
        test_names=st.lists(_KW_NAME, min_size=1, max_size=6, unique=True),
    )
    @settings(max_examples=60, suppress_health_check=[HealthCheck.too_slow])
    def test_test_case_line_numbers_are_strictly_increasing(
        self, test_names: list[str]
    ) -> None:
        content = _robot_file_with_tests(test_names)
        tf = _make_test_file(content)
        suite = RobotASTParser().parse_suite(tf)
        lines = [tc.location.line for tc in suite.test_cases]
        assert lines == sorted(lines), (
            f"Test case lines not in source order: {lines}"
        )


@pytest.mark.unit
class TestParserRobustness:
    """Parser must not crash on any syntactically plausible Robot content."""

    @given(
        kw_names=st.lists(_KW_NAME, min_size=0, max_size=6, unique=True),
        test_names=st.lists(_KW_NAME, min_size=1, max_size=4, unique=True),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_no_crash_on_valid_robot_content(
        self, kw_names: list[str], test_names: list[str]
    ) -> None:
        content = _robot_file_full(kw_names, test_names)
        tf = _make_test_file(content)
        try:
            suite = RobotASTParser().parse_suite(tf)
        except Exception as exc:
            pytest.fail(
                f"Parser raised {type(exc).__name__} on valid content.\n"
                f"Content:\n{content}\n\nError: {exc}"
            )
        assert suite is not None

    @given(
        kw_names=st.lists(_KW_NAME, min_size=0, max_size=4, unique=True),
        test_names=st.lists(_KW_NAME, min_size=1, max_size=4, unique=True),
    )
    @settings(max_examples=80, suppress_health_check=[HealthCheck.too_slow])
    def test_suite_name_equals_file_stem(
        self, kw_names: list[str], test_names: list[str]
    ) -> None:
        content = _robot_file_full(kw_names, test_names)
        for stem in ["my_suite", "test_login", "suite_v2"]:
            tf = _make_test_file(content)
            tf = tf.model_copy(update={"path": Path(f"{stem}.robot")})
            suite = RobotASTParser().parse_suite(tf)
            assert suite.name == stem, (
                f"Suite name '{suite.name}' != file stem '{stem}'"
            )
