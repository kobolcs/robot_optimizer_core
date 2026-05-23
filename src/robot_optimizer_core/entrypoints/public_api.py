# src/robot_optimizer_core/entrypoints/public_api.py
"""High-level API functions for Robot Framework Optimizer Core.

This module provides the main entry points for using the Core package.
These functions handle common use cases with sensible defaults.

Example:
    Analyzing files and directories::

        from robot_optimizer_core import analyze_file, analyze_directory

        # Analyze a single file
        findings = analyze_file("tests/login.robot")

        # Analyze a directory
        all_findings = analyze_directory("tests/", recursive=True)

        # Custom analyzers
        findings = analyze_file(
            "tests/login.robot",
            analyzers=["dead_code", "sleep_detector"]
        )

        # Filter by severity or pattern
        findings = analyze_file(
            "tests/login.robot",
            severity_filter=Severity.WARNING,
            pattern_filter=["dead_code"],
        )
"""

from __future__ import annotations

import dataclasses
import logging
import time
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    cast,
)

from ..application.analyzers import BaseAnalyzer, SuiteAwareAnalyzer
from ..application.services.analysis_service import DirectoryResults
from ..composition.container import get_container
from ..domain.entities import TestFile
from ..domain.value_objects.results import AnalysisMeta, FileAnalysisResult
from ..exceptions import AnalysisError, RobotFileNotFoundError

if TYPE_CHECKING:
    from ..domain.value_objects import Finding, Severity
    from ..domain.value_objects.robot_ast import (
        RobotImport,
        RobotKeyword,
        RobotTestCase,
    )
    from ..infrastructure.config import Settings
    from ..infrastructure.metrics.collector import MetricsCollector

from ..application.services.analysis_service import ErrorHandling
from ..premium import PremiumFeatureError


@dataclasses.dataclass
class SuiteInfo:
    """Suite-level aggregate info returned inside :class:`SuiteAnalysisResult`."""

    files: int = 0
    keywords: list[RobotKeyword] = dataclasses.field(default_factory=list)
    test_cases: list[RobotTestCase] = dataclasses.field(default_factory=list)
    imports: list[RobotImport] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class SuiteStatistics:
    """Finding statistics returned inside :class:`SuiteAnalysisResult`."""

    total_findings: int = 0
    findings_by_severity: dict[str, int] = dataclasses.field(default_factory=dict)
    findings_by_type: dict[str, int] = dataclasses.field(default_factory=dict)
    keyword_count: int = 0
    test_count: int = 0
    import_count: int = 0


@dataclasses.dataclass
class SuiteAnalysisResult:
    """Result returned by :func:`analyze_suite`.

    Attributes:
        findings: All findings across every file in the suite.
        file_findings: Per-file breakdown of findings.
        suite_info: Aggregate suite structure (keywords, tests, imports).
        statistics: Finding counts grouped by severity and type.
        errors: Per-file errors that occurred during analysis.  An entry here
            means the file was partially analysed or skipped; findings for
            that file may be missing.
    """

    findings: list[Finding] = dataclasses.field(default_factory=list)
    file_findings: dict[Path, list[Finding]] = dataclasses.field(default_factory=dict)
    suite_info: SuiteInfo = dataclasses.field(default_factory=SuiteInfo)
    statistics: SuiteStatistics = dataclasses.field(default_factory=SuiteStatistics)
    errors: list[tuple[Path, Exception]] = dataclasses.field(default_factory=list)


__all__ = [
    "AnalysisMeta",
    "DirectoryResults",
    "FileAnalysisResult",
    "PremiumFeatureError",
    "SuiteAnalysisResult",
    "SuiteInfo",
    "SuiteStatistics",
    "analyze_directory",
    "analyze_file",
    "analyze_suite",
]

logger = logging.getLogger(__name__)


def _str_analyzer_names(
    analyzers: list[str | BaseAnalyzer] | None,
) -> list[str] | None:
    """Extract string analyzer names from a mixed name/instance list.

    Returns None when *analyzers* is None or contains no string names,
    which signals "run all registered analyzers" to the cache-key logic.
    """
    if not analyzers:
        return None
    names = [a for a in analyzers if isinstance(a, str)]
    return names or None


