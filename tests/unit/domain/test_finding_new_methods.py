# tests/unit/domain/test_finding_new_methods.py
"""Tests for Finding.to_sarif() and Finding.filter_suppressed() (Tasks 23-24)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from robot_optimizer_core.domain.entities import TestFile
from robot_optimizer_core.domain.value_objects import (
    Finding,
    Location,
    Pattern,
    PatternType,
    Severity,
)


def _make_finding(
    file_path: Path = Path("test.robot"),
    line: int = 5,
    pattern_type: PatternType = PatternType.SLEEP_IN_TEST,
    severity: Severity = Severity.WARNING,
    message: str = "Sleep used",
) -> Finding:
    pattern = Pattern(
        type=pattern_type,
        name="Sleep in Test",
        description="Sleep used",
        recommendation="Use Wait Instead",
        documentation_url=None,
        auto_fixable=True,
    )
    return Finding.create(
        pattern=pattern,
        severity=severity,
        location=Location(file_path=file_path, line=line),
        message=message,
    )


@pytest.mark.unit
class TestFindingToSarif:
    def test_sarif_structure_has_required_keys(self) -> None:
        finding = _make_finding()
        sarif = finding.to_sarif()
        assert "ruleId" in sarif
        assert "level" in sarif
        assert "message" in sarif
        assert "locations" in sarif

    def test_sarif_level_mapping(self) -> None:
        assert _make_finding(severity=Severity.ERROR).to_sarif()["level"] == "error"
        assert _make_finding(severity=Severity.WARNING).to_sarif()["level"] == "warning"
        assert _make_finding(severity=Severity.INFO).to_sarif()["level"] == "note"

    def test_sarif_message_text(self) -> None:
        finding = _make_finding(message="Custom message here")
        sarif = finding.to_sarif()
        assert sarif["message"]["text"] == "Custom message here"

    def test_sarif_physical_location(self) -> None:
        finding = _make_finding(file_path=Path("/tests/login.robot"), line=42)
        sarif = finding.to_sarif()
        physical = sarif["locations"][0]["physicalLocation"]
        assert physical["region"]["startLine"] == 42

    def test_sarif_rule_id_is_pattern_type_name(self) -> None:
        finding = _make_finding(pattern_type=PatternType.UNUSED_KEYWORD)
        sarif = finding.to_sarif()
        assert sarif["ruleId"] == "UNUSED_KEYWORD"

    def test_sarif_properties_include_recommendation(self) -> None:
        finding = _make_finding()
        sarif = finding.to_sarif()
        assert "recommendation" in sarif["properties"]

    def test_sarif_with_end_line(self) -> None:
        loc = Location(
            file_path=Path("x.robot"), line=10, column=1, end_line=12, end_column=5
        )
        pattern = Pattern(
            type=PatternType.SLEEP_IN_TEST,
            name="S",
            description="d",
            recommendation="r",
            documentation_url=None,
            auto_fixable=False,
        )
        finding = Finding.create(
            pattern=pattern,
            severity=Severity.INFO,
            location=loc,
            message="msg",
        )
        sarif = finding.to_sarif()
        region = sarif["locations"][0]["physicalLocation"]["region"]
        assert region["endLine"] == 12
        assert region["endColumn"] == 5


@pytest.mark.unit
class TestFindingSuppress:
    def test_bare_ignore_suppresses_all(self) -> None:
        finding = _make_finding()
        assert finding.is_suppressed_by("    Sleep    10    # robot-optimizer: ignore")

    def test_ignore_with_matching_tag(self) -> None:
        finding = _make_finding(pattern_type=PatternType.SLEEP_IN_TEST)
        line = "    Sleep    10    # robot-optimizer: ignore[sleep_in_test]"
        assert finding.is_suppressed_by(line)

    def test_ignore_with_non_matching_tag(self) -> None:
        finding = _make_finding(pattern_type=PatternType.SLEEP_IN_TEST)
        line = "    Sleep    10    # robot-optimizer: ignore[dead_code]"
        assert not finding.is_suppressed_by(line)

    def test_ignore_case_insensitive(self) -> None:
        finding = _make_finding(pattern_type=PatternType.SLEEP_IN_TEST)
        line = "    Sleep    10    # Robot-Optimizer: IGNORE[SLEEP_IN_TEST]"
        assert finding.is_suppressed_by(line)

    def test_no_comment_not_suppressed(self) -> None:
        finding = _make_finding()
        assert not finding.is_suppressed_by("    Sleep    10")

    def test_filter_suppressed_removes_suppressed(self) -> None:
        f1 = _make_finding(line=1)
        f2 = _make_finding(line=2)
        source = [
            "    Sleep    5    # robot-optimizer: ignore",
            "    Sleep    10",
        ]
        result = Finding.filter_suppressed([f1, f2], source)
        assert f1 not in result
        assert f2 in result

    def test_filter_suppressed_empty_returns_all(self) -> None:
        findings = [_make_finding(line=1), _make_finding(line=2)]
        result = Finding.filter_suppressed(findings, [])
        assert result == findings

    def test_multiple_tags_comma_separated(self) -> None:
        finding = _make_finding(pattern_type=PatternType.SLEEP_IN_TEST)
        line = "    Sleep    1    # robot-optimizer: ignore[dead_code, sleep_in_test]"
        assert finding.is_suppressed_by(line)


@pytest.mark.unit
class TestFlakinessStatsTrend:
    """Tests for the new ``trend`` computed field on FlakinessStats (Task 12)."""

    def test_worsening_trend(self) -> None:
        from robot_optimizer_core.domain.value_objects import FlakinessStats

        stats = FlakinessStats(
            test_name="My Test",
            file_path=Path("t.robot"),
            total_runs=20,
            failures=10,
            recent_failures=8,
            recent_runs=10,
            older_failures=2,
            older_runs=10,
        )
        assert stats.trend == "worsening"

    def test_improving_trend(self) -> None:
        from robot_optimizer_core.domain.value_objects import FlakinessStats

        stats = FlakinessStats(
            test_name="My Test",
            file_path=Path("t.robot"),
            total_runs=20,
            failures=5,
            recent_failures=1,
            recent_runs=10,
            older_failures=4,
            older_runs=10,
        )
        assert stats.trend == "improving"

    def test_stable_trend(self) -> None:
        from robot_optimizer_core.domain.value_objects import FlakinessStats

        stats = FlakinessStats(
            test_name="My Test",
            file_path=Path("t.robot"),
            total_runs=20,
            failures=4,
            recent_failures=2,
            recent_runs=10,
            older_failures=2,
            older_runs=10,
        )
        assert stats.trend == "stable"

    def test_unknown_trend_when_insufficient_data(self) -> None:
        from robot_optimizer_core.domain.value_objects import FlakinessStats

        stats = FlakinessStats(
            test_name="My Test",
            file_path=Path("t.robot"),
            total_runs=5,
            failures=2,
        )
        assert stats.trend == "unknown"
