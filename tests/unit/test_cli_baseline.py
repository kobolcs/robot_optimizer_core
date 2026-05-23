# tests/unit/test_cli_baseline.py
"""Unit tests for the --baseline CLI feature."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from robot_optimizer_core.domain.value_objects import (
    Finding,
    Location,
    Pattern,
    PatternType,
    Severity,
)
from robot_optimizer_core.entrypoints.cli._baseline import (
    BaselineKey,
    filter_baseline,
    load_baseline,
    save_baseline,
)

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
# load_baseline
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadBaseline:
    def test_missing_file_returns_empty_set(self, tmp_path: Path) -> None:
        result = load_baseline(tmp_path / "nonexistent.json")
        assert result == set()

    def test_loads_fingerprint_format(self, tmp_path: Path) -> None:
        f = _make_finding()
        baseline_file = tmp_path / "baseline.json"
        baseline_file.write_text(
            json.dumps([{"fingerprint": f.fingerprint, "file_path": "suite.robot",
                         "pattern_type": "SLEEP_IN_TEST", "line": 10}]),
            encoding="utf-8",
        )
        keys = load_baseline(baseline_file)
        assert f.fingerprint in keys
        assert len(keys) == 1

    def test_loads_legacy_format(self, tmp_path: Path) -> None:
        """Old (file_path, pattern_type, line) entries are read without crashing."""
        baseline_file = tmp_path / "baseline.json"
        baseline_file.write_text(
            json.dumps([
                {"file_path": "suite.robot", "pattern_type": "SLEEP_IN_TEST", "line": 10},
                {"file_path": "other.robot", "pattern_type": "DUPLICATE_KEYWORD", "line": 5},
            ]),
            encoding="utf-8",
        )
        keys = load_baseline(baseline_file)
        # Legacy keys are stored as synthetic strings — they won't match real fingerprints.
        assert len(keys) == 2
        for k in keys:
            assert k.startswith("legacy:")

    def test_invalid_json_raises_value_error(self, tmp_path: Path) -> None:
        baseline_file = tmp_path / "bad.json"
        baseline_file.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError, match="Cannot parse baseline"):
            load_baseline(baseline_file)

    def test_os_error_raises_value_error(self, tmp_path: Path) -> None:
        baseline_file = tmp_path / "unreadable.json"
        baseline_file.write_text("[]", encoding="utf-8")
        baseline_file.chmod(0o000)
        try:
            with pytest.raises(ValueError, match="Cannot read baseline"):
                load_baseline(baseline_file)
        finally:
            baseline_file.chmod(0o644)

    def test_skips_malformed_entries(self, tmp_path: Path) -> None:
        f = _make_finding()
        baseline_file = tmp_path / "baseline.json"
        baseline_file.write_text(
            json.dumps([
                {"fingerprint": f.fingerprint},
                None,
                123,
            ]),
            encoding="utf-8",
        )
        keys = load_baseline(baseline_file)
        assert f.fingerprint in keys
        assert len(keys) == 1

    def test_inject_base_for_hermetic_loading(self, tmp_path: Path) -> None:
        """load_baseline accepts an explicit base so tests don't need monkeypatch."""
        f = _make_finding()
        baseline_file = tmp_path / "baseline.json"
        save_baseline([f], baseline_file, base=tmp_path)
        keys = load_baseline(baseline_file, base=tmp_path)
        assert f.fingerprint in keys


