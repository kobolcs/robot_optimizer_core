# src/robot_optimizer_core/analyzers/dead_code.py
"""Dead code analyzer for finding unused keywords and duplicates.

This analyzer detects:
- Unused keywords that are defined but never called
- Duplicate keyword definitions
- Keywords that are only used in their own definition (recursion)

Example:
    Using the dead code analyzer::
    
        from robot_optimizer_core.analyzers import DeadCodeAnalyzer
        from robot_optimizer_core import TestFile
        
        analyzer = DeadCodeAnalyzer()
        test_file = TestFile.from_path("tests/login.robot")
        findings = analyzer.analyze(test_file)
        
        for finding in findings:
            if finding.pattern.type == PatternType.UNUSED_KEYWORD:
                print(f"Unused: {finding.context['keyword_name']}")
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from ..domain.entities import TestFile
from ..domain.value_objects import Finding, Location, Pattern, PatternType, Severity
from .base import BaseAnalyzer


class DeadCodeAnalyzer(BaseAnalyzer):
    """Analyzer for detecting dead code in Robot Framework files.
    
    This analyzer uses regex-based pattern matching to find unused
    and duplicate keywords. The Pro version extends this with
    AST-based analysis for more accuracy.
    
    Configuration:
        check_unused: Whether to check for unused keywords (default: True).
        check_duplicates: Whether to check for duplicates (default: True).
        ignore_patterns: List of keyword patterns to ignore.
    """
    
    def __init__(self, config: Dict[str, any] = None) -> None:
        """Initialize the analyzer.
        
        Args:
            config: Analyzer configuration.
        """
        super().__init__(config)
        
        # Compile regex patterns once
        self._section_pattern = re.compile(
            r'^\*+\s*(Test Cases?|Keywords?|Settings?|Variables?)\s*\*+',
            re.IGNORECASE
        )
        self._keyword_def_pattern = re.compile(
            r'^([A-Za-z][A-Za-z0-9 _]*[A-Za-z0-9])\s*$'
        )
        self._keyword_usage_pattern = re.compile(
            r'^\s+([\w\s\.]+?)(?:\s{2,}|$)'
        )
        
        # Configuration
        self._check_unused = self.get_config_value("check_unused", True)
        self._check_duplicates = self.get_config_value("check_duplicates", True)
        self._ignore_patterns = self.get_config_value("ignore_patterns", [])
    
    @property
    def name(self) -> str:
        """Get analyzer name.
        
        Returns:
            Analyzer name.
        """
        return "dead_code"
    
    @property
    def description(self) -> str:
        """Get analyzer description.
        
        Returns:
            Analyzer description.
        """
        return "Finds unused keywords and duplicate definitions"
    
    @property
    def tags(self) -> List[str]:
        """Get analyzer tags.
        
        Returns:
            List of tags.
        """
        return ["keywords", "maintenance", "cleanup"]
    
    @property
    def supports_auto_fix(self) -> bool:
        """Check if analyzer supports auto-fixing.
        
        Returns:
            True (dead code can be auto-removed).
        """
        return True
    
    def analyze(self, test_file: TestFile) -> List[Finding]:
        """Analyze test file for dead code.
        
        Args:
            test_file: The test file to analyze.
            
        Returns:
            List of findings.
        """
        findings = []
        
        if self._check_unused:
            findings.extend(self._find_unused_keywords(test_file))
        
        if self._check_duplicates:
            findings.extend(self._find_duplicate_keywords(test_file))
        
        return findings
    
    def _find_unused_keywords(self, test_file: TestFile) -> List[Finding]:
        """Find unused keywords in the file.
        
        Args:
            test_file: The test file to analyze.
            
        Returns:
            List of unused keyword findings.
        """
        lines = test_file.content.splitlines()
        
        # Parse file structure
        keyword_definitions: Dict[str, int] = {}
        keyword_usages: Set[str] = set()
        current_section = None
        in_keyword_section = False
        current_keyword = None
        
        for line_num, line in enumerate(lines, 1):
            # Check section headers
            section_match = self._section_pattern.match(line)
            if section_match:
                current_section = section_match.group(1).lower()
                in_keyword_section = 'keyword' in current_section
                continue
            
            # Skip empty lines and comments
            if not line.strip() or line.strip().startswith('#'):
                continue
            
            # In keywords section - track definitions
            if in_keyword_section and not line.startswith((' ', '\t')):
                match = self._keyword_def_pattern.match(line)
                if match:
                    keyword_name = match.group(1)
                    if not self._should_ignore_keyword(keyword_name):
                        keyword_definitions[keyword_name] = line_num
                        current_keyword = keyword_name
            
            # Track keyword usage
            elif line.startswith((' ', '\t')):
                match = self._keyword_usage_pattern.match(line)
                if match:
                    potential_keyword = match.group(1).strip()
                    
                    # Split on multiple spaces to handle arguments
                    keyword_parts = potential_keyword.split('  ')
                    if keyword_parts:
                        keyword_call = keyword_parts[0].strip()
                        
                        # Skip built-in keywords
                        if not self._is_builtin_keyword(keyword_call):
                            keyword_usages.add(keyword_call)
                            
                            # Check for self-recursion
                            if current_keyword and keyword_call == current_keyword:
                                self._logger.debug(
                                    f"Keyword '{current_keyword}' calls itself",
                                    extra={"line": line_num}
                                )
        
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
                    keyword_name=keyword_name,
                    line_content=lines[line_num - 1] if line_num <= len(lines) else ""
                )
                findings.append(finding)
        
        return findings
    
    def _find_duplicate_keywords(self, test_file: TestFile) -> List[Finding]:
        """Find duplicate keyword definitions.
        
        Args:
            test_file: The test file to analyze.
            
        Returns:
            List of duplicate keyword findings.
        """
        lines = test_file.content.splitlines()
        keyword_definitions: Dict[str, List[int]] = defaultdict(list)
        in_keyword_section = False
        
        for line_num, line in enumerate(lines, 1):
            # Check section headers
            if self._section_pattern.match(line):
                in_keyword_section = 'keyword' in line.lower()
                continue
            
            # In keywords section - track definitions
            if in_keyword_section and not line.startswith((' ', '\t')):
                match = self._keyword_def_pattern.match(line)
                if match:
                    keyword_name = match.group(1)
                    if not self._should_ignore_keyword(keyword_name):
                        keyword_definitions[keyword_name].append(line_num)
        
        # Create findings for duplicates
        findings = []
        for keyword_name, locations in keyword_definitions.items():
            if len(locations) > 1:
                pattern = Pattern.duplicate_keyword(keyword_name)
                
                # Create finding for the first occurrence
                finding = Finding.create(
                    pattern=pattern,
                    severity=Severity.ERROR,
                    location=Location(file_path=test_file.path, line=locations[0]),
                    message=f"Keyword '{keyword_name}' defined {len(locations)} times at lines: {locations}",
                    keyword_name=keyword_name,
                    occurrences=locations,
                    duplicate_count=len(locations),
                    all_locations=[
                        {"line": loc, "content": lines[loc - 1] if loc <= len(lines) else ""}
                        for loc in locations
                    ]
                )
                findings.append(finding)
                
                # Also create findings for other occurrences
                for loc in locations[1:]:
                    dup_finding = Finding.create(
                        pattern=pattern,
                        severity=Severity.ERROR,
                        location=Location(file_path=test_file.path, line=loc),
                        message=f"Duplicate definition of keyword '{keyword_name}' (first defined at line {locations[0]})",
                        keyword_name=keyword_name,
                        first_occurrence=locations[0],
                        line_content=lines[loc - 1] if loc <= len(lines) else ""
                    )
                    findings.append(dup_finding)
        
        return findings
    
    def _is_builtin_keyword(self, keyword_name: str) -> bool:
        """Check if keyword is a built-in Robot Framework keyword.
        
        Args:
            keyword_name: Name of the keyword.
            
        Returns:
            True if keyword is built-in.
        """
        # Common built-in keywords
        builtins = {
            # BuiltIn library
            'log', 'log to console', 'set variable', 'get variable value',
            'should be equal', 'should contain', 'should be true', 'should be false',
            'should be empty', 'should not be empty', 'should exist', 'should not exist',
            'run keyword', 'run keyword if', 'run keyword and return status',
            'run keyword and ignore error', 'run keywords',
            'sleep', 'comment', 'no operation', 'fail', 'pass execution',
            'fatal error', 'set test message', 'set test documentation',
            'set suite variable', 'set global variable', 'set local variable',
            'get time', 'get library instance', 'import library',
            'wait until keyword succeeds', 'repeat keyword',
            
            # Collections
            'append to list', 'get from list', 'get from dictionary',
            
            # String
            'get length', 'should be string', 'convert to string',
            
            # Common patterns
            'setup', 'teardown', 'test setup', 'test teardown',
            'suite setup', 'suite teardown'
        }
        
        keyword_lower = keyword_name.lower()
        
        # Direct match
        if keyword_lower in builtins:
            return True
        
        # Library keyword format (Library.Keyword)
        if '.' in keyword_name:
            return True
        
        # BDD style keywords
        if keyword_lower.startswith(('given ', 'when ', 'then ', 'and ', 'but ')):
            return True
        
        return False
    
    def _should_ignore_keyword(self, keyword_name: str) -> bool:
        """Check if keyword should be ignored based on patterns.
        
        Args:
            keyword_name: Name of the keyword.
            
        Returns:
            True if keyword should be ignored.
        """
        for pattern in self._ignore_patterns:
            if re.match(pattern, keyword_name):
                return True
        return False
    
    def validate_config(self) -> None:
        """Validate analyzer configuration.
        
        Raises:
            ConfigurationError: If configuration is invalid.
        """
        # Validate ignore patterns are valid regex
        for pattern in self._ignore_patterns:
            try:
                re.compile(pattern)
            except re.error as e:
                from ..exceptions import ConfigurationError
                raise ConfigurationError(
                    f"Invalid ignore pattern regex: {pattern}",
                    config_key="ignore_patterns",
                    provided_value=pattern,
                    details={"error": str(e)}
                )