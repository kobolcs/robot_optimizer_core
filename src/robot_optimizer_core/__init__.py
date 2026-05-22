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
from .application.analyzers import (
    AnalyzerRegistry as AnalyzerRegistry,
)
from .application.analyzers import (
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
    list_analyzers,
    register_analyzer,
)
from .application.analyzers import (
    get_analyzer_registry as get_analyzer_registry,
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
from .infrastructure.config import Settings, get_settings, reset_settings

# Application context — primary entry point for wiring services
from .composition.context import (
    ApplicationConfig as ApplicationConfig,
)
from .composition.context import (
    ApplicationContext as ApplicationContext,
)
from .composition.context import (
    create_application as create_application,
)
from .composition.context import (
    create_test_application as create_test_application,
)

# Core services — not part of the public API; importable for advanced use
from .infrastructure.discovery import FileDiscoveryService as FileDiscoveryService

# Core domain models — primary value objects (Finding, Location, Pattern, etc.) in __all__;
# additional types (FlakinessStats, SleepPattern, TestResult) and base types re-exported
# for advanced consumers but intentionally excluded from __all__ to reduce surface area
from .domain.base import (
    AggregateRoot as AggregateRoot,
)
from .domain.base import (
    DomainEvent as DomainEvent,
)
from .domain.base import (
    Entity as Entity,
)
from .domain.base import (
    ValueObject as ValueObject,
)
from .domain.entities import TestFile
from .domain.value_objects import (
    Finding,
    Location,
    Pattern,
    PatternType,
    Severity,
)
from .domain.value_objects import (
    FlakinessStats as FlakinessStats,
)
from .domain.value_objects import (
    SleepPattern as SleepPattern,
)
from .domain.value_objects import (
    TestResult as TestResult,
)

# Exceptions
from .exceptions import (
    AnalysisError,
    ConfigurationError,
    PluginError,
    RobotOptimizerError,
)

# Listener — not part of the public API; importable for advanced use
from .listener import FlakinessListener as FlakinessListener

# Logging — not part of the public API; importable for advanced use
from .infrastructure.logging.adapter import configure_logging as configure_logging
from .infrastructure.logging.adapter import get_logger as get_logger

# Metrics — not part of the public API; importable for advanced use
from .infrastructure.metrics.collector import (
    MetricsCollector as MetricsCollector,
)
from .infrastructure.metrics.collector import (
    configure_metrics as configure_metrics,
)
from .infrastructure.metrics.collector import (
    get_metrics as get_metrics,
)
from .infrastructure.parsers import RobotASTParser as RobotASTParser

# Plugin system
from .infrastructure.plugins.manager import Plugin, PluginMetadata
from .premium import PremiumFeatureError, is_premium_installed

# File I/O providers — for advanced use (testing, custom sources)
from .infrastructure.file_provider import (
    DiskFileProvider as DiskFileProvider,
)
from .infrastructure.file_provider import (
    FileProvider as FileProvider,
)
from .infrastructure.file_provider import (
    InMemoryFileProvider as InMemoryFileProvider,
)

# Service layer (recommended for most uses)
from .application.services.analysis_service import (
    AnalysisResult,
    AnalysisService,
    DirectoryAnalysisResult,
)

__all__ = [
    "AnalysisError",
    # Service layer (recommended for most uses)
    "AnalysisResult",
    "AnalysisService",
    "DirectoryAnalysisResult",
    # Application context — primary entry point for wiring services
    "ApplicationConfig",
    "ApplicationContext",
    # Analyzer classes
    "BaseAnalyzer",
    "ConfigurationError",
    "DeadCodeAnalyzer",
    # Domain value objects used in findings
    "DiskFileProvider",
    "FileProvider",
    "Finding",
    "FlakinessAnalyzer",
    "HardcodedValueAnalyzer",
    "InMemoryFileProvider",
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
    "create_application",
    "create_test_application",
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
