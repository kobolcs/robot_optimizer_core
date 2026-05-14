# src/robot_optimizer_core/service.py
"""High-level analysis service that decouples CLI from framework details.

This module provides the AnalysisService facade, which offers a simplified
interface to the analysis framework while hiding complexity of the DI container,
metrics, logging, and analyzer registry.

The service is the primary interface for CLI and other consumers; it replaces
direct calls to api.analyze_file() and api.analyze_directory().
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from .api import analyze_directory as _api_analyze_directory
from .api import analyze_file as _api_analyze_file
from .config import Settings
from .di import get_container
from .domain.value_objects import Finding, Severity

if TYPE_CHECKING:
    from .analyzers import BaseAnalyzer

__all__ = ["AnalysisResult", "AnalysisService", "DirectoryAnalysisResult"]


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
    def error_count(self) -> int:
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
            "error_count": self.error_count,
            "total_findings": self.total_findings,
            "errors": [(str(path), str(exc)) for path, exc in self.errors],
        }


class AnalysisService:
    """High-level analysis service (facade over the analysis framework).

    This service provides a clean, simplified API for analyzing Robot Framework
    files and directories. It handles dependency injection, configuration,
    and error handling internally, keeping complexity out of consumers like
    the CLI.

    Example:
        >>> service = AnalysisService()
        >>> result = service.analyze_file("tests/login.robot")
        >>> print(f"Found {len(result.findings)} issues")
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the analysis service.

        Args:
            settings: Optional custom settings. If not provided, uses global settings
                from the DI container.
        """
        self.container = get_container()
        self.settings = settings or self.container.resolve("settings")

    def analyze_file(
        self,
        file_path: str | Path,
        analyzers: list[str | BaseAnalyzer] | None = None,
        severity_filter: Severity | None = None,
    ) -> AnalysisResult:
        """Analyze a single Robot Framework file.

        Args:
            file_path: Path to the .robot or .resource file
            analyzers: Optional list of analyzer names to run (default: all)
            severity_filter: Optional minimum severity to return

        Returns:
            AnalysisResult with findings and any errors
        """
        file_path = Path(file_path)
        try:
            findings = _api_analyze_file(
                file_path,
                analyzers=analyzers,
                settings=self.settings,
                severity_filter=severity_filter,
            )
            return AnalysisResult(
                file_path=file_path,
                findings=findings,
            )
        except Exception as exc:
            return AnalysisResult(
                file_path=file_path,
                findings=[],
                error=exc,
            )

    def analyze_directory(
        self,
        directory: str | Path,
        patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        recursive: bool = True,
        analyzers: list[str | BaseAnalyzer] | None = None,
        severity_filter: Severity | None = None,
    ) -> DirectoryAnalysisResult:
        """Analyze all Robot Framework files in a directory.

        Args:
            directory: Path to the directory
            patterns: Optional file patterns to include (default: *.robot, *.resource)
            exclude_patterns: Optional patterns to exclude
            recursive: Whether to search subdirectories (default: True)
            analyzers: Optional list of analyzer names to run (default: all)
            severity_filter: Optional minimum severity to return

        Returns:
            DirectoryAnalysisResult with all findings and any errors
        """
        directory = Path(directory)
        results_dict = _api_analyze_directory(
            directory,
            patterns=patterns,
            exclude_patterns=exclude_patterns,
            recursive=recursive,
            analyzers=analyzers,
            settings=self.settings,
            error_handling="warn",  # Return partial results on error
            severity_filter=severity_filter,
        )

        # Extract errors from DirectoryResults
        errors = list(getattr(results_dict, "errors", []))

        return DirectoryAnalysisResult(
            directory=directory,
            results=dict(results_dict),  # Convert DirectoryResults to plain dict
            errors=errors,
        )

    def list_analyzers(self) -> dict[str, dict[str, Any]]:
        """List all available analyzers.

        Returns:
            Dictionary mapping analyzer names to their metadata
        """
        registry = self.container.resolve("analyzer_registry")
        result = {}
        for name in registry.list():
            try:
                result[name] = registry.get_info(name)
            except Exception:
                result[name] = {"name": name, "error": "Failed to load info"}
        return result
