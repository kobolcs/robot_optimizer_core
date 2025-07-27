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
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, List, Optional, Union

from .analyzers import get_analyzer, list_analyzers
from .config import get_settings
from .di import get_container
from .discovery import FileDiscoveryService
from .domain.entities import TestFile
from .domain.value_objects import Finding
from .exceptions import AnalysisError, FileNotFoundError
from .logging import get_logger, log_analysis_complete, log_analysis_start
from .metrics import get_metrics
from .parsers import RobotASTParser

logger = get_logger(__name__)


def analyze_file(
    file_path: Union[str, Path],
    analyzers: Optional[List[Union[str, "BaseAnalyzer"]]] = None,
    settings: Optional["Settings"] = None
) -> List[Finding]:
    """Analyze a single Robot Framework file.
    
    This is the main entry point for analyzing individual files.
    It handles file loading, parsing, and running the specified analyzers.
    
    Args:
        file_path: Path to the Robot Framework file.
        analyzers: List of analyzer names or instances (default: all).
        settings: Configuration settings (default: global settings).
        
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
        raise FileNotFoundError(path)
    
    # Get settings
    if settings is None:
        settings = get_settings()
    
    # Get metrics collector
    metrics = get_metrics()
    
    # Load file
    try:
        test_file = TestFile.from_path(path)
    except Exception as e:
        raise AnalysisError(
            f"Failed to load file: {e}",
            file_path=path
        ) from e
    
    # Get analyzers
    analyzer_instances = _get_analyzer_instances(analyzers, settings)
    
    # Run analysis
    all_findings: List[Finding] = []
    
    for analyzer in analyzer_instances:
        analyzer_name = analyzer.name
        
        # Log and track analysis start
        log_analysis_start(path, analyzer_name, logger)
        start_time = time.time()
        
        try:
            # Run analyzer
            findings = analyzer.analyze(test_file)
            all_findings.extend(findings)
            
            # Track success
            duration = time.time() - start_time
            log_analysis_complete(
                path, analyzer_name, len(findings), duration, logger
            )
            
            metrics.increment("analysis.completed")
            metrics.increment(f"analysis.{analyzer_name}.completed")
            metrics.timing(f"analysis.{analyzer_name}.duration", duration)
            metrics.gauge(f"analysis.{analyzer_name}.findings", len(findings))
            
        except Exception as e:
            # Track failure
            metrics.increment("analysis.failed")
            metrics.increment(f"analysis.{analyzer_name}.failed")
            
            raise AnalysisError(
                f"Analysis failed: {e}",
                file_path=path,
                analyzer=analyzer_name
            ) from e
    
    # Track total findings
    metrics.gauge("findings.total", len(all_findings))
    
    return all_findings


def analyze_directory(
    directory_path: Union[str, Path],
    patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    recursive: bool = True,
    analyzers: Optional[List[Union[str, "BaseAnalyzer"]]] = None,
    settings: Optional["Settings"] = None,
    fail_fast: bool = False
) -> Dict[Path, List[Finding]]:
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
        fail_fast: Stop on first error.
        
    Returns:
        Dictionary mapping file paths to findings.
        
    Raises:
        FileNotFoundError: If directory doesn't exist.
        AnalysisError: If analysis fails (when fail_fast=True).
        
    Example:
        >>> findings_map = analyze_directory("tests/", recursive=True)
        >>> for file_path, findings in findings_map.items():
        ...     print(f"{file_path}: {len(findings)} findings")
    """
    # Convert to Path
    path = Path(directory_path)
    
    # Validate directory exists
    if not path.exists():
        raise FileNotFoundError(path)
    
    if not path.is_dir():
        raise AnalysisError(
            "Path is not a directory",
            file_path=path
        )
    
    # Get settings
    if settings is None:
        settings = get_settings()
    
    # Get file discovery service
    container = get_container()
    discovery = container.resolve("file_discovery")
    
    # Discover files
    if patterns is None:
        patterns = settings.file_patterns
    
    if exclude_patterns is None:
        exclude_patterns = settings.exclude_patterns
    
    files = discovery.find_files(
        root_path=path,
        patterns=patterns,
        exclude_patterns=exclude_patterns,
        recursive=recursive
    )
    
    logger.info(
        "Starting directory analysis",
        extra={
            "directory": str(path),
            "file_count": len(files),
            "recursive": recursive
        }
    )
    
    # Analyze each file
    results: Dict[Path, List[Finding]] = {}
    errors: List[tuple[Path, Exception]] = []
    
    for file_path in files:
        try:
            findings = analyze_file(file_path, analyzers, settings)
            results[file_path] = findings
            
        except Exception as e:
            if fail_fast:
                raise
            
            errors.append((file_path, e))
            logger.error(
                f"Failed to analyze file: {file_path}",
                extra={"file": str(file_path), "error": str(e)},
                exc_info=True
            )
    
    # Log summary
    total_findings = sum(len(findings) for findings in results.values())
    logger.info(
        "Directory analysis complete",
        extra={
            "directory": str(path),
            "files_analyzed": len(results),
            "files_failed": len(errors),
            "total_findings": total_findings
        }
    )
    
    # Track metrics
    metrics = get_metrics()
    metrics.gauge("batch.files_analyzed", len(results))
    metrics.gauge("batch.files_failed", len(errors))
    metrics.gauge("batch.total_findings", total_findings)
    
    return results


