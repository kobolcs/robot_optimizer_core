# src/robot_optimizer_core/api.py
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
import functools
import os
import time
import warnings
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    cast,
)

from .analyzers import BaseAnalyzer, SuiteAwareAnalyzer
from .infrastructure.cache.analysis_cache import AnalysisCache
from .di import get_container
from .domain.entities import TestFile
from .domain.value_objects import Finding, Severity
from .exceptions import AnalysisError, RobotFileNotFoundError
from .infrastructure.logging.adapter import get_logger, log_analysis_complete, log_analysis_start

if TYPE_CHECKING:
    from .infrastructure.config import Settings
    from .domain.value_objects.robot_ast import RobotImport, RobotKeyword, RobotTestCase
    from .infrastructure.metrics.collector import MetricsCollector

from .premium import PremiumFeatureError

# Supported error_handling values.
ErrorHandling = Literal["raise", "skip", "warn"]


@dataclasses.dataclass
class DirectoryResults:
    """Mapping of file paths to findings returned by :func:`analyze_directory`.

    Attributes:
        findings: Dictionary mapping file paths to their findings.
        errors: List of (path, exception) pairs for files that could not be analysed.
    """

    findings: dict[Path, list[Finding]] = dataclasses.field(default_factory=dict)
    errors: list[tuple[Path, Exception]] = dataclasses.field(default_factory=list)


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
    suite_info: SuiteInfo = dataclasses.field(
        default_factory=lambda: SuiteInfo()
    )
    statistics: SuiteStatistics = dataclasses.field(
        default_factory=lambda: SuiteStatistics()
    )
    errors: list[tuple[Path, Exception]] = dataclasses.field(default_factory=list)


__all__ = [
    "AnalysisCache",
    "DirectoryResults",
    "PremiumFeatureError",
    "SuiteAnalysisResult",
    "SuiteInfo",
    "SuiteStatistics",
    "analyze_directory",
    "analyze_file",
    "analyze_suite",
]

logger = get_logger(__name__)


def _warn_deprecated_param(old: str, new: str, since: str, stacklevel: int = 3) -> None:
    warnings.warn(
        f"The '{old}' parameter is deprecated since {since}. Use '{new}' instead.",
        DeprecationWarning,
        stacklevel=stacklevel,
    )