# ---------------------------------------------------------------------------
# save_baseline
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSaveBaseline:
    def test_creates_file(self, tmp_path: Path) -> None:
        baseline_file = tmp_path / "baseline.json"
        f = _make_finding()
        save_baseline([f], baseline_file, base=tmp_path)
        assert baseline_file.exists()

    def test_written_entries_are_loadable(self, tmp_path: Path) -> None:
        baseline_file = tmp_path / "baseline.json"
        findings = [
            _make_finding(file_path=Path("a.robot"), line=1),
            _make_finding(file_path=Path("b.robot"), line=99, pattern_type=PatternType.NO_TAGS),
        ]
        save_baseline(findings, baseline_file, base=tmp_path)
        keys = load_baseline(baseline_file, base=tmp_path)
        for f in findings:
            assert f.fingerprint in keys
        assert len(keys) == 2

    def test_entry_contains_human_readable_fields(self, tmp_path: Path) -> None:
        baseline_file = tmp_path / "baseline.json"
        f = _make_finding(line=42)
        save_baseline([f], baseline_file, base=tmp_path)
        data = json.loads(baseline_file.read_text())
        assert data[0]["fingerprint"] == f.fingerprint
        assert data[0]["pattern_type"] == "SLEEP_IN_TEST"
        assert data[0]["line"] == 42

    def test_empty_findings_writes_empty_array(self, tmp_path: Path) -> None:
        baseline_file = tmp_path / "baseline.json"
        save_baseline([], baseline_file, base=tmp_path)
        data = json.loads(baseline_file.read_text())
        assert data == []

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        baseline_file = tmp_path / "baseline.json"
        f1 = _make_finding(line=1)
        f2 = _make_finding(line=2)
        save_baseline([f1], baseline_file, base=tmp_path)
        save_baseline([f2], baseline_file, base=tmp_path)
        keys = load_baseline(baseline_file, base=tmp_path)
        assert f2.fingerprint in keys
        assert f1.fingerprint not in keys
        assert len(keys) == 1

    def test_base_controls_relative_path(self, tmp_path: Path) -> None:
        """file_path stored relative to base, not cwd."""
        robot_file = tmp_path / "sub" / "test.robot"
        f = _make_finding(file_path=robot_file, line=5)
        baseline_file = tmp_path / "baseline.json"
        save_baseline([f], baseline_file, base=tmp_path)
        data = json.loads(baseline_file.read_text())
        assert data[0]["file_path"] == "sub/test.robot"


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
        baseline: set[BaselineKey] = {f1.fingerprint, f2.fingerprint}
        new, suppressed = filter_baseline([f1, f2], baseline)
        assert new == []
        assert suppressed == [f1, f2]

    def test_partial_match(self) -> None:
        f1 = _make_finding(line=1)
        f2 = _make_finding(line=2)
        baseline: set[BaselineKey] = {f1.fingerprint}
        new, suppressed = filter_baseline([f1, f2], baseline)
        assert new == [f2]
        assert suppressed == [f1]

    def test_different_file_not_suppressed(self) -> None:
        baseline_finding = _make_finding(file_path=Path("a.robot"), line=10)
        current_finding = _make_finding(file_path=Path("b.robot"), line=10)
        baseline: set[BaselineKey] = {baseline_finding.fingerprint}
        new, suppressed = filter_baseline([current_finding], baseline)
        assert new == [current_finding]
        assert suppressed == []

    def test_different_line_not_suppressed(self) -> None:
        baseline_finding = _make_finding(line=10)
        current_finding = _make_finding(line=11)
        baseline: set[BaselineKey] = {baseline_finding.fingerprint}
        new, suppressed = filter_baseline([current_finding], baseline)
        assert new == [current_finding]
        assert suppressed == []

    def test_different_pattern_type_not_suppressed(self) -> None:
        baseline_finding = _make_finding(pattern_type=PatternType.SLEEP_IN_TEST)
        current_finding = _make_finding(pattern_type=PatternType.DUPLICATE_KEYWORD)
        baseline: set[BaselineKey] = {baseline_finding.fingerprint}
        new, suppressed = filter_baseline([current_finding], baseline)
        assert new == [current_finding]
        assert suppressed == []

    def test_empty_findings_returns_empty(self) -> None:
        new, suppressed = filter_baseline([], {"some-fingerprint-key"})
        assert new == []
        assert suppressed == []

    def test_message_change_not_suppressed(self) -> None:
        """fingerprint includes message so wording changes are treated as new."""
        f1 = _make_finding(message="Sleep 5s detected")
        f2 = _make_finding(message="Sleep 10s detected")
        assert f1.fingerprint != f2.fingerprint
        baseline: set[BaselineKey] = {f1.fingerprint}
        new, suppressed = filter_baseline([f2], baseline)
        assert new == [f2]
        assert suppressed == []
