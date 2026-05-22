# tests/unit/analyzers/test_dead_code_property.py
"""Property-based tests for DeadCodeAnalyzer using Hypothesis (Task 25).

These tests assert structural invariants that must hold for any valid input:
- No finding references a line beyond the file's total line count.
- No two findings share the same (location, pattern_type) combination.
- Keyword names that ARE called never appear in UNUSED_KEYWORD findings.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from robot_optimizer_core.application.analyzers import DeadCodeAnalyzer
from robot_optimizer_core.domain.entities import TestFile
from robot_optimizer_core.domain.value_objects import PatternType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IDENTIFIER_CHARS = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters=" _"),
    min_size=3,
    max_size=30,
)
_KW_NAME = st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=3, max_size=20).map(
    str.title
)


def _make_robot_content(
    kw_names: list[str],
    called: list[str],
    test_names: list[str],
) -> str:
    """Build a minimal Robot Framework file from components."""
    lines = ["*** Test Cases ***"]
    for test in test_names:
        safe = test.replace("*", "").strip() or "My Test"
        lines.append(safe)
        for kw in called:
            safe_kw = kw.strip()
            if safe_kw:
                lines.append(f"    {safe_kw}")
    lines.append("")
    lines.append("*** Keywords ***")
    for kw in kw_names:
        safe = kw.replace("*", "").strip()
        if safe:
            lines.append(safe)
            lines.append("    Log    something")
    return "\n".join(lines)


def _make_file(content: str) -> TestFile:
    return TestFile(
        path=Path("generated.robot"),
        content=content,
        size_bytes=len(content),
        last_modified_utc=datetime.now(),
    )


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeadCodeAnalyzerProperties:
    """Hypothesis-driven invariant checks for DeadCodeAnalyzer."""

    @given(
        kw_names=st.lists(_KW_NAME, min_size=0, max_size=6, unique=True),
        test_names=st.lists(_KW_NAME, min_size=1, max_size=4),
        called_subset=st.data(),
    )
    @settings(
        max_examples=80,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_no_finding_exceeds_file_line_count(
        self,
        kw_names: list[str],
        test_names: list[str],
        called_subset: st.DataObject,
    ) -> None:
        """No finding may reference a line number beyond the total file line count."""
        if kw_names:
            called = called_subset.draw(
                st.lists(
                    st.sampled_from(kw_names),
                    min_size=0,
                    max_size=max(1, len(kw_names)),
                )
            )
        else:
            called = []

        content = _make_robot_content(kw_names, called, test_names)
        test_file = _make_file(content)
        line_count = test_file.line_count

        analyzer = DeadCodeAnalyzer()
        findings = analyzer.analyze(test_file)

        for finding in findings:
            assert finding.location.line >= 1, (
                f"Finding line {finding.location.line} < 1"
            )
            assert finding.location.line <= line_count, (
                f"Finding at line {finding.location.line} "
                f"exceeds file line count {line_count}"
            )

    @given(
        kw_names=st.lists(_KW_NAME, min_size=1, max_size=6, unique=True),
        test_names=st.lists(_KW_NAME, min_size=1, max_size=3),
    )
    @settings(
        max_examples=60,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_no_duplicate_findings_same_location_and_type(
        self,
        kw_names: list[str],
        test_names: list[str],
    ) -> None:
        """No two findings should share the exact same (file, line, pattern_type)."""
        content = _make_robot_content(kw_names, [], test_names)
        test_file = _make_file(content)

        analyzer = DeadCodeAnalyzer()
        findings = analyzer.analyze(test_file)

        seen: set[tuple[str, int, str]] = set()
        for finding in findings:
            key = (
                str(finding.location.file_path),
                finding.location.line,
                str(finding.pattern.type),
            )
            assert key not in seen, f"Duplicate finding at {key}: {finding.message}"
            seen.add(key)

    @given(
        kw_names=st.lists(_KW_NAME, min_size=1, max_size=5, unique=True),
        test_names=st.lists(_KW_NAME, min_size=1, max_size=3),
    )
    @settings(
        max_examples=60,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_called_keywords_not_in_unused_findings(
        self,
        kw_names: list[str],
        test_names: list[str],
    ) -> None:
        """A keyword that appears in the test body must not be flagged as unused."""
        content = _make_robot_content(kw_names, kw_names, test_names)
        test_file = _make_file(content)

        analyzer = DeadCodeAnalyzer()
        findings = analyzer.analyze(test_file)

        unused_names = {
            f.context.get("keyword_name", "").lower()
            for f in findings
            if f.pattern.type == PatternType.UNUSED_KEYWORD and f.context
        }
        for kw in kw_names:
            # If the keyword is called, it must not appear in unused findings
            assert kw.lower() not in unused_names, (
                f"Keyword '{kw}' was called but still flagged as unused"
            )
