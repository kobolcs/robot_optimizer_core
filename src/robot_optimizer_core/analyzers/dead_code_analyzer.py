# src/robot_optimizer/domain/services/dead_code_analyzer.py
"""Enhanced dead code analyzer using AST parsing."""
from typing import List, Dict, Set, Optional
from collections import defaultdict

from ..entities import TestFile
from ..value_objects import Pattern, PatternType, Finding, Location, Severity
from ..repositories.robot_parser_repository import RobotParserRepository


class DeadCodeAnalyzer:
    """Domain service using AST for accurate dead code analysis."""
    
    def __init__(self, parser: Optional[RobotParserRepository] = None):
        self.parser = parser
    
    def find_unused_keywords(self, test_file: TestFile) -> List[Finding]:
        """Find unused keywords using AST analysis or regex fallback."""
        if self.parser:
            return self._analyze_with_parser(test_file)
        else:
            return self._analyze_with_regex(test_file)
    
    def _analyze_with_parser(self, test_file: TestFile) -> List[Finding]:
        """Use AST parser for accurate analysis."""
        suite = self.parser.parse_suite(test_file)
        
        # Get all keyword definitions
        keyword_definitions = {kw.name.lower(): kw for kw in suite.keywords}
        
        # Get all keyword calls
        keyword_calls = suite.all_keyword_calls
        called_keywords = {call.keyword_name.lower() for call in keyword_calls}
        
        # Find unused keywords
        unused_keywords = []
        for name, keyword in keyword_definitions.items():
            if name not in called_keywords:
                unused_keywords.append(keyword)
        
        # Find duplicate keywords
        duplicates = self._find_duplicate_keywords(suite.keywords)
        
        # Find complex keywords
        complex_keywords = self._find_complex_keywords(suite.keywords)
        
        # Create findings
        findings = []
        findings.extend(self._create_unused_findings(unused_keywords, test_file))
        findings.extend(self._create_duplicate_findings(duplicates, test_file))
        findings.extend(self._create_complex_findings(complex_keywords, test_file))
        
        return findings
    
    def _analyze_with_regex(self, test_file: TestFile) -> List[Finding]:
        """Fallback regex-based analysis."""
        import re
        
        lines = test_file.content.splitlines()
        findings = []
        
        # Track keyword definitions and usage
        keyword_definitions = {}
        keyword_usages = set()
        in_keyword_section = False
        current_keyword = None
        
        # Patterns
        section_pattern = re.compile(r'^\*+\s*(Test Cases?|Keywords?)\s*\*+', re.IGNORECASE)
        keyword_def_pattern = re.compile(r'^([A-Za-z][A-Za-z0-9 _]*[A-Za-z0-9])\s*$')
        keyword_usage_pattern = re.compile(r'^\s+([\w\s\.]+?)(?:\s{2,}|$)')
        
        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # Check section headers
            section_match = section_pattern.match(line)
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
                    match = keyword_def_pattern.match(line)
                    if match:
                        keyword_name = match.group(1)
                        if keyword_name not in keyword_definitions:
                            keyword_definitions[keyword_name] = []
                        keyword_definitions[keyword_name].append(line_num)
                        current_keyword = keyword_name
                else:
                    # Keyword body - check for usage
                    if current_keyword:
                        usage_match = keyword_usage_pattern.match(line)
                        if usage_match:
                            potential_keyword = usage_match.group(1).strip()
                            # Exclude built-in keywords
                            if not self._is_builtin_keyword(potential_keyword):
                                keyword_usages.add(potential_keyword)
            else:
                # In test cases - track usage
                if line.startswith((' ', '\t')):
                    usage_match = keyword_usage_pattern.match(line)
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
        
        # Find duplicate keywords
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
    
    def find_missing_documentation(self, test_file: TestFile) -> List[Finding]:
        """Find keywords and test cases missing documentation."""
        if not self.parser:
            return []  # Can't reliably detect without AST
        
        suite = self.parser.parse_suite(test_file)
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
        
        # Check test cases  
        for test in suite.test_cases:
            if not test.documentation:
                pattern = Pattern(
                    type=PatternType.MISSING_DOCUMENTATION,
                    name="Missing Test Documentation",
                    description=f"Test case '{test.name}' has no documentation",
                    recommendation="Add [Documentation] to explain test purpose",
                    auto_fixable=False
                )
                
                finding = Finding.create(
                    pattern=pattern,
                    severity=Severity.INFO,
                    location=test.location,
                    message=f"Test case '{test.name}' lacks documentation",
                    test_name=test.name,
                    element_type="test"
                )
                findings.append(finding)
        
        return findings
    
    def find_long_test_cases(self, test_file: TestFile, threshold: int = 50) -> List[Finding]:
        """Find test cases that are too long."""
        if not self.parser:
            return []  # Can't reliably detect without AST
        
        suite = self.parser.parse_suite(test_file)
        findings = []
        
        for test in suite.test_cases:
            if test.line_count > threshold:
                pattern = Pattern.long_test_case(test.line_count, threshold)
                
                finding = Finding.create(
                    pattern=pattern,
                    severity=Severity.WARNING,
                    location=test.location,
                    message=f"Test case '{test.name}' is {test.line_count} lines long",
                    test_name=test.name,
                    line_count=test.line_count,
                    threshold=threshold
                )
                findings.append(finding)
        
        return findings
    
    def find_complex_keywords(self, test_file: TestFile, threshold: int = 10) -> List[Finding]:
        """Find keywords that are too complex."""
        if not self.parser:
            return []
        
        suite = self.parser.parse_suite(test_file)
        complex_keywords = self._find_complex_keywords(suite.keywords, threshold)
        return self._create_complex_findings(complex_keywords, test_file)
    
    def _find_duplicate_keywords(self, keywords: List) -> Dict[str, List]:
        """Find keywords defined multiple times."""
        keyword_map = defaultdict(list)
        
        for keyword in keywords:
            keyword_map[keyword.name.lower()].append(keyword)
        
        return {
            name: kws for name, kws in keyword_map.items() 
            if len(kws) > 1
        }
    
    def _find_complex_keywords(self, keywords: List, threshold: int = 10) -> List:
        """Find keywords that are too complex (too many keyword calls)."""
        complex_keywords = []
        
        for keyword in keywords:
            if len(keyword.body_calls) > threshold:
                complex_keywords.append(keyword)
        
        return complex_keywords
    
    def _create_unused_findings(self, unused_keywords: List, test_file: TestFile) -> List[Finding]:
        """Create findings for unused keywords."""
        findings = []
        
        for keyword in unused_keywords:
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
    
    def _create_duplicate_findings(self, duplicates: Dict[str, List], test_file: TestFile) -> List[Finding]:
        """Create findings for duplicate keywords."""
        findings = []
        
        for name, keywords in duplicates.items():
            pattern = Pattern.duplicate_keyword(keywords[0].name)
            
            # Use first occurrence for main finding
            first = keywords[0]
            finding = Finding.create(
                pattern=pattern,
                severity=Severity.ERROR,
                location=first.location,
                message=f"Keyword '{first.name}' defined {len(keywords)} times",
                keyword_name=first.name,
                occurrences=[kw.location.line for kw in keywords],
                duplicate_count=len(keywords)
            )
            findings.append(finding)
        
        return findings
    
    def _create_complex_findings(self, complex_keywords: List, test_file: TestFile) -> List[Finding]:
        """Create findings for overly complex keywords."""
        findings = []
        
        for keyword in complex_keywords:
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
                cyclomatic_complexity=len(keyword.body_calls) // 3  # Rough estimate
            )
            findings.append(finding)
        
        return findings
    
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