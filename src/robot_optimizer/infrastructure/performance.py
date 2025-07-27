# src/robot_optimizer/infrastructure/performance.py
"""Performance optimizations for the analyzer."""
from functools import lru_cache
from typing import Dict, Any, List, TypedDict, Optional
import hashlib
from pathlib import Path
from datetime import datetime

from ..domain.entities import TestFile
from ..domain.value_objects.robot_ast import RobotSuite


class AnalysisSummaryDict(TypedDict):
    """Type-safe dictionary for analysis summaries."""
    id: str
    file: str
    started_at: str
    completed_at: Optional[str]
    duration_seconds: Optional[float]
    finding_count: int
    error_count: int
    warning_count: int
    info_count: int
    auto_fixable_count: int
    pattern_summary: Dict[str, int]


class CachedRobotParser:
    """Parser with caching for performance."""
    
    def __init__(self, base_parser):
        self.base_parser = base_parser
        self._cache: Dict[str, RobotSuite] = {}
    
    def parse_suite(self, test_file: TestFile) -> RobotSuite:
        """Parse with caching based on content hash."""
        cache_key = self._get_cache_key(test_file)
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        suite = self.base_parser.parse_suite(test_file)
        self._cache[cache_key] = suite
        
        # Limit cache size
        if len(self._cache) > 128:
            # Remove oldest entries
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        
        return suite
    
    @staticmethod
    def _get_cache_key(test_file: TestFile) -> str:
        """Generate cache key from file content."""
        content_hash = hashlib.md5(test_file.content.encode()).hexdigest()
        return f"{test_file.path}:{content_hash}"
