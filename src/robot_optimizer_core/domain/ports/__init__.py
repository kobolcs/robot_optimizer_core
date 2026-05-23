# src/robot_optimizer_core/domain/ports/__init__.py
"""Domain port interfaces (dependency-inversion boundaries)."""

from .analyzer import IAnalyzer, ISuiteAnalyzer
from .analyzer_registry import IAnalyzerRegistry
from .cache import IAnalysisCache
from .file_discovery import IFileDiscovery
from .file_provider import FileProvider
from .metrics import IMetrics
from .parser import IParser
from .plugin import IPluginRegistry, Plugin, PluginMetadata
from .repository import ITestFileRepository, ITestResultRepository

__all__ = [
    "FileProvider",
    "IAnalysisCache",
    "IAnalyzer",
    "IAnalyzerRegistry",
    "IFileDiscovery",
    "IMetrics",
    "IParser",
    "IPluginRegistry",
    "ISuiteAnalyzer",
    "ITestFileRepository",
    "ITestResultRepository",
    "Plugin",
    "PluginMetadata",
]
