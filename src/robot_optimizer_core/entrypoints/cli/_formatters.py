# src/robot_optimizer_core/entrypoints/cli/_formatters.py
"""Plain-text, JSON, SARIF, and JUnit XML output formatters."""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...domain.value_objects import Finding, Severity

# ANSI colour helpers (disabled when not a tty)
_COLOURS: dict[int, str] = {}  # populated lazily to avoid circular import at module load


def _get_colours() -> dict[object, str]:
    from ...domain.value_objects import Severity as _Sev

    return {
        _Sev.ERROR: "\033[31m",
        _Sev.WARNING: "\033[33m",
        _Sev.INFO: "\033[36m",
    }


_RESET = "\033[0m"


def _colour(text: str, severity: Severity) -> str:
    if not sys.stdout.isatty():
        return text
    colours = _get_colours()
    return f"{colours.get(severity, '')}{text}{_RESET}"


def _format_text(findings: list[Finding], path: Path) -> str:
    if not findings:
        return f"No findings in {path}\n"

    lines: list[str] = [
        f"\nAnalysis results for {path}  ({len(findings)} finding(s))\n"
    ]
    for f in sorted(
        findings, key=lambda x: (str(x.location.file_path), x.location.line)
    ):
        sev_label = _colour(f.severity.name.upper(), f.severity)
        loc = f"{f.location.file_path}:{f.location.line}"
        lines.append(f"  {sev_label}  {loc}")
        lines.append(f"    {f.pattern.name}: {f.message}")
        if f.pattern.recommendation != f.message:
            lines.append(f"    → {f.pattern.recommendation}")
        lines.append("")
    return "\n".join(lines)


def _format_json(findings: list[Finding]) -> str:
    records = [f.to_dict() for f in findings]
    output = {
        "schema_version": "1",
        "findings": records,
    }
    return json.dumps(output, indent=2, default=str)


def _format_sarif(findings: list[Finding], path: Path) -> str:
    """Produce a SARIF 2.1.0 JSON string from a list of findings."""
    seen_rules: dict[str, dict[str, object]] = {}
    results: list[dict[str, object]] = []

    root = path.resolve() if path.is_dir() else path.parent.resolve()

    for finding in sorted(
        findings,
        key=lambda x: (
            str(x.location.file_path),
            x.location.line,
            x.pattern.name,
            x.message,
        ),
    ):
        result = finding.to_sarif()
        try:
            physical = result["locations"][0]["physicalLocation"]
            artifact = physical["artifactLocation"]
            file_uri = artifact.get("uri", "")
            candidate = Path(str(file_uri))
            artifact["uri"] = str(candidate.resolve().relative_to(root)).replace(
                "\\", "/"
            )
        except (KeyError, IndexError, ValueError, OSError, TypeError):
            pass

        rule_id = str(result.get("ruleId", ""))
        results.append(result)
        if rule_id not in seen_rules:
            rule: dict[str, object] = {
                "id": rule_id,
                "name": finding.pattern.name,
                "shortDescription": {"text": finding.pattern.name},
            }
            if finding.pattern.documentation_url:
                rule["helpUri"] = finding.pattern.documentation_url
            seen_rules[rule_id] = rule

    sarif = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "robot-optimizer",
                        "rules": [seen_rules[key] for key in sorted(seen_rules)],
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(sarif, indent=2, default=str)


def _format_junit(findings: list[Finding], path: Path) -> str:
    """Produce a JUnit XML report from a list of findings.

    Each finding becomes a testcase with a failure element.
    Suite name is the analyzed path.
    """
    testsuite = ET.Element("testsuite")
    testsuite.set("name", str(path))
    testsuite.set("tests", str(len(findings)))

    failures_count = sum(
        1 for f in findings if f.severity.name == "ERROR"
    )
    testsuite.set("failures", str(failures_count))

    for finding in sorted(
        findings,
        key=lambda x: (
            str(x.location.file_path),
            x.location.line,
            x.pattern.name,
        ),
    ):
        testcase = ET.SubElement(testsuite, "testcase")
        pattern_type = finding.pattern.type
        assert pattern_type is not None
        testcase.set(
            "name",
            f"{pattern_type.name} at line {finding.location.line}",
        )
        testcase.set("classname", str(finding.location.file_path))

        failure = ET.SubElement(testcase, "failure")
        failure.set("message", finding.pattern.name)
        failure.set("type", finding.severity.name)
        failure.text = finding.message

    # Convert to string with XML declaration
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(testsuite, encoding="unicode")
