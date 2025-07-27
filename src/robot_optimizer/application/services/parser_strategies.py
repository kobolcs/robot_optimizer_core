# src/robot_optimizer/domain/services/parser_strategies.py
"""Parser strategies for Robot Framework analysis."""
from abc import ABC, abstractmethod
from typing import List, Set, Dict, Optional
import re

from ..entities import TestFile
from ..value_objects import Finding, Pattern, PatternType, Location, Severity
from ..repositories.robot_parser_repository import RobotParserRepository


class ParserStrategy(ABC):
    """Abstract base for parsing strategies."""
    
    @abstractmethod
    def find_unused_keywords(self, test_file: TestFile) -> List[Finding]:
        """Find unused keywords in the test file."""
        pass
    
    @abstractmethod
    def find_duplicate_keywords(self, test_file: TestFile) -> List[Finding]:
        """Find duplicate keyword definitions."""
        pass
    
    @abstractmethod
    def find_complex_keywords(self, test_file: TestFile, threshold: int = 10) -> List[Finding]:
        """Find overly complex keywords."""
        pass


class ASTParserStrategy(ParserStrategy):
    """AST-based parsing strategy using Robot Framework parser."""
    
    def __init__(self, parser: RobotParserRepository):
        self.parser = parser
    
    def find_unused_keywords(self, test_file: TestFile) -> List[Finding]:
        """Find unused keywords using AST analysis."""
        suite = self.parser.parse_suite(test_file)
        
        # Get all keyword definitions
        keyword_definitions = {kw.name.lower(): kw for kw in suite.keywords}
        
        # Get all keyword calls
        keyword_calls = suite.all_keyword_calls
        called_keywords = {call.keyword_name.lower() for call in keyword_calls}
        
        # Find unused keywords
        findings = []
        for name, keyword in keyword_definitions.items():
            if name not in called_keywords:
                pattern = Pattern(
                    type=PatternType.UNUSED_KEYWORD,
                    name="Unused Keyword",
                    description=f"Keyword '{keyword.name}' is defined but never used",
                    recommendation="Remove unused keyword to reduce maintenance burden",
                    auto_fixable=True
                )
                
                finding = Finding.create(
                    pattern=pattern,
                    severity=Severity.WARNING,
                    location=keyword.location,
                    message=f"Unused keyword '{keyword.name}' - can be safely removed",
                    keyword_name=keyword.name,
                    has_documentation=keyword.has_documentation,
                    argument_count=len(keyword.arguments),
                    maintenance_time_saved_hours=0.5
                )
                findings.append(finding)
        
        return findings
    
    def find_duplicate_keywords(self, test_file: TestFile) -> List[Finding]:
        """Find duplicate keywords using AST."""
        suite = self.parser.parse_suite(test_file)
        
        keyword_map = {}
        for keyword in suite.keywords:
            name_lower = keyword.name.lower()
            if name_lower not in keyword_map:
                keyword_map[name_lower] = []
            keyword_map[name_lower].append(keyword)
        
        findings = []
        for name, keywords in keyword_map.items():
            if len(keywords) > 1:
                pattern = Pattern.duplicate_keyword(keywords[0].name)
                
                finding = Finding.create(
                    pattern=pattern,
                    severity=Severity.ERROR,
                    location=keywords[0].location,
                    message=f"Keyword '{keywords[0].name}' defined {len(keywords)} times",
                    keyword_name=keywords[0].name,
                    occurrences=[kw.location.line for kw in keywords],
                    duplicate_count=len(keywords)
                )
                findings.append(finding)
        
        return findings
    
    def find_complex_keywords(self, test_file: TestFile, threshold: int = 10) -> List[Finding]:
        """Find complex keywords using AST."""
        suite = self.parser.parse_suite(test_file)
        
        findings = []
        for keyword in suite.keywords:
            if len(keyword.body_calls) > threshold:
                pattern = Pattern(
                    type=PatternType.COMPLEX_KEYWORD,
                    name="Complex Keyword",
                    description=f"Keyword '{keyword.name}' has {len(keyword.body_calls)} keyword calls",
                    recommendation="Break down into smaller, focused keywords",
                    auto_fixable=False
                )
                
                finding = Finding.create(
                    pattern=pattern,
                    severity=Severity.WARNING,
                    location=keyword.location,
                    message=f"Complex keyword with {len(keyword.body_calls)} calls - consider refactoring",
                    keyword_name=keyword.name,
                    call_count=len(keyword.body_calls),
                    cyclomatic_complexity=len(keyword.body_calls) // 3
                )
                findings.append(finding)
        
        return findings


