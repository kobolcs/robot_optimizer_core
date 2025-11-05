# src/robot_optimizer_core/analyzers/dead_code.py
"""Dead code analyzer for Robot Framework test suites.

This analyzer detects unused keywords and duplicate definitions
that can be safely removed to improve maintainability.
"""
from __future__ import annotations

from collections import defaultdict
try:
    from typing import override
except ImportError:
    from typing_extensions import override

from ..domain.entities import TestFile
from ..domain.value_objects import Finding, Location, Pattern, PatternType, Severity
from .base import BaseAnalyzer, ConfigValue


class DeadCodeAnalyzer(BaseAnalyzer):
    """Analyzer for detecting dead code in Robot Framework files.
    
    Detects:
    - Unused keywords
    - Duplicate keyword definitions
    - Unreachable code after RETURN statements
    """

    def __init__(self, config: dict[str, ConfigValue] | None = None) -> None:
        """Initialize the analyzer."""
        super().__init__(config)
        self._check_unused = self.get_config_value("check_unused", True)
        self._check_duplicates = self.get_config_value("check_duplicates", True)
        self._check_unreachable = self.get_config_value("check_unreachable", True)

    @property
    @override
    def name(self) -> str:
        return "dead_code"

    @property
    @override
    def description(self) -> str:
        return "Detects unused keywords and duplicate definitions"

    @property
    @override
    def tags(self) -> list[str]:
        return ["cleanup", "maintainability", "code-quality"]

    @override
    def analyze(self, test_file: TestFile) -> list[Finding]:
        """Analyze test file for dead code."""
        findings = []

        # Parse the file structure in a single pass (optimization)
        keywords, keyword_calls = self._extract_keywords_and_calls(test_file)

        if self._check_unused:
            findings.extend(self._find_unused_keywords(keywords, keyword_calls, test_file))

        if self._check_duplicates:
            findings.extend(self._find_duplicate_keywords(keywords, test_file))

        if self._check_unreachable:
            findings.extend(self._find_unreachable_code(test_file))

        return findings

    def _extract_keywords_and_calls(
        self,
        test_file: TestFile
    ) -> tuple[dict[str, list[int]], set[str]]:
        """Extract keyword definitions and calls in a single pass (optimized).

        This method combines the functionality of _extract_keywords and
        _extract_keyword_calls to avoid iterating through the file twice (N+1 fix).

        Returns:
            Tuple of (keywords dict, keyword calls set)
        """
        keywords = defaultdict(list)
        calls = set()
        lines = test_file.content.splitlines()

        in_keywords_section = False
        in_test_or_keyword = False

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                continue

            # Check for section markers
            if stripped.startswith('***'):
                in_keywords_section = 'keyword' in stripped.lower()
                in_test_or_keyword = 'test case' in stripped.lower() or 'keyword' in stripped.lower()
                continue

            # Extract keyword definitions (non-indented lines in keywords section)
            if in_keywords_section and not line.startswith((' ', '\t')):
                keyword_name = stripped
                keywords[keyword_name.lower()].append(line_num)

            # Extract keyword calls (indented lines in test/keyword sections)
            if in_test_or_keyword and line.startswith((' ', '\t')):
                parts = stripped.split()
                if parts:
                    # First part is usually the keyword name
                    calls.add(parts[0].lower())

        return dict(keywords), calls

    def _find_unused_keywords(
        self,
        keywords: dict[str, list[int]],
        calls: set[str],
        test_file: TestFile
    ) -> list[Finding]:
        """Find keywords that are never called."""
        findings = []

        for keyword_name, line_numbers in keywords.items():
            if keyword_name not in calls:
                # Skip special keywords
                if keyword_name in {'suite setup', 'suite teardown', 'test setup', 'test teardown'}:
                    continue

                pattern = Pattern(
                    type=PatternType.UNUSED_KEYWORD,
                    name="Unused Keyword",
                    description=f"Keyword '{keyword_name}' is never called",
                    recommendation="Remove this keyword or use it in your tests",
                    auto_fixable=True
                )

                finding = Finding.create(
                    pattern=pattern,
                    severity=Severity.WARNING,
                    location=Location(file_path=test_file.path, line=line_numbers[0]),
                    message=f"Keyword '{keyword_name}' is defined but never used"
                )
                findings.append(finding)

        return findings

    def _find_duplicate_keywords(
        self,
        keywords: dict[str, list[int]],
        test_file: TestFile
    ) -> list[Finding]:
        """Find keywords defined multiple times."""
        findings = []

        for keyword_name, line_numbers in keywords.items():
            if len(line_numbers) > 1:
                pattern = Pattern.duplicate_keyword(keyword_name)

                # Create findings for all duplicates after the first
                for line_num in line_numbers[1:]:
                    finding = Finding.create(
                        pattern=pattern,
                        severity=Severity.ERROR,
                        location=Location(file_path=test_file.path, line=line_num),
                        message=f"Keyword '{keyword_name}' is already defined at line {line_numbers[0]}",
                        first_definition_line=line_numbers[0],
                        duplicate_count=len(line_numbers)
                    )
                    findings.append(finding)

        return findings

    def _find_unreachable_code(self, test_file: TestFile) -> list[Finding]:
        """Find code after RETURN statements."""
        findings = []
        lines = test_file.content.splitlines()

        in_keyword = False
        found_return = False
        current_keyword = None

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            # Track keyword boundaries
            if not line.startswith((' ', '\t')) and stripped:
                in_keyword = False
                found_return = False
                if '***' not in line:
                    current_keyword = stripped
                    in_keyword = True

            # Check for RETURN
            if in_keyword and stripped.upper().startswith('RETURN'):
                found_return = True
                continue

            # Check for code after RETURN
            if found_return and in_keyword and stripped and not stripped.startswith('#'):
                pattern = Pattern(
                    type=PatternType.UNREACHABLE_CODE,
                    name="Unreachable Code",
                    description="Code after RETURN statement will never execute",
                    recommendation="Remove the unreachable code or move it before RETURN",
                    auto_fixable=True
                )

                finding = Finding.create(
                    pattern=pattern,
                    severity=Severity.WARNING,
                    location=Location(file_path=test_file.path, line=line_num),
                    message=f"Unreachable code after RETURN in keyword '{current_keyword}'",
                    keyword_name=current_keyword
                )
                findings.append(finding)

                # Only report first line of unreachable code per keyword
                found_return = False

        return findings
