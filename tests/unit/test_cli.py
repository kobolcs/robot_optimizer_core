# tests/unit/test_cli.py
"""Tests for the robot-optimizer CLI."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from robot_optimizer_core.cli import _format_html, main
from robot_optimizer_core.domain.value_objects import Finding, Severity
from robot_optimizer_core.domain.value_objects.location import Location
from robot_optimizer_core.domain.value_objects.pattern import Pattern, PatternType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_finding(
    file_path: Path = Path("suite.robot"),
    line: int = 10,
    severity: Severity = Severity.WARNING,
    message: str = "Use explicit wait",
) -> Finding:
    pattern = Pattern(
        type=PatternType.SLEEP_IN_TEST,
        name="Sleep in Test Case",
        description="Sleep detected",
        recommendation="Use explicit wait",
    )
    return Finding.create(
        pattern=pattern,
        severity=severity,
        location=Location(file_path=file_path, line=line),
        message=message,
    )


# ---------------------------------------------------------------------------
# --version
# ---------------------------------------------------------------------------


class TestVersion:
    def test_version_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# analyze: missing / bad path
# ---------------------------------------------------------------------------


class TestAnalyzePath:
    def test_missing_path_exits_error(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["analyze", str(tmp_path / "nonexistent.robot")])
        assert exc.value.code == 2

    def test_analysis_error_exits_error(self, tmp_path: Path) -> None:
        rf_file = tmp_path / "t.robot"
        rf_file.write_text("*** Test Cases ***\n")
        from robot_optimizer_core.exceptions import AnalysisError

        with patch(
            "robot_optimizer_core.cli.analyze_file", side_effect=AnalysisError("boom")
        ), pytest.raises(SystemExit) as exc:
            main(["analyze", str(rf_file)])
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# analyze: clean file → exit 0
# ---------------------------------------------------------------------------


class TestAnalyzeClean:
    def test_no_findings_exits_zero(self, tmp_path: Path) -> None:
        rf_file = tmp_path / "t.robot"
        rf_file.write_text("*** Test Cases ***\n")
        with patch("robot_optimizer_core.cli.analyze_file", return_value=[]):
            with pytest.raises(SystemExit) as exc:
                main(["analyze", str(rf_file)])
        assert exc.value.code == 0

    def test_no_fail_flag_exits_zero_despite_findings(self, tmp_path: Path) -> None:
        rf_file = tmp_path / "t.robot"
        rf_file.write_text("*** Test Cases ***\n")
        findings = [_make_finding(rf_file)]
        with patch("robot_optimizer_core.cli.analyze_file", return_value=findings):
            with pytest.raises(SystemExit) as exc:
                main(["analyze", str(rf_file), "--no-fail"])
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# analyze: findings → exit 1
# ---------------------------------------------------------------------------


class TestAnalyzeFindings:
    def test_findings_exits_one(self, tmp_path: Path) -> None:
        rf_file = tmp_path / "t.robot"
        rf_file.write_text("*** Test Cases ***\n")
        findings = [_make_finding(rf_file)]
        with patch("robot_optimizer_core.cli.analyze_file", return_value=findings):
            with pytest.raises(SystemExit) as exc:
                main(["analyze", str(rf_file)])
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# analyze: directory
# ---------------------------------------------------------------------------


class TestAnalyzeDirectory:
    def test_directory_aggregates_findings(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.robot"
        f2 = tmp_path / "b.robot"
        f1.write_text("*** Test Cases ***\n")
        f2.write_text("*** Test Cases ***\n")
        findings = {f1: [_make_finding(f1)], f2: []}
        with patch("robot_optimizer_core.cli.analyze_directory", return_value=findings):
            with pytest.raises(SystemExit) as exc:
                main(["analyze", str(tmp_path)])
        assert exc.value.code == 1

    def test_directory_no_findings_exits_zero(self, tmp_path: Path) -> None:
        with patch("robot_optimizer_core.cli.analyze_directory", return_value={}):
            with pytest.raises(SystemExit) as exc:
                main(["analyze", str(tmp_path)])
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# --format json
# ---------------------------------------------------------------------------


class TestJsonFormat:
    def test_json_format_is_valid_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rf_file = tmp_path / "t.robot"
        rf_file.write_text("*** Test Cases ***\n")
        findings = [_make_finding(rf_file)]
        with patch("robot_optimizer_core.cli.analyze_file", return_value=findings):
            with pytest.raises(SystemExit):
                main(["analyze", str(rf_file), "--format", "json"])
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["message"] == "Use explicit wait"

    def test_json_severity_is_plain_string(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Severity in JSON output must be a plain string, not 'Severity.WARNING'."""
        rf_file = tmp_path / "t.robot"
        rf_file.write_text("*** Test Cases ***\n")
        findings = [_make_finding(rf_file, severity=Severity.WARNING)]
        with patch("robot_optimizer_core.cli.analyze_file", return_value=findings):
            with pytest.raises(SystemExit):
                main(["analyze", str(rf_file), "--format", "json"])
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed[0]["severity"] == "WARNING"

    def test_json_empty_findings_is_empty_list(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rf_file = tmp_path / "t.robot"
        rf_file.write_text("*** Test Cases ***\n")
        with patch("robot_optimizer_core.cli.analyze_file", return_value=[]):
            with pytest.raises(SystemExit):
                main(["analyze", str(rf_file), "--format", "json"])
        out = capsys.readouterr().out
        assert json.loads(out) == []


# ---------------------------------------------------------------------------
# --output-file
# ---------------------------------------------------------------------------


class TestOutputFile:
    def test_writes_to_file(self, tmp_path: Path) -> None:
        rf_file = tmp_path / "t.robot"
        rf_file.write_text("*** Test Cases ***\n")
        out_file = tmp_path / "out.txt"
        findings = [_make_finding(rf_file)]
        with patch("robot_optimizer_core.cli.analyze_file", return_value=findings):
            with pytest.raises(SystemExit):
                main(["analyze", str(rf_file), "--output-file", str(out_file)])
        assert out_file.exists()
        assert "Sleep in Test Case" in out_file.read_text()


# ---------------------------------------------------------------------------
# --analyzers
# ---------------------------------------------------------------------------


class TestAnalyzerSelection:
    def test_passes_analyzer_names_to_api(self, tmp_path: Path) -> None:
        rf_file = tmp_path / "t.robot"
        rf_file.write_text("*** Test Cases ***\n")
        mock = MagicMock(return_value=[])
        with patch("robot_optimizer_core.cli.analyze_file", mock):
            with pytest.raises(SystemExit):
                main(
                    ["analyze", str(rf_file), "--analyzers", "dead_code,sleep_detector"]
                )
        call_kwargs = mock.call_args.kwargs
        assert call_kwargs["analyzers"] == ["dead_code", "sleep_detector"]


class TestHtmlFormat:
    def test_format_html_escapes_and_contains_metadata(self, tmp_path: Path) -> None:
        finding = _make_finding(file_path=Path("<suite>.robot"), message="Use <wait>")
        html = _format_html([finding], tmp_path)
        assert "Robot Framework Suite Health Report" in html
        assert "Total findings: 1" in html
        assert "&lt;suite&gt;.robot" in html
        assert "Use &lt;wait&gt;" in html

    def test_format_html_no_findings_message(self, tmp_path: Path) -> None:
        html = _format_html([], tmp_path)
        assert "No findings." in html
