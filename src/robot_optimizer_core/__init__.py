# src/robot_optimizer_core/__init__.py
"""Robot Framework Optimizer Core - Shared analysis engine.

This package provides the core functionality for analyzing Robot Framework
test suites, including:

- Dead code detection
- Sleep pattern analysis  
- Test flakiness detection
- Extensible analyzer framework

The Core package is designed to be extended by the Pro version for
advanced features while providing a solid foundation for the free MVP.
"""

__version__ = "0.1.0"

# Make key components available at package level
from .domain.entities import TestFile
from .domain.value_objects import (
    Finding, Pattern, PatternType, Severity, Location
)
from .analyzers import (
    BaseAnalyzer, DeadCodeAnalyzer, SleepDetector, FlakinessAnalyzer
)

__all__ = [
    # Version
    "__version__",
    
    # Core entities
    "TestFile",
    
    # Value objects
    "Finding",
    "Pattern", 
    "PatternType",
    "Severity",
    "Location",
    
    # Analyzers
    "BaseAnalyzer",
    "DeadCodeAnalyzer",
    "SleepDetector",
    "FlakinessAnalyzer",
]
