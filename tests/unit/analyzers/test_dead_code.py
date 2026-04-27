# tests/unit/analyzers/test_dead_code.py
"""Unit tests for DeadCodeAnalyzer.

Comprehensive tests for dead code detection including unused keywords,
duplicates, and edge cases.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from robot_optimizer_core.analyzers import DeadCodeAnalyzer
from robot_optimizer_core.domain.entities import TestFile
from robot_optimizer_core.domain.value_objects import PatternType, Severity


@pytest.mark.unit
class TestDeadCodeAnalyzer:
    """Test the DeadCodeAnalyzer."""

    @pytest.fixture
    def analyzer(self) -> DeadCodeAnalyzer:
        """Create analyzer instance."""
        return DeadCodeAnalyzer()

    def test_analyzer_properties(self, analyzer: DeadCodeAnalyzer) -> None:
        """Test analyzer metadata properties."""
        assert analyzer.name == "dead_code"
        assert analyzer.description == "Finds unused keywords and duplicate definitions"
        assert analyzer.tags == ["keywords", "maintenance", "cleanup"]
        assert analyzer.supports_auto_fix is True
        assert analyzer.version == "1.0.0"

    def test_find_unused_keyword(self, analyzer: DeadCodeAnalyzer) -> None:
        """Test detection of unused keywords."""
        content = """*** Test Cases ***
Test Case 1
    Used Keyword
    
*** Keywords ***
Used Keyword
    Log    This is used
    
Unused Keyword
    Log    This is never called
    
Another Unused
    [Documentation]    Also not used
    Log    Never executed
"""

        test_file = TestFile(
            path=Path("test.robot"),
            content=content,
            size_bytes=len(content),
            last_modified_utc=datetime.now()
        )

        findings = analyzer.analyze(test_file)

        # Should find 2 unused keywords
        unused_findings = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert len(unused_findings) == 2

        # Check the findings
        keyword_names = [f.context.get("keyword_name") for f in unused_findings]
        assert "Unused Keyword" in keyword_names
        assert "Another Unused" in keyword_names

        # Check severity and properties
        for finding in unused_findings:
            assert finding.severity == Severity.WARNING
            assert finding.is_auto_fixable is True
            assert "never used" in finding.message.lower()

    def test_find_duplicate_keywords(self, analyzer: DeadCodeAnalyzer) -> None:
        """Test detection of duplicate keyword definitions."""
        content = """*** Keywords ***
Login User
    [Arguments]    ${username}    ${password}
    Input Text    id=user    ${username}
    Input Text    id=pass    ${password}
    
Do Something
    Log    First implementation
    
Login User
    [Documentation]    Duplicate definition
    Log    Different implementation
    
Do Something
    Log    Second implementation
"""

        test_file = TestFile(
            path=Path("test.robot"),
            content=content,
            size_bytes=len(content),
            last_modified_utc=datetime.now()
        )

        findings = analyzer.analyze(test_file)

        # Should find duplicates
        dup_findings = [f for f in findings if f.pattern.type == PatternType.DUPLICATE_KEYWORD]
        assert len(dup_findings) >= 2  # At least one finding per duplicate

        # Check severity
        for finding in dup_findings:
            assert finding.severity == Severity.ERROR
            assert not finding.is_auto_fixable  # Can't auto-fix duplicates

    def test_keyword_used_in_same_keyword(self, analyzer: DeadCodeAnalyzer) -> None:
        """Test that self-recursion is detected correctly."""
        content = """*** Keywords ***
Recursive Keyword
    Log    Before recursion
    Recursive Keyword
    Log    After recursion
    
Normal Keyword
    Log    Just logging
"""

        test_file = TestFile(
            path=Path("test.robot"),
            content=content,
            size_bytes=len(content),
            last_modified_utc=datetime.now()
        )

        findings = analyzer.analyze(test_file)

        # Recursive keyword is "used" (by itself) so not unused
        # Normal keyword is unused
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert len(unused) == 1
        assert unused[0].context["keyword_name"] == "Normal Keyword"

    def test_builtin_keywords_ignored(self, analyzer: DeadCodeAnalyzer) -> None:
        """Test that built-in keywords are not flagged as unused."""
        content = """*** Test Cases ***
Test With Builtins
    Log    Message
    Should Be Equal    1    1
    Run Keyword If    True    Log    Conditional
    Sleep    1s
    
*** Keywords ***
My Keyword
    Log To Console    Testing
"""

        test_file = TestFile(
            path=Path("test.robot"),
            content=content,
            size_bytes=len(content),
            last_modified_utc=datetime.now()
        )

        findings = analyzer.analyze(test_file)

        # My Keyword is unused, but builtins should be ignored
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert len(unused) == 1
        assert unused[0].context["keyword_name"] == "My Keyword"

    def test_library_keywords_ignored(self, analyzer: DeadCodeAnalyzer) -> None:
        """Test that library keywords (with dots) are ignored."""
        content = """*** Test Cases ***
Test With Library Keywords
    SeleniumLibrary.Open Browser    http://example.com    chrome
    BuiltIn.Log    Using library prefix
    Collections.Append To List    ${list}    item
    
*** Keywords ***
Local Keyword
    Log    Not used anywhere
