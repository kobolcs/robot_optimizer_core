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
    HardcodedValueAnalyzer,
    NamingConventionAnalyzer,
    SetupTeardownAnalyzer,
    SleepDetector,
    TagConsistencyAnalyzer,
    TestDocumentationAnalyzer,
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

# Dependency injection — not part of the public API; importable for advanced use
from .di import ThreadSafeContainer, get_container

# Core services — not part of the public API; importable for advanced use
from .discovery import FileDiscoveryService

# Core domain models — public value objects in __all__; base types re-exported for
# advanced consumers but intentionally excluded from __all__ to reduce surface area
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

# Listener — not part of the public API; importable for advanced use
from .listener import FlakinessListener

# Logging — not part of the public API; importable for advanced use
from .logging import configure_logging, get_logger

# Metrics — not part of the public API; importable for advanced use
from .metrics import MetricsCollector, configure_metrics, get_metrics
from .parsers import RobotASTParser

# Plugin system
from .plugin import Plugin, PluginMetadata
from .premium import PremiumFeatureError, is_premium_installed

# Alias preserved for consumers that relied on it before the narrowing of __all__
Container = ThreadSafeContainer

__all__ = [
    "AnalysisError",
    # Analyzer classes
    "BaseAnalyzer",
    "ConfigurationError",
    "DeadCodeAnalyzer",
    # Domain value objects used in findings
    "Finding",
    "FlakinessAnalyzer",
    "HardcodedValueAnalyzer",
    "Location",
    "NamingConventionAnalyzer",
    "Pattern",
    "PatternType",
    # Plugin system
    "Plugin",
    "PluginError",
    "PluginMetadata",
    "PremiumFeatureError",
    # Exceptions
    "RobotOptimizerError",
    # Configuration
    "Settings",
    "SetupTeardownAnalyzer",
    "Severity",
    "SleepDetector",
    "SuiteAnalysisResult",
    "SuiteInfo",
    "SuiteStatistics",
    "TagConsistencyAnalyzer",
    "TestDocumentationAnalyzer",
    "TestFile",
    # Version
    "__version__",
    "__version_info__",
    "analyze_directory",
    # High-level API — primary entry points
    "analyze_file",
    "analyze_suite",
    "get_analyzer",
    "get_settings",
    # Premium detection (useful for plugin authors)
    "is_premium_installed",
    "list_analyzers",
    "register_analyzer",
    "reset_settings",
]


def __dir__() -> list[str]:
    """Return list of public attributes."""
    return __all__
