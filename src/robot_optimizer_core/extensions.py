# src/robot_optimizer_core/extensions.py
"""Stable public surface for third-party analyzer and plugin authors.

Import everything you need to write a plugin or custom analyzer from this
module.  Internal module paths (``application.analyzers.base``,
``infrastructure.plugins.manager``, etc.) are **not** part of the public API
and may change between releases without notice.

Example — writing a custom analyzer::

    from robot_optimizer_core.extensions import BaseAnalyzer, Finding, TestFile

    class MyAnalyzer(BaseAnalyzer):
        @property
        def name(self) -> str:
            return "my_analyzer"

        @property
        def description(self) -> str:
            return "Detects something interesting."

        def analyze(self, test_file: TestFile) -> list[Finding]:
            return []

Example — writing a plugin that contributes an analyzer::

    from robot_optimizer_core.extensions import (
        BaseAnalyzer,
        Finding,
        Plugin,
        PluginMetadata,
        TestFile,
    )

    class MyPlugin(Plugin):
        @property
        def metadata(self) -> PluginMetadata:
            return PluginMetadata(
                name="my_plugin",
                version="1.0.0",
                description="My plugin",
                author="Me",
            )

        def activate(self) -> None:
            self.is_active = True

        def deactivate(self) -> None:
            self.is_active = False

        def contribute_analyzers(self) -> list[type]:
            return [MyAnalyzer]
"""

from __future__ import annotations

# --- domain value objects (stable, immutable) ---
from .domain.value_objects.finding import Finding
from .domain.value_objects.location import Location
from .domain.value_objects.remediation import RemediationHint
from .domain.value_objects.results import AnalysisMeta, FileAnalysisResult
from .domain.value_objects.severity import Severity

# --- domain entities ---
from .domain.entities.test_file import TestFile

# --- domain ports ---
from .domain.ports.analyzer import IAnalyzer, ISuiteAnalyzer
from .domain.ports.metrics import IMetrics
from .domain.ports.plugin import IPluginRegistry, Plugin, PluginMetadata

# --- application base classes ---
from .application.analyzers.base import BaseAnalyzer, ConfigValue, SuiteAwareAnalyzer

# --- error taxonomy ---
from .exceptions import ErrorCategory, StructuredError

__all__ = [
    # Value objects
    "AnalysisMeta",
    "FileAnalysisResult",
    "Finding",
    "Location",
    "RemediationHint",
    "Severity",
    # Entities
    "TestFile",
    # Ports
    "IAnalyzer",
    "ISuiteAnalyzer",
    "IMetrics",
    "IPluginRegistry",
    # Plugin extension point
    "Plugin",
    "PluginMetadata",
    # Analyzer extension point
    "BaseAnalyzer",
    "ConfigValue",
    "SuiteAwareAnalyzer",
    # Error taxonomy
    "ErrorCategory",
    "StructuredError",
]