"""

        test_file = TestFile(
            path=Path("test.robot"),
            content=content,
            size_bytes=len(content),
            last_modified_utc=datetime.now()
        )

        findings = analyzer.analyze(test_file)

        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert len(unused) == 1
        assert unused[0].context["keyword_name"] == "Local Keyword"

    def test_bdd_keywords_ignored(self, analyzer: DeadCodeAnalyzer) -> None:
        """Test that BDD-style keywords are handled correctly."""
        content = """*** Test Cases ***
BDD Test
    Given system is ready
    When user performs action
    Then result should be visible
    And another condition is met
    But exception should not occur
    
*** Keywords ***
system is ready
    Log    Setup done
    
user performs action
    Log    Action performed
    
result should be visible
    Log    Checking result
    
another condition is met
    Log    Additional check
    
exception should not occur
    Log    No exceptions
"""

        test_file = TestFile(
            path=Path("test.robot"),
            content=content,
            size_bytes=len(content),
            last_modified_utc=datetime.now()
        )

        findings = analyzer.analyze(test_file)

        # All keywords are used with BDD prefixes, so none should be unused
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert len(unused) == 0

    def test_configuration_options(self) -> None:
        """Test analyzer configuration options."""
        # Disable unused keyword check
        analyzer = DeadCodeAnalyzer(config={"check_unused": False})

        content = """*** Keywords ***
Unused Keyword
    Log    Not used
    
Duplicate
    Log    First
    
Duplicate
    Log    Second
"""

        test_file = TestFile(
            path=Path("test.robot"),
            content=content,
            size_bytes=len(content),
            last_modified_utc=datetime.now()
        )

        findings = analyzer.analyze(test_file)

        # Should only find duplicates, not unused
        assert all(f.pattern.type == PatternType.DUPLICATE_KEYWORD for f in findings)

        # Disable duplicate check
        analyzer2 = DeadCodeAnalyzer(config={"check_duplicates": False})
        findings2 = analyzer2.analyze(test_file)

        # Should only find unused, not duplicates
        assert all(f.pattern.type == PatternType.UNUSED_KEYWORD for f in findings2)

    def test_ignore_patterns(self) -> None:
        """Test ignoring keywords by pattern."""
        analyzer = DeadCodeAnalyzer(config={
            "ignore_patterns": ["^Test.*", ".*Helper$"]
        })

        content = """*** Keywords ***
Test Setup Keyword
    Log    Would be unused but ignored
    
Database Helper
    Log    Also ignored
    
Normal Unused Keyword
    Log    This should be detected
"""

        test_file = TestFile(
            path=Path("test.robot"),
            content=content,
            size_bytes=len(content),
            last_modified_utc=datetime.now()
        )

        findings = analyzer.analyze(test_file)

        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert len(unused) == 1
        assert unused[0].context["keyword_name"] == "Normal Unused Keyword"

    def test_edge_cases(self, analyzer: DeadCodeAnalyzer) -> None:
        """Test edge cases and malformed content."""
        # Empty file
        empty_file = TestFile(
            path=Path("empty.robot"),
            content="",
            size_bytes=0,
            last_modified_utc=datetime.now()
        )
        findings = analyzer.analyze(empty_file)
        assert len(findings) == 0

        # No keywords section
        no_keywords = TestFile(
            path=Path("no_keywords.robot"),
            content="*** Test Cases ***\nTest\n    Log    Hi",
            size_bytes=100,
            last_modified_utc=datetime.now()
        )
        findings = analyzer.analyze(no_keywords)
        assert len(findings) == 0

        # Malformed keyword names
        malformed = TestFile(
            path=Path("malformed.robot"),
            content="""*** Keywords ***
123 Invalid Start With Number
    Log    Won't be detected
    
    
    Log    Indented line without keyword
    
Valid Keyword Name
    Log    This is fine but unused
""",
            size_bytes=200,
            last_modified_utc=datetime.now()
        )
        findings = analyzer.analyze(malformed)

        # Should only find the valid keyword as unused
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert len(unused) == 1
        assert unused[0].context["keyword_name"] == "Valid Keyword Name"

    def test_case_sensitivity(self, analyzer: DeadCodeAnalyzer) -> None:
        """Test that keyword usage is case-sensitive."""
        content = """*** Test Cases ***
Test
    my keyword    # lowercase usage
    
*** Keywords ***
My Keyword
    Log    Mixed case definition
"""

        test_file = TestFile(
            path=Path("test.robot"),
            content=content,
            size_bytes=len(content),
            last_modified_utc=datetime.now()
        )

        findings = analyzer.analyze(test_file)

        # Robot Framework is case-insensitive, so keyword should be considered used
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert len(unused) == 0

    def test_complex_keyword_usage(self, analyzer: DeadCodeAnalyzer) -> None:
        """Test detection with complex keyword usage patterns."""
        content = """*** Test Cases ***
Complex Test
    Run Keyword    Dynamic Keyword Name
    Run Keywords    Keyword One    AND    Keyword Two
    
*** Keywords ***
Dynamic Keyword Name
    Log    Called dynamically
    
Keyword One
    Log    First
    
Keyword Two  
    Log    Second
    
Static Unused
    Log    Not called
"""

        test_file = TestFile(
            path=Path("test.robot"),
            content=content,
            size_bytes=len(content),
            last_modified_utc=datetime.now()
        )

        findings = analyzer.analyze(test_file)

        # All keywords except "Static Unused" are used
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert len(unused) == 1
        assert unused[0].context["keyword_name"] == "Static Unused"
