# tests/unit/test_cli_baseline.py
"""Unit tests for the --baseline CLI feature."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from robot_optimizer_core.cli._baseline import (
    BaselineKey,
    _finding_key,
    filter_baseline,
    load_baseline,
    save_baseline,
)
from robot_optimizer_core.domain.value_objects import Finding, Location, Pattern, PatternType, Severity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(
    file_path: Path = Path("suite.robot"),
    line: int = 10,
    pattern_type: PatternType = PatternType.SLEEP_IN_TEST,
    severity: Severity = Severity.WARNING,
    message: str = "Use explicit wait",
) -> Finding:
    pattern = Pattern(
        type=pattern_type,
        name="Test Pattern",
        description="A pattern",
        recommendation="Fix it",
    )
    return Finding.create(
        pattern=pattern,
        severity=severity,
        location=Location(file_path=file_path, line=line),
        message=message,
    )


# ---------------------------------------------------------------------------
# _finding_key
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFindingKey:
    def test_key_components(self) -> None:
        f = _make_finding(file_path=Path("tests/suite.robot"), line=42)
        key = _finding_key(f)
        assert key == ("tests/suite.robot", "SLEEP_IN_TEST", 42)

    def test_uses_posix_path(self) -> None:
        f = _make_finding(file_path=Path("a/b/c.robot"), line=1)
        file_part, *_ = _finding_key(f)
        assert "\\" not in file_part

    def test_different_pattern_types_give_different_keys(self) -> None:
        f1 = _make_finding(pattern_type=PatternType.SLEEP_IN_TEST)
        f2 = _make_finding(pattern_type=PatternType.DUPLICATE_KEYWORD)
        assert _finding_key(f1) != _finding_key(f2)

    def test_different_lines_give_different_keys(self) -> None:
        f1 = _make_finding(line=1)
        f2 = _make_finding(line=2)
        assert _finding_key(f1) != _finding_key(f2)


# ---------------------------------------------------------------------------
# load_baseline
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadBaseline:
    def test_missing_file_returns_empty_set(self, tmp_path: Path) -> None:
        result = load_baseline(tmp_path / "nonexistent.json")
        assert result == set()

    def test_loads_valid_file(self, tmp_path: Path) -> None:
        baseline_file = tmp_path / "baseline.json"
        baseline_file.write_text(
            json.dumps([
                {"file_path": "suite.robot", "pattern_type": "SLEEP_IN_TEST", "line": 10},
                {"file_path": "other.robot", "pattern_type": "DUPLICATE_KEYWORD", "line": 5},
            ]),
            encoding="utf-8",
        )
        keys = load_baseline(baseline_file)
        assert ("suite.robot", "SLEEP_IN_TEST", 10) in keys
        assert ("other.robot", "DUPLICATE_KEYWORD", 5) in keys
        assert len(keys) == 2

    def test_invalid_json_raises_value_error(self, tmp_path: Path) -> None:
        baseline_file = tmp_path / "bad.json"
        baseline_file.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError, match="Cannot parse baseline"):
            load_baseline(baseline_file)

    def test_skips_malformed_entries(self, tmp_path: Path) -> None:
        baseline_file = tmp_path / "baseline.json"
        baseline_file.write_text(
            json.dumps([
                {"file_path": "suite.robot", "pattern_type": "SLEEP_IN_TEST", "line": 10},
                {"missing_key": True},
                None,
            ]),
            encoding="utf-8",
        )
        keys = load_baseline(baseline_file)
        assert len(keys) == 1
        assert ("suite.robot", "SLEEP_IN_TEST", 10) in keys

    def test_line_coerced_to_int(self, tmp_path: Path) -> None:
        baseline_file = tmp_path / "baseline.json"
        baseline_file.write_text(
            json.dumps([{"file_path": "a.robot", "pattern_type": "NO_TAGS", "line": "7"}]),
            encoding="utf-8",
        )
        keys = load_baseline(baseline_file)
        assert ("a.robot", "NO_TAGS", 7) in keys


# ---------------------------------------------------------------------------
# save_baseline
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSaveBaseline:
    def test_creates_file(self, tmp_path: Path) -> None:
        baseline_file = tmp_path / "baseline.json"
        f = _make_finding()
        save_baseline([f], baseline_file)
        assert baseline_file.exists()

    def test_written_entries_are_loadable(self, tmp_path: Path) -> None:
        baseline_file = tmp_path / "baseline.json"
        findings = [
            _make_finding(file_path=Path("a.robot"), line=1),
            _make_finding(file_path=Path("b.robot"), line=99, pattern_type=PatternType.NO_TAGS),
        ]
        save_baseline(findings, baseline_file)
        keys = load_baseline(baseline_file)
        assert ("a.robot", "SLEEP_IN_TEST", 1) in keys
        assert ("b.robot", "NO_TAGS", 99) in keys
        assert len(keys) == 2

    def test_empty_findings_writes_empty_array(self, tmp_path: Path) -> None:
        baseline_file = tmp_path / "baseline.json"
        save_baseline([], baseline_file)
        data = json.loads(baseline_file.read_text())
        assert data == []

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        baseline_file = tmp_path / "baseline.json"
        save_baseline([_make_finding(line=1)], baseline_file)
        save_baseline([_make_finding(line=2)], baseline_file)
        keys = load_baseline(baseline_file)
        assert len(keys) == 1
        assert ("suite.robot", "SLEEP_IN_TEST", 2) in keys


# ---------------------------------------------------------------------------
# filter_baseline
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFilterBaseline:
    def test_empty_baseline_everything_is_new(self) -> None:
        findings = [_make_finding(line=1), _make_finding(line=2)]
        new, suppressed = filter_baseline(findings, set())
        assert new == findings
        assert suppressed == []

    def test_full_match_everything_suppressed(self) -> None:
        f1 = _make_finding(line=1)
        f2 = _make_finding(line=2)
        baseline: set[BaselineKey] = {_finding_key(f1), _finding_key(f2)}
        new, suppressed = filter_baseline([f1, f2], baseline)
        assert new == []
        assert suppressed == [f1, f2]

    def test_partial_match(self) -> None:
        f1 = _make_finding(line=1)
        f2 = _make_finding(line=2)
        baseline: set[BaselineKey] = {_finding_key(f1)}
        new, suppressed = filter_baseline([f1, f2], baseline)
        assert new == [f2]
        assert suppressed == [f1]

    def test_different_file_not_suppressed(self) -> None:
        baseline_finding = _make_finding(file_path=Path("a.robot"), line=10)
        current_finding = _make_finding(file_path=Path("b.robot"), line=10)
        baseline: set[BaselineKey] = {_finding_key(baseline_finding)}
        new, suppressed = filter_baseline([current_finding], baseline)
        assert new == [current_finding]
        assert suppressed == []

    def test_different_line_not_suppressed(self) -> None:
        baseline_finding = _make_finding(line=10)
        current_finding = _make_finding(line=11)
        baseline: set[BaselineKey] = {_finding_key(baseline_finding)}
        new, suppressed = filter_baseline([current_finding], baseline)
        assert new == [current_finding]
        assert suppressed == []

    def test_different_pattern_type_not_suppressed(self) -> None:
        baseline_finding = _make_finding(pattern_type=PatternType.SLEEP_IN_TEST)
        current_finding = _make_finding(pattern_type=PatternType.DUPLICATE_KEYWORD)
        baseline: set[BaselineKey] = {_finding_key(baseline_finding)}
        new, suppressed = filter_baseline([current_finding], baseline)
        assert new == [current_finding]
        assert suppressed == []

    def test_empty_findings_returns_empty(self) -> None:
        new, suppressed = filter_baseline([], {("x.robot", "SLEEP_IN_TEST", 1)})
        assert new == []
        assert suppressed == []
