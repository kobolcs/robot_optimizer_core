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
        from pathlib import Path
        
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

from typing import TYPE_CHECKING

# Version
from .__version__ import __version__, __version_info__

# Core domain models
from .domain.base import ValueObject, Entity, AggregateRoot, DomainEvent
from .domain.entities import TestFile
from .domain.value_objects import (
    Finding,
    Location,
    Pattern,
    PatternType,
    Severity,
    SleepPattern,
    TestResult,
    FlakinessStats,
)

# Analyzers
from .analyzers import (
    BaseAnalyzer,
    AnalyzerRegistry,
    DeadCodeAnalyzer,
    SleepDetector,
    FlakinessAnalyzer,
    register_analyzer,
    get_analyzer,
    list_analyzers,
)

# Core services
from .discovery import FileDiscoveryService
from .parsers import RobotASTParser

# Configuration
from .config import Settings, get_settings

# Exceptions
from .exceptions import (
    RobotOptimizerError,
    AnalysisError,
    ConfigurationError,
    PluginError,
)

# Logging
from .logging import get_logger, configure_logging

# Metrics
from .metrics import MetricsCollector, get_metrics

# Dependency injection
from .di import Container, get_container

# Plugin system
from .plugin import Plugin, PluginMetadata

# Deprecation utilities
from .deprecation import deprecated, deprecation_warning

# High-level API functions
from .api import analyze_file, analyze_directory, analyze_suite

if TYPE_CHECKING:
    from pathlib import Path

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
    "list_analyzers",
    
    # Services
    "FileDiscoveryService",
    "RobotASTParser",
    
    # Configuration
    "Settings",
    "get_settings",
    
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
    
    # DI
    "Container",
    "get_container",
    
    # Plugins
    "Plugin",
    "PluginMetadata",
    
    # Utilities
    "deprecated",
    "deprecation_warning",
    
    # High-level API
    "analyze_file",
    "analyze_directory", 
    "analyze_suite",
]


def __dir__() -> list[str]:
    """Return list of public attributes.
    
    Returns:
        List of attribute names exposed by this module.
    """
    return __all__