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

import functools
import os
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Literal, TypedDict

from .di import get_container
from .domain.entities import TestFile
from .domain.value_objects import Finding, Severity
from .exceptions import AnalysisError, RobotFileNotFoundError
from .logging import get_logger, log_analysis_complete, log_analysis_start

if TYPE_CHECKING:
    from .analyzers import BaseAnalyzer
    from .config import Settings
    from .domain.value_objects.robot_ast import RobotImport, RobotKeyword, RobotTestCase

from .premium import PremiumFeatureError

# Supported error_handling values.
ErrorHandling = Literal["raise", "skip", "warn"]


class DirectoryResults(dict):  # type: ignore[type-arg]
    """Mapping of file paths to findings returned by :func:`analyze_directory`.

    Behaves exactly like a plain :class:`dict` but carries an ``errors`` field
    that lists ``(path, exception)`` pairs for files that could not
    be analysed.  This avoids dynamically patching a plain dict.
    """

    errors: list[tuple[Path, Exception]]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.errors = []


class SuiteInfo(TypedDict):
    """Suite-level aggregate info returned inside :class:`SuiteAnalysisResult`."""

    files: int
    keywords: list[RobotKeyword]
    test_cases: list[RobotTestCase]
    imports: list[RobotImport]


class SuiteStatistics(TypedDict):
    """Finding statistics returned inside :class:`SuiteAnalysisResult`."""

    total_findings: int
    findings_by_severity: dict[str, int]
    findings_by_type: dict[str, int]
    keyword_count: int
    test_count: int
    import_count: int


class SuiteAnalysisResult(TypedDict):
    """Typed result returned by :func:`analyze_suite`."""

    findings: list[Finding]
    file_findings: dict[Path, list[Finding]]
    suite_info: SuiteInfo
    statistics: SuiteStatistics


__all__ = [
    "PremiumFeatureError",
    "SuiteAnalysisResult",
    "SuiteInfo",
    "SuiteStatistics",
    "analyze_directory",
    "analyze_file",
    "analyze_suite",
]

logger = get_logger(__name__)


