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
            last_modified_utc=datetime.now(),
        )

        findings = analyzer.analyze(test_file)

        # Should find 2 unused keywords
        unused_findings = [
            f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD
        ]
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

    def test_extract_keywords_and_calls_returns_three_values(
        self, analyzer: DeadCodeAnalyzer
    ) -> None:
        """Regression test for display-name refactor tuple shape."""
        content = """*** Test Cases ***
Case
    My Keyword

*** Keywords ***
My Keyword
    No Operation
"""
        test_file = TestFile(
            path=Path("test.robot"),
            content=content,
            size_bytes=len(content),
            last_modified_utc=datetime.now(),
        )

        keywords, calls, display_names = analyzer._extract_keywords_and_calls(test_file)

        assert isinstance(keywords, dict)
        assert isinstance(calls, set)
        assert isinstance(display_names, dict)
        assert "my keyword" in display_names
        assert display_names["my keyword"] == "My Keyword"

    def test_unused_keyword_preserves_original_display_case(
        self, analyzer: DeadCodeAnalyzer
    ) -> None:
        content = """*** Keywords ***
MiXeD Case Keyword
    No Operation
"""
        test_file = TestFile(
            path=Path("test.robot"),
            content=content,
            size_bytes=len(content),
            last_modified_utc=datetime.now(),
        )

        findings = analyzer.analyze(test_file)
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]

        assert len(unused) == 1
        assert unused[0].context["keyword_name"] == "MiXeD Case Keyword"
        assert "MiXeD Case Keyword" in unused[0].message

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
            last_modified_utc=datetime.now(),
        )

        findings = analyzer.analyze(test_file)

        # Should find duplicates
        dup_findings = [
            f for f in findings if f.pattern.type == PatternType.DUPLICATE_KEYWORD
        ]
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
            last_modified_utc=datetime.now(),
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
            last_modified_utc=datetime.now(),
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
            last_modified_utc=datetime.now(),
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
            last_modified_utc=datetime.now(),
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
            last_modified_utc=datetime.now(),
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
        analyzer = DeadCodeAnalyzer(
            config={"ignore_patterns": ["^Test.*", ".*Helper$"]}
        )

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
            last_modified_utc=datetime.now(),
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
            last_modified_utc=datetime.now(),
        )
        findings = analyzer.analyze(empty_file)
        assert len(findings) == 0

        # No keywords section
        no_keywords = TestFile(
            path=Path("no_keywords.robot"),
            content="*** Test Cases ***\nTest\n    Log    Hi",
            size_bytes=100,
            last_modified_utc=datetime.now(),
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
            last_modified_utc=datetime.now(),
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
            last_modified_utc=datetime.now(),
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
            last_modified_utc=datetime.now(),
        )

        findings = analyzer.analyze(test_file)

        # All keywords except "Static Unused" are used
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert len(unused) == 1
        assert unused[0].context["keyword_name"] == "Static Unused"


@pytest.mark.unit
class TestDeadCodeAnalyzerASTExtraction:
    """Tests covering the AST-based keyword/call extraction paths."""

    @pytest.fixture
    def analyzer(self) -> DeadCodeAnalyzer:
        return DeadCodeAnalyzer()

    def _make(self, content: str) -> TestFile:
        return TestFile(
            path=Path("test.robot"),
            content=content,
            size_bytes=len(content),
            last_modified_utc=datetime.now(),
        )

    def test_test_case_setup_keyword_not_flagged(
        self, analyzer: DeadCodeAnalyzer
    ) -> None:
        """A keyword used only in [Setup] must not appear in unused findings."""
        content = (
            "*** Test Cases ***\n"
            "My Test\n"
            "    [Setup]    My Setup Keyword\n"
            "    Log    body\n"
            "\n"
            "*** Keywords ***\n"
            "My Setup Keyword\n"
            "    Log    setup done\n"
        )
        findings = analyzer.analyze(self._make(content))
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        names = [f.context["keyword_name"] for f in unused]
        assert "My Setup Keyword" not in names

    def test_test_case_teardown_keyword_not_flagged(
        self, analyzer: DeadCodeAnalyzer
    ) -> None:
        """A keyword used only in [Teardown] must not appear in unused findings."""
        content = (
            "*** Test Cases ***\n"
            "My Test\n"
            "    Log    body\n"
            "    [Teardown]    My Teardown Keyword\n"
            "\n"
            "*** Keywords ***\n"
            "My Teardown Keyword\n"
            "    Log    teardown done\n"
        )
        findings = analyzer.analyze(self._make(content))
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        names = [f.context["keyword_name"] for f in unused]
        assert "My Teardown Keyword" not in names

    def test_if_block_call_not_flagged(self, analyzer: DeadCodeAnalyzer) -> None:
        """A keyword called only inside an IF block must not be flagged."""
        content = (
            "*** Test Cases ***\n"
            "My Test\n"
            "    IF    ${condition}\n"
            "        My Conditional Keyword\n"
            "    END\n"
            "\n"
            "*** Keywords ***\n"
            "My Conditional Keyword\n"
            "    Log    conditional\n"
        )
        findings = analyzer.analyze(self._make(content))
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert len(unused) == 0

    def test_for_loop_call_not_flagged(self, analyzer: DeadCodeAnalyzer) -> None:
        """A keyword called only inside a FOR loop must not be flagged."""
        content = (
            "*** Test Cases ***\n"
            "My Test\n"
            "    FOR    ${i}    IN RANGE    3\n"
            "        My Loop Keyword\n"
            "    END\n"
            "\n"
            "*** Keywords ***\n"
            "My Loop Keyword\n"
            "    Log    iteration\n"
        )
        findings = analyzer.analyze(self._make(content))
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert len(unused) == 0

    def test_else_branch_call_not_flagged(self, analyzer: DeadCodeAnalyzer) -> None:
        """A keyword called only in an ELSE branch must not be flagged."""
        content = (
            "*** Test Cases ***\n"
            "My Test\n"
            "    IF    ${flag}\n"
            "        Log    true branch\n"
            "    ELSE\n"
            "        My Else Keyword\n"
            "    END\n"
            "\n"
            "*** Keywords ***\n"
            "My Else Keyword\n"
            "    Log    else path\n"
        )
        findings = analyzer.analyze(self._make(content))
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert len(unused) == 0

    def test_ast_extraction_still_catches_truly_unused_keywords(
        self, analyzer: DeadCodeAnalyzer
    ) -> None:
        """AST path must still flag keywords that are genuinely not called."""
        content = (
            "*** Test Cases ***\n"
            "My Test\n"
            "    [Setup]    Used In Setup\n"
            "    IF    ${x}\n"
            "        Used In If\n"
            "    END\n"
            "\n"
            "*** Keywords ***\n"
            "Used In Setup\n"
            "    Log    a\n"
            "\n"
            "Used In If\n"
            "    Log    b\n"
            "\n"
            "Truly Unused\n"
            "    Log    nobody calls me\n"
        )
        findings = analyzer.analyze(self._make(content))
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert len(unused) == 1
        assert unused[0].context["keyword_name"] == "Truly Unused"