def _get_or_build_service() -> Any:
    """Build an AnalysisService wired via the composition context."""
    from ..composition.context import get_analysis_service

    return get_analysis_service()



def analyze_file(
    file_path: str | Path,
    analyzers: list[str | BaseAnalyzer] | None = None,
    settings: Settings | None = None,
    min_severity: Severity | None = None,
    pattern_filter: list[str] | None = None,
    metrics: MetricsCollector | None = None,
) -> FileAnalysisResult:
    """Analyze a single Robot Framework file.

    Args:
        file_path: Path to the Robot Framework file.
        analyzers: List of analyzer names or instances (default: all).
        settings: Configuration settings (default: global settings).
        min_severity: When given, only findings at or more severe than this
            level are returned (e.g. ``Severity.WARNING`` drops INFO findings).
        pattern_filter: When given, only findings whose analyzer name
            matches one of these strings are returned.
        metrics: Optional metrics collector (default: global instance).

    Returns:
        :class:`~robot_optimizer_core.domain.value_objects.results.FileAnalysisResult`
        containing findings and analysis metadata.  The result is iterable
        (``for f in result``) and supports ``len(result)`` for call-sites
        written against the old ``list[Finding]`` return type.

    Raises:
        RobotFileNotFoundError: If the file doesn't exist.
        AnalysisError: If analysis fails.

    Example:
        >>> result = analyze_file("tests/login.robot")
        >>> for finding in result:
        ...     print(f"{finding.severity.name}: {finding.message}")
    """
    path = Path(file_path)
    if not path.exists():
        raise RobotFileNotFoundError(path)

    service = _get_or_build_service()
    resolved_settings = settings or service.settings
    t0 = time.time()
    findings = service._run_file_analysis(
        path, analyzers, resolved_settings, min_severity, pattern_filter, metrics
    )
    duration_ms = (time.time() - t0) * 1000

    analyzer_instances = service._get_analyzer_instances(analyzers, resolved_settings)
    meta = AnalysisMeta(
        duration_ms=duration_ms,
        analyzer_names=tuple(a.name for a in analyzer_instances),
    )
    return FileAnalysisResult(file_path=path, findings=findings, meta=meta)


def _analyze_one_file(
    file_path: Path,
    analyzers: list[str | BaseAnalyzer] | None,
    settings: Settings,
    min_severity: Severity | None,
    pattern_filter: list[str] | None,
) -> tuple[Path, list[Finding]]:
    """Analyze a single file and return (path, findings). Used by analyze_directory."""
    result = analyze_file(
        file_path,
        analyzers,
        settings,
        min_severity=min_severity,
        pattern_filter=pattern_filter,
    )
    return file_path, result.findings


