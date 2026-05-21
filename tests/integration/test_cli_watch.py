# tests/integration/test_cli_watch.py
"""Integration tests for CLI watch mode and output formats."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


@pytest.mark.integration
class TestWatchMode:
    def test_watch_flag_accepted(self, tmp_path: Path) -> None:
        """Watch mode flag should be accepted by the parser."""
        f = tmp_path / "test.robot"
        f.write_bytes(b"*** Test Cases ***\nMy Test\n    Log    hello\n")

        from robot_optimizer_core.cli._parser import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["analyze", str(f), "--watch"])
        assert args.watch is True

    def test_watch_mode_detects_new_findings(self, tmp_path: Path) -> None:
        """Watch mode should detect when new findings appear."""
        test_file = tmp_path / "test.robot"
        test_file.write_bytes(b"*** Test Cases ***\nMy Test\n    Log    hello\n")

        from robot_optimizer_core.cli._commands import _compute_finding_diff
        from robot_optimizer_core.domain.value_objects import Finding, Severity
        from robot_optimizer_core.domain.value_objects.location import Location
        from robot_optimizer_core.domain.value_objects.pattern import (
            Pattern,
            PatternType,
        )

        pattern = Pattern(
            type=PatternType.SLEEP_IN_TEST,
            name="Sleep in Test Case",
            description="Sleep detected",
            recommendation="Use explicit wait",
        )

        # Simulate previous findings (empty)
        prev_findings = []

        # Simulate current findings (with new sleep)
        curr_findings = [
            Finding.create(
                pattern=pattern,
                severity=Severity.WARNING,
                location=Location(file_path=test_file, line=3),
                message="Sleep detected",
            )
        ]

        new, resolved = _compute_finding_diff(prev_findings, curr_findings)
        assert len(new) == 1
        assert len(resolved) == 0
        assert new[0].pattern.type == PatternType.SLEEP_IN_TEST

    def test_watch_mode_detects_resolved_findings(self, tmp_path: Path) -> None:
        """Watch mode should detect when findings are resolved."""
        test_file = tmp_path / "test.robot"

        from robot_optimizer_core.cli._commands import _compute_finding_diff
        from robot_optimizer_core.domain.value_objects import Finding, Severity
        from robot_optimizer_core.domain.value_objects.location import Location
        from robot_optimizer_core.domain.value_objects.pattern import (
            Pattern,
            PatternType,
        )

        pattern = Pattern(
            type=PatternType.SLEEP_IN_TEST,
            name="Sleep in Test Case",
            description="Sleep detected",
            recommendation="Use explicit wait",
        )

        # Simulate previous findings (with sleep)
        prev_findings = [
            Finding.create(
                pattern=pattern,
                severity=Severity.WARNING,
                location=Location(file_path=test_file, line=3),
                message="Sleep detected",
            )
        ]

        # Simulate current findings (empty)
        curr_findings = []

        new, resolved = _compute_finding_diff(prev_findings, curr_findings)
        assert len(new) == 0
        assert len(resolved) == 1
        assert resolved[0].pattern.type == PatternType.SLEEP_IN_TEST

    def test_watch_mode_no_changes(self, tmp_path: Path) -> None:
        """Watch mode should handle when there are no changes."""
        test_file = tmp_path / "test.robot"

        from robot_optimizer_core.cli._commands import _compute_finding_diff
        from robot_optimizer_core.domain.value_objects import Finding, Severity
        from robot_optimizer_core.domain.value_objects.location import Location
        from robot_optimizer_core.domain.value_objects.pattern import (
            Pattern,
            PatternType,
        )

        pattern = Pattern(
            type=PatternType.SLEEP_IN_TEST,
            name="Sleep in Test Case",
            description="Sleep detected",
            recommendation="Use explicit wait",
        )

        finding = Finding.create(
            pattern=pattern,
            severity=Severity.WARNING,
            location=Location(file_path=test_file, line=3),
            message="Sleep detected",
        )

        # Simulate same findings
        prev_findings = [finding]
        curr_findings = [finding]

        new, resolved = _compute_finding_diff(prev_findings, curr_findings)
        assert len(new) == 0
        assert len(resolved) == 0

    def test_print_watch_diff_no_changes(self, capsys) -> None:
        """_print_watch_diff should show message when there are no changes."""
        from robot_optimizer_core.cli._commands import _print_watch_diff

        _print_watch_diff([], [])
        captured = capsys.readouterr()
        assert "[✓] No changes" in captured.err

    def test_print_watch_diff_with_new_findings(self, tmp_path: Path, capsys) -> None:
        """_print_watch_diff should display new findings."""
        from robot_optimizer_core.cli._commands import _print_watch_diff
        from robot_optimizer_core.domain.value_objects import Finding, Severity
        from robot_optimizer_core.domain.value_objects.location import Location
        from robot_optimizer_core.domain.value_objects.pattern import (
            Pattern,
            PatternType,
        )

        test_file = tmp_path / "test.robot"
        pattern = Pattern(
            type=PatternType.SLEEP_IN_TEST,
            name="Sleep in Test Case",
            description="Sleep detected",
            recommendation="Use explicit wait",
        )
        finding = Finding.create(
            pattern=pattern,
            severity=Severity.ERROR,
            location=Location(file_path=test_file, line=10),
            message="Sleep detected",
        )

        _print_watch_diff([finding], [])
        captured = capsys.readouterr()
        assert "[+] New findings" in captured.err
        assert "Sleep in Test Case" in captured.err

    def test_print_watch_diff_with_resolved_findings(self, tmp_path: Path, capsys) -> None:
        """_print_watch_diff should display resolved findings."""
        from robot_optimizer_core.cli._commands import _print_watch_diff
        from robot_optimizer_core.domain.value_objects import Finding, Severity
        from robot_optimizer_core.domain.value_objects.location import Location
        from robot_optimizer_core.domain.value_objects.pattern import (
            Pattern,
            PatternType,
        )

        test_file = tmp_path / "test.robot"
        pattern = Pattern(
            type=PatternType.SLEEP_IN_TEST,
            name="Sleep in Test Case",
            description="Sleep detected",
            recommendation="Use explicit wait",
        )
        finding = Finding.create(
            pattern=pattern,
            severity=Severity.WARNING,
            location=Location(file_path=test_file, line=10),
            message="Sleep detected",
        )

        _print_watch_diff([], [finding])
        captured = capsys.readouterr()
        assert "[✓] Resolved findings" in captured.err
        assert "Sleep in Test Case" in captured.err


@pytest.mark.integration
class TestCliOutputFormats:
    def test_cli_junit_format_output(self, tmp_path: Path) -> None:
        """CLI should produce valid JUnit XML when --format junit is used."""
        test_file = tmp_path / "test.robot"
        test_file.write_bytes(b"*** Test Cases ***\nMy Test\n    Sleep    5s\n")

        from unittest.mock import MagicMock

        from robot_optimizer_core.cli._commands import _run_analyze

        args = MagicMock()
        args.path = str(test_file)
        args.format = "junit"
        args.output_file = None
        args.analyzers = None
        args.min_severity = None
        args.config = None
        args.no_cache = False
        args.clear_cache = False
        args.watch = False
        args.no_fail = True
        args.baseline = None
        args.update_baseline = False

        exit_code = _run_analyze(args)
        # Should succeed (exit 0 due to no_fail=True)
        assert exit_code == 0

    def test_cli_junit_format_to_file(self, tmp_path: Path) -> None:
        """CLI should write JUnit XML to file correctly."""
        test_file = tmp_path / "test.robot"
        test_file.write_bytes(b"*** Test Cases ***\nMy Test\n    Sleep    5s\n")
        output_file = tmp_path / "output.xml"

        from unittest.mock import MagicMock

        from robot_optimizer_core.cli._commands import _run_analyze

        args = MagicMock()
        args.path = str(test_file)
        args.format = "junit"
        args.output_file = str(output_file)
        args.analyzers = None
        args.min_severity = None
        args.config = None
        args.no_cache = False
        args.clear_cache = False
        args.watch = False
        args.no_fail = True
        args.baseline = None
        args.update_baseline = False

        exit_code = _run_analyze(args)
        assert exit_code == 0
        assert output_file.exists()

        # Verify the output is valid XML
        xml_content = output_file.read_text()
        assert '<?xml version="1.0" encoding="UTF-8"?>' in xml_content
        root = ET.fromstring(xml_content)
        assert root.tag == "testsuite"