@pytest.mark.unit
class TestDeadCodeAnalyzerSuite:
    """Cross-file (suite-level) analysis via analyze_suite."""

    def _make(self, path: str, content: str) -> TestFile:
        return TestFile(
            path=Path(path),
            content=content,
            size_bytes=len(content),
            last_modified_utc=datetime.now(),
        )

    def test_empty_suite_returns_no_findings(self) -> None:
        assert DeadCodeAnalyzer().analyze_suite([]) == []

    def test_keyword_used_in_another_file_is_not_flagged(self) -> None:
        keywords_file = self._make(
            "keywords.robot",
            "*** Keywords ***\nShared Keyword\n    Log    shared\n",
        )
        tests_file = self._make(
            "tests.robot",
            "*** Test Cases ***\nMy Test\n    Shared Keyword\n",
        )
        findings = DeadCodeAnalyzer().analyze_suite([keywords_file, tests_file])
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert not any(f.context["keyword_name"] == "Shared Keyword" for f in unused)

    def test_keyword_unused_across_all_files_is_flagged(self) -> None:
        keywords_file = self._make(
            "keywords.robot",
            "*** Keywords ***\nNever Used\n    Log    dead\n",
        )
        tests_file = self._make(
            "tests.robot",
            "*** Test Cases ***\nMy Test\n    Log    hello\n",
        )
        findings = DeadCodeAnalyzer().analyze_suite([keywords_file, tests_file])
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert any(f.context["keyword_name"] == "Never Used" for f in unused)

    def test_keyword_used_only_within_same_file_not_flagged(self) -> None:
        """Single-file self-call should suppress unused report suite-wide too."""
        content = (
            "*** Test Cases ***\nT\n    Local KW\n"
            "*** Keywords ***\nLocal KW\n    Log    ok\n"
        )
        file_ = self._make("solo.robot", content)
        findings = DeadCodeAnalyzer().analyze_suite([file_])
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert not any(f.context["keyword_name"] == "Local KW" for f in unused)

    def test_duplicate_still_reported_suite_wide(self) -> None:
        content = (
            "*** Keywords ***\nDuplicate KW\n    Log    first\n\n"
            "Duplicate KW\n    Log    second\n"
        )
        file_ = self._make("dups.robot", content)
        findings = DeadCodeAnalyzer().analyze_suite([file_])
        assert any(f.pattern.type == PatternType.DUPLICATE_KEYWORD for f in findings)

    def test_lifecycle_keywords_not_flagged_suite_wide(self) -> None:
        content = "*** Keywords ***\nSuite Setup\n    Log    setup\n"
        file_ = self._make("lifecycle.robot", content)
        findings = DeadCodeAnalyzer().analyze_suite([file_])
        unused = [f for f in findings if f.pattern.type == PatternType.UNUSED_KEYWORD]
        assert not any("suite setup" in f.message.lower() for f in unused)

    def test_return_in_test_case_not_flagged_as_unreachable(self) -> None:
        """RETURN inside *** Test Cases *** must never be treated as unreachable code."""
        content = """*** Test Cases ***
My Test
    Log    before
    RETURN
    Log    after RETURN in test case

*** Keywords ***
My Keyword
    Log    keyword body
    RETURN
    Log    this IS unreachable
"""
        file_ = self._make("mixed.robot", content)
        findings = DeadCodeAnalyzer().analyze_suite([file_])
        unreachable = [
            f for f in findings if f.pattern.type == PatternType.UNREACHABLE_CODE
        ]
        # Only one finding: the keyword body, not the test case body
        assert len(unreachable) == 1
        assert "My Keyword" in unreachable[0].message
