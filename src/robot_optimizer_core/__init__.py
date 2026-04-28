# src/robot_optimizer_core/__init__.py
"""Robot Framework Optimizer Core - Analysis engine for Robot Framework test suites.

This package provides the core functionality for analyzing Robot Framework
test suites, including:

- Dead code detection
- Sleep pattern analysis
- Test flakiness detection
- Extensible analyzer framework
- Plugin system for custom analyzers

Example:
    Basic usage of the Core package::

        from robot_optimizer_core import analyze_file, DeadCodeAnalyzer

        # Analyze a single file
        test_file = Path("tests/login.robot")
        findings = analyze_file(test_file, analyzers=[DeadCodeAnalyzer()])

        for finding in findings:
            print(f"{finding.severity.name}: {finding.message}")

Attributes:
    __version__ (str): The version of the Core package.
    __all__ (list[str]): Public API exports.

"""

from __future__ import annotations

# Version
from .__version__ import __version__, __version_info__

# Analyzers
from .analyzers import (
    AnalyzerRegistry,
    BaseAnalyzer,
    DeadCodeAnalyzer,
    FlakinessAnalyzer,
    SleepDetector,
    get_analyzer,
    get_analyzer_registry,
    list_analyzers,
    register_analyzer,
)

# High-level API functions
from .api import (
    SuiteAnalysisResult,
    SuiteInfo,
    SuiteStatistics,
    analyze_directory,
    analyze_file,
    analyze_suite,
)

# Configuration
from .config import Settings, get_settings, reset_settings

# Deprecation utilities
from .deprecation import deprecated, deprecation_warning

# Dependency injection
from .di import ThreadSafeContainer, get_container

# Core services
from .discovery import FileDiscoveryService

# Core domain models
from .domain.base import AggregateRoot, DomainEvent, Entity, ValueObject
from .domain.entities import TestFile
from .domain.value_objects import (
    Finding,
    FlakinessStats,
    Location,
    Pattern,
    PatternType,
    Severity,
    SleepPattern,
    TestResult,
)

# Exceptions
from .exceptions import (
    AnalysisError,
    ConfigurationError,
    PluginError,
    RobotOptimizerError,
)

# Listener
from .listener import FlakinessListener

# Logging
from .logging import configure_logging, get_logger

# Metrics
from .metrics import MetricsCollector, configure_metrics, get_metrics
from .parsers import RobotASTParser

# Plugin system
from .plugin import Plugin, PluginMetadata

# Alias for backward compatibility
Container = ThreadSafeContainer

__all__ = [
    # Version
    "__version__",
    "__version_info__",
    # Domain models
    "ValueObject",
    "Entity",
    "AggregateRoot",
    "DomainEvent",
    "TestFile",
    # Value objects
    "Finding",
    "Location",
    "Pattern",
    "PatternType",
    "Severity",
    "SleepPattern",
    "TestResult",
    "FlakinessStats",
    # Analyzers
    "BaseAnalyzer",
    "AnalyzerRegistry",
    "DeadCodeAnalyzer",
    "SleepDetector",
    "FlakinessAnalyzer",
    "register_analyzer",
    "get_analyzer",
    "get_analyzer_registry",
    "list_analyzers",
    # Services
    "FileDiscoveryService",
    "RobotASTParser",
    # Configuration
    "Settings",
    "get_settings",
    "reset_settings",
    # Exceptions
    "RobotOptimizerError",
    "AnalysisError",
    "ConfigurationError",
    "PluginError",
    # Logging
    "get_logger",
    "configure_logging",
    # Metrics
    "MetricsCollector",
    "get_metrics",
    "configure_metrics",
    # DI
    "Container",
    "get_container",
    # Plugins
    "Plugin",
    "PluginMetadata",
    # Listener
    "FlakinessListener",
    # Utilities
    "deprecated",
    "deprecation_warning",
    # High-level API
    "analyze_file",
    "analyze_directory",
    "analyze_suite",
    "SuiteAnalysisResult",
    "SuiteInfo",
    "SuiteStatistics",
]


def __dir__() -> list[str]:
    """Return list of public attributes.

    Returns:
        List of attribute names exposed by this module.
    """
    return __all__
