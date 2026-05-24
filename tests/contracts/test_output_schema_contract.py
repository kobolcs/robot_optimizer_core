# tests/contracts/test_output_schema_contract.py
"""Output schema contract tests — pin JSON and SARIF output structure.

These tests validate that the --format=json and --format=sarif outputs remain
structurally compatible across releases. A failure here means a breaking change
to the output schema that would break downstream consumers (CI integrations,
SAST dashboards, IDE plugins).

How to make a legitimate schema change:
  1. Add the new key to both the schema artifact and the test assertions.
  2. Never remove a key without a major version bump.
  3. Update tests/contracts/schemas/output_v1.json accordingly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from robot_optimizer_core import analyze_file
from robot_optimizer_core.domain.value_objects.finding import Finding
from robot_optimizer_core.domain.value_objects.location import Location
from robot_optimizer_core.domain.value_objects.pattern import Pattern, PatternType
from robot_optimizer_core.domain.value_objects.remediation import RemediationHint
from robot_optimizer_core.domain.value_objects.severity import Severity
from robot_optimizer_core.entrypoints.cli._formatters import (
    _format_json,
    _format_sarif,
)

_SCHEMAS_DIR = Path(__file__).parent / "schemas"

_SLEEP_ROBOT = """\
*** Test Cases ***
Sleep Test
    Sleep    5 seconds
