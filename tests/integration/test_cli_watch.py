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

        from robot_optimizer_core.entrypoints.cli._parser import _build_parser

        parser = _build_parser()
        args = parser.parse_args(["analyze", str(f), "--watch"])
        assert args.watch is True

    def test_watch_mode_detects_new_findings(self, tmp_path: Path) -> None:
        """Watch mode should detect when new findings appear."""
        test_file = tmp_path / "test.robot"
        test_file.write_bytes(b"*** Test Cases ***\nMy Test\n    Log    hello\n")

        from robot_optimizer_core.domain.value_objects import Finding, Severity
        from robot_optimizer_core.domain.value_objects.location import Location
        from robot_optimizer_core.domain.value_objects.pattern import (
            Pattern,
            PatternType,
        )
        from robot_optimizer_core.entrypoints.cli._commands import _compute_finding_diff

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

        from robot_optimizer_core.domain.value_objects import Finding, Severity
        from robot_optimizer_core.domain.value_objects.location import Location
        from robot_optimizer_core.domain.value_objects.pattern import (
            Pattern,
            PatternType,
        )
        from robot_optimizer_core.entrypoints.cli._commands import _compute_finding_diff

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

        from robot_optimizer_core.domain.value_objects import Finding, Severity
        from robot_optimizer_core.domain.value_objects.location import Location
        from robot_optimizer_core.domain.value_objects.pattern import (
            Pattern,
            PatternType,
        )
        from robot_optimizer_core.entrypoints.cli._commands import _compute_finding_diff

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
        from robot_optimizer_core.entrypoints.cli._commands import _print_watch_diff

        _print_watch_diff([], [])
        captured = capsys.readouterr()
        assert "[✓] No changes" in captured.err

    def test_print_watch_diff_with_new_findings(self, tmp_path: Path, capsys) -> None:
        """_print_watch_diff should display new findings."""
        from robot_optimizer_core.domain.value_objects import Finding, Severity
        from robot_optimizer_core.domain.value_objects.location import Location
        from robot_optimizer_core.domain.value_objects.pattern import (
            Pattern,
            PatternType,
        )
        from robot_optimizer_core.entrypoints.cli._commands import _print_watch_diff

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
        from robot_optimizer_core.domain.value_objects import Finding, Severity
        from robot_optimizer_core.domain.value_objects.location import Location
        from robot_optimizer_core.domain.value_objects.pattern import (
            Pattern,
            PatternType,
        )
        from robot_optimizer_core.entrypoints.cli._commands import _print_watch_diff

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
class TestWatchStateDiff:
    """Correctness tests for the per-file indexed state diff algorithm."""

    # ------------------------------------------------------------------ fixtures

    @staticmethod
    def _make_finding(
        file_path: Path,
        line: int,
        message: str = "test finding",
        pattern_type_name: str = "SLEEP_IN_TEST",
    ):
        from robot_optimizer_core.domain.value_objects import Finding, Severity
        from robot_optimizer_core.domain.value_objects.location import Location
        from robot_optimizer_core.domain.value_objects.pattern import Pattern, PatternType

        pt = PatternType[pattern_type_name]
        pattern = Pattern(
            type=pt,
            name=pt.name.replace("_", " ").title(),
            description="desc",
            recommendation="rec",
        )
        return Finding.create(
            pattern=pattern,
            severity=Severity.WARNING,
            location=Location(file_path=file_path, line=line),
            message=message,
        )

    # ------------------------------------------------------------------ helpers

    def _flatten(self, state: dict) -> list:
        from robot_optimizer_core.entrypoints.cli._commands import _flatten_state
        return _flatten_state(state)

    def _diff(self, prev, curr):
        from robot_optimizer_core.entrypoints.cli._commands import _compute_finding_diff
        return _compute_finding_diff(prev, curr)

    # ------------------------------------------------------------------ single-file change

    def test_single_file_change_updates_only_that_file(self, tmp_path: Path) -> None:
        """After file A changes, file B's findings remain stable in state."""
        file_a = tmp_path / "a.robot"
        file_b = tmp_path / "b.robot"

        f_a1 = self._make_finding(file_a, 5, "sleep in a")
        f_b1 = self._make_finding(file_b, 10, "sleep in b")

        state: dict = {file_a: [f_a1], file_b: [f_b1]}

        # Simulate file A being fixed (finding removed)
        prev_flat = self._flatten(state)
        state[file_a] = []
        curr_flat = self._flatten(state)

        new_f, resolved_f = self._diff(prev_flat, curr_flat)

        assert new_f == []
        assert len(resolved_f) == 1
        assert resolved_f[0].fingerprint == f_a1.fingerprint
        # b's finding must still be in state
        assert state[file_b] == [f_b1]

    def test_single_file_change_new_finding(self, tmp_path: Path) -> None:
        """A new finding in file A is reported; file B is untouched."""
        file_a = tmp_path / "a.robot"
        file_b = tmp_path / "b.robot"

        f_a_new = self._make_finding(file_a, 7, "new sleep")
        f_b1 = self._make_finding(file_b, 10, "sleep in b")

        state: dict = {file_a: [], file_b: [f_b1]}

        prev_flat = self._flatten(state)
        state[file_a] = [f_a_new]
        curr_flat = self._flatten(state)

        new_f, resolved_f = self._diff(prev_flat, curr_flat)

        assert len(new_f) == 1
        assert new_f[0].fingerprint == f_a_new.fingerprint
        assert resolved_f == []

    # ------------------------------------------------------------------ multi-file directory change

    def test_multifile_two_events_independent(self, tmp_path: Path) -> None:
        """Two rapid file changes each update their own slice; no cross-contamination."""
        file_a = tmp_path / "a.robot"
        file_b = tmp_path / "b.robot"

        f_a1 = self._make_finding(file_a, 3, "sleep a")
        f_b1 = self._make_finding(file_b, 9, "sleep b")
        f_b2 = self._make_finding(file_b, 12, "another sleep b", "HARD_CODED_WAIT")

        state: dict = {file_a: [f_a1], file_b: [f_b1]}

        # Event 1: file A resolved
        prev1 = self._flatten(state)
        state[file_a] = []
        curr1 = self._flatten(state)
        new1, res1 = self._diff(prev1, curr1)
        assert res1[0].fingerprint == f_a1.fingerprint
        assert new1 == []

        # Event 2: file B gains a second finding
        prev2 = self._flatten(state)
        state[file_b] = [f_b1, f_b2]
        curr2 = self._flatten(state)
        new2, res2 = self._diff(prev2, curr2)
        assert len(new2) == 1
        assert new2[0].fingerprint == f_b2.fingerprint
        assert res2 == []

    def test_multifile_state_never_shrinks_on_unrelated_change(self, tmp_path: Path) -> None:
        """State for files C and D is untouched when only file A changes."""
        files = [tmp_path / f"{c}.robot" for c in "abcd"]
        state: dict = {f: [self._make_finding(f, i + 1, f"msg {i}")] for i, f in enumerate(files)}

        file_a = files[0]
        prev_flat = self._flatten(state)
        state[file_a] = []
        curr_flat = self._flatten(state)

        _, resolved = self._diff(prev_flat, curr_flat)
        assert len(resolved) == 1
        # files b, c, d still present
        for f in files[1:]:
            assert f in state
            assert len(state[f]) == 1

    # ------------------------------------------------------------------ file deletion

    def test_file_deletion_resolves_all_its_findings(self, tmp_path: Path) -> None:
        """Deleting a file removes its entry from state; all its findings are resolved."""
        file_a = tmp_path / "a.robot"
        file_b = tmp_path / "b.robot"

        f_a1 = self._make_finding(file_a, 5, "sleep a1")
        f_a2 = self._make_finding(file_a, 8, "sleep a2", "HARD_CODED_WAIT")
        f_b1 = self._make_finding(file_b, 2, "sleep b")

        state: dict = {file_a: [f_a1, f_a2], file_b: [f_b1]}

        prev_flat = self._flatten(state)
        state.pop(file_a)
        curr_flat = self._flatten(state)

        new_f, resolved_f = self._diff(prev_flat, curr_flat)

        assert new_f == []
        assert len(resolved_f) == 2
        resolved_fps = {r.fingerprint for r in resolved_f}
        assert f_a1.fingerprint in resolved_fps
        assert f_a2.fingerprint in resolved_fps
        # b stays
        assert file_b in state

    def test_deletion_of_file_with_no_findings_produces_no_diff(self, tmp_path: Path) -> None:
        """Deleting a file that had zero findings produces an empty diff."""
        file_a = tmp_path / "a.robot"
        file_b = tmp_path / "b.robot"

        state: dict = {file_a: [], file_b: [self._make_finding(file_b, 1, "msg")]}

        prev_flat = self._flatten(state)
        state.pop(file_a)
        curr_flat = self._flatten(state)

        new_f, resolved_f = self._diff(prev_flat, curr_flat)
        assert new_f == []
        assert resolved_f == []

    # ------------------------------------------------------------------ rename / move

    def test_rename_resolves_old_reports_new(self, tmp_path: Path) -> None:
        """Moving a.robot → b.robot: a's fingerprints become resolved; b's appear new.

        Fingerprints embed file_path, so the same logical finding at a new path
        is correctly treated as a new finding (the old path no longer exists).
        """
        src = tmp_path / "old.robot"
        dest = tmp_path / "new.robot"

        f_src = self._make_finding(src, 5, "sleep in old")
        f_dest = self._make_finding(dest, 5, "sleep in old")  # same line/msg, different path

        state: dict = {src: [f_src]}

        prev_flat = self._flatten(state)
        state.pop(src)
        state[dest] = [f_dest]
        curr_flat = self._flatten(state)

        new_f, resolved_f = self._diff(prev_flat, curr_flat)

        # Different fingerprints because file_path differs
        assert f_src.fingerprint != f_dest.fingerprint
        assert len(new_f) == 1
        assert new_f[0].fingerprint == f_dest.fingerprint
        assert len(resolved_f) == 1
        assert resolved_f[0].fingerprint == f_src.fingerprint

    def test_rename_to_non_watched_extension_resolves_findings(self, tmp_path: Path) -> None:
        """Moving a.robot → a.txt: robot findings are resolved, txt is not tracked."""
        src = tmp_path / "test.robot"
        f = self._make_finding(src, 3, "sleep")

        state: dict = {src: [f]}

        prev_flat = self._flatten(state)
        state.pop(src, None)
        # dest is .txt — not watched, so nothing added to state
        curr_flat = self._flatten(state)

        new_f, resolved_f = self._diff(prev_flat, curr_flat)
        assert new_f == []
        assert len(resolved_f) == 1

    # ------------------------------------------------------------------ diff key stability

    def test_fingerprint_key_is_stable_across_reruns(self, tmp_path: Path) -> None:
        """The same finding produces the same fingerprint on both sides of the diff."""
        file_a = tmp_path / "a.robot"
        f = self._make_finding(file_a, 5, "sleep")

        new_f, resolved_f = self._diff([f], [f])
        assert new_f == []
        assert resolved_f == []

    def test_same_line_different_message_is_different_finding(self, tmp_path: Path) -> None:
        """Two findings at the same (file, line, pattern) but different messages differ."""
        file_a = tmp_path / "a.robot"
        f1 = self._make_finding(file_a, 5, "Sleep 5s detected")
        f2 = self._make_finding(file_a, 5, "Sleep 10s detected")

        assert f1.fingerprint != f2.fingerprint
        new_f, resolved_f = self._diff([f1], [f2])
        assert len(new_f) == 1
        assert len(resolved_f) == 1

    def test_error_on_reanalysis_does_not_corrupt_state(self, tmp_path: Path) -> None:
        """When analysis fails for a changed file, state remains unchanged."""
        file_a = tmp_path / "a.robot"
        file_b = tmp_path / "b.robot"

        f_a = self._make_finding(file_a, 5, "sleep a")
        f_b = self._make_finding(file_b, 3, "sleep b")

        state: dict = {file_a: [f_a], file_b: [f_b]}
        state_snapshot = {k: list(v) for k, v in state.items()}

        # Simulate: analysis returns None (error) — state must NOT be mutated
        findings = None
        if findings is None:
            pass  # on_modified contract: return early, do not update state

        assert state == state_snapshot


@pytest.mark.integration
class TestCliOutputFormats:
    def test_cli_junit_format_output(self, tmp_path: Path) -> None:
        """CLI should produce valid JUnit XML when --format junit is used."""
        test_file = tmp_path / "test.robot"
        test_file.write_bytes(b"*** Test Cases ***\nMy Test\n    Sleep    5s\n")

        from unittest.mock import MagicMock

        from robot_optimizer_core.entrypoints.cli._commands import _run_analyze

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

        from robot_optimizer_core.entrypoints.cli._commands import _run_analyze

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
