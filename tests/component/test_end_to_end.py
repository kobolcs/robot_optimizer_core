# tests/component/test_end_to_end.py
"""End-to-end component tests for the full analysis pipeline.

These tests drive the system from raw .robot file content through file
discovery, parsing, analysis, and finding collection — no mocks, no
external services.  They verify the components integrate correctly as a
whole system.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from robot_optimizer_core.api import analyze_directory, analyze_file
from robot_optimizer_core.discovery import FileDiscoveryService
from robot_optimizer_core.domain.value_objects import PatternType, Severity


_SUITE_WITH_ISSUES = """\
*** Settings ***
Documentation    Suite with detectable issues

*** Test Cases ***
Test With Sleep
    [Documentation]    Uses sleep anti-pattern
    [Tags]    smoke
    Log    start
    Sleep    5s
    Live Keyword

Test Without Tags
    [Documentation]    Missing tags
    Log    no tags here

*** Keywords ***
Live Keyword
    [Documentation]    Called from Test With Sleep
    Log    alive

Dead Keyword
    [Documentation]    Never called anywhere
    Log    dead
"""

_CLEAN_SUITE = """\
*** Test Cases ***
Clean Test
    [Documentation]    No issues
    [Tags]    unit
    Log    ok
"""


@pytest.mark.component
class TestFullAnalysisPipeline:
    """File → parse → analyze → findings."""

    def test_sleep_detected_in_e2e_flow(self, tmp_path: Path) -> None:
        f = tmp_path / "suite.robot"
        f.write_bytes(_SUITE_WITH_ISSUES.encode())

        findings = analyze_file(f, analyzers=["sleep_detector"])

        sleep_findings = [fi for fi in findings if fi.pattern.type == PatternType.SLEEP_IN_TEST]
        assert len(sleep_findings) >= 1
        assert sleep_findings[0].severity in (Severity.WARNING, Severity.ERROR)

    def test_dead_code_detected_in_e2e_flow(self, tmp_path: Path) -> None:
        f = tmp_path / "suite.robot"
        f.write_bytes(_SUITE_WITH_ISSUES.encode())

        findings = analyze_file(f, analyzers=["dead_code"])

        unused = [fi for fi in findings if fi.pattern.type == PatternType.UNUSED_KEYWORD]
        keyword_names = [fi.context["keyword_name"] for fi in unused]
        assert "Dead Keyword" in keyword_names
        assert "Live Keyword" not in keyword_names

    def test_clean_file_produces_no_sleep_findings(self, tmp_path: Path) -> None:
        f = tmp_path / "clean.robot"
        f.write_bytes(_CLEAN_SUITE.encode())

        findings = analyze_file(f, analyzers=["sleep_detector"])

        sleep_findings = [fi for fi in findings if fi.pattern.type == PatternType.SLEEP_IN_TEST]
        assert sleep_findings == []

    def test_analyze_file_default_analyzers_return_findings(self, tmp_path: Path) -> None:
        f = tmp_path / "suite.robot"
        f.write_bytes(_SUITE_WITH_ISSUES.encode())

        findings = analyze_file(f)

        assert len(findings) > 0
        pattern_types = {fi.pattern.type for fi in findings}
        assert len(pattern_types) >= 2

    def test_findings_have_valid_locations(self, tmp_path: Path) -> None:
        f = tmp_path / "suite.robot"
        f.write_bytes(_SUITE_WITH_ISSUES.encode())

        findings = analyze_file(f)

        for fi in findings:
            assert fi.location.line >= 1
            assert fi.location.file_path == f


@pytest.mark.component
class TestDirectoryAnalysisPipeline:
    """analyze_directory integrates discovery + per-file analysis."""

    def test_directory_analysis_covers_all_robot_files(self, tmp_path: Path) -> None:
        for i in range(3):
            (tmp_path / f"suite_{i}.robot").write_bytes(
                f"*** Test Cases ***\nTest {i}\n    Sleep    {i + 1}s\n".encode()
            )

        results = analyze_directory(tmp_path, analyzers=["sleep_detector"])
        all_findings = [f for fs in results.findings.values() for f in fs]
        assert len(all_findings) == 3

    def test_directory_analysis_ignores_non_robot_files(self, tmp_path: Path) -> None:
        (tmp_path / "suite.robot").write_bytes(
            b"*** Test Cases ***\nT\n    Sleep    1s\n"
        )
        (tmp_path / "readme.txt").write_bytes(b"not a robot file\n")
        (tmp_path / "data.json").write_bytes(b'{"key": "value"}\n')

        results = analyze_directory(tmp_path, analyzers=["sleep_detector"])
        assert all(p.suffix == ".robot" for p in results.findings.keys())

    def test_empty_directory_returns_no_findings(self, tmp_path: Path) -> None:
        results = analyze_directory(tmp_path)
        assert len(results.findings) == 0


@pytest.mark.component
class TestDiscoveryToAnalysisPipeline:
    """FileDiscoveryService feeds directly into the analysis API."""

    def test_discovered_files_all_produce_findings(self, tmp_path: Path) -> None:
        for name in ("a.robot", "b.robot"):
            (tmp_path / name).write_bytes(
                b"*** Test Cases ***\nT\n    Sleep    2s\n"
            )

        discovery = FileDiscoveryService()
        robot_files = discovery.find_files(tmp_path, patterns=["*.robot"])
        assert len(robot_files) == 2

        all_findings: list = []
        for path in robot_files:
            all_findings.extend(analyze_file(path, analyzers=["sleep_detector"]))

        assert len(all_findings) == 2

    def test_discovery_respects_subdirectories(self, tmp_path: Path) -> None:
        subdir = tmp_path / "sub"
        subdir.mkdir()
        (tmp_path / "root.robot").write_bytes(b"*** Test Cases ***\nT\n    Log    hi\n")
        (subdir / "nested.robot").write_bytes(b"*** Test Cases ***\nT\n    Log    hi\n")

        discovery = FileDiscoveryService()
        files = discovery.find_files(tmp_path, patterns=["*.robot"])
        assert len(files) == 2


@pytest.mark.component
class TestMultiAnalyzerPipeline:
    """Multiple analyzers run on the same file without interference."""

    def test_sleep_and_dead_code_analyzers_combined(self, tmp_path: Path) -> None:
        f = tmp_path / "suite.robot"
        f.write_bytes(_SUITE_WITH_ISSUES.encode())

        findings = analyze_file(f, analyzers=["sleep_detector", "dead_code"])

        actual_types = {fi.pattern.type for fi in findings}
        assert PatternType.SLEEP_IN_TEST in actual_types
        assert PatternType.UNUSED_KEYWORD in actual_types

    def test_each_finding_references_correct_file(self, tmp_path: Path) -> None:
        f = tmp_path / "suite.robot"
        f.write_bytes(_SUITE_WITH_ISSUES.encode())

        findings = analyze_file(f)

        for fi in findings:
            assert fi.location.file_path.resolve() == f.resolve()
