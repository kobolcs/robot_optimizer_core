# tests/component/test_analyzer_determinism.py
"""Analyzer determinism tests — same input must always produce identical output.

These tests exercise the invariant from the test strategy plan §2:
"Analyzer determinism: identical input → identical output, always."

They run analysis multiple times (sequentially and concurrently) and assert
that every run produces byte-identical results. A failure here means the
engine has a hidden source of non-determinism: a random UUID, a mutable
default, a dict-ordering dependency, or an unseeded RNG in an analyzer.
"""

from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path

import pytest

from robot_optimizer_core import analyze_file, analyze_directory
from robot_optimizer_core.entrypoints.cli._formatters import _format_json, _format_sarif

_MIXED_ROBOT = """\
*** Settings ***
Library    Collections

*** Variables ***
${TIMEOUT}    5

*** Test Cases ***
Sleep Test
    Sleep    3 seconds
    Log    done

Clean Test
    Log    all good

Another Sleep
    Sleep    ${TIMEOUT} seconds

*** Keywords ***
My Helper
    [Arguments]    ${x}
    Log    ${x}

Unused Keyword
    Log    never called
"""


@pytest.fixture
def mixed_robot_file(tmp_path: Path) -> Path:
    f = tmp_path / "mixed.robot"
    f.write_text(_MIXED_ROBOT, encoding="utf-8")
    return f


@pytest.fixture
def mixed_robot_dir(tmp_path: Path) -> Path:
    d = tmp_path / "suite"
    d.mkdir()
    for i in range(5):
        (d / f"file_{i}.robot").write_text(
            _MIXED_ROBOT.replace("Sleep Test", f"Sleep Test {i}"),
            encoding="utf-8",
        )
    return d


@pytest.mark.component
class TestAnalyzeFileDeterminism:
    """analyze_file() is deterministic across sequential re-runs."""

    def test_findings_identical_on_repeated_calls(self, mixed_robot_file: Path) -> None:
        results = [analyze_file(mixed_robot_file) for _ in range(5)]
        fingerprints_0 = [f.fingerprint for f in results[0].findings]
        for i, result in enumerate(results[1:], start=1):
            assert [f.fingerprint for f in result.findings] == fingerprints_0, (
                f"Run {i} produced different fingerprints than run 0"
            )

    def test_finding_ids_identical_on_repeated_calls(self, mixed_robot_file: Path) -> None:
        """IDs must be deterministic (UUID5 from fingerprint, not UUID4)."""
        results = [analyze_file(mixed_robot_file) for _ in range(5)]
        ids_0 = [str(f.id) for f in results[0].findings]
        for i, result in enumerate(results[1:], start=1):
            assert [str(f.id) for f in result.findings] == ids_0, (
                f"Run {i} produced different IDs than run 0 — UUID4 leak?"
            )

    def test_finding_count_identical_on_repeated_calls(self, mixed_robot_file: Path) -> None:
        counts = [len(analyze_file(mixed_robot_file).findings) for _ in range(10)]
        assert len(set(counts)) == 1, f"Non-deterministic finding count across runs: {counts}"

    def test_finding_order_identical_on_repeated_calls(self, mixed_robot_file: Path) -> None:
        """Finding list order must be stable — no dict/set traversal ordering."""
        results = [analyze_file(mixed_robot_file) for _ in range(5)]
        order_0 = [(f.location.line, f.pattern.type.name) for f in results[0].findings]
        for i, result in enumerate(results[1:], start=1):
            order_i = [(f.location.line, f.pattern.type.name) for f in result.findings]
            assert order_i == order_0, (
                f"Run {i} returned findings in a different order than run 0"
            )

    def test_json_output_byte_identical_on_repeated_calls(self, mixed_robot_file: Path) -> None:
        outputs = [_format_json(analyze_file(mixed_robot_file).findings) for _ in range(5)]
        assert len(set(outputs)) == 1, "JSON output is not byte-identical across runs"

    def test_sarif_output_byte_identical_on_repeated_calls(self, mixed_robot_file: Path) -> None:
        outputs = [
            _format_sarif(analyze_file(mixed_robot_file).findings, mixed_robot_file)
            for _ in range(5)
        ]
        assert len(set(outputs)) == 1, "SARIF output is not byte-identical across runs"