def analyze_file(
    file_path: str | Path,
    analyzers: list[str | BaseAnalyzer] | None = None,
    settings: Settings | None = None,
    severity_filter: Severity | None = None,
    pattern_filter: list[str] | None = None,
) -> list[Finding]:
    """Analyze a single Robot Framework file.

    This is the main entry point for analyzing individual files.
    It handles file loading, parsing, and running the specified analyzers.

    Args:
        file_path: Path to the Robot Framework file.
        analyzers: List of analyzer names or instances (default: all).
        settings: Configuration settings (default: global settings).
        severity_filter: When given, only findings at or more severe than
            this level are returned (e.g. ``Severity.WARNING`` drops INFO).
        pattern_filter: When given, only findings whose analyzer name
            matches one of these strings are returned.

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
    # Convert to Path
    path = Path(file_path)

    # Validate file exists
    if not path.exists():
        raise RobotFileNotFoundError(path)

    # Resolve services through the DI container
    container = get_container()
    if settings is None:
        settings = container.resolve("settings")

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
            metrics.increment(f"analysis.{analyzer_name}.completed")
            metrics.timing(f"analysis.{analyzer_name}.duration", duration)
            metrics.gauge(f"analysis.{analyzer_name}.findings", len(findings))

        except Exception as e:
            # Track failure
            metrics.increment("analysis.failed")
            metrics.increment(f"analysis.{analyzer_name}.failed")

            raise AnalysisError(
                f"Analysis failed: {e}", file_path=path, analyzer=analyzer_name
            ) from e

    # Track total findings
    metrics.gauge("findings.total", len(all_findings))

    # Apply severity filter after all analyzers complete.
    if severity_filter is not None:
        all_findings = [f for f in all_findings if f.severity <= severity_filter]

    return all_findings


def analyze_directory(
    directory_path: str | Path,
    patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    recursive: bool = True,
    analyzers: list[str | BaseAnalyzer] | None = None,
    settings: Settings | None = None,
    fail_fast: bool = False,
    error_handling: ErrorHandling = "raise",
    severity_filter: Severity | None = None,
    pattern_filter: list[str] | None = None,
    max_workers: int | None = None,
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

        severity_filter: Only return findings at or more severe than this level.
        pattern_filter: Only run/return findings from analyzers with these names.
        max_workers: Maximum number of threads for parallel file analysis
            Defaults to ``min(4, cpu_count)``. Pass ``1`` to
            force sequential behaviour.

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
    # Convert to Path
    path = Path(directory_path)

    # Emit deprecation warning for fail_fast before any other processing
    if fail_fast:
        warnings.warn(
            "The 'fail_fast' parameter is deprecated since 1.0.0b1 and will be "
            "removed in a future release. Use error_handling='raise' instead.",
            DeprecationWarning,
            stacklevel=2,
        )

    # Validate directory exists
    if not path.exists():
        raise RobotFileNotFoundError(path)

    if not path.is_dir():
        raise AnalysisError("Path is not a directory", file_path=path)

    # Resolve services through the DI container
    container = get_container()
    if settings is None:
        settings = container.resolve("settings")
    discovery: Any = container.resolve("file_discovery")

    # Discover files
    if patterns is None:
        patterns = settings.file_patterns

    if exclude_patterns is None:
        exclude_patterns = settings.exclude_patterns

    files = discovery.find_files(
        root_path=path,
        patterns=patterns,
        exclude_patterns=exclude_patterns,
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

    _default_workers = min(4, (os.cpu_count() or 1))
    effective_workers = max_workers if max_workers is not None else _default_workers

    analyze_fn = functools.partial(
        _analyze_one_file,
        analyzers=analyzers,
        settings=settings,
        severity_filter=severity_filter,
        pattern_filter=pattern_filter,
    )
    dir_results, file_errors = _execute_directory_analysis(
        files, analyze_fn, effective_workers, fail_fast
    )

    # Log summary
    total_findings = sum(len(findings) for findings in dir_results.values())
    logger.info(
        "Directory analysis complete",
        extra={
            "directory": str(path),
            "files_analyzed": len(dir_results),
            "files_failed": len(file_errors),
            "total_findings": total_findings,
        },
    )

    # Track metrics
    metrics = container.resolve("metrics")
    metrics.gauge("batch.files_analyzed", len(dir_results))
    metrics.gauge("batch.files_failed", len(file_errors))
    metrics.gauge("batch.total_findings", total_findings)

    # Configurable per-file error handling.
    if file_errors:
        effective_handling = error_handling
        if fail_fast:
            effective_handling = "raise"

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
        # "skip": silently continue

    return dir_results


def analyze_suite(
    suite_path: str | Path,
    analyzers: list[str | BaseAnalyzer] | None = None,
    settings: Settings | None = None,
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
        >>> print(f"Total findings: {len(results['findings'])}")
        >>> print(f"Keywords: {results['suite_info']['keyword_count']}")
    """
    path = Path(suite_path)
    container = get_container()

    # Single file or directory?
    if path.is_file():
        files: list[Path] = [path]
    else:
        discovery: Any = container.resolve("file_discovery")
        files = discovery.find_files(path)

    parser: Any = container.resolve("parser")
    suite_info: SuiteInfo = {
        "files": len(files),
        "keywords": [],
        "test_cases": [],
        "imports": [],
    }

    # Load TestFile objects once for suite-level dead-code analysis.
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

    # Gather suite structure info
    for tf in test_files:
        try:
            robot_suite = parser.parse_suite(tf)
            suite_info["keywords"].extend(robot_suite.keywords)
            suite_info["test_cases"].extend(robot_suite.test_cases)
            suite_info["imports"].extend(robot_suite.imports)
        except Exception as e:
            logger.warning(
                f"Failed to parse suite structure: {tf.path}", extra={"error": str(e)}
            )

    # Determine effective analyzer list
    if settings is None:
        settings = container.resolve("settings")
    analyzer_instances = _get_analyzer_instances(analyzers, settings)

    # Separate dead_code for suite-level cross-file analysis.
    from .analyzers import DeadCodeAnalyzer

    dead_code_analyzer: DeadCodeAnalyzer | None = None
    other_analyzers: list[BaseAnalyzer] = []
    for a in analyzer_instances:
        if isinstance(a, DeadCodeAnalyzer):
            dead_code_analyzer = a
        else:
            other_analyzers.append(a)

    # Run non-dead-code analyzers per file using safe analyzer execution.
    all_findings: list[Finding] = []
    file_findings: dict[Path, list[Finding]] = {tf.path: [] for tf in test_files}

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

    # Run dead_code at suite level for cross-file accuracy.
    if dead_code_analyzer is not None and test_files:
        dc_findings = dead_code_analyzer.analyze_suite(test_files)
        all_findings.extend(dc_findings)
        # Distribute findings back to file_findings map
        for f in dc_findings:
            fpath = f.location.file_path
            if fpath in file_findings:
                file_findings[fpath].append(f)
            else:
                file_findings[fpath] = [f]

    findings_by_severity: dict[str, int] = {}
    findings_by_type: dict[str, int] = {}
    for finding in all_findings:
        sev = finding.severity.name
        findings_by_severity[sev] = findings_by_severity.get(sev, 0) + 1
        pt = finding.pattern.type.name  # type: ignore[attr-defined]
        findings_by_type[pt] = findings_by_type.get(pt, 0) + 1

    statistics: SuiteStatistics = {
        "total_findings": len(all_findings),
        "findings_by_severity": findings_by_severity,
        "findings_by_type": findings_by_type,
        "keyword_count": len(suite_info["keywords"]),
        "test_count": len(suite_info["test_cases"]),
        "import_count": len(suite_info["imports"]),
    }

    return SuiteAnalysisResult(
        findings=all_findings,
        file_findings=file_findings,
        suite_info=suite_info,
        statistics=statistics,
    )