def analyze_directory(
    directory_path: str | Path,
    patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    recursive: bool = True,
    analyzers: list[str | BaseAnalyzer] | None = None,
    settings: Settings | None = None,
    error_handling: ErrorHandling = "raise",
    min_severity: Severity | None = None,
    pattern_filter: list[str] | None = None,
    max_workers: int | None = None,
    metrics: MetricsCollector | None = None,
    use_cache: bool = True,
) -> DirectoryResults:
    """Analyze all Robot Framework files in a directory.

    Args:
        directory_path: Path to the directory.
        patterns: File patterns to include (default: ["*.robot", "*.resource"]).
        exclude_patterns: Patterns to exclude (default: from settings).
        recursive: Whether to search subdirectories.
        analyzers: List of analyzer names or instances.
        settings: Configuration settings.
        error_handling: How to handle per-file analysis errors.
            ``"raise"`` re-raises as ExceptionGroup (default).
            ``"skip"`` silently discards failed files and returns partial results.
            ``"warn"`` logs a warning and returns partial results (exit-code 3
            on the CLI).
        min_severity: Only return findings at or more severe than this level.
        pattern_filter: Only run/return findings from analyzers with these names.
        max_workers: Maximum number of threads for parallel file analysis.
            Defaults to ``min(4, cpu_count)``. Pass ``1`` to force sequential.
        metrics: Optional metrics collector (default: global instance).
        use_cache: When ``True`` (default), unchanged files return cached results.
            Pass ``False`` to force a full re-analysis.

    Returns:
        :class:`~robot_optimizer_core.application.services.analysis_service.DirectoryResults`
        with ``.findings`` (dict of path → list[Finding]) and ``.errors``.

    Raises:
        RobotFileNotFoundError: If directory doesn't exist.
        ExceptionGroup: If analysis fails and ``error_handling="raise"``.

    Example:
        >>> result = analyze_directory("tests/", recursive=True)
        >>> for file_path, findings in result.findings.items():
        ...     print(f"{file_path}: {len(findings)} findings")
    """
    _dir = Path(directory_path)
    if not _dir.exists():
        raise RobotFileNotFoundError(_dir)
    if not _dir.is_dir():
        raise AnalysisError("Path is not a directory", file_path=_dir)
    path = _dir
    container = get_container()
    if settings is None:
        settings = container.resolve("settings")
    if metrics is None:
        metrics = container.resolve("metrics")

    import functools
    # min_severity is intentionally omitted here so that analyze_fn always
    # returns the full finding set.  run_directory_analysis applies the filter
    # after cache writes, ensuring the cache stores unfiltered results and the
    # same cache entry is valid for any severity threshold.
    analyze_fn = functools.partial(
        _analyze_one_file,
        analyzers=analyzers,
        settings=settings,
        min_severity=None,
        pattern_filter=pattern_filter,
    )

    return cast(
        "DirectoryResults",
        _get_or_build_service().run_directory_analysis(
            directory_path=path,
            analyze_fn=analyze_fn,
            patterns=patterns,
            exclude_patterns=exclude_patterns,
            recursive=recursive,
            settings=settings,
            fail_fast=False,
            error_handling=error_handling,
            max_workers=max_workers,
            metrics=metrics,
            use_cache=use_cache,
            min_severity=min_severity,
            analyzer_names=_str_analyzer_names(analyzers),
        ),
    )


def _load_test_files(files: list[Path]) -> list[TestFile]:
    """Load TestFile objects from file paths."""
    test_files: list[TestFile] = []
    for file_path in files:
        try:
            tf = TestFile.from_path(file_path)
            test_files.append(tf)
        except Exception as e:
            logger.warning(
                f"Failed to load file for suite analysis: {file_path}",
                extra={"error": str(e)},
            )
    return test_files


def _gather_suite_structure(
    test_files: list[TestFile], parser: Any
) -> tuple[SuiteInfo, list[Path]]:
    """Parse and gather suite structure information."""
    suite_info = SuiteInfo(files=len(test_files))
    failed_paths: list[Path] = []
    for tf in test_files:
        try:
            robot_suite = parser.parse_suite(tf)
            suite_info.keywords.extend(robot_suite.keywords)
            suite_info.test_cases.extend(robot_suite.test_cases)
            suite_info.imports.extend(robot_suite.imports)
        except Exception as e:
            logger.warning(
                f"Failed to parse suite structure: {tf.path}", extra={"error": str(e)}
            )
            failed_paths.append(tf.path)
    return suite_info, failed_paths


def _analyze_with_other_analyzers(
    test_files: list[TestFile],
    other_analyzers: list[BaseAnalyzer],
) -> tuple[list[Finding], dict[Path, list[Finding]], list[tuple[Path, Exception]]]:
    """Run non-suite-aware analyzers on each file."""
    all_findings: list[Finding] = []
    file_findings: dict[Path, list[Finding]] = {tf.path: [] for tf in test_files}
    errors: list[tuple[Path, Exception]] = []

    for tf in test_files:
        for analyzer in other_analyzers:
            try:
                findings = analyzer.safe_analyze(tf)
                all_findings.extend(findings)
                file_findings[tf.path].extend(findings)
            except Exception as e:
                logger.error(
                    f"Analyzer {analyzer.name} failed on {tf.path}: {e}",
                    exc_info=True,
                )
                errors.append((tf.path, e))

    return all_findings, file_findings, errors


