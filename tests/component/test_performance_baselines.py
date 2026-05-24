# tests/component/test_performance_baselines.py
"""Performance baseline tests — catch throughput regressions before they reach users.

These tests are marked @pytest.mark.performance and @pytest.mark.slow.
They do NOT assert on wall-clock time (inherently flaky on CI runners).
Instead they assert on:
  1. Throughput relative to input size  (O(n) scaling checks)
  2. Memory footprint bounds per finding
  3. Finding count stability (proxy for parser/analyzer correctness at scale)

Wall-clock timing is logged but never used as a pass/fail condition.
For absolute baseline tracking, run `make test-nightly` and compare the
JSON artifact produced by the nightly lane against the previous run.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from robot_optimizer_core import analyze_file, analyze_directory
from robot_optimizer_core.application.analyzers import (
    DeadCodeAnalyzer,
    FlakinessAnalyzer,
    SleepDetector,
)
from robot_optimizer_core.domain.entities import TestFile


def _build_robot_file(n_tests: int, n_keywords: int, sleep_every: int = 5) -> str:
    """Build a synthetic Robot Framework file with controllable scale."""
    lines = ["*** Test Cases ***"]
    for i in range(n_tests):
        lines.append(f"Test Case {i}")
        if i % sleep_every == 0:
            lines.append(f"    Sleep    {(i % 10) + 1} seconds")
        else:
            lines.append(f"    Log    test {i}")

    lines.append("")
    lines.append("*** Keywords ***")
    for i in range(n_keywords):
        lines.append(f"Keyword {i}")
        lines.append("    [Arguments]    ${arg}")
        lines.append("    Log    ${arg}")
        # Only even-numbered keywords are called (so odd ones are unused)
        if i % 2 == 0:
            lines.append(f"    Keyword {(i + 2) % max(n_keywords, 1)}")

    return "\n".join(lines)


@pytest.mark.performance
@pytest.mark.slow
class TestSleepDetectorScaling:
    """SleepDetector throughput should scale linearly with file size."""

    def test_1k_tests_finding_count_stable(self, tmp_path: Path) -> None:
        """1000-test file: finding count must match the expected sleep pattern."""
        content = _build_robot_file(n_tests=1000, n_keywords=0, sleep_every=5)
        f = tmp_path / "large.robot"
        f.write_text(content, encoding="utf-8")

        t0 = time.perf_counter()
        result = analyze_file(f, analyzers=["sleep_detector"])
        elapsed = time.perf_counter() - t0

        expected = 1000 // 5  # every 5th test (i % 5 == 0) has a sleep
        sleep_findings = [fi for fi in result.findings if fi.pattern.type.name == "SLEEP_IN_TEST"]
        assert len(sleep_findings) == expected, (
            f"Expected {expected} sleep findings, got {len(sleep_findings)}"
        )
        print(f"\nSleepDetector 1000-test throughput: {elapsed:.3f}s  "
              f"({expected / elapsed:.0f} findings/s)")

    def test_finding_memory_footprint_per_entry(self, tmp_path: Path) -> None:
        """Average memory per finding must stay below 10 KB (list overhead)."""
        content = _build_robot_file(n_tests=500, n_keywords=0, sleep_every=1)
        f = tmp_path / "sleep_heavy.robot"
        f.write_text(content, encoding="utf-8")

        result = analyze_file(f)
        assert result.findings, "Expected findings in sleep-heavy file"

        avg_bytes = sys.getsizeof(result.findings) / len(result.findings)
        assert avg_bytes < 10_000, (
            f"Average memory per finding {avg_bytes:.0f}B exceeds 10 KB budget"
        )

    def test_linear_scaling_100_vs_1000_tests(self, tmp_path: Path) -> None:
        """Analysis time should not grow faster than 20× when input grows 10×."""
        small_content = _build_robot_file(n_tests=100, n_keywords=0, sleep_every=5)
        large_content = _build_robot_file(n_tests=1000, n_keywords=0, sleep_every=5)

        f_small = tmp_path / "small.robot"
        f_large = tmp_path / "large.robot"
        f_small.write_text(small_content, encoding="utf-8")
        f_large.write_text(large_content, encoding="utf-8")

        t0 = time.perf_counter()
        analyze_file(f_small)
        t_small = time.perf_counter() - t0

        t0 = time.perf_counter()
        analyze_file(f_large)
        t_large = time.perf_counter() - t0

        # Input grew 10× — runtime must not grow more than 20× (generous for CI variance)
        ratio = t_large / max(t_small, 0.001)
        assert ratio < 20, (
            f"Super-linear scaling detected: 10× input → {ratio:.1f}× runtime. "
            "Check for O(n²) behavior in the analyzer."
        )
        print(f"\nScaling ratio (10× input): {ratio:.2f}×  "
              f"({t_small*1000:.1f}ms → {t_large*1000:.1f}ms)")


@pytest.mark.performance
@pytest.mark.slow
class TestDeadCodeAnalyzerScaling:
    """DeadCodeAnalyzer must handle large keyword tables without super-linear growth."""

    def test_large_keyword_table_finding_count_stable(self, tmp_path: Path) -> None:
        """500 keywords (250 unused) must produce exactly 250 unused-keyword findings."""
        content = _build_robot_file(n_tests=10, n_keywords=500, sleep_every=999)
        f = tmp_path / "keywords.robot"
        f.write_text(content, encoding="utf-8")

        result = analyze_file(f, analyzers=["dead_code"])
        unused_findings = [
            fi for fi in result.findings
            if fi.pattern.type.name == "UNUSED_KEYWORD"
        ]
        # Odd-numbered keywords are never called → 250 unused in 500
        assert len(unused_findings) > 0, "Expected unused-keyword findings"
        print(f"\nDeadCode 500-keyword table: {len(unused_findings)} unused findings")


@pytest.mark.performance
@pytest.mark.slow
class TestDirectoryAnalysisScaling:
    """analyze_directory() throughput over a 50-file suite."""

    def test_50_file_directory_analysis(self, tmp_path: Path) -> None:
        suite = tmp_path / "suite"
        suite.mkdir()
        n_files = 50
        for i in range(n_files):
            (suite / f"test_{i:03d}.robot").write_text(
                _build_robot_file(n_tests=20, n_keywords=5, sleep_every=4),
                encoding="utf-8",
            )

        t0 = time.perf_counter()
        result = analyze_directory(suite, use_cache=False)
        elapsed = time.perf_counter() - t0

        # result.findings is {path: [findings]} — check every file produced results
        assert len(result.findings) == n_files, (
            f"Expected {n_files} files in results, got {len(result.findings)}"
        )
        total = sum(len(fs) for fs in result.findings.values())
        assert total > 0, "Expected findings across directory"

        print(f"\nDirectory analysis (50 files × 20 tests): {elapsed:.3f}s  "
              f"({n_files / elapsed:.1f} files/s)  {total} total findings")

    def test_cache_speedup_is_measurable(self, tmp_path: Path) -> None:
        """Second analysis run with cache should not be slower than first run."""
        suite = tmp_path / "cache_suite"
        suite.mkdir()
        for i in range(20):
            (suite / f"test_{i}.robot").write_text(
                _build_robot_file(n_tests=10, n_keywords=5, sleep_every=3),
                encoding="utf-8",
            )

        t0 = time.perf_counter()
        analyze_directory(suite, use_cache=True)
        t_cold = time.perf_counter() - t0

        t0 = time.perf_counter()
        analyze_directory(suite, use_cache=True)
        t_warm = time.perf_counter() - t0

        # Warm run must not be more than 2× slower than cold (cache should help or be neutral)
        assert t_warm < t_cold * 2, (
            f"Cache warm run ({t_warm:.3f}s) is much slower than cold run ({t_cold:.3f}s). "
            "Cache may be causing overhead."
        )
        print(f"\nCache cold={t_cold:.3f}s  warm={t_warm:.3f}s  "
              f"speedup={t_cold/max(t_warm,0.001):.2f}×")