@pytest.mark.component
class TestAnalyzeFileConcurrentDeterminism:
    """analyze_file() produces identical results under concurrent load."""

    def test_concurrent_runs_produce_identical_results(self, mixed_robot_file: Path) -> None:
        """20 concurrent analyze_file() calls on the same file must all agree."""
        n = 20
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(analyze_file, mixed_robot_file) for _ in range(n)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        fingerprint_sets = [
            frozenset(f.fingerprint for f in r.findings) for r in results
        ]
        reference = fingerprint_sets[0]
        diverged = [i for i, s in enumerate(fingerprint_sets) if s != reference]
        assert not diverged, (
            f"Concurrent runs {diverged} produced different fingerprint sets — "
            "engine has a race condition or shared mutable state"
        )

    def test_concurrent_runs_produce_identical_counts(self, mixed_robot_file: Path) -> None:
        n = 20
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(lambda: len(analyze_file(mixed_robot_file).findings)) for _ in range(n)]
            counts = [f.result() for f in concurrent.futures.as_completed(futures)]
        assert len(set(counts)) == 1, f"Non-deterministic finding counts under concurrency: {set(counts)}"


@pytest.mark.component
class TestAnalyzeDirectoryDeterminism:
    """analyze_directory() is deterministic on repeated calls."""

    def test_per_file_finding_counts_identical(self, mixed_robot_dir: Path) -> None:
        results = [analyze_directory(mixed_robot_dir, use_cache=False) for _ in range(3)]
        counts_0 = {str(p): len(fs) for p, fs in results[0].findings.items()}
        for i, result in enumerate(results[1:], start=1):
            counts_i = {str(p): len(fs) for p, fs in result.findings.items()}
            assert counts_i == counts_0, (
                f"Directory run {i} produced different per-file counts than run 0"
            )

    def test_json_output_deterministic_across_directory_runs(
        self, mixed_robot_dir: Path
    ) -> None:
        all_findings = [
            finding
            for result in [analyze_directory(mixed_robot_dir, use_cache=False) for _ in range(3)]
            for findings in result.findings.values()
            for finding in findings
        ]
        # Group by run (each run contributes len(findings_per_file) × 5 files findings)
        run_size = len(all_findings) // 3
        run_fingerprints = [
            sorted(f.fingerprint for f in all_findings[i * run_size: (i + 1) * run_size])
            for i in range(3)
        ]
        assert run_fingerprints[0] == run_fingerprints[1] == run_fingerprints[2], (
            "Directory analysis produced different fingerprints across runs"
        )


@pytest.mark.component
class TestAnalyzerCacheConsistency:
    """Cached results must be identical to fresh results."""

    def test_cached_result_matches_fresh_result(self, mixed_robot_file: Path) -> None:
        fresh = analyze_file(mixed_robot_file)
        cached = analyze_file(mixed_robot_file)
        assert [f.fingerprint for f in fresh.findings] == [f.fingerprint for f in cached.findings], (
            "Cached analysis result differs from fresh analysis — cache invalidation bug"
        )

    def test_cache_disabled_matches_cache_enabled(self, mixed_robot_dir: Path) -> None:
        with_cache = analyze_directory(mixed_robot_dir, use_cache=True)
        without_cache = analyze_directory(mixed_robot_dir, use_cache=False)
        cache_counts = {str(p): len(fs) for p, fs in with_cache.findings.items()}
        fresh_counts = {str(p): len(fs) for p, fs in without_cache.findings.items()}
        assert cache_counts == fresh_counts, (
            "use_cache=True and use_cache=False produced different finding counts"
        )