def _run_suite_analysis(
    dead_code_analyzer: SuiteAwareAnalyzer | None,
    test_files: list[TestFile],
    all_findings: list[Finding],
    file_findings: dict[Path, list[Finding]],
) -> None:
    """Run suite-aware analyzer at suite level and integrate findings."""
    if dead_code_analyzer is None or not test_files:
        return
    dc_findings = dead_code_analyzer.analyze_suite(test_files)
    all_findings.extend(dc_findings)
    for f in dc_findings:
        fpath = f.location.file_path
        if fpath in file_findings:
            file_findings[fpath].append(f)
        else:
            file_findings[fpath] = [f]


def _calculate_suite_statistics(
    all_findings: list[Finding], suite_info: SuiteInfo
) -> SuiteStatistics:
    """Calculate analysis statistics."""
    findings_by_severity: dict[str, int] = {}
    findings_by_type: dict[str, int] = {}
    for finding in all_findings:
        sev = finding.severity.name
        findings_by_severity[sev] = findings_by_severity.get(sev, 0) + 1
        pt = finding.pattern.type.name
        findings_by_type[pt] = findings_by_type.get(pt, 0) + 1

    return SuiteStatistics(
        total_findings=len(all_findings),
        findings_by_severity=findings_by_severity,
        findings_by_type=findings_by_type,
        keyword_count=len(suite_info.keywords),
        test_count=len(suite_info.test_cases),
        import_count=len(suite_info.imports),
    )


def analyze_suite(
    suite_path: str | Path,
    analyzers: list[str | BaseAnalyzer] | None = None,
    settings: Settings | None = None,
    min_severity: Severity | None = None,
) -> SuiteAnalysisResult:
    """Analyze a Robot Framework test suite with AST parsing.

    When the ``dead_code`` analyzer is active, this function uses
    :meth:`~robot_optimizer_core.application.analyzers.DeadCodeAnalyzer.analyze_suite`
    for cross-file unused keyword detection.  Per-file findings from all other
    analyzers are preserved; dead-code findings are replaced with the
    suite-level ones to avoid false positives caused by keywords that are
    called from *other* files in the suite.

    Args:
        suite_path: Path to suite file or directory.
        analyzers: List of analyzer names or instances.
        settings: Configuration settings.
        min_severity: Only return findings at or above this severity.

    Returns:
        SuiteAnalysisResult with findings, suite info, and statistics.

    Example:
        >>> results = analyze_suite("tests/")
        >>> print(f"Total findings: {len(results.findings)}")
        >>> print(f"Keywords: {len(results.suite_info.keywords)}")
    """
    path = Path(suite_path)
    container = get_container()

    if path.is_file():
        files: list[Path] = [path]
    else:
        discovery: Any = container.resolve("file_discovery")
        files = discovery.find_files(path)

    parser: Any = container.resolve("parser")
    test_files = _load_test_files(files)
    suite_info, parse_failed_paths = _gather_suite_structure(test_files, parser)

    if parse_failed_paths:
        failed_set = set(parse_failed_paths)
        test_files_for_suite = [tf for tf in test_files if tf.path not in failed_set]
    else:
        test_files_for_suite = test_files

    if settings is None:
        settings = container.resolve("settings")
    service = _get_or_build_service()
    analyzer_instances = service._get_analyzer_instances(analyzers, settings)

    suite_aware_analyzers: list[SuiteAwareAnalyzer] = []
    other_analyzers: list[BaseAnalyzer] = []
    for a in analyzer_instances:
        if isinstance(a, SuiteAwareAnalyzer):
            suite_aware_analyzers.append(a)
        else:
            other_analyzers.append(a)

    all_findings, file_findings, suite_errors = _analyze_with_other_analyzers(
        test_files, other_analyzers
    )
    for _suite_analyzer in suite_aware_analyzers:
        _run_suite_analysis(_suite_analyzer, test_files_for_suite, all_findings, file_findings)

    if min_severity is not None:
        all_findings = [f for f in all_findings if f.severity <= min_severity]
        file_findings = {
            p: [f for f in fs if f.severity <= min_severity]
            for p, fs in file_findings.items()
        }

    statistics = _calculate_suite_statistics(all_findings, suite_info)

    return SuiteAnalysisResult(
        findings=all_findings,
        file_findings=file_findings,
        suite_info=suite_info,
        statistics=statistics,
        errors=suite_errors,
    )