class RegexParserStrategy(ParserStrategy):
    """Regex-based fallback parsing strategy."""
    
    def __init__(self):
        self.section_pattern = re.compile(r'^\*+\s*(Test Cases?|Keywords?)\s*\*+', re.IGNORECASE)
        self.keyword_def_pattern = re.compile(r'^([A-Za-z][A-Za-z0-9 _]*[A-Za-z0-9])\s*$')
        self.keyword_usage_pattern = re.compile(r'^\s+([\w\s\.]+?)(?:\s{2,}|$)')
    
    def find_unused_keywords(self, test_file: TestFile) -> List[Finding]:
        """Find unused keywords using regex."""
        lines = test_file.content.splitlines()
        findings = []
        
        # Track keyword definitions and usage
        keyword_definitions = {}
        keyword_usages = set()
        in_keyword_section = False
        current_keyword = None
        
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # Check section headers
            section_match = self.section_pattern.match(line)
            if section_match:
                in_keyword_section = 'keyword' in section_match.group(1).lower()
                current_keyword = None
                continue
            
            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                continue
            
            # In keywords section - track definitions
            if in_keyword_section:
                if not line.startswith((' ', '\t')):
                    # Potential keyword definition
                    match = self.keyword_def_pattern.match(line)
                    if match:
                        keyword_name = match.group(1)
                        if keyword_name not in keyword_definitions:
                            keyword_definitions[keyword_name] = []
                        keyword_definitions[keyword_name].append(line_num)
                        current_keyword = keyword_name
                else:
                    # Keyword body - check for usage
                    if current_keyword:
                        usage_match = self.keyword_usage_pattern.match(line)
                        if usage_match:
                            potential_keyword = usage_match.group(1).strip()
                            # Exclude built-in keywords
                            if not self._is_builtin_keyword(potential_keyword):
                                keyword_usages.add(potential_keyword)
            else:
                # In test cases - track usage
                if line.startswith((' ', '\t')):
                    usage_match = self.keyword_usage_pattern.match(line)
                    if usage_match:
                        potential_keyword = usage_match.group(1).strip()
                        if not self._is_builtin_keyword(potential_keyword):
                            keyword_usages.add(potential_keyword)
        
        # Find unused keywords
        for keyword_name, locations in keyword_definitions.items():
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
                    location=Location(file_path=test_file.path, line=locations[0]),
                    message=f"Unused keyword '{keyword_name}' - can be safely removed",
                    keyword_name=keyword_name,
                    maintenance_time_saved_hours=0.5
                )
                findings.append(finding)
        
        return findings
    
    def find_duplicate_keywords(self, test_file: TestFile) -> List[Finding]:
        """Find duplicate keywords using regex."""
        lines = test_file.content.splitlines()
        findings = []
        
        keyword_definitions = {}
        in_keyword_section = False
        
        for line_num, line in enumerate(lines, 1):
            section_match = self.section_pattern.match(line)
            if section_match:
                in_keyword_section = 'keyword' in section_match.group(1).lower()
                continue
            
            if in_keyword_section and not line.startswith((' ', '\t')):
                match = self.keyword_def_pattern.match(line)
                if match:
                    keyword_name = match.group(1)
                    if keyword_name not in keyword_definitions:
                        keyword_definitions[keyword_name] = []
                    keyword_definitions[keyword_name].append(line_num)
        
        # Find duplicates
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
    
    def find_complex_keywords(self, test_file: TestFile, threshold: int = 10) -> List[Finding]:
        """Find complex keywords using regex (limited capability)."""
        # Regex strategy has limited capability for complexity analysis
        # Would need to count indented lines under each keyword
        return []
    
    def _is_builtin_keyword(self, keyword_name: str) -> bool:
        """Check if keyword is a built-in Robot Framework keyword."""
        builtins = {
            'log', 'log to console', 'set variable', 'should be equal',
            'should contain', 'should be true', 'should be false',
            'run keyword', 'run keyword if', 'run keyword and return status',
            'wait until keyword succeeds', 'sleep', 'comment',
            'no operation', 'fail', 'pass execution', 'return from keyword',
            'continue for loop', 'exit for loop', 'get time',
            'evaluate', 'call method', 'catenate', 'create list',
            'create dictionary', 'get length', 'length should be',
            'should be empty', 'should not be empty', 'convert to',
            'set test variable', 'set suite variable', 'set global variable'
        }
        
        return keyword_name.lower() in builtins or '.' in keyword_name


# Updated DeadCodeAnalyzer to use strategies
class DeadCodeAnalyzer:
    """Domain service using strategy pattern for dead code analysis."""
    
    def __init__(self, parser: Optional[RobotParserRepository] = None):
        if parser:
            self.strategy = ASTParserStrategy(parser)
        else:
            self.strategy = RegexParserStrategy()
    
    def find_unused_keywords(self, test_file: TestFile) -> List[Finding]:
        """Find unused keywords using the configured strategy."""
        findings = []
        findings.extend(self.strategy.find_unused_keywords(test_file))
        findings.extend(self.strategy.find_duplicate_keywords(test_file))
        findings.extend(self.strategy.find_complex_keywords(test_file))
        return findings
    
    def find_missing_documentation(self, test_file: TestFile) -> List[Finding]:
        """Find keywords and test cases missing documentation."""
        if isinstance(self.strategy, ASTParserStrategy):
            return self._find_missing_docs_ast(test_file)
        return []  # Regex strategy can't reliably detect documentation
    
    def _find_missing_docs_ast(self, test_file: TestFile) -> List[Finding]:
        """Find missing documentation using AST."""
        if not isinstance(self.strategy, ASTParserStrategy):
            return []
            
        suite = self.strategy.parser.parse_suite(test_file)
        findings = []
        
        # Check keywords
        for keyword in suite.keywords:
            if not keyword.has_documentation:
                pattern = Pattern(
                    type=PatternType.MISSING_DOCUMENTATION,
                    name="Missing Keyword Documentation",
                    description=f"Keyword '{keyword.name}' has no documentation",
                    recommendation="Add [Documentation] to explain keyword purpose and usage",
                    auto_fixable=False
                )
                
                finding = Finding.create(
                    pattern=pattern,
                    severity=Severity.WARNING,
                    location=keyword.location,
                    message=f"Keyword '{keyword.name}' lacks documentation",
                    keyword_name=keyword.name,
                    element_type="keyword"
                )
                findings.append(finding)
        
        return findings