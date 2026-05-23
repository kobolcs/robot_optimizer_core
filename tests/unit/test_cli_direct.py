# tests/unit/test_cli_direct.py
"""Unit tests that call main() directly (no subprocess) against real temp files.

Unlike test_cli.py — which patches analyze_file — these tests run the full
analysis pipeline so coverage instruments the actual analyzer code paths.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from robot_optimizer_core.entrypoints.cli import main

_SLEEP_ROBOT = b"*** Test Cases ***\nMy Test\n    Sleep    5\n"
_CLEAN_ROBOT = b"*** Test Cases ***\nMy Test\n    Log    hello\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> int:
    """Patch sys.argv, call main(), and return the exit code."""
    monkeypatch.setattr(sys, "argv", ["robot-optimizer", *args])
    with pytest.raises(SystemExit) as exc:
        main()
    return exc.value.code


# ---------------------------------------------------------------------------
# analyze — real file, no mocking
# ---------------------------------------------------------------------------


class TestAnalyzeRealFile:
    def test_file_with_sleep_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A real .robot file containing Sleep should produce findings → exit 1."""
        f = tmp_path / "suite.robot"
        f.write_bytes(_SLEEP_ROBOT)
        code = _run(monkeypatch, ["analyze", str(f)])
        assert code == 1

    def test_missing_file_exits_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        code = _run(monkeypatch, ["analyze", str(tmp_path / "nosuch.robot")])
        assert code == 2


# ---------------------------------------------------------------------------
# --format json — real pipeline output
# ---------------------------------------------------------------------------


class TestFormatJsonReal:
    def test_json_output_is_valid_list(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        f = tmp_path / "suite.robot"
        f.write_bytes(_SLEEP_ROBOT)
        _run(monkeypatch, ["analyze", str(f), "--format", "json", "--no-fail"])
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["schema_version"] == "1"
        assert isinstance(parsed["findings"], list)

    def test_json_findings_have_expected_keys(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        f = tmp_path / "suite.robot"
        f.write_bytes(_SLEEP_ROBOT)
        _run(monkeypatch, ["analyze", str(f), "--format", "json", "--no-fail"])
        parsed = json.loads(capsys.readouterr().out)
        findings = parsed["findings"]
        assert len(findings) > 0
        finding = findings[0]
        assert "severity" in finding
        assert "message" in finding

    def test_json_severity_is_plain_string(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        f = tmp_path / "suite.robot"
        f.write_bytes(_SLEEP_ROBOT)
        _run(monkeypatch, ["analyze", str(f), "--format", "json", "--no-fail"])
        parsed = json.loads(capsys.readouterr().out)
        findings = parsed["findings"]
        assert all(isinstance(item["severity"], str) for item in findings)
        assert all("." not in item["severity"] for item in findings)


# ---------------------------------------------------------------------------
# --min-severity WARNING filtering
# ---------------------------------------------------------------------------


class TestMinSeverityFiltering:
    def test_min_severity_error_excludes_warnings(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Findings below ERROR must not appear when --min-severity ERROR is set."""
        f = tmp_path / "suite.robot"
        f.write_bytes(_SLEEP_ROBOT)
        _run(
            monkeypatch,
            ["analyze", str(f), "--format", "json", "--min-severity", "ERROR", "--no-fail"],
        )
        parsed = json.loads(capsys.readouterr().out)
        severities = {item["severity"] for item in parsed["findings"]}
        assert "WARNING" not in severities
        assert "INFO" not in severities

    def test_min_severity_warning_keeps_warnings(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        f = tmp_path / "suite.robot"
        f.write_bytes(_SLEEP_ROBOT)
        _run(
            monkeypatch,
            ["analyze", str(f), "--format", "json", "--min-severity", "WARNING", "--no-fail"],
        )
        parsed = json.loads(capsys.readouterr().out)
        # Sleep detector fires at WARNING; the list must be non-empty
        assert len(parsed["findings"]) > 0


# ---------------------------------------------------------------------------
# --no-fail
# ---------------------------------------------------------------------------


class TestNoFail:
    def test_no_fail_exits_zero_with_findings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        f = tmp_path / "suite.robot"
        f.write_bytes(_SLEEP_ROBOT)
        code = _run(monkeypatch, ["analyze", str(f), "--no-fail"])
        assert code == 0

    def test_no_fail_clean_file_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        f = tmp_path / "clean.robot"
        f.write_bytes(_CLEAN_ROBOT)
        code = _run(monkeypatch, ["analyze", str(f), "--no-fail"])
        assert code == 0


# ---------------------------------------------------------------------------
# list-analyzers subcommand
# ---------------------------------------------------------------------------


class TestListAnalyzersDirect:
    def test_exits_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        code = _run(monkeypatch, ["list-analyzers"])
        assert code == 0

    def test_text_output_contains_known_analyzer(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _run(monkeypatch, ["list-analyzers"])
        out = capsys.readouterr().out
        assert "dead_code" in out
        assert "sleep_detector" in out

    def test_json_output_lists_all_core_analyzers(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _run(monkeypatch, ["list-analyzers", "--format", "json"])
        records = json.loads(capsys.readouterr().out)
        names = {r["name"] for r in records}
        expected = {
            "dead_code",
            "sleep_detector",
            "hardcoded_value",
            "naming_convention",
            "setup_teardown",
            "tag_consistency",
            "test_documentation",
        }
        assert expected.issubset(names)
