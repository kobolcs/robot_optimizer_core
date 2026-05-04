# tests/unit/domain/value_objects/test_pattern.py
"""Unit tests for Pattern value object.

Comprehensive tests for Pattern and PatternType to ensure complete coverage
and mutation testing resilience.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from robot_optimizer_core.domain.value_objects import Pattern, PatternType


@pytest.mark.unit
class TestPatternType:
    """Test the PatternType enum."""

    def test_pattern_type_categories(self) -> None:
        """Test that all pattern types exist and are categorized."""
        # Keyword patterns
        assert PatternType.DUPLICATE_KEYWORD
        assert PatternType.UNUSED_KEYWORD
        assert PatternType.COMPLEX_KEYWORD
        assert PatternType.MISSING_DOCUMENTATION

        # Wait patterns
        assert PatternType.SLEEP_IN_TEST
        assert PatternType.HARD_CODED_WAIT
        assert PatternType.INEFFICIENT_WAIT

        # Locator patterns
        assert PatternType.FRAGILE_XPATH
        assert PatternType.ABSOLUTE_XPATH
        assert PatternType.COMPLEX_CSS
        assert PatternType.ID_OVER_XPATH

        # Structure patterns
        assert PatternType.LONG_TEST_CASE
        assert PatternType.NO_TAGS
        assert PatternType.DUPLICATE_TEST
        assert PatternType.MISSING_SETUP_TEARDOWN

        # Variable patterns
        assert PatternType.HARDCODED_VALUE
        assert PatternType.UNUSED_VARIABLE
        assert PatternType.GLOBAL_VARIABLE_MISUSE

        # Import patterns
        assert PatternType.UNUSED_IMPORT
        assert PatternType.WILDCARD_IMPORT
        assert PatternType.CIRCULAR_IMPORT

    def test_pattern_type_names(self) -> None:
        """Test pattern type string representations."""
        assert PatternType.DUPLICATE_KEYWORD.name == "DUPLICATE_KEYWORD"
        assert PatternType.SLEEP_IN_TEST.name == "SLEEP_IN_TEST"
        assert PatternType.FRAGILE_XPATH.name == "FRAGILE_XPATH"


@pytest.mark.unit
class TestPattern:
    """Test the Pattern value object."""

    def test_pattern_type_classvar_uses_builtin_type(self) -> None:
        """Regression test: class-level PatternType alias remains usable."""
        assert Pattern.PatternType is PatternType
        assert Pattern.PatternType.SLEEP_IN_TEST is PatternType.SLEEP_IN_TEST

    def test_create_pattern(self) -> None:
        """Test creating a basic pattern."""
        pattern = Pattern(
            type=PatternType.DUPLICATE_KEYWORD,
            name="Duplicate Keyword Definition",
            description="Found duplicate keyword 'Login'",
            recommendation="Remove duplicate definitions or consolidate",
        )

        assert pattern.type == PatternType.DUPLICATE_KEYWORD
        assert pattern.name == "Duplicate Keyword Definition"
        assert pattern.description == "Found duplicate keyword 'Login'"
        assert pattern.recommendation == "Remove duplicate definitions or consolidate"
        assert pattern.documentation_url is None
        assert pattern.auto_fixable is False

    def test_create_pattern_with_all_fields(self) -> None:
        """Test creating pattern with optional fields."""
        pattern = Pattern(
            type=PatternType.SLEEP_IN_TEST,
            name="Sleep in Test",
            description="Sleep usage detected",
            recommendation="Use explicit waits",
            documentation_url="https://docs.example.com/waits",
            auto_fixable=True,
        )

        assert pattern.documentation_url == "https://docs.example.com/waits"
        assert pattern.auto_fixable is True

    def test_pattern_validation(self) -> None:
        """Test pattern field validation."""
        # Empty name
        with pytest.raises(ValidationError) as exc_info:
            Pattern(
                type=PatternType.DUPLICATE_KEYWORD,
                name="",
                description="Description",
                recommendation="Recommendation",
            )
        assert "at least 1 character" in str(exc_info.value)

        # Whitespace-only name
        with pytest.raises(ValidationError) as exc_info:
            Pattern(
                type=PatternType.DUPLICATE_KEYWORD,
                name="   ",
                description="Description",
                recommendation="Recommendation",
            )
        assert "Field cannot be empty" in str(exc_info.value)

        # Empty description
        with pytest.raises(ValidationError):
            Pattern(
                type=PatternType.DUPLICATE_KEYWORD,
                name="Name",
                description="",
                recommendation="Recommendation",
            )

        # Empty recommendation
        with pytest.raises(ValidationError):
            Pattern(
                type=PatternType.DUPLICATE_KEYWORD,
                name="Name",
                description="Description",
                recommendation="   ",
            )

    def test_duplicate_keyword_factory(self) -> None:
        """Test the duplicate keyword factory method."""
        pattern = Pattern.duplicate_keyword("Login With Credentials")

        assert pattern.type == PatternType.DUPLICATE_KEYWORD
        assert pattern.name == "Duplicate Keyword Definition"
        assert "Login With Credentials" in pattern.description
        assert "multiple times" in pattern.description
        assert "Remove duplicate" in pattern.recommendation
        assert pattern.auto_fixable is False
        assert pattern.documentation_url is None

    def test_sleep_in_test_factory(self) -> None:
        """Test the sleep in test factory method."""
        pattern = Pattern.sleep_in_test("5 seconds")

        assert pattern.type == PatternType.SLEEP_IN_TEST
        assert pattern.name == "Sleep in Test Case"
        assert "Sleep 5 seconds" in pattern.description
        assert "slow and fragile" in pattern.description
        assert "explicit waits" in pattern.recommendation
        assert pattern.auto_fixable is True
        assert pattern.documentation_url is not None
        assert "Wait%20Until%20Keyword%20Succeeds" in pattern.documentation_url

    def test_fragile_xpath_factory(self) -> None:
        """Test the fragile XPath factory method."""
        xpath = "//div[3]/table[1]/tbody/tr[2]/td[5]"
        pattern = Pattern.fragile_xpath(xpath)

        assert pattern.type == PatternType.FRAGILE_XPATH
        assert pattern.name == "Fragile XPath Selector"
        assert xpath in pattern.description
        assert "positional indices" in pattern.description
        assert "stable attributes" in pattern.recommendation
        assert "@id" in pattern.recommendation
        assert pattern.auto_fixable is False

    def test_long_test_case_factory(self) -> None:
        """Test the long test case factory method."""
        # Default threshold
        pattern1 = Pattern.long_test_case(75)
        assert pattern1.type == PatternType.LONG_TEST_CASE
        assert pattern1.name == "Long Test Case"
        assert "75 lines" in pattern1.description
        assert "threshold: 50" in pattern1.description
        assert "smaller, focused test cases" in pattern1.recommendation
        assert pattern1.auto_fixable is False

        # Custom threshold
        pattern2 = Pattern.long_test_case(100, threshold=80)
        assert "100 lines" in pattern2.description
        assert "threshold: 80" in pattern2.description

    def test_pattern_category(self) -> None:
        """Test pattern category classification."""
        # Keywords category
        assert Pattern.duplicate_keyword("Test").category == "Keywords"
        assert (
            Pattern(
                type=PatternType.UNUSED_KEYWORD,
                name="Unused",
                description="Desc",
                recommendation="Rec",
            ).category
            == "Keywords"
        )

        # Waits category
        assert Pattern.sleep_in_test("1s").category == "Waits"
        assert (
            Pattern(
                type=PatternType.INEFFICIENT_WAIT,
                name="Bad Wait",
                description="Desc",
                recommendation="Rec",
            ).category
            == "Waits"
        )

        # Locators category
        assert Pattern.fragile_xpath("//div").category == "Locators"
        assert (
            Pattern(
                type=PatternType.COMPLEX_CSS,
                name="Complex CSS",
                description="Desc",
                recommendation="Rec",
            ).category
            == "Locators"
        )

        # Structure category
        assert Pattern.long_test_case(100).category == "Structure"
        assert (
            Pattern(
                type=PatternType.NO_TAGS,
                name="No Tags",
                description="Desc",
                recommendation="Rec",
            ).category
            == "Structure"
        )

        # Variables category
        assert (
            Pattern(
                type=PatternType.HARDCODED_VALUE,
                name="Hardcoded",
                description="Desc",
                recommendation="Rec",
            ).category
            == "Variables"
        )

        # Imports category
        assert (
            Pattern(
                type=PatternType.WILDCARD_IMPORT,
                name="Wildcard",
                description="Desc",
                recommendation="Rec",
            ).category
            == "Imports"
        )

    def test_all_pattern_types_have_categories(self) -> None:
        """Ensure all pattern types have defined categories."""
        for pattern_type in PatternType:
            pattern = Pattern(
                type=pattern_type,
                name=f"Test {pattern_type.name}",
                description="Test description",
                recommendation="Test recommendation",
            )
            # All should have proper categories, not "Other"
            assert pattern.category in [
                "Keywords",
                "Waits",
                "Locators",
                "Structure",
                "Variables",
                "Imports",
            ]
            assert pattern.category != "Other"

    def test_pattern_equality(self) -> None:
        """Test pattern equality comparison."""
        p1 = Pattern.duplicate_keyword("Login")
        p2 = Pattern.duplicate_keyword("Login")
        p3 = Pattern.duplicate_keyword("Logout")
        p4 = Pattern.sleep_in_test("1s")

        # Same factory calls produce equal patterns
        assert p1 == p2
        assert hash(p1) == hash(p2)

        # Different keyword names
        assert p1 != p3
        assert hash(p1) != hash(p3)

        # Different pattern types
        assert p1 != p4
        assert hash(p1) != hash(p4)

        # Different type comparison
        assert p1 != "pattern"
        assert p1 != 42

    def test_pattern_immutability(self) -> None:
        """Test that patterns are immutable."""
        pattern = Pattern.duplicate_keyword("Test")

        with pytest.raises(ValidationError):
            pattern.name = "New Name"

        with pytest.raises(ValidationError):
            pattern.auto_fixable = True

        with pytest.raises(ValidationError):
            pattern.type = PatternType.SLEEP_IN_TEST

    def test_pattern_whitespace_stripping(self) -> None:
        """Test that string fields are stripped of whitespace."""
        pattern = Pattern(
            type=PatternType.DUPLICATE_KEYWORD,
            name="  Duplicate Keyword  ",
            description="  Found duplicate  ",
            recommendation="  Remove it  ",
        )

        assert pattern.name == "Duplicate Keyword"
        assert pattern.description == "Found duplicate"
        assert pattern.recommendation == "Remove it"
