# tests/unit/test_cli.py
"""Tests for the robot-optimizer CLI."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from robot_optimizer_core.cli import _format_html, _format_sarif, main
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
        rf_file.write_bytes("*** Test Cases ***\n".encode("utf-8"))
        from robot_optimizer_core.exceptions import AnalysisError

        with (
            patch(
                "robot_optimizer_core.cli.analyze_file",
                side_effect=AnalysisError("boom"),
            ),
            pytest.raises(SystemExit) as exc,
        ):
            main(["analyze", str(rf_file)])
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# analyze: clean file → exit 0
# ---------------------------------------------------------------------------


class TestAnalyzeClean:
    def test_no_findings_exits_zero(self, tmp_path: Path) -> None:
        rf_file = tmp_path / "t.robot"
        rf_file.write_bytes("*** Test Cases ***\n".encode("utf-8"))
        with patch("robot_optimizer_core.cli.analyze_file", return_value=[]):
            with pytest.raises(SystemExit) as exc:
                main(["analyze", str(rf_file)])
        assert exc.value.code == 0

    def test_no_fail_flag_exits_zero_despite_findings(self, tmp_path: Path) -> None:
        rf_file = tmp_path / "t.robot"
        rf_file.write_bytes("*** Test Cases ***\n".encode("utf-8"))
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
        rf_file.write_bytes("*** Test Cases ***\n".encode("utf-8"))
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
        f1.write_bytes("*** Test Cases ***\n".encode("utf-8"))
        f2.write_bytes("*** Test Cases ***\n".encode("utf-8"))
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
        rf_file.write_bytes("*** Test Cases ***\n".encode("utf-8"))
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
        rf_file.write_bytes("*** Test Cases ***\n".encode("utf-8"))
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
        rf_file.write_bytes("*** Test Cases ***\n".encode("utf-8"))
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
        rf_file.write_bytes("*** Test Cases ***\n".encode("utf-8"))
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
        rf_file.write_bytes("*** Test Cases ***\n".encode("utf-8"))
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
        suite_dir = tmp_path / "<suite>"
        suite_dir.mkdir()
        finding = _make_finding(
            file_path=suite_dir / "<suite>.robot",
            message="Use <wait>",
        )
        html = _format_html([finding], suite_dir)
        assert "Robot Framework Suite Health Report" in html
        assert "Executive summary" in html
        assert "Health status" in html
        assert "Recommended actions" in html
        assert "Appendix — Detailed Findings" in html
        assert "Total findings: 1" in html
        assert "&lt;suite&gt;.robot" in html
        assert "Use &lt;wait&gt;" in html
        assert str((suite_dir / "<suite>.robot").resolve()) not in html

    def test_format_html_no_findings_message(self, tmp_path: Path) -> None:
        html = _format_html([], tmp_path)
        assert "Robot Framework Suite Health Report" in html
        assert "Executive summary" in html
        assert "Health status" in html
        assert "Healthy" in html
        assert "No findings were detected" in html

    def test_format_html_auto_fixable_count_uses_flag_not_recommendation(
        self, tmp_path: Path
    ) -> None:
        auto_fixable_pattern = Pattern(
            type=PatternType.SLEEP_IN_TEST,
            name="Sleep in Test Case",
            description="Sleep detected",
            recommendation="Use explicit wait",
            auto_fixable=True,
        )
        not_auto_fixable_pattern = Pattern(
            type=PatternType.HARDCODED_VALUE,
            name="Hardcoded URL",
            description="URL detected",
            recommendation="Move URL to variable",
            auto_fixable=False,
        )
        findings = [
            Finding.create(
                pattern=auto_fixable_pattern,
                severity=Severity.WARNING,
                location=Location(file_path=tmp_path / "a.robot", line=1),
                message="Sleep used",
            ),
            Finding.create(
                pattern=not_auto_fixable_pattern,
                severity=Severity.WARNING,
                location=Location(file_path=tmp_path / "b.robot", line=2),
                message="Hardcoded URL",
            ),
        ]

        html = _format_html(findings, tmp_path)
        assert "<strong>Auto-fixable findings</strong><div>1</div>" in html


class TestUpgradeCommand:
    def test_upgrade_message_includes_basic_html_as_core(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["upgrade"])
        assert exc.value.code == 0

        output = capsys.readouterr().out
        assert "Basic HTML report" in output
        assert "Advanced branded HTML reports" in output
        assert "PDF export" in output
        assert "HTML / PDF reports" not in output


# ---------------------------------------------------------------------------
# --format sarif
# ---------------------------------------------------------------------------


class TestSarifFormat:
    def test_sarif_is_valid_json_with_required_structure(self, tmp_path: Path) -> None:
        """SARIF output must be valid JSON with the required top-level fields."""
        finding = _make_finding(file_path=tmp_path / "suite.robot")
        output = _format_sarif([finding], tmp_path)
        parsed = json.loads(output)
        assert parsed["version"] == "2.1.0"
        assert "$schema" in parsed
        assert len(parsed["runs"]) == 1
        run = parsed["runs"][0]
        assert "tool" in run
        assert "results" in run
        assert "rules" in run["tool"]["driver"]

    def test_sarif_results_and_rules_are_present(self, tmp_path: Path) -> None:
        """Each finding must produce a result entry and a corresponding rule."""
        finding = _make_finding(file_path=tmp_path / "suite.robot")
        parsed = json.loads(_format_sarif([finding], tmp_path))
        run = parsed["runs"][0]
        assert len(run["results"]) == 1
        assert len(run["tool"]["driver"]["rules"]) == 1
        rule = run["tool"]["driver"]["rules"][0]
        assert "id" in rule
        assert "name" in rule
        assert "shortDescription" in rule

    def test_sarif_empty_findings(self, tmp_path: Path) -> None:
        """No findings should produce an empty results list and rules list."""
        parsed = json.loads(_format_sarif([], tmp_path))
        run = parsed["runs"][0]
        assert run["results"] == []
        assert run["tool"]["driver"]["rules"] == []

    def test_sarif_artifact_uri_directory_analysis(self, tmp_path: Path) -> None:
        """For directory analysis, artifact URI must be relative to the directory root."""
        robot_file = tmp_path / "suite.robot"
        finding = _make_finding(file_path=robot_file)
        parsed = json.loads(_format_sarif([finding], tmp_path))
        uri = parsed["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
            "artifactLocation"
        ]["uri"]
        assert uri == "suite.robot"
        assert str(tmp_path) not in uri

    def test_sarif_artifact_uri_single_file_analysis(self, tmp_path: Path) -> None:
        """For single-file analysis, artifact URI must be relative to the file's parent dir."""
        robot_file = tmp_path / "suite.robot"
        finding = _make_finding(file_path=robot_file)
        # Pass the file itself as the analysed path (single-file mode)
        parsed = json.loads(_format_sarif([finding], robot_file))
        uri = parsed["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
            "artifactLocation"
        ]["uri"]
        assert uri == "suite.robot"
        assert str(tmp_path) not in uri

    def test_sarif_deterministic_ordering(self, tmp_path: Path) -> None:
        """Results must be emitted in a stable, sorted order regardless of input order."""
        f1 = _make_finding(file_path=tmp_path / "b.robot", line=5, message="msg B")
        f2 = _make_finding(file_path=tmp_path / "a.robot", line=10, message="msg A")
        f3 = _make_finding(file_path=tmp_path / "a.robot", line=3, message="msg A")

        # Run twice with different orderings; results must be identical.
        out1 = _format_sarif([f1, f2, f3], tmp_path)
        out2 = _format_sarif([f3, f1, f2], tmp_path)
        assert json.loads(out1) == json.loads(out2)

        # The first result should be the finding on a.robot line 3.
        parsed = json.loads(out1)
        first_result = parsed["runs"][0]["results"][0]
        assert (
            first_result["locations"][0]["physicalLocation"]["region"]["startLine"] == 3
        )

    def test_sarif_rules_deduplicated_and_sorted(self, tmp_path: Path) -> None:
        """Duplicate rule IDs must appear only once and rules must be sorted."""
        f1 = _make_finding(file_path=tmp_path / "a.robot", line=1)
        f2 = _make_finding(file_path=tmp_path / "a.robot", line=2)
        # Both findings use the same pattern type → same rule ID.
        parsed = json.loads(_format_sarif([f1, f2], tmp_path))
        rules = parsed["runs"][0]["tool"]["driver"]["rules"]
        rule_ids = [r["id"] for r in rules]
        assert len(rule_ids) == len(set(rule_ids)), "Duplicate rule IDs found"
        assert rule_ids == sorted(rule_ids), "Rules are not sorted"
