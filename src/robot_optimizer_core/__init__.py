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
    AnalyzerRegistry,  # noqa: F401
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
    get_analyzer_registry,  # noqa: F401
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
from .di import ThreadSafeContainer, get_container  # noqa: F401

# Core services — not part of the public API; importable for advanced use
from .discovery import FileDiscoveryService  # noqa: F401

# Core domain models — public value objects in __all__; base types re-exported for
# advanced consumers but intentionally excluded from __all__ to reduce surface area
from .domain.base import AggregateRoot, DomainEvent, Entity, ValueObject  # noqa: F401
from .domain.entities import TestFile
from .domain.value_objects import (
    Finding,
    FlakinessStats,  # noqa: F401
    Location,
    Pattern,
    PatternType,
    Severity,
    SleepPattern,  # noqa: F401
    TestResult,  # noqa: F401
)

# Exceptions
from .exceptions import (
    AnalysisError,
    ConfigurationError,
    PluginError,
    RobotOptimizerError,
)

# Listener — not part of the public API; importable for advanced use
from .listener import FlakinessListener  # noqa: F401

# Logging — not part of the public API; importable for advanced use
from .logging import configure_logging, get_logger  # noqa: F401

# Metrics — not part of the public API; importable for advanced use
from .metrics import MetricsCollector, configure_metrics, get_metrics  # noqa: F401
from .parsers import RobotASTParser  # noqa: F401

# Plugin system
from .plugin import Plugin, PluginMetadata
from .premium import PremiumFeatureError, is_premium_installed

# Alias preserved for consumers that relied on it before the narrowing of __all__
Container = ThreadSafeContainer  # noqa: F401

__all__ = [
    # Version
    "__version__",
    "__version_info__",
    # High-level API — primary entry points
    "analyze_file",
    "analyze_directory",
    "analyze_suite",
    "SuiteAnalysisResult",
    "SuiteInfo",
    "SuiteStatistics",
    # Analyzer classes
    "BaseAnalyzer",
    "DeadCodeAnalyzer",
    "SleepDetector",
    "FlakinessAnalyzer",
    "HardcodedValueAnalyzer",
    "NamingConventionAnalyzer",
    "SetupTeardownAnalyzer",
    "TagConsistencyAnalyzer",
    "TestDocumentationAnalyzer",
    "register_analyzer",
    "get_analyzer",
    "list_analyzers",
    # Domain value objects used in findings
    "Finding",
    "Location",
    "Pattern",
    "PatternType",
    "Severity",
    "TestFile",
    # Configuration
    "Settings",
    "get_settings",
    "reset_settings",
    # Exceptions
    "RobotOptimizerError",
    "AnalysisError",
    "ConfigurationError",
    "PluginError",
    "PremiumFeatureError",
    # Plugin system
    "Plugin",
    "PluginMetadata",
    # Premium detection (useful for plugin authors)
    "is_premium_installed",
]


def __dir__() -> list[str]:
    """Return list of public attributes."""
    return __all__