def analyze_file(
    file_path: str | Path,
    analyzers: list[str | BaseAnalyzer] | None = None,
    settings: Settings | None = None,
    min_severity: Severity | None = None,
    pattern_filter: list[str] | None = None,
    metrics: MetricsCollector | None = None,
    *,
    severity_filter: Severity | None = None,
) -> list[Finding]:
    """Analyze a single Robot Framework file.

    This is the main entry point for analyzing individual files.
    It handles file loading, parsing, and running the specified analyzers.

    Args:
        file_path: Path to the Robot Framework file.
        analyzers: List of analyzer names or instances (default: all).
        settings: Configuration settings (default: global settings).
        min_severity: When given, only findings at or more severe than this
            level are returned (e.g. ``Severity.WARNING`` drops INFO findings).
        pattern_filter: When given, only findings whose analyzer name
            matches one of these strings are returned.
        metrics: Optional metrics collector for recording analysis metrics
            (default: global metrics instance). Pass a no-op implementation
            to disable metrics collection.
        severity_filter: Deprecated alias for *min_severity*.  Will be
            removed in a future release.

    Returns:
        List of findings from all analyzers.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        AnalysisError: If analysis fails.

    Example:
        >>> findings = analyze_file("tests/login.robot")
        >>> for finding in findings:
        ...     print(f"{finding.severity.name}: {finding.message}")
    """
    if severity_filter is not None:
        _warn_deprecated_param("severity_filter", "min_severity", "1.0.0b1", stacklevel=2)
        if min_severity is None:
            min_severity = severity_filter
    # Convert to Path
    path = Path(file_path)

    # Validate file exists
    if not path.exists():
        raise RobotFileNotFoundError(path)

    # Resolve services through the DI container (only if needed)
    if settings is None or metrics is None:
        container = get_container()
        if settings is None:
            settings = container.resolve("settings")
        if metrics is None:
            metrics = container.resolve("metrics")

    # Enforce max file size before reading content and load file
    try:
        file_size = path.stat().st_size
        if file_size > settings.max_file_size_bytes:
            raise AnalysisError(
                f"File exceeds maximum size: {path} "
                f"({file_size} bytes, limit: {settings.max_file_size_bytes} bytes)",
                file_path=path,
            )

        test_file = TestFile.from_path(path)
    except AnalysisError:
        raise
    except Exception as e:
        raise AnalysisError(f"Failed to load file: {e}", file_path=path) from e

    # Get analyzers
    analyzer_instances = _get_analyzer_instances(analyzers, settings)

    # Run analysis
    all_findings: list[Finding] = []

    for analyzer in analyzer_instances:
        analyzer_name = analyzer.name

        # Skip filtered analyzers early to avoid unnecessary analyzer work.
        if pattern_filter is not None and analyzer_name not in pattern_filter:
            continue

        # Log and track analysis start
        log_analysis_start(path, analyzer_name, logger)
        start_time = time.time()

        try:
            # Run analyzer
            findings = analyzer.safe_analyze(test_file)
            all_findings.extend(findings)

            # Track success
            duration = time.time() - start_time
            log_analysis_complete(path, analyzer_name, len(findings), duration, logger)

            metrics.increment("analysis.completed")
            metrics.timing(f"analyzer.{analyzer_name}.duration", duration)
            metrics.gauge(f"analyzer.{analyzer_name}.findings", len(findings))

        except AnalysisError:
            # safe_analyze already wrapped, logged, and recorded the per-analyzer
            # failure metric; only record the top-level counter here to avoid
            # double-counting the per-analyzer metric.
            metrics.increment("analysis.failed")
            raise

        except Exception as e:
            # Unexpected error outside safe_analyze (e.g. metrics/logging failure).
            metrics.increment("analysis.failed")
            metrics.increment(f"analyzer.{analyzer_name}.failed")
            raise AnalysisError(
                f"Analysis failed: {e}", file_path=path, analyzer=analyzer_name
            ) from e

    # Track total findings
    metrics.gauge("findings.total", len(all_findings))

    # Apply min_severity filter after all analyzers complete.
    if min_severity is not None:
        all_findings = [f for f in all_findings if f.severity <= min_severity]

    return all_findings


def _validate_directory_path(directory_path: str | Path) -> Path:
    """Validate that the directory path exists and is a directory."""
    path = Path(directory_path)
    if not path.exists():
        raise RobotFileNotFoundError(path)
    if not path.is_dir():
        raise AnalysisError("Path is not a directory", file_path=path)
    return path


def _handle_directory_analysis_errors(
    file_errors: list[tuple[Path, Exception]],
    error_handling: ErrorHandling,
    fail_fast: bool,
    dir_results: DirectoryResults,
) -> None:
    """Handle errors from directory analysis based on error_handling mode."""
    if not file_errors:
        return
    effective_handling = "raise" if fail_fast else error_handling
    if effective_handling == "raise":
        raise ExceptionGroup(
            f"Analysis failed for {len(file_errors)} files",
            [e for _, e in file_errors],
        )
    if effective_handling == "warn":
        logger.warning(
            f"Analysis had partial failures: {len(file_errors)} file(s) could not be analyzed",
            extra={"failed_files": [str(p) for p, _ in file_errors]},
        )
        dir_results.errors = file_errors


