# tests/unit/test_cli.py
"""Tests for the robot-optimizer CLI."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from robot_optimizer_core.domain.value_objects import Finding, Severity
from robot_optimizer_core.domain.value_objects.location import Location
from robot_optimizer_core.domain.value_objects.pattern import Pattern, PatternType
from robot_optimizer_core.entrypoints.cli import main
from robot_optimizer_core.entrypoints.cli._formatters import (
    _format_junit,
    _format_sarif,
)
from robot_optimizer_core.entrypoints.cli._html import (
    _PATTERN_CATEGORY_DEFAULT,
    _PATTERN_CATEGORY_MAP,
    _format_html,
    _html_category_metadata,
    _html_display_path,
    _html_health_status,
    _html_render_action_items,
    _html_render_category_cards,
    _html_render_findings_table,
    _html_render_grouped_findings,
)

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
# _html_display_path
# ---------------------------------------------------------------------------


class TestHtmlDisplayPath:
    def test_returns_relative_path_when_inside_root(self, tmp_path: Path) -> None:
        root = tmp_path
        file_path = tmp_path / "sub" / "suite.robot"
        file_path.parent.mkdir()
        file_path.touch()
        result = _html_display_path(file_path, root)
        assert result == str(Path("sub") / "suite.robot")

    def test_falls_back_to_str_when_outside_root(self, tmp_path: Path) -> None:
        root = tmp_path / "sub"
        root.mkdir()
        outside = tmp_path / "other.robot"
        outside.touch()
        result = _html_display_path(outside, root)
        assert result == str(outside)


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
        rf_file.write_bytes(b"*** Test Cases ***\n")
        from robot_optimizer_core.exceptions import AnalysisError

        with (
            patch(
                "robot_optimizer_core.entrypoints.cli._commands.analyze_file",
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
        rf_file.write_bytes(b"*** Test Cases ***\n")
        with patch("robot_optimizer_core.entrypoints.cli._commands.analyze_file", return_value=[]):
            with pytest.raises(SystemExit) as exc:
                main(["analyze", str(rf_file)])
        assert exc.value.code == 0

    def test_no_fail_flag_exits_zero_despite_findings(self, tmp_path: Path) -> None:
        rf_file = tmp_path / "t.robot"
        rf_file.write_bytes(b"*** Test Cases ***\n")
        findings = [_make_finding(rf_file)]
        with patch("robot_optimizer_core.entrypoints.cli._commands.analyze_file", return_value=findings):
            with pytest.raises(SystemExit) as exc:
                main(["analyze", str(rf_file), "--no-fail"])
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# analyze: findings → exit 1
# ---------------------------------------------------------------------------


class TestAnalyzeFindings:
    def test_findings_exits_one(self, tmp_path: Path) -> None:
        rf_file = tmp_path / "t.robot"
        rf_file.write_bytes(b"*** Test Cases ***\n")
        findings = [_make_finding(rf_file)]
        with patch("robot_optimizer_core.entrypoints.cli._commands.analyze_file", return_value=findings):
            with pytest.raises(SystemExit) as exc:
                main(["analyze", str(rf_file)])
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# analyze: directory
# ---------------------------------------------------------------------------


class TestAnalyzeDirectory:
    def test_directory_aggregates_findings(self, tmp_path: Path) -> None:
        from robot_optimizer_core.entrypoints.public_api import DirectoryResults

        f1 = tmp_path / "a.robot"
        f2 = tmp_path / "b.robot"
        f1.write_bytes(b"*** Test Cases ***\n")
        f2.write_bytes(b"*** Test Cases ***\n")
        findings = DirectoryResults(findings={f1: [_make_finding(f1)], f2: []})
        with patch("robot_optimizer_core.entrypoints.cli._commands.analyze_directory", return_value=findings):
            with pytest.raises(SystemExit) as exc:
                main(["analyze", str(tmp_path)])
        assert exc.value.code == 1

    def test_directory_no_findings_exits_zero(self, tmp_path: Path) -> None:
        from robot_optimizer_core.entrypoints.public_api import DirectoryResults

        with patch("robot_optimizer_core.entrypoints.cli._commands.analyze_directory", return_value=DirectoryResults()):
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
        rf_file.write_bytes(b"*** Test Cases ***\n")
        findings = [_make_finding(rf_file)]
        with patch("robot_optimizer_core.entrypoints.cli._commands.analyze_file", return_value=findings):
            with pytest.raises(SystemExit):
                main(["analyze", str(rf_file), "--format", "json"])
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["schema_version"] == "1"
        findings = parsed["findings"]
        assert len(findings) == 1
        assert findings[0]["message"] == "Use explicit wait"

    def test_json_severity_is_plain_string(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Severity in JSON output must be a plain string, not 'Severity.WARNING'."""
        rf_file = tmp_path / "t.robot"
        rf_file.write_bytes(b"*** Test Cases ***\n")
        findings = [_make_finding(rf_file, severity=Severity.WARNING)]
        with patch("robot_optimizer_core.entrypoints.cli._commands.analyze_file", return_value=findings):
            with pytest.raises(SystemExit):
                main(["analyze", str(rf_file), "--format", "json"])
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["findings"][0]["severity"] == "WARNING"

    def test_json_empty_findings_is_empty_list(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rf_file = tmp_path / "t.robot"
        rf_file.write_bytes(b"*** Test Cases ***\n")
        with patch("robot_optimizer_core.entrypoints.cli._commands.analyze_file", return_value=[]):
            with pytest.raises(SystemExit):
                main(["analyze", str(rf_file), "--format", "json"])
        out = capsys.readouterr().out
        result = json.loads(out)
        assert result["schema_version"] == "1"
        assert result["findings"] == []


# ---------------------------------------------------------------------------
# --output-file
# ---------------------------------------------------------------------------


class TestOutputFile:
    def test_writes_to_file(self, tmp_path: Path) -> None:
        rf_file = tmp_path / "t.robot"
        rf_file.write_bytes(b"*** Test Cases ***\n")
        out_file = tmp_path / "out.txt"
        findings = [_make_finding(rf_file)]
        with patch("robot_optimizer_core.entrypoints.cli._commands.analyze_file", return_value=findings):
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
        rf_file.write_bytes(b"*** Test Cases ***\n")
        mock = MagicMock(return_value=[])
        with patch("robot_optimizer_core.entrypoints.cli._commands.analyze_file", mock):
            with pytest.raises(SystemExit):
                main(
                    ["analyze", str(rf_file), "--analyzers", "dead_code,sleep_detector"]
                )
        call_kwargs = mock.call_args.kwargs
        assert call_kwargs["analyzers"] == ["dead_code", "sleep_detector"]


class TestHtmlFormat:
    def test_format_html_escapes_and_contains_metadata(self, tmp_path: Path) -> None:
        # Use a valid directory name on all platforms (< > are forbidden on Windows)
        suite_dir = tmp_path / "suite"
        suite_dir.mkdir()
        finding = _make_finding(
            file_path=suite_dir / "suite.robot",
            message="Use <wait>",
        )
        html = _format_html([finding], suite_dir)
        assert "Robot Framework Suite Health Report" in html
        assert "Executive summary" in html
        assert "Health status" in html
        assert "Recommended actions" in html
        assert "Appendix — Detailed Findings" in html
        assert "Total findings: <strong>1</strong>" in html
        assert "suite.robot" in html
        assert "Use &lt;wait&gt;" in html
        assert str((suite_dir / "suite.robot").resolve()) not in html

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
        assert "Auto-fixable findings" in html
        assert '<div class="metric-value">1</div>' in html


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


# ---------------------------------------------------------------------------
# _html_health_status
# ---------------------------------------------------------------------------


class TestHtmlHealthStatus:
    def _counts(self, error: int = 0, warning: int = 0, info: int = 0) -> dict[str, int]:
        return {"ERROR": error, "WARNING": warning, "INFO": info}

    def test_high_risk_on_any_error(self) -> None:
        assert _html_health_status(self._counts(error=1), []) == "High Risk"

    def test_high_risk_on_ten_or_more_warnings(self) -> None:
        assert _html_health_status(self._counts(warning=10), []) == "High Risk"

    def test_moderate_risk_on_some_warnings(self) -> None:
        assert _html_health_status(self._counts(warning=3), []) == "Moderate Risk"

    def test_healthy_when_no_findings(self) -> None:
        assert _html_health_status(self._counts(), []) == "Healthy"

    def test_low_risk_on_few_info_findings(self, tmp_path: Path) -> None:
        findings = [_make_finding(tmp_path / "a.robot", severity=Severity.INFO) for _ in range(3)]
        assert _html_health_status(self._counts(), findings) == "Low Risk"

    def test_moderate_risk_on_many_info_findings(self, tmp_path: Path) -> None:
        findings = [_make_finding(tmp_path / "a.robot", severity=Severity.INFO) for _ in range(6)]
        assert _html_health_status(self._counts(), findings) == "Moderate Risk"


# ---------------------------------------------------------------------------
# _html_render_category_cards
# ---------------------------------------------------------------------------


class TestHtmlRenderCategoryCards:
    def test_empty_list_returns_empty_string(self) -> None:
        assert _html_render_category_cards([]) == ""

    def test_renders_category_name_and_count(self) -> None:
        cards = _html_render_category_cards(
            [("Stability / flakiness risk", {"count": 3, "impact": "High", "action": "Fix it"})]
        )
        assert "Stability / flakiness risk" in cards
        assert "<strong>3</strong>" in cards

    def test_escapes_html_in_category(self) -> None:
        cards = _html_render_category_cards(
            [("<script>", {"count": 1, "impact": "x", "action": "y"})]
        )
        assert "<script>" not in cards
        assert "&lt;script&gt;" in cards

    def test_multiple_categories_all_rendered(self) -> None:
        cats = [
            ("Cat A", {"count": 1, "impact": "i1", "action": "a1"}),
            ("Cat B", {"count": 2, "impact": "i2", "action": "a2"}),
        ]
        result = _html_render_category_cards(cats)
        assert "Cat A" in result
        assert "Cat B" in result


# ---------------------------------------------------------------------------
# _html_render_action_items
# ---------------------------------------------------------------------------


class TestHtmlRenderActionItems:
    def _finding_with_pattern_name(self, name: str, tmp_path: Path) -> Finding:
        pattern = Pattern(
            type=PatternType.SLEEP_IN_TEST,
            name=name,
            description="desc",
            recommendation="rec",
        )
        return Finding.create(
            pattern=pattern,
            severity=Severity.WARNING,
            location=Location(file_path=tmp_path / "a.robot", line=1),
            message="msg",
        )

    def test_no_findings_returns_empty(self) -> None:
        assert _html_render_action_items([]) == ""

    def test_sleep_finding_triggers_explicit_waits_item(self, tmp_path: Path) -> None:
        f = self._finding_with_pattern_name("Sleep in Test Case", tmp_path)
        result = _html_render_action_items([f])
        assert "Replace fixed sleeps with explicit waits" in result

    def test_unused_keyword_finding_triggers_item(self, tmp_path: Path) -> None:
        f = self._finding_with_pattern_name("Unused Keyword detected", tmp_path)
        result = _html_render_action_items([f])
        assert "Remove or confirm unused legacy keywords" in result

    def test_hardcoded_finding_triggers_item(self, tmp_path: Path) -> None:
        f = self._finding_with_pattern_name("Hardcoded URL", tmp_path)
        result = _html_render_action_items([f])
        assert "Move hardcoded URLs/config into variables" in result

    def test_irrelevant_finding_not_included(self, tmp_path: Path) -> None:
        f = self._finding_with_pattern_name("Some Other Pattern", tmp_path)
        result = _html_render_action_items([f])
        assert "<li>" not in result


# ---------------------------------------------------------------------------
# _html_render_findings_table
# ---------------------------------------------------------------------------


class TestHtmlRenderFindingsTable:
    def test_no_findings_returns_empty_string(self, tmp_path: Path) -> None:
        assert _html_render_findings_table([], tmp_path) == ""

    def test_renders_table_with_finding_data(self, tmp_path: Path) -> None:
        f = _make_finding(file_path=tmp_path / "suite.robot", line=7)
        result = _html_render_findings_table([f], tmp_path)
        assert "<table>" in result
        assert "suite.robot" in result
        assert "7" in result
        assert "WARNING" in result

    def test_rows_sorted_by_file_then_line(self, tmp_path: Path) -> None:
        f1 = _make_finding(file_path=tmp_path / "b.robot", line=5)
        f2 = _make_finding(file_path=tmp_path / "a.robot", line=10)
        f3 = _make_finding(file_path=tmp_path / "a.robot", line=2)
        result = _html_render_findings_table([f1, f2, f3], tmp_path)
        pos_a2 = result.index(">2<")
        pos_a10 = result.index(">10<")
        pos_b5 = result.index(">5<")
        assert pos_a2 < pos_a10 < pos_b5

    def test_escapes_html_in_message(self, tmp_path: Path) -> None:
        f = _make_finding(file_path=tmp_path / "a.robot", message="Use <wait>")
        result = _html_render_findings_table([f], tmp_path)
        assert "Use &lt;wait&gt;" in result
        assert "Use <wait>" not in result


# ---------------------------------------------------------------------------
# _html_render_grouped_findings
# ---------------------------------------------------------------------------


class TestHtmlRenderGroupedFindings:
    def test_empty_categories_returns_empty_string(self, tmp_path: Path) -> None:
        assert _html_render_grouped_findings([], {}, tmp_path) == ""

    def test_renders_section_per_category(self, tmp_path: Path) -> None:
        f = _make_finding(file_path=tmp_path / "a.robot", line=1)
        result = _html_render_grouped_findings(
            ["Cat A"], {"Cat A": [f]}, tmp_path
        )
        assert "<section" in result
        assert "Cat A" in result

    def test_findings_within_category_sorted_by_file_line(self, tmp_path: Path) -> None:
        f1 = _make_finding(file_path=tmp_path / "b.robot", line=1)
        f2 = _make_finding(file_path=tmp_path / "a.robot", line=5)
        f3 = _make_finding(file_path=tmp_path / "a.robot", line=2)
        result = _html_render_grouped_findings(
            ["All"], {"All": [f1, f2, f3]}, tmp_path
        )
        pos_a2 = result.index(":2<")
        pos_a5 = result.index(":5<")
        pos_b1 = result.index(":1<")
        assert pos_a2 < pos_a5 < pos_b1

    def test_escapes_severity_and_message(self, tmp_path: Path) -> None:
        f = _make_finding(file_path=tmp_path / "a.robot", message="Bad <tag>")
        result = _html_render_grouped_findings(["C"], {"C": [f]}, tmp_path)
        assert "Bad &lt;tag&gt;" in result


# ---------------------------------------------------------------------------
# _html_category_metadata / _PATTERN_CATEGORY_MAP
# ---------------------------------------------------------------------------


def _first_keyword(entry: tuple) -> str:
    """Return the first keyword string from a _PATTERN_CATEGORY_MAP entry."""
    return entry[0][0]


class TestHtmlCategoryMetadata:
    @pytest.mark.parametrize("entry", _PATTERN_CATEGORY_MAP)
    def test_keyword_match_returns_correct_tuple(
        self, entry: tuple[tuple[str, ...], str, str, str]
    ) -> None:
        keywords, category, impact, action = entry
        result = _html_category_metadata(keywords[0])
        assert result == (category, impact, action)

    @pytest.mark.parametrize("entry", _PATTERN_CATEGORY_MAP)
    def test_keyword_match_is_case_insensitive(
        self, entry: tuple[tuple[str, ...], str, str, str]
    ) -> None:
        keywords, category, impact, action = entry
        result = _html_category_metadata(keywords[0].upper())
        assert result == (category, impact, action)

    def test_all_keywords_in_each_entry_match(self) -> None:
        for keywords, category, impact, action in _PATTERN_CATEGORY_MAP:
            for kw in keywords:
                assert _html_category_metadata(kw) == (category, impact, action)
                assert _html_category_metadata(kw.upper()) == (category, impact, action)

    def test_no_keyword_match_returns_default(self) -> None:
        result = _html_category_metadata("zzz_no_such_pattern_zzz")
        assert result == _PATTERN_CATEGORY_DEFAULT

    def test_partial_keyword_match_within_pattern_name(self) -> None:
        # "sleep" keyword should match a pattern name containing "sleep"
        category, impact, action = _html_category_metadata("Sleep in Test Case")
        assert category  # non-empty
        assert impact
        assert action

    def test_integration_category_cards_contain_metadata(self, tmp_path: Path) -> None:
        # Pattern name is "Sleep in Test Case" — "sleep" keyword triggers the first entry
        _, category, impact, action = _PATTERN_CATEGORY_MAP[0]
        top_categories = [(category, {"count": 1, "impact": impact, "action": action})]
        html = _html_render_category_cards(top_categories)  # type: ignore[arg-type]
        assert category in html
        assert impact in html
        assert action in html


# ---------------------------------------------------------------------------
# subcommands: list-analyzers, upgrade
# ---------------------------------------------------------------------------


class TestListAnalyzers:
    def test_list_analyzers_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["list-analyzers"])
        assert exc.value.code == 0

    def test_list_analyzers_json_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit):
            main(["list-analyzers", "--format", "json"])
        out = capsys.readouterr().out
        records = json.loads(out)
        assert isinstance(records, list)
        assert len(records) > 0

    def test_list_analyzers_text_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit):
            main(["list-analyzers"])
        out = capsys.readouterr().out
        assert "analyzers" in out.lower()


