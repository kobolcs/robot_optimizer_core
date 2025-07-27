# src/robot_optimizer_core/analyzers/dead_code.py
"""Basic dead code analyzer for Robot Framework tests."""
import re
from typing import List, Dict, Set

from .base_analyzer import BaseAnalyzer
from ..domain.entities import TestFile
from ..domain.value_objects import Finding, Pattern, PatternType, Severity, Location


class DeadCodeAnalyzer(BaseAnalyzer):
    """Basic analyzer for finding unused keywords.
    
    This is the Core version with basic regex-based detection.
    The Pro version extends this with AST parsing and advanced features.
    """
    
    @property
    def name(self) -> str:
        return "Dead Code Analyzer"
    
    @property
    def description(self) -> str:
        return "Finds unused keywords and duplicate definitions"
    
    def __init__(self):
        # Compile patterns once for efficiency
        self.section_pattern = re.compile(r'^\*+\s*(Test Cases?|Keywords?)\s*\*+', re.IGNORECASE)
        self.keyword_def_pattern = re.compile(r'^([A-Za-z][A-Za-z0-9 _]*[A-Za-z0-9])\s*$')
        self.keyword_usage_pattern = re.compile(r'^\s+([\w\s\.]+?)(?:\s{2,}|$)')
    
    def analyze(self, test_file: TestFile) -> List[Finding]:
        """Analyze test file for dead code using basic regex approach."""
        findings = []
        
        findings.extend(self._find_unused_keywords(test_file))
        findings.extend(self._find_duplicate_keywords(test_file))
        
        return findings
    
    def _find_unused_keywords(self, test_file: TestFile) -> List[Finding]:
        """Find unused keywords using basic pattern matching."""
        lines = test_file.content.splitlines()
        
        # Track definitions and usage
        keyword_definitions: Dict[str, int] = {}
        keyword_usages: Set[str] = set()
        in_keyword_section = False
        
        for line_num, line in enumerate(lines, 1):
            # Check section headers
            if self.section_pattern.match(line):
                in_keyword_section = 'keyword' in line.lower()
                continue
            
            # Skip empty lines and comments
            if not line.strip() or line.strip().startswith('#'):
                continue
            
            # In keywords section - track definitions
            if in_keyword_section and not line.startswith((' ', '\t')):
                match = self.keyword_def_pattern.match(line)
                if match:
                    keyword_name = match.group(1)
                    keyword_definitions[keyword_name] = line_num
            
            # Track keyword usage
            elif line.startswith((' ', '\t')):
                match = self.keyword_usage_pattern.match(line)
                if match:
                    potential_keyword = match.group(1).strip()
                    if not self._is_builtin_keyword(potential_keyword):
                        keyword_usages.add(potential_keyword)
        
        # Find unused keywords
        findings = []
        for keyword_name, line_num in keyword_definitions.items():
            if keyword_name not in keyword_usages:
                pattern = Pattern(
                    type=PatternType.UNUSED_KEYWORD,
                    name="Unused Keyword",
                    description=f"Keyword '{keyword_name}' is defined but never used",
                    recommendation="Remove unused keyword to reduce maintenance burden",
                    auto_fixable=True
                )
                
                finding = Finding.create(
                    pattern=pattern,
                    severity=Severity.WARNING,
                    location=Location(file_path=test_file.path, line=line_num),
                    message=f"Unused keyword '{keyword_name}' - can be safely removed",
                    keyword_name=keyword_name
                )
                findings.append(finding)
        
        return findings
    
    def _find_duplicate_keywords(self, test_file: TestFile) -> List[Finding]:
        """Find duplicate keyword definitions."""
        lines = test_file.content.splitlines()
        keyword_definitions: Dict[str, List[int]] = {}
        in_keyword_section = False
        
        for line_num, line in enumerate(lines, 1):
            if self.section_pattern.match(line):
                in_keyword_section = 'keyword' in line.lower()
                continue
            
            if in_keyword_section and not line.startswith((' ', '\t')):
                match = self.keyword_def_pattern.match(line)
                if match:
                    keyword_name = match.group(1)
                    if keyword_name not in keyword_definitions:
                        keyword_definitions[keyword_name] = []
                    keyword_definitions[keyword_name].append(line_num)
        
        # Create findings for duplicates
        findings = []
        for keyword_name, locations in keyword_definitions.items():
            if len(locations) > 1:
                pattern = Pattern.duplicate_keyword(keyword_name)
                
                finding = Finding.create(
                    pattern=pattern,
                    severity=Severity.ERROR,
                    location=Location(file_path=test_file.path, line=locations[0]),
                    message=f"Keyword '{keyword_name}' defined {len(locations)} times",
                    keyword_name=keyword_name,
                    occurrences=locations,
                    duplicate_count=len(locations)
                )
                findings.append(finding)
        
        return findings
    
    def _is_builtin_keyword(self, keyword_name: str) -> bool:
        """Check if keyword is a built-in Robot Framework keyword."""
        builtins = {
            'log', 'log to console', 'set variable', 'should be equal',
            'should contain', 'should be true', 'should be false',
            'run keyword', 'run keyword if', 'sleep', 'comment',
            'no operation', 'fail', 'pass execution'
        }
        return keyword_name.lower() in builtins or '.' in keyword_name