def analyze_suite(
    suite_path: Union[str, Path],
    analyzers: Optional[List[Union[str, "BaseAnalyzer"]]] = None,
    settings: Optional["Settings"] = None
) -> Dict[str, Any]:
    """Analyze a Robot Framework test suite with AST parsing.
    
    This function provides more detailed analysis using the AST parser,
    including cross-file references and suite-level insights.
    
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
    
    # Single file or directory?
    if path.is_file():
        files = [path]
    else:
        container = get_container()
        discovery = container.resolve("file_discovery")
        files = discovery.find_files(path)
    
    # Parse suite structure
    parser = container.resolve("parser")
    suite_info = {
        "files": len(files),
        "keywords": [],
        "test_cases": [],
        "imports": []
    }
    
    # Analyze files and collect suite info
    all_findings: List[Finding] = []
    file_findings: Dict[Path, List[Finding]] = {}
    
    for file_path in files:
        # Load and parse
        test_file = TestFile.from_path(file_path)
        
        try:
            robot_suite = parser.parse_suite(test_file)
            
            # Collect suite info
            suite_info["keywords"].extend(robot_suite.keywords)
            suite_info["test_cases"].extend(robot_suite.test_cases)
            suite_info["imports"].extend(robot_suite.imports)
            
        except Exception as e:
            logger.warning(
                f"Failed to parse suite structure: {file_path}",
                extra={"error": str(e)}
            )
        
        # Run analyzers
        findings = analyze_file(file_path, analyzers, settings)
        all_findings.extend(findings)
        file_findings[file_path] = findings
    
    # Calculate statistics
    statistics = {
        "total_findings": len(all_findings),
        "findings_by_severity": {},
        "findings_by_type": {},
        "keyword_count": len(suite_info["keywords"]),
        "test_count": len(suite_info["test_cases"]),
        "import_count": len(suite_info["imports"])
    }
    
    # Group findings
    for finding in all_findings:
        # By severity
        severity = finding.severity.name
        statistics["findings_by_severity"][severity] = (
            statistics["findings_by_severity"].get(severity, 0) + 1
        )
        
        # By type
        pattern_type = finding.pattern.type.name
        statistics["findings_by_type"][pattern_type] = (
            statistics["findings_by_type"].get(pattern_type, 0) + 1
        )
    
    return {
        "findings": all_findings,
        "file_findings": file_findings,
        "suite_info": suite_info,
        "statistics": statistics
    }


def _get_analyzer_instances(
    analyzers: Optional[List[Union[str, "BaseAnalyzer"]]],
    settings: "Settings"
) -> List["BaseAnalyzer"]:
    """Get analyzer instances from names or objects.
    
    Args:
        analyzers: List of analyzer names or instances.
        settings: Configuration settings.
        
    Returns:
        List of analyzer instances.
    """
    if analyzers is None:
        # Use all registered analyzers
        analyzer_names = list_analyzers()
        return [get_analyzer(name) for name in analyzer_names]
    
    instances = []
    for analyzer in analyzers:
        if isinstance(analyzer, str):
            # Get by name
            instances.append(get_analyzer(analyzer))
        else:
            # Already an instance
            instances.append(analyzer)
    
    return instances