"""


@pytest.fixture
def sleep_robot_file(tmp_path: Path) -> Path:
    f = tmp_path / "sleep_suite.robot"
    f.write_text(_SLEEP_ROBOT, encoding="utf-8")
    return f


@pytest.fixture
def sleep_findings(sleep_robot_file: Path) -> list:
    return analyze_file(sleep_robot_file).findings


@pytest.mark.contract
class TestJsonOutputSchema:
    """JSON output structure matches the pinned schema artifact."""

    def test_top_level_has_schema_version(self, sleep_findings: list) -> None:
        output = json.loads(_format_json(sleep_findings))
        assert "schema_version" in output

    def test_schema_version_is_pinned_value(self, sleep_findings: list) -> None:
        schema = json.loads((_SCHEMAS_DIR / "output_v1.json").read_text())
        output = json.loads(_format_json(sleep_findings))
        assert output["schema_version"] == schema["schema_version"]

    def test_top_level_has_findings_key(self, sleep_findings: list) -> None:
        output = json.loads(_format_json(sleep_findings))
        assert "findings" in output
        assert isinstance(output["findings"], list)

    def test_top_level_keys_match_pinned_schema(self, sleep_findings: list) -> None:
        schema = json.loads((_SCHEMAS_DIR / "output_v1.json").read_text())
        output = json.loads(_format_json(sleep_findings))
        required = set(schema["required_top_level_keys"])
        assert required <= set(output.keys()), f"Missing top-level keys: {required - set(output.keys())}"

    def test_finding_has_all_required_keys(self, sleep_findings: list) -> None:
        schema = json.loads((_SCHEMAS_DIR / "output_v1.json").read_text())
        output = json.loads(_format_json(sleep_findings))
        assert output["findings"], "Expected at least one finding for schema validation"
        required = set(schema["required_finding_keys"])
        for finding in output["findings"]:
            missing = required - set(finding.keys())
            assert not missing, f"Finding missing required keys: {missing}"

    def test_finding_location_has_required_keys(self, sleep_findings: list) -> None:
        schema = json.loads((_SCHEMAS_DIR / "output_v1.json").read_text())
        output = json.loads(_format_json(sleep_findings))
        required = set(schema["required_location_keys"])
        for finding in output["findings"]:
            loc = finding.get("location", {})
            missing = required - set(loc.keys())
            assert not missing, f"Location missing required keys: {missing}"

    def test_empty_findings_produces_valid_schema(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.robot"
        f.write_text("*** Test Cases ***\nClean\n    Log    ok\n", encoding="utf-8")
        findings = analyze_file(f).findings
        output = json.loads(_format_json(findings))
        assert "schema_version" in output
        assert "findings" in output
        assert isinstance(output["findings"], list)

    def test_finding_severity_is_string(self, sleep_findings: list) -> None:
        output = json.loads(_format_json(sleep_findings))
        for finding in output["findings"]:
            assert isinstance(finding["severity"], str)

    def test_finding_line_is_integer(self, sleep_findings: list) -> None:
        output = json.loads(_format_json(sleep_findings))
        for finding in output["findings"]:
            assert isinstance(finding["line"], int)

    def test_output_is_deterministic(self, sleep_robot_file: Path) -> None:
        """Same input must produce byte-identical JSON output on repeated calls."""
        findings_a = analyze_file(sleep_robot_file).findings
        findings_b = analyze_file(sleep_robot_file).findings
        assert _format_json(findings_a) == _format_json(findings_b)


@pytest.mark.contract
class TestSarifOutputSchema:
    """SARIF 2.1.0 output structure matches the pinned schema artifact."""

    def test_top_level_has_schema_key(self, sleep_findings: list, sleep_robot_file: Path) -> None:
        output = json.loads(_format_sarif(sleep_findings, sleep_robot_file))
        assert "$schema" in output

    def test_top_level_version_is_sarif_2_1_0(self, sleep_findings: list, sleep_robot_file: Path) -> None:
        schema = json.loads((_SCHEMAS_DIR / "sarif_structure.json").read_text())
        output = json.loads(_format_sarif(sleep_findings, sleep_robot_file))
        assert output["version"] == schema["sarif_version"]

    def test_top_level_keys_match_pinned_schema(self, sleep_findings: list, sleep_robot_file: Path) -> None:
        schema = json.loads((_SCHEMAS_DIR / "sarif_structure.json").read_text())
        output = json.loads(_format_sarif(sleep_findings, sleep_robot_file))
        required = set(schema["required_top_level_keys"])
        assert required <= set(output.keys())

    def test_runs_is_non_empty_list(self, sleep_findings: list, sleep_robot_file: Path) -> None:
        output = json.loads(_format_sarif(sleep_findings, sleep_robot_file))
        assert isinstance(output["runs"], list)
        assert len(output["runs"]) >= 1

    def test_run_has_tool_and_results(self, sleep_findings: list, sleep_robot_file: Path) -> None:
        schema = json.loads((_SCHEMAS_DIR / "sarif_structure.json").read_text())
        output = json.loads(_format_sarif(sleep_findings, sleep_robot_file))
        run = output["runs"][0]
        required = set(schema["required_run_keys"])
        assert required <= set(run.keys())

    def test_result_has_required_keys(self, sleep_findings: list, sleep_robot_file: Path) -> None:
        schema = json.loads((_SCHEMAS_DIR / "sarif_structure.json").read_text())
        output = json.loads(_format_sarif(sleep_findings, sleep_robot_file))
        run = output["runs"][0]
        assert run["results"], "Expected at least one SARIF result"
        required = set(schema["required_result_keys"])
        for result in run["results"]:
            missing = required - set(result.keys())
            assert not missing, f"SARIF result missing keys: {missing}"

    def test_tool_driver_has_rules(self, sleep_findings: list, sleep_robot_file: Path) -> None:
        output = json.loads(_format_sarif(sleep_findings, sleep_robot_file))
        run = output["runs"][0]
        driver = run["tool"]["driver"]
        assert "rules" in driver
        assert isinstance(driver["rules"], list)
        assert len(driver["rules"]) >= 1

    def test_rule_has_required_keys(self, sleep_findings: list, sleep_robot_file: Path) -> None:
        schema = json.loads((_SCHEMAS_DIR / "sarif_structure.json").read_text())
        output = json.loads(_format_sarif(sleep_findings, sleep_robot_file))
        run = output["runs"][0]
        required = set(schema["required_rule_keys"])
        for rule in run["tool"]["driver"]["rules"]:
            missing = required - set(rule.keys())
            assert not missing, f"SARIF rule missing keys: {missing}"

    def test_sarif_output_is_deterministic(self, sleep_robot_file: Path) -> None:
        """Same input must produce identical SARIF output on repeated calls."""
        findings_a = analyze_file(sleep_robot_file).findings
        findings_b = analyze_file(sleep_robot_file).findings
        assert _format_sarif(findings_a, sleep_robot_file) == _format_sarif(findings_b, sleep_robot_file)


@pytest.mark.contract
class TestFindingWithRemediation:
    """Finding.to_dict() serializes RemediationHint correctly when present."""

    def _make_finding_with_remediation(self) -> Finding:
        pattern = Pattern(
            type=PatternType.SLEEP_IN_TEST,
            name="Sleep in Test",
            description="Sleep detected",
            recommendation="Use explicit wait",
        )
        remediation = RemediationHint(
            summary="Replace Sleep with explicit wait keyword",
            effort="low",
            steps=("Remove Sleep    N seconds", "Add Wait Until Element Is Visible"),
            docs_url="https://example.com/docs",
            auto_fixable=False,
        )
        return Finding(
            pattern=pattern,
            severity=Severity.WARNING,
            location=Location(file_path=Path("t.robot"), line=5),
            message="Use explicit wait instead of Sleep",
            remediation=remediation,
        )

    def test_remediation_serialized_in_to_dict(self) -> None:
        finding = self._make_finding_with_remediation()
        d = finding.to_dict()
        assert d["remediation"] is not None
        assert d["remediation"]["summary"] == "Replace Sleep with explicit wait keyword"
        assert d["remediation"]["effort"] == "low"
        assert isinstance(d["remediation"]["steps"], list)

    def test_remediation_keys_are_complete(self) -> None:
        finding = self._make_finding_with_remediation()
        rem = finding.to_dict()["remediation"]
        assert set(rem.keys()) == {"summary", "effort", "steps", "docs_url", "auto_fixable", "related_rule_ids"}

    def test_json_output_includes_remediation(self) -> None:
        finding = self._make_finding_with_remediation()
        output = json.loads(_format_json([finding]))
        assert output["findings"][0]["remediation"] is not None
