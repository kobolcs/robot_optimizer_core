# src/robot_optimizer_core/application/services/analysis_service.py
"""High-level analysis service that decouples CLI from framework details.

This module provides the AnalysisService facade, which offers a simplified
interface to the analysis framework while hiding complexity of the DI container,
metrics, logging, and analyzer registry.

The service is the primary interface for CLI and other consumers.  All directory
orchestration logic (thread pool, caching, error dispatch, filtering) lives here.
Dependencies (file_discovery, registry, metrics) are injected via __init__ so the
service is testable without global state.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from ...domain.entities import TestFile
from ...domain.ports.analyzer_registry import IAnalyzerRegistry
from ...domain.ports.cache import IAnalysisCache
from ...domain.ports.file_discovery import IFileDiscovery
from ...domain.value_objects import Finding, Severity
from ...exceptions import AnalysisError, RobotFileNotFoundError
from ...infrastructure.config import Settings
from ...infrastructure.logging.adapter import (
    get_logger,
    log_analysis_complete,
    log_analysis_start,
)

if TYPE_CHECKING:
    from ...domain.ports.metrics import IMetrics
    from ..analyzers import BaseAnalyzer

__all__ = [
    "AnalysisResult",
    "AnalysisService",
    "DirectoryAnalysisResult",
    "DirectoryResults",
]

ErrorHandling = Literal["raise", "skip", "warn"]

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


class AnalysisResult(NamedTuple):
    """Result from analyzing a single file."""

    file_path: Path
    findings: list[Finding]
    error: Exception | None = None

    @property
    def is_success(self) -> bool:
        """True if analysis succeeded."""
        return self.error is None

    @property
    def error_count(self) -> int:
        """Count of ERROR-level findings."""
        return sum(1 for f in self.findings if f.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        """Count of WARNING-level findings."""
        return sum(1 for f in self.findings if f.severity == Severity.WARNING)

    @property
    def info_count(self) -> int:
        """Count of INFO-level findings."""
        return sum(1 for f in self.findings if f.severity == Severity.INFO)


class DirectoryAnalysisResult(NamedTuple):
    """Result from analyzing a directory."""

    directory: Path
    results: dict[Path, list[Finding]]
    errors: list[tuple[Path, Exception]]

    @property
    def all_findings(self) -> list[Finding]:
        """All findings across all files."""
        return [f for findings in self.results.values() for f in findings]

    @property
    def success_count(self) -> int:
        """Number of successfully analyzed files."""
        return len(self.results)

    @property
    def failed_file_count(self) -> int:
        """Number of files that failed analysis."""
        return len(self.errors)

    @property
    def total_findings(self) -> int:
        """Total findings across all files."""
        return sum(len(findings) for findings in self.results.values())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "directory": str(self.directory),
            "success_count": self.success_count,
            "failed_file_count": self.failed_file_count,
            "total_findings": self.total_findings,
            "errors": [(str(path), str(exc)) for path, exc in self.errors],
        }


@dataclasses.dataclass
class DirectoryResults:
    """Mapping of file paths to findings from directory analysis.

    Attributes:
        findings: Dictionary mapping file paths to their findings.
        errors: List of (path, exception) pairs for files that could not be analysed.
    """

    findings: dict[Path, list[Finding]] = dataclasses.field(default_factory=dict)
    errors: list[tuple[Path, Exception]] = dataclasses.field(default_factory=list)


# ---------------------------------------------------------------------------
# Module-level helpers (moved from public_api to break the inversion)
# ---------------------------------------------------------------------------


def _validate_directory_path(directory_path: str | Path) -> Path:
    """Validate that the directory path exists and is a directory."""
    path = Path(directory_path)
    if not path.exists():
        raise RobotFileNotFoundError(path)
    if not path.is_dir():
        raise AnalysisError("Path is not a directory", file_path=path)
    return path


def _resolve_cache(
    files: list[Path], cache: AnalysisCache
) -> tuple[list[Path], dict[Path, list[Finding]], dict[Path, str]]:
    """Split *files* into cache hits and misses."""
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
        except OSError:  # pragma: no cover
            misses.append(fp)

    return misses, hits, hashes


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


# ---------------------------------------------------------------------------
# AnalysisService
# ---------------------------------------------------------------------------


class AnalysisService:
    """High-level analysis service that owns all orchestration logic.

    This service handles file discovery, caching, thread pool execution,
    error dispatch, and result filtering for directory analysis.  Per-file
    analysis is handled by ``_run_file_analysis`` so that entrypoints remain
    thin wrappers.

    Dependencies are injected via __init__; the container is only consulted
    as a fallback when a dependency is not provided.

    Example:
        >>> service = AnalysisService()
        >>> result = service.analyze_file("tests/login.robot")
        >>> print(f"Found {len(result.findings)} issues")
    """

    def __init__(
        self,
        settings: Settings | None = None,
        metrics: IMetrics | None = None,
        file_discovery: IFileDiscovery | None = None,
        registry: IAnalyzerRegistry | None = None,
        cache: IAnalysisCache | None = None,
    ) -> None:
        if settings is None or metrics is None or file_discovery is None or registry is None:
            from ...composition.container import get_container  # lazy: keeps app layer clean
            container = get_container()
            self.settings: Settings = settings or container.resolve("settings")
            self._metrics: IMetrics = metrics or container.resolve("metrics")
            self._file_discovery: IFileDiscovery = file_discovery or container.resolve("file_discovery")
            self._registry: IAnalyzerRegistry = registry or container.resolve("analyzer_registry")
        else:
            self.settings = settings
            self._metrics = metrics
            self._file_discovery = file_discovery
            self._registry = registry
        self._cache: IAnalysisCache | None = cache

    # ------------------------------------------------------------------
    # Analyzer resolution helpers
    # ------------------------------------------------------------------

    def _create_analyzer_instance(
        self, name: str, config: dict[str, object] | None = None
    ) -> BaseAnalyzer:
        """Create a fresh analyzer instance, injecting per-analyzer config."""
        from ..analyzers.base import BaseAnalyzer as _BaseAnalyzer

        cls = self._registry.analyzers.get(name)
        if cls is None:  # pragma: no cover
            return self._registry.create(name)  # type: ignore[no-any-return]
        instance = cls(config=config or {})
        if not isinstance(instance, _BaseAnalyzer):  # pragma: no cover
            raise AnalysisError(
                f"Analyzer '{name}' did not produce a BaseAnalyzer instance"
            )
        return instance

    def _get_analyzer_instances(
        self,
        analyzers: list[str | BaseAnalyzer] | None,
        settings: Settings,
    ) -> list[BaseAnalyzer]:
        """Resolve analyzer names/instances into concrete BaseAnalyzer objects."""
        from ..analyzers.base import BaseAnalyzer as _BaseAnalyzer

        analyzer_config = settings.analyzer_config

        if analyzers is None:
            names = [
                name
                for name in self._registry.list()
                if not getattr(
                    self._registry.analyzers.get(name), "requires_external_repo", False
                )
            ]
            return [
                self._create_analyzer_instance(name, analyzer_config.get(name))
                for name in names
            ]

        instances: list[BaseAnalyzer] = []
        for analyzer in analyzers:
            match analyzer:
                case str():
                    instances.append(
                        self._create_analyzer_instance(
                            analyzer, analyzer_config.get(analyzer)
                        )
                    )
                case _:
                    instances.append(analyzer)  # type: ignore[arg-type]

        return instances

    # ------------------------------------------------------------------
    # Single-file analysis
    # ------------------------------------------------------------------

    def _run_file_analysis(
        self,
        file_path: Path,
        analyzers: list[str | BaseAnalyzer] | None,
        settings: Settings | None,
        min_severity: Severity | None,
        pattern_filter: list[str] | None,
        metrics: IMetrics | None = None,
    ) -> list[Finding]:
        """Core per-file analysis logic.

        Args:
            file_path: Validated path to an existing .robot/.resource file.
            analyzers: Analyzer names or instances; None means run all.
            settings: Configuration; falls back to self.settings when None.
            min_severity: Drop findings below this severity when set.
            pattern_filter: Only run/return findings from analyzers named here.
            metrics: Metrics sink; falls back to self._metrics when None.

        Returns:
            List of findings (filtered by severity and pattern).

        Raises:
            AnalysisError: On file-load or per-analyzer failure.
        """
        resolved_settings = settings or self.settings
        resolved_metrics = metrics or self._metrics

        try:
            file_size = file_path.stat().st_size
            if file_size > resolved_settings.max_file_size_bytes:
                raise AnalysisError(
                    f"File exceeds maximum size: {file_path} "
                    f"({file_size} bytes, limit: {resolved_settings.max_file_size_bytes} bytes)",
                    file_path=file_path,
                )
            test_file = TestFile.from_path(file_path)
        except AnalysisError:
            raise
        except Exception as e:
            raise AnalysisError(f"Failed to load file: {e}", file_path=file_path) from e

        analyzer_instances = self._get_analyzer_instances(analyzers, resolved_settings)
        all_findings: list[Finding] = []

        for analyzer in analyzer_instances:
            analyzer_name = analyzer.name

            if pattern_filter is not None and analyzer_name not in pattern_filter:
                continue

            log_analysis_start(file_path, analyzer_name, logger)
            start_time = time.time()

            try:
                findings = analyzer.safe_analyze(test_file)
                all_findings.extend(findings)

                duration = time.time() - start_time
                log_analysis_complete(file_path, analyzer_name, len(findings), duration, logger)

                resolved_metrics.increment("analysis.completed")
                resolved_metrics.timing(f"analyzer.{analyzer_name}.duration", duration)
                resolved_metrics.gauge(f"analyzer.{analyzer_name}.findings", len(findings))

            except AnalysisError:
                resolved_metrics.increment("analysis.failed")
                raise

            except Exception as e:
                resolved_metrics.increment("analysis.failed")
                resolved_metrics.increment(f"analyzer.{analyzer_name}.failed")
                raise AnalysisError(
                    f"Analysis failed: {e}", file_path=file_path, analyzer=analyzer_name
                ) from e

        resolved_metrics.gauge("findings.total", len(all_findings))

        if min_severity is not None:
            all_findings = [f for f in all_findings if f.severity <= min_severity]

        return all_findings

    def analyze_file(
        self,
        file_path: str | Path,
        analyzers: list[str | BaseAnalyzer] | None = None,
        min_severity: Severity | None = None,
    ) -> AnalysisResult:
        """Analyze a single Robot Framework file.

        Args:
            file_path: Path to the .robot or .resource file.
            analyzers: Optional list of analyzer names to run (default: all).
            min_severity: Optional minimum severity to return.

        Returns:
            AnalysisResult with findings and any errors.  Never raises.
        """
        file_path = Path(file_path)
        try:
            if not file_path.exists():
                raise RobotFileNotFoundError(file_path)
            findings = self._run_file_analysis(
                file_path,
                analyzers=analyzers,
                settings=None,
                min_severity=min_severity,
                pattern_filter=None,
            )
            return AnalysisResult(file_path=file_path, findings=findings)
        except Exception as exc:
            return AnalysisResult(file_path=file_path, findings=[], error=exc)

    # ------------------------------------------------------------------
    # Directory orchestration
    # ------------------------------------------------------------------

    def run_directory_analysis(
        self,
        directory_path: Path,
        analyze_fn: Callable[[Path], tuple[Path, list[Finding]]],
        patterns: list[str] | None,
        exclude_patterns: list[str] | None,
        recursive: bool,
        settings: Settings,
        fail_fast: bool,
        error_handling: ErrorHandling,
        max_workers: int | None,
        metrics: Any,
        use_cache: bool,
    ) -> Any:
        """Execute directory analysis: discovery, cache, thread pool, metrics, errors."""
        resolved_patterns = patterns or settings.file_patterns
        resolved_excludes = exclude_patterns or settings.exclude_patterns
        files = self._file_discovery.find_files(
            root_path=directory_path,
            patterns=resolved_patterns,
            exclude_patterns=resolved_excludes,
            recursive=recursive,
        )

        logger.info(
            "Starting directory analysis",
            extra={
                "directory": str(directory_path),
                "file_count": len(files),
                "recursive": recursive,
            },
        )

        active_cache: IAnalysisCache | None = None
        cache_hits: dict[Path, list[Finding]] = {}
        file_hashes: dict[Path, str] = {}
        files_to_analyze = files

        if use_cache and self._cache is not None:
            active_cache = self._cache
            files_to_analyze, cache_hits, file_hashes = _resolve_cache(files, active_cache)
            hit_count = len(cache_hits)
            miss_count = len(files_to_analyze)
            if hit_count or miss_count:
                logger.debug("Cache: %d hit(s), %d miss(es)", hit_count, miss_count)
                metrics.gauge("cache.hits", hit_count)
                metrics.gauge("cache.misses", miss_count)
                if files:  # pragma: no branch
                    metrics.gauge("cache.hit_rate", hit_count / len(files))

        _default_workers = min(4, (os.cpu_count() or 1))
        effective_workers = max_workers if max_workers is not None else _default_workers
        dir_results: DirectoryResults
        dir_results, file_errors = _execute_directory_analysis(
            files_to_analyze, analyze_fn, effective_workers, fail_fast
        )

        for fp, cached_findings in cache_hits.items():
            dir_results.findings[fp] = cached_findings
        if active_cache is not None:
            for fp, new_findings in dir_results.findings.items():
                if fp not in cache_hits and fp in file_hashes:
                    active_cache.put(fp, file_hashes[fp], new_findings)
            active_cache.flush()

        total_findings = sum(len(f) for f in dir_results.findings.values())
        logger.info(
            "Directory analysis complete",
            extra={
                "directory": str(directory_path),
                "files_analyzed": len(dir_results.findings),
                "files_failed": len(file_errors),
                "total_findings": total_findings,
            },
        )

        metrics.gauge("batch.files_analyzed", len(dir_results.findings))
        metrics.gauge("batch.files_failed", len(file_errors))
        metrics.gauge("batch.total_findings", total_findings)

        _handle_directory_analysis_errors(file_errors, error_handling, fail_fast, dir_results)

        return dir_results

    def analyze_directory(
        self,
        directory: str | Path,
        patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        recursive: bool = True,
        analyzers: list[str | BaseAnalyzer] | None = None,
        min_severity: Severity | None = None,
        error_handling: ErrorHandling = "warn",
    ) -> DirectoryAnalysisResult:
        """Analyze all Robot Framework files in a directory.

        Args:
            directory: Path to the directory.
            patterns: Optional file patterns to include (default: *.robot, *.resource).
            exclude_patterns: Optional patterns to exclude.
            recursive: Whether to search subdirectories (default: True).
            analyzers: Optional list of analyzer names to run (default: all).
            min_severity: Optional minimum severity to return.
            error_handling: How to handle per-file errors (default: "warn").

        Returns:
            DirectoryAnalysisResult with all findings and any errors.
        """
        directory_path = _validate_directory_path(directory)

        def _analyze_one(fp: Path) -> tuple[Path, list[Finding]]:
            findings = self._run_file_analysis(
                fp,
                analyzers=analyzers,
                settings=None,
                min_severity=min_severity,
                pattern_filter=None,
            )
            return fp, findings

        dir_results = self.run_directory_analysis(
            directory_path=directory_path,
            analyze_fn=_analyze_one,
            patterns=patterns,
            exclude_patterns=exclude_patterns,
            recursive=recursive,
            settings=self.settings,
            fail_fast=False,
            error_handling=error_handling,
            max_workers=None,
            metrics=self._metrics,
            use_cache=True,
        )

        return DirectoryAnalysisResult(
            directory=directory_path,
            results=dir_results.findings,
            errors=dir_results.errors,
        )

    # ------------------------------------------------------------------
    # Registry introspection
    # ------------------------------------------------------------------

    def list_analyzers(self) -> dict[str, dict[str, Any]]:
        """List all available analyzers.

        Returns:
            Dictionary mapping analyzer names to their metadata.
        """
        result: dict[str, dict[str, Any]] = {}
        for name in self._registry.list():
            try:
                result[name] = self._registry.get_info(name)
            except Exception:
                result[name] = {"name": name, "error": "Failed to load info"}
        return result

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def clear_cache(self) -> None:
        """Remove all cached analysis results from the backing store.

        No-op when the service was created without a cache.
        """
        if self._cache is not None:
            self._cache.clear()
