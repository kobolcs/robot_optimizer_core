# tests/integration/test_cli_watch.py
"""Integration tests for CLI watch mode."""

from __future__ import annotations

import time
from pathlib import Path
from threading import Thread
from unittest.mock import patch

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
        from robot_optimizer_core.domain.value_objects.pattern import Pattern, PatternType

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
        from robot_optimizer_core.domain.value_objects.pattern import Pattern, PatternType

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
        from robot_optimizer_core.domain.value_objects.pattern import Pattern, PatternType

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
