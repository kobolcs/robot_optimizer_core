# src/robot_optimizer_core/domain/ports/__init__.py
"""Domain port interfaces (dependency-inversion boundaries)."""

from .analyzer import IAnalyzer, ISuiteAnalyzer
from .file_provider import FileProvider
from .metrics import IMetrics
from .parser import IParser
from .plugin import Plugin, PluginMetadata
from .repository import ITestFileRepository, ITestResultRepository

__all__ = [
    "FileProvider",
    "IAnalyzer",
    "IMetrics",
    "IParser",
    "ISuiteAnalyzer",
    "ITestFileRepository",
    "ITestResultRepository",
    "Plugin",
    "PluginMetadata",
]