def analyze_directory(
    directory_path: str | Path,
    patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    recursive: bool = True,
    analyzers: list[str | BaseAnalyzer] | None = None,
    settings: Settings | None = None,
    fail_fast: bool = False,
    error_handling: ErrorHandling = "raise",
    min_severity: Severity | None = None,
    pattern_filter: list[str] | None = None,
    max_workers: int | None = None,
    metrics: MetricsCollector | None = None,
    use_cache: bool = True,
    *,
    severity_filter: Severity | None = None,
) -> DirectoryResults:
    """Analyze all Robot Framework files in a directory.

    This function discovers and analyzes all matching files in a directory,
    returning a mapping of file paths to their findings.

    Args:
        directory_path: Path to the directory.
        patterns: File patterns to include (default: ["*.robot", "*.resource"]).
        exclude_patterns: Patterns to exclude (default: from settings).
        recursive: Whether to search subdirectories.
        analyzers: List of analyzer names or instances.
        settings: Configuration settings.
        fail_fast: Stop on first error (deprecated; prefer ``error_handling``).
        error_handling: How to handle per-file analysis errors.
            ``"raise"`` re-raises as ExceptionGroup (default for the Python API).
            ``"skip"`` silently discards failed files and returns partial results.
            ``"warn"`` logs a warning and returns partial results (exit-code 3
            on the CLI).

            .. note::
                The CLI always invokes this function with ``error_handling="warn"``
                so that a single bad file does not abort a directory scan.  The
                Python API defaults to ``"raise"`` to surface errors immediately.
                Pass ``error_handling="warn"`` explicitly if you want CLI-like
                behaviour from the Python API.

        min_severity: Only return findings at or more severe than this level.
        pattern_filter: Only run/return findings from analyzers with these names.
        severity_filter: Deprecated alias for *min_severity*.  Will be
            removed in a future release.
        max_workers: Maximum number of threads for parallel file analysis
            Defaults to ``min(4, cpu_count)``. Pass ``1`` to
            force sequential behaviour.
        metrics: Optional metrics collector for recording batch metrics
            (default: global metrics instance). Pass a no-op implementation
            to disable metrics collection.
        use_cache: When ``True`` (default), unchanged files are skipped and
            their findings are returned from ``~/.cache/robot-optimizer/cache.json``.
            Pass ``False`` to force a full re-analysis (equivalent to
            ``--no-cache`` on the CLI).

    Returns:
        Dictionary mapping file paths to findings.

    Raises:
        FileNotFoundError: If directory doesn't exist.
        AnalysisError: If analysis fails (when fail_fast=True or
            ``error_handling="raise"``).

    Example:
        >>> findings_map = analyze_directory("tests/", recursive=True)
        >>> for file_path, findings in findings_map.items():
        ...     print(f"{file_path}: {len(findings)} findings")
    """
    # Deprecation warnings
    if fail_fast:
        warnings.warn(
            "The 'fail_fast' parameter is deprecated since 1.0.0b1 and will be "
            "removed in a future release. Use error_handling='raise' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
    if severity_filter is not None:
        _warn_deprecated_param("severity_filter", "min_severity", "1.0.0b1", stacklevel=2)
        if min_severity is None:
            min_severity = severity_filter

    # Validate directory and resolve settings
    path = _validate_directory_path(directory_path)
    container = get_container()
    if settings is None:
        settings = container.resolve("settings")
    discovery: Any = container.resolve("file_discovery")

    # Discover files with resolved patterns
    resolved_patterns = patterns or settings.file_patterns
    resolved_excludes = exclude_patterns or settings.exclude_patterns
    files = discovery.find_files(
        root_path=path,
        patterns=resolved_patterns,
        exclude_patterns=resolved_excludes,
        recursive=recursive,
    )

    logger.info(
        "Starting directory analysis",
        extra={
            "directory": str(path),
            "file_count": len(files),
            "recursive": recursive,
        },
    )

    # Resolve cache hits before dispatching to the thread pool.
    cache: AnalysisCache | None = None
    cache_hits: dict[Path, list[Finding]] = {}
    file_hashes: dict[Path, str] = {}
    files_to_analyze = files

    if metrics is None:
        metrics = container.resolve("metrics")

    if use_cache:
        cache = AnalysisCache()
        files_to_analyze, cache_hits, file_hashes = _resolve_cache(files, cache)
        hit_count = len(cache_hits)
        miss_count = len(files_to_analyze)
        if hit_count or miss_count:
            logger.debug(
                "Cache: %d hit(s), %d miss(es)", hit_count, miss_count
            )
            metrics.gauge("cache.hits", hit_count)
            metrics.gauge("cache.misses", miss_count)
            if files:
                metrics.gauge("cache.hit_rate", hit_count / len(files))

    # Execute analysis on cache misses only.
    _default_workers = min(4, (os.cpu_count() or 1))
    effective_workers = max_workers if max_workers is not None else _default_workers
    analyze_fn = functools.partial(
        _analyze_one_file,
        analyzers=analyzers,
        settings=settings,
        min_severity=min_severity,
        pattern_filter=pattern_filter,
    )
    dir_results, file_errors = _execute_directory_analysis(
        files_to_analyze, analyze_fn, effective_workers, fail_fast
    )

    # Merge cache hits into results and persist new entries.
    for fp, cached_findings in cache_hits.items():
        dir_results.findings[fp] = cached_findings
    if cache is not None:
        for fp, new_findings in dir_results.findings.items():
            if fp not in cache_hits and fp in file_hashes:
                cache.put(fp, file_hashes[fp], new_findings)
        cache.flush()

    # Log and track metrics
    total_findings = sum(len(findings) for findings in dir_results.findings.values())
    logger.info(
        "Directory analysis complete",
        extra={
            "directory": str(path),
            "files_analyzed": len(dir_results.findings),
            "files_failed": len(file_errors),
            "total_findings": total_findings,
        },
    )

    metrics.gauge("batch.files_analyzed", len(dir_results.findings))
    metrics.gauge("batch.files_failed", len(file_errors))
    metrics.gauge("batch.total_findings", total_findings)

    # Handle errors
    _handle_directory_analysis_errors(
        file_errors, error_handling, fail_fast, dir_results
    )

    return dir_results


def _resolve_cache(
    files: list[Path], cache: AnalysisCache
) -> tuple[list[Path], dict[Path, list[Finding]], dict[Path, str]]:
    """Split *files* into cache hits and misses.

    Returns ``(misses, hits_findings, hashes)`` where *misses* is the list of
    files that must be analysed, *hits_findings* maps each cached file to its
    findings, and *hashes* maps every file to its SHA-256 digest.
    """
    misses: list[Path] = []
    hits: dict[Path, list[Finding]] = {}
    hashes: dict[Path, str] = {}

    for fp in files:
        try:
            h = cache.file_hash(fp)
            hashes[fp] = h
            cached = cache.get(fp, h)
            if cached is not None:
                hits[fp] = cached
            else:
                misses.append(fp)
        except OSError:
            # Unhashable file (e.g. permission error) → treat as miss.
            misses.append(fp)

    return misses, hits, hashes


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
    """Parse and gather suite structure information.

    Returns ``(suite_info, failed_paths)`` where *failed_paths* lists files
    that could not be parsed.  Callers should exclude those files from
    suite-level analysis to avoid false-positive dead-code findings.
    """
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
    """Run non-suite-aware analyzers on each file.

    Returns ``(all_findings, file_findings, errors)`` where *errors* lists
    ``(path, exception)`` pairs for analyzer failures so callers can surface
    partial-analysis conditions instead of silently swallowing them.
    """
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
    :meth:`~robot_optimizer_core.analyzers.DeadCodeAnalyzer.analyze_suite`
    for cross-file unused keyword detection.  Per-file findings from all other
    analyzers are preserved; dead-code findings are replaced with the
    suite-level ones to avoid false positives caused by keywords that are
    called from *other* files in the suite.

    Args:
        suite_path: Path to suite file or directory.
        analyzers: List of analyzer names or instances.
        settings: Configuration settings.

    Returns:
        Dictionary with analysis results including:
        - findings: List of all findings
        - suite_info: Parsed suite information
        - statistics: Analysis statistics

    Example:
        >>> results = analyze_suite("tests/")
        >>> print(f"Total findings: {len(results.findings)}")
        >>> print(f"Keywords: {len(results.suite_info.keywords)}")
    """
    path = Path(suite_path)
    container = get_container()

    # Single file or directory?
    if path.is_file():
        files: list[Path] = [path]
    else:
        discovery: Any = container.resolve("file_discovery")
        files = discovery.find_files(path)

    # Load test files and gather suite structure
    parser: Any = container.resolve("parser")
    test_files = _load_test_files(files)
    suite_info, parse_failed_paths = _gather_suite_structure(test_files, parser)

    # Exclude files whose suite structure could not be parsed from suite-level
    # analysis.  Passing them to a SuiteAwareAnalyzer would produce false-positive
    # findings for symbols that are only defined in the unparseable files.
    if parse_failed_paths:
        failed_set = set(parse_failed_paths)
        test_files_for_suite = [tf for tf in test_files if tf.path not in failed_set]
    else:
        test_files_for_suite = test_files

    # Resolve settings and analyzer instances
    if settings is None:
        settings = container.resolve("settings")
    analyzer_instances = _get_analyzer_instances(analyzers, settings)

    # Separate suite-aware analyzers (those implementing SuiteAwareAnalyzer protocol)
    # from per-file analyzers.  Every analyzer that provides analyze_suite() participates
    # in cross-file detection; third-party analyzers can join without touching api.py.
    suite_aware_analyzers: list[SuiteAwareAnalyzer] = []
    other_analyzers: list[BaseAnalyzer] = []
    for a in analyzer_instances:
        if isinstance(a, SuiteAwareAnalyzer):
            suite_aware_analyzers.append(a)
        else:
            other_analyzers.append(a)

    # Run per-file analyzers on ALL test files (not just parse-succeeded ones)
    all_findings, file_findings, suite_errors = _analyze_with_other_analyzers(
        test_files, other_analyzers
    )
    # Run suite-aware analyzers only on files that parsed successfully
    for _suite_analyzer in suite_aware_analyzers:
        _run_suite_analysis(_suite_analyzer, test_files_for_suite, all_findings, file_findings)

    # Apply min_severity filter before computing statistics and returning.
    if min_severity is not None:
        all_findings = [f for f in all_findings if f.severity <= min_severity]
        file_findings = {
            p: [f for f in fs if f.severity <= min_severity]
            for p, fs in file_findings.items()
        }

    # Calculate statistics
    statistics = _calculate_suite_statistics(all_findings, suite_info)

    return SuiteAnalysisResult(
        findings=all_findings,
        file_findings=file_findings,
        suite_info=suite_info,
        statistics=statistics,
        errors=suite_errors,
    )


def _analyze_one_file(
    file_path: Path,
    analyzers: list[str | BaseAnalyzer] | None,
    settings: Settings,
    min_severity: Severity | None,
    pattern_filter: list[str] | None,
) -> tuple[Path, list[Finding]]:
    """Analyze a single file and return (path, findings). Used by analyze_directory."""
    findings = analyze_file(
        file_path,
        analyzers,
        settings,
        min_severity=min_severity,
        pattern_filter=pattern_filter,
    )
    return file_path, findings


def _run_sequential(
    files: list[Path],
    analyze_fn: Callable[[Path], tuple[Path, list[Finding]]],
    fail_fast: bool,
    dir_results: DirectoryResults,
    file_errors: list[tuple[Path, Exception]],
) -> None:
    """Analyze files one at a time, appending results and errors in-place."""
    for file_path in files:
        try:
            _, file_findings = analyze_fn(file_path)
            dir_results.findings[file_path] = file_findings
        except Exception as e:
            if fail_fast:
                raise
            file_errors.append((file_path, e))
            logger.exception(
                "Failed to analyze file",
                extra={"file": str(file_path), "error": str(e)},
            )


def _run_parallel(
    files: list[Path],
    analyze_fn: Callable[[Path], tuple[Path, list[Finding]]],
    effective_workers: int,
    dir_results: DirectoryResults,
    file_errors: list[tuple[Path, Exception]],
) -> None:
    """Analyze files using a thread pool, appending results and errors in-place."""
    with ThreadPoolExecutor(max_workers=effective_workers) as pool:
        future_to_path = {pool.submit(analyze_fn, fp): fp for fp in files}
        for future in as_completed(future_to_path):
            fp = future_to_path[future]
            try:
                _, file_findings = future.result()
                dir_results.findings[fp] = file_findings
            except Exception as e:
                file_errors.append((fp, e))
                logger.exception(
                    "Failed to analyze file",
                    extra={"file": str(fp), "error": str(e)},
                )


def _execute_directory_analysis(
    files: list[Path],
    analyze_fn: Callable[[Path], tuple[Path, list[Finding]]],
    effective_workers: int,
    fail_fast: bool,
) -> tuple[DirectoryResults, list[tuple[Path, Exception]]]:
    """Run per-file analysis sequentially or in parallel; return results and errors."""
    dir_results: DirectoryResults = DirectoryResults()
    file_errors: list[tuple[Path, Exception]] = []

    if effective_workers == 1 or len(files) <= 1 or fail_fast:
        _run_sequential(files, analyze_fn, fail_fast, dir_results, file_errors)
    else:
        _run_parallel(files, analyze_fn, effective_workers, dir_results, file_errors)

    return dir_results, file_errors


def _create_analyzer_instance(
    name: str, config: dict[str, object] | None = None
) -> BaseAnalyzer:
    """Create a fresh analyzer instance, injecting per-analyzer config when provided.

    Args:
        name: Registered analyzer name (e.g. ``"dead_code"``).
        config: Optional config dict to pass to the analyzer constructor.

    Returns:
        A new ``BaseAnalyzer`` instance.
    """
    registry = get_container().resolve("analyzer_registry")
    cls = registry.analyzers.get(name)
    if cls is None:
        # Fall back to the registry's create() which will raise with a clear message
        return cast("BaseAnalyzer", registry.create(name))
    return cast("BaseAnalyzer", cls(config=config or {}))


def _get_analyzer_instances(
    analyzers: list[str | BaseAnalyzer] | None, settings: Settings
) -> list[BaseAnalyzer]:
    """Resolve a list of analyzer names/instances into concrete ``BaseAnalyzer`` objects.

    Per-analyzer configuration from ``Settings.analyzer_config`` is passed to
    each named analyzer at construction time.

    Args:
        analyzers: List of analyzer names or pre-constructed instances.
            Pass ``None`` to use all registered analyzers that do not require
            an external repository.
        settings: Configuration settings. ``settings.analyzer_config`` is
            consulted for per-analyzer overrides.

    Returns:
        List of ready-to-use ``BaseAnalyzer`` instances.
    """
    analyzer_config = settings.analyzer_config

    if analyzers is None:
        registry = get_container().resolve("analyzer_registry")
        names = [
            name
            for name in registry.list()
            if not getattr(
                registry.analyzers.get(name), "requires_external_repo", False
            )
        ]
        return [
            _create_analyzer_instance(name, analyzer_config.get(name))
            for name in names
        ]

    instances = []
    for analyzer in analyzers:
        match analyzer:
            case str():
                instances.append(
                    _create_analyzer_instance(analyzer, analyzer_config.get(analyzer))
                )
            case _:
                instances.append(analyzer)

    return instances