def _analyze_one_file(
    file_path: Path,
    analyzers: list[str | BaseAnalyzer] | None,
    settings: Settings,
    severity_filter: Severity | None,
    pattern_filter: list[str] | None,
) -> tuple[Path, list[Finding]]:
    """Analyze a single file and return (path, findings). Used by analyze_directory."""
    findings = analyze_file(
        file_path,
        analyzers,
        settings,
        severity_filter=severity_filter,
        pattern_filter=pattern_filter,
    )
    return file_path, findings


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
        for file_path in files:
            try:
                _, file_findings = analyze_fn(file_path)
                dir_results[file_path] = file_findings
            except Exception as e:
                if fail_fast:
                    raise
                file_errors.append((file_path, e))
                logger.exception(
                    "Failed to analyze file",
                    extra={"file": str(file_path), "error": str(e)},
                )
    else:
        with ThreadPoolExecutor(max_workers=effective_workers) as pool:
            future_to_path = {pool.submit(analyze_fn, fp): fp for fp in files}
            for future in as_completed(future_to_path):
                fp = future_to_path[future]
                try:
                    _, file_findings = future.result()
                    dir_results[fp] = file_findings
                except Exception as e:
                    file_errors.append((fp, e))
                    logger.exception(
                        "Failed to analyze file",
                        extra={"file": str(fp), "error": str(e)},
                    )

    return dir_results, file_errors


def _create_analyzer_instance(name: str) -> BaseAnalyzer:
    """Create a fresh analyzer instance for each analysis execution."""
    return get_container().resolve("analyzer_registry").create(name)


def _get_analyzer_instances(
    analyzers: list[str | BaseAnalyzer] | None, settings: Settings
) -> list[BaseAnalyzer]:
    """Get analyzer instances from names or objects.

    Args:
        analyzers: List of analyzer names or instances.
        settings: Configuration settings.

    Returns:
        List of analyzer instances.
    """
    if analyzers is None:
        # Check requires_external_repo at the class level before instantiation;
        # analyzers that need an external repo raise on construction without one.
        registry = get_container().resolve("analyzer_registry")
        names = [
            name
            for name in registry.list()
            if not getattr(
                registry.analyzers.get(name), "requires_external_repo", False
            )
        ]
        return [_create_analyzer_instance(name) for name in names]

    instances = []
    for analyzer in analyzers:
        match analyzer:
            case str():
                # Get by name
                instances.append(_create_analyzer_instance(analyzer))
            case _:
                # Already an instance
                instances.append(analyzer)

    return instances