class TestUpgrade:
    def test_upgrade_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["upgrade"])
        assert exc.value.code == 0

    def test_upgrade_output_contains_feature_table(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit):
            main(["upgrade"])
        out = capsys.readouterr().out
        assert "Feature" in out


# ---------------------------------------------------------------------------
# --debug and --verbose flags
# ---------------------------------------------------------------------------


class TestVerboseDebugFlags:
    def test_verbose_flag_accepted(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\n")
        with patch("robot_optimizer_core.entrypoints.cli._commands.analyze_file", return_value=[]):
            with pytest.raises(SystemExit) as exc:
                main(["--verbose", "analyze", str(f)])
        assert exc.value.code == 0

    def test_debug_flag_accepted(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\n")
        with patch("robot_optimizer_core.entrypoints.cli._commands.analyze_file", return_value=[]):
            with pytest.raises(SystemExit) as exc:
                main(["--debug", "analyze", str(f)])
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# --min-severity invalid value
# ---------------------------------------------------------------------------


class TestMinSeverityInvalid:
    def test_invalid_severity_exits_error(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\n")
        with pytest.raises(SystemExit) as exc:
            main(["analyze", str(f), "--min-severity", "BADVAL"])
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# --config flag errors
# ---------------------------------------------------------------------------


class TestConfigFlag:
    def test_nonexistent_config_exits_error(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\n")
        with pytest.raises(SystemExit) as exc:
            main(["analyze", str(f), "--config", str(tmp_path / "nope.toml")])
        assert exc.value.code == 2

    def test_invalid_config_settings_exits_error(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\n")
        # TOML with conflicting settings causes ConfigurationError in Settings
        bad_toml = tmp_path / "bad.toml"
        bad_toml.write_text(
            "[tool.robot-optimizer]\n"
            'file_patterns = ["*.robot"]\n'
            'exclude_patterns = ["*.robot"]\n'
        )
        with pytest.raises(SystemExit) as exc:
            main(["analyze", str(f), "--config", str(bad_toml)])
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# --output-file errors
# ---------------------------------------------------------------------------


class TestOutputFileError:
    def test_unwritable_output_file_exits_error(self, tmp_path: Path) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\n")
        findings = [_make_finding(f)]
        bad_out = tmp_path / "nonexistent_dir" / "out.txt"
        with patch("robot_optimizer_core.entrypoints.cli._commands.analyze_file", return_value=findings):
            with pytest.raises(SystemExit) as exc:
                main(
                    ["analyze", str(f), "--output-file", str(bad_out)]
                )
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# sarif format via CLI
# ---------------------------------------------------------------------------


class TestSarifFormatCli:
    def test_sarif_format_valid_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\n")
        findings = [_make_finding(f)]
        with patch("robot_optimizer_core.entrypoints.cli._commands.analyze_file", return_value=findings):
            with pytest.raises(SystemExit):
                main(["analyze", str(f), "--format", "sarif"])
        out = capsys.readouterr().out
        sarif = json.loads(out)
        assert sarif["version"] == "2.1.0"

    def test_sarif_finding_with_documentation_url(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        pattern = Pattern(
            type=PatternType.SLEEP_IN_TEST,
            name="Sleep in Test",
            description="Sleep used",
            recommendation="Use wait",
            documentation_url="https://example.com/docs",
        )

        finding = Finding.create(
            pattern=pattern,
            severity=Severity.WARNING,
            location=Location(file_path=tmp_path / "t.robot", line=5),
            message="Sleep found",
        )
        sarif = json.loads(_format_sarif([finding], tmp_path))
        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        assert any("helpUri" in r for r in rules)


# ---------------------------------------------------------------------------
# html format via CLI
# ---------------------------------------------------------------------------


class TestHtmlFormatViaCLI:
    def test_html_format_via_main(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\n")
        findings = [_make_finding(f)]
        with patch("robot_optimizer_core.entrypoints.cli._commands.analyze_file", return_value=findings):
            with pytest.raises(SystemExit):
                main(["analyze", str(f), "--format", "html"])
        out = capsys.readouterr().out
        assert "Robot Framework" in out


# ---------------------------------------------------------------------------
# --format junit
# ---------------------------------------------------------------------------


class TestJunitFormat:
    def test_junit_is_valid_xml(self, tmp_path: Path) -> None:
        """JUnit output must be valid XML."""
        finding = _make_finding(file_path=tmp_path / "suite.robot")
        output = _format_junit([finding], tmp_path)
        # Should not raise an exception
        root = ET.fromstring(output)
        assert root is not None

    def test_junit_has_testsuite_root(self, tmp_path: Path) -> None:
        """JUnit output must have a testsuite root element."""
        finding = _make_finding(file_path=tmp_path / "suite.robot")
        output = _format_junit([finding], tmp_path)
        root = ET.fromstring(output)
        assert root.tag == "testsuite"

    def test_junit_testsuite_name_is_path(self, tmp_path: Path) -> None:
        """testsuite name attribute must be the analyzed path."""
        finding = _make_finding(file_path=tmp_path / "suite.robot")
        output = _format_junit([finding], tmp_path)
        root = ET.fromstring(output)
        assert root.get("name") == str(tmp_path)

    def test_junit_tests_count(self, tmp_path: Path) -> None:
        """testsuite tests attribute must match finding count."""
        f1 = _make_finding(file_path=tmp_path / "a.robot")
        f2 = _make_finding(file_path=tmp_path / "b.robot")
        output = _format_junit([f1, f2], tmp_path)
        root = ET.fromstring(output)
        assert root.get("tests") == "2"

    def test_junit_empty_findings(self, tmp_path: Path) -> None:
        """Empty findings should produce a valid testsuite with 0 tests."""
        output = _format_junit([], tmp_path)
        root = ET.fromstring(output)
        assert root.get("tests") == "0"
        assert len(root) == 0

    def test_junit_testcase_name_includes_pattern_type_and_line(
        self, tmp_path: Path
    ) -> None:
        """testcase name must be '{pattern_type} at line {line}'."""
        finding = _make_finding(
            file_path=tmp_path / "suite.robot", line=42
        )
        output = _format_junit([finding], tmp_path)
        root = ET.fromstring(output)
        testcase = root.find("testcase")
        assert testcase is not None
        name = testcase.get("name")
        assert "SLEEP_IN_TEST" in name
        assert "at line 42" in name

    def test_junit_testcase_classname_is_file_path(self, tmp_path: Path) -> None:
        """testcase classname must be the file path."""
        robot_file = tmp_path / "suite.robot"
        finding = _make_finding(file_path=robot_file)
        output = _format_junit([finding], tmp_path)
        root = ET.fromstring(output)
        testcase = root.find("testcase")
        assert testcase is not None
        assert testcase.get("classname") == str(robot_file)

    def test_junit_failure_element_present(self, tmp_path: Path) -> None:
        """Each testcase must have a failure element."""
        finding = _make_finding(file_path=tmp_path / "suite.robot")
        output = _format_junit([finding], tmp_path)
        root = ET.fromstring(output)
        testcase = root.find("testcase")
        failure = testcase.find("failure")
        assert failure is not None

    def test_junit_failure_message_is_pattern_name(self, tmp_path: Path) -> None:
        """failure message attribute must be the pattern name."""
        finding = _make_finding(file_path=tmp_path / "suite.robot")
        output = _format_junit([finding], tmp_path)
        root = ET.fromstring(output)
        failure = root.find("testcase/failure")
        assert failure.get("message") == "Sleep in Test Case"

    def test_junit_failure_type_is_severity(self, tmp_path: Path) -> None:
        """failure type attribute must be the severity."""
        finding = _make_finding(
            file_path=tmp_path / "suite.robot", severity=Severity.ERROR
        )
        output = _format_junit([finding], tmp_path)
        root = ET.fromstring(output)
        failure = root.find("testcase/failure")
        assert failure.get("type") == "ERROR"

    def test_junit_failure_text_is_finding_message(self, tmp_path: Path) -> None:
        """failure text content must be the finding message."""
        finding = _make_finding(
            file_path=tmp_path / "suite.robot",
            message="Custom finding message",
        )
        output = _format_junit([finding], tmp_path)
        root = ET.fromstring(output)
        failure = root.find("testcase/failure")
        assert failure.text == "Custom finding message"

    def test_junit_failures_count_is_error_severity(self, tmp_path: Path) -> None:
        """failures attribute must count ERROR severity findings only."""
        f1 = _make_finding(
            file_path=tmp_path / "a.robot", severity=Severity.ERROR
        )
        f2 = _make_finding(
            file_path=tmp_path / "b.robot", severity=Severity.WARNING
        )
        f3 = _make_finding(
            file_path=tmp_path / "c.robot", severity=Severity.ERROR
        )
        output = _format_junit([f1, f2, f3], tmp_path)
        root = ET.fromstring(output)
        assert root.get("failures") == "2"

    def test_junit_deterministic_ordering(self, tmp_path: Path) -> None:
        """testcases must be in deterministic order (file, then line)."""
        f1 = _make_finding(file_path=tmp_path / "b.robot", line=5)
        f2 = _make_finding(file_path=tmp_path / "a.robot", line=10)
        f3 = _make_finding(file_path=tmp_path / "a.robot", line=3)

        output1 = _format_junit([f1, f2, f3], tmp_path)
        output2 = _format_junit([f3, f1, f2], tmp_path)
        assert output1 == output2

        root = ET.fromstring(output1)
        testcases = root.findall("testcase")
        names = [tc.get("name") for tc in testcases]
        # a.robot:3, a.robot:10, b.robot:5
        assert "3" in names[0]
        assert "10" in names[1]
        assert "5" in names[2]

    def test_junit_has_xml_declaration(self, tmp_path: Path) -> None:
        """Output must start with XML declaration."""
        finding = _make_finding(file_path=tmp_path / "suite.robot")
        output = _format_junit([finding], tmp_path)
        assert output.startswith('<?xml version="1.0"')


# ---------------------------------------------------------------------------
# partial failure (directory with errors)
# ---------------------------------------------------------------------------


class TestPartialFailure:
    def test_partial_failure_exits_three(self, tmp_path: Path) -> None:
        from robot_optimizer_core.entrypoints.public_api import DirectoryResults

        results = DirectoryResults()
        results.errors = [(tmp_path / "bad.robot", Exception("parse fail"))]

        with patch("robot_optimizer_core.entrypoints.cli._commands.analyze_directory", return_value=results):
            with pytest.raises(SystemExit) as exc:
                main(["analyze", str(tmp_path)])
        assert exc.value.code == 3


# ---------------------------------------------------------------------------
# _colour helper (tty path)
# ---------------------------------------------------------------------------


class TestColour:
    def test_colour_applied_when_tty(self) -> None:
        from robot_optimizer_core.entrypoints.cli._formatters import _colour

        with patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            result = _colour("WARN", Severity.WARNING)
        assert "WARN" in result
