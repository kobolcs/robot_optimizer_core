"""Base analyzer interface for Robot Framework analysis."""
from abc import ABC, abstractmethod
from typing import List

from ..domain.entities import TestFile
from ..domain.value_objects import Finding


class BaseAnalyzer(ABC):
    """Abstract base class for all analyzers."""
    
    @abstractmethod
    def analyze(self, test_file: TestFile) -> List[Finding]:
        """Analyze a test file and return findings.
        
        Args:
            test_file: The test file to analyze
            
        Returns:
            List of findings discovered
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Get the analyzer name."""
        pass
    
    @property 
    @abstractmethod
    def description(self) -> str:
        """Get the analyzer description."""
        pass
