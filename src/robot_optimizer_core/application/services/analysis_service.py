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

import functools
import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from ...composition.container import get_container
from ...domain.value_objects import Finding, Severity
from ...infrastructure.cache.analysis_cache import AnalysisCache
from ...infrastructure.config import Settings
from ...infrastructure.logging.adapter import get_logger

if TYPE_CHECKING:
    from ...domain.ports.metrics import IMetrics
    from ..analyzers import BaseAnalyzer

__all__ = ["AnalysisResult", "AnalysisService", "DirectoryAnalysisResult"]

ErrorHandling = Literal["raise", "skip", "warn"]

logger = get_logger(__name__)


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


class AnalysisService:
    """High-level analysis service that owns all orchestration logic.

    This service handles file discovery, caching, thread pool execution,
    error dispatch, and result filtering for directory analysis.  Per-file
    analysis delegates back to the public API so that existing monkeypatch
    tests continue to work.

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
        file_discovery: Any | None = None,
        registry: Any | None = None,
    ) -> None:
        """Initialise the analysis service.

        Args:
            settings: Configuration settings; falls back to container if None.
            metrics: Metrics implementation; falls back to container if None.
            file_discovery: File discovery service; falls back to container if None.
            registry: Analyzer registry; falls back to container if None.
        """
        container = get_container()
        self.settings: Settings = settings or container.resolve("settings")
        self._metrics: IMetrics = metrics or container.resolve("metrics")
        self._file_discovery: Any = file_discovery or container.resolve("file_discovery")
        self._registry: Any = registry or container.resolve("analyzer_registry")

    # ------------------------------------------------------------------
    # Single-file analysis
    # ------------------------------------------------------------------

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
        from ...entrypoints.public_api import analyze_file as _api_analyze_file

        file_path = Path(file_path)
        try:
            findings = _api_analyze_file(
                file_path,
                analyzers=analyzers,
                settings=self.settings,
                min_severity=min_severity,
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
        """Execute directory analysis: discovery, cache, thread pool, metrics, errors.

        Args:
            directory_path: Validated directory path.
            analyze_fn: Per-file callable ``(path) -> (path, findings)``.
            patterns: File glob patterns to include.
            exclude_patterns: Patterns to exclude.
            recursive: Whether to recurse into subdirectories.
            settings: Resolved configuration settings.
            fail_fast: Stop after the first per-file failure (sequential only).
            error_handling: How to surface per-file errors.
            max_workers: Thread-pool size; None for auto.
            metrics: Metrics implementation for counters and gauges.
            use_cache: When True, skip unchanged files using the on-disk cache.

        Returns:
            ``DirectoryResults`` dataclass from the public API.
        """
        from ...entrypoints.public_api import (
            DirectoryResults,
            _execute_directory_analysis,
            _handle_directory_analysis_errors,
            _resolve_cache,
        )

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

        cache: AnalysisCache | None = None
        cache_hits: dict[Path, list[Finding]] = {}
        file_hashes: dict[Path, str] = {}
        files_to_analyze = files

        if use_cache:
            cache = AnalysisCache()
            files_to_analyze, cache_hits, file_hashes = _resolve_cache(files, cache)
            hit_count = len(cache_hits)
            miss_count = len(files_to_analyze)
            if hit_count or miss_count:
                logger.debug("Cache: %d hit(s), %d miss(es)", hit_count, miss_count)
                metrics.gauge("cache.hits", hit_count)
                metrics.gauge("cache.misses", miss_count)
                if files:
                    metrics.gauge("cache.hit_rate", hit_count / len(files))

        _default_workers = min(4, (os.cpu_count() or 1))
        effective_workers = max_workers if max_workers is not None else _default_workers
        dir_results: DirectoryResults
        dir_results, file_errors = _execute_directory_analysis(
            files_to_analyze, analyze_fn, effective_workers, fail_fast
        )

        for fp, cached_findings in cache_hits.items():
            dir_results.findings[fp] = cached_findings
        if cache is not None:
            for fp, new_findings in dir_results.findings.items():
                if fp not in cache_hits and fp in file_hashes:
                    cache.put(fp, file_hashes[fp], new_findings)
            cache.flush()

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
        from ...entrypoints.public_api import (
            _analyze_one_file,
            _validate_directory_path,
        )

        directory_path = _validate_directory_path(directory)

        analyze_fn = functools.partial(
            _analyze_one_file,
            analyzers=analyzers,
            settings=self.settings,
            min_severity=min_severity,
            pattern_filter=None,
        )

        dir_results = self.run_directory_analysis(
            directory_path=directory_path,
            analyze_fn=analyze_fn,
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
