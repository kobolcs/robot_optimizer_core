# src/robot_optimizer_core/domain/value_objects/pattern.py
"""Pattern value object for representing optimization patterns."""

import builtins
from enum import Enum, auto
from typing import ClassVar

from pydantic import ConfigDict, Field, field_validator

from ..base import ValueObject


class PatternType(Enum):
    """Types of optimization patterns."""

    # Keyword patterns
    DUPLICATE_KEYWORD = auto()
    UNUSED_KEYWORD = auto()
    COMPLEX_KEYWORD = auto()
    MISSING_DOCUMENTATION = auto()
    CAMEL_CASE_NAME = auto()

    # Wait patterns
    SLEEP_IN_TEST = auto()
    HARD_CODED_WAIT = auto()
    INEFFICIENT_WAIT = auto()

    # Locator patterns
    FRAGILE_XPATH = auto()
    ABSOLUTE_XPATH = auto()
    COMPLEX_CSS = auto()
    ID_OVER_XPATH = auto()

    # Structure patterns
    LONG_TEST_CASE = auto()
    NO_TAGS = auto()
    SINGLETON_TAG = auto()
    RESERVED_TAG = auto()
    DUPLICATE_TEST = auto()
    MISSING_SETUP_TEARDOWN = auto()
    UNREACHABLE_CODE = auto()

    # Variable patterns
    HARDCODED_VALUE = auto()
    UNUSED_VARIABLE = auto()
    GLOBAL_VARIABLE_MISUSE = auto()

    # Import patterns
    UNUSED_IMPORT = auto()
    WILDCARD_IMPORT = auto()
    CIRCULAR_IMPORT = auto()


class Pattern(ValueObject):
    """Represents an optimization pattern that was matched."""

    model_config = ConfigDict(use_enum_values=False)

    # Backward-compatible nested enum access: Pattern.PatternType.X
    PatternType: ClassVar[builtins.type[PatternType]] = PatternType

    type: PatternType = Field(..., description="Type of pattern")  # type: ignore[valid-type]
    name: str = Field(..., min_length=1, description="Pattern name")
    description: str = Field(..., min_length=1, description="Pattern description")
    recommendation: str = Field(
        ..., min_length=1, description="Recommendation for fixing"
    )
    documentation_url: str | None = Field(None, description="URL to documentation")
    auto_fixable: bool = Field(False, description="Whether this can be auto-fixed")

    @field_validator("name", "description", "recommendation", mode="before")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        """Ensure string fields are not empty."""
        if v == "":
            return v
        if not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

    @classmethod
    def duplicate_keyword(cls, keyword_name: str) -> "Pattern":
        """Create a pattern for duplicate keyword detection."""
        return cls(
            type=PatternType.DUPLICATE_KEYWORD,
            name="Duplicate Keyword Definition",
            description=(f"Keyword '{keyword_name}' is defined multiple times"),
            recommendation=(
                "Remove duplicate definitions or consolidate into a single keyword"
            ),
            documentation_url=None,
            auto_fixable=False,
        )

    @classmethod
    def sleep_in_test(cls, sleep_duration: str) -> "Pattern":
        """Create a pattern for sleep usage in tests."""
        return cls(
            type=PatternType.SLEEP_IN_TEST,
            name="Sleep in Test Case",
            description=(
                f"Test uses 'Sleep {sleep_duration}' which makes tests slow and fragile"
            ),
            recommendation=(
                "Replace with explicit waits (Wait Until Element Is Visible, etc.)"
            ),
            documentation_url=(
                "https://robotframework.org/robotframework/latest/"
                "libraries/BuiltIn.html#Wait%20Until%20Keyword%20Succeeds"
            ),
            auto_fixable=True,
        )

    @classmethod
    def fragile_xpath(cls, xpath: str) -> "Pattern":
        """Create a pattern for fragile XPath detection."""
        return cls(
            type=PatternType.FRAGILE_XPATH,
            name="Fragile XPath Selector",
            description=(f"XPath '{xpath}' uses positional indices which break easily"),
            recommendation=(
                "Use more stable attributes like @id, @class, or @data-testid"
            ),
            documentation_url=None,
            auto_fixable=False,
        )

    @classmethod
    def long_test_case(cls, line_count: int, threshold: int = 50) -> "Pattern":
        """Create a pattern for overly long test cases."""
        return cls(
            type=PatternType.LONG_TEST_CASE,
            name="Long Test Case",
            description=(f"Test case has {line_count} lines (threshold: {threshold})"),
            recommendation=(
                "Break down into smaller, focused test cases or "
                "extract common steps into keywords"
            ),
            documentation_url=None,
            auto_fixable=False,
        )

    @property
    def category(self) -> str:
        """Get the category of this pattern type."""
        categories = {
            PatternType.DUPLICATE_KEYWORD: "Keywords",
            PatternType.UNUSED_KEYWORD: "Keywords",
            PatternType.COMPLEX_KEYWORD: "Keywords",
            PatternType.MISSING_DOCUMENTATION: "Keywords",
            PatternType.CAMEL_CASE_NAME: "Naming",
            PatternType.SLEEP_IN_TEST: "Waits",
            PatternType.HARD_CODED_WAIT: "Waits",
            PatternType.INEFFICIENT_WAIT: "Waits",
            PatternType.FRAGILE_XPATH: "Locators",
            PatternType.ABSOLUTE_XPATH: "Locators",
            PatternType.COMPLEX_CSS: "Locators",
            PatternType.ID_OVER_XPATH: "Locators",
            PatternType.LONG_TEST_CASE: "Structure",
            PatternType.NO_TAGS: "Structure",
            PatternType.SINGLETON_TAG: "Structure",
            PatternType.RESERVED_TAG: "Structure",
            PatternType.DUPLICATE_TEST: "Structure",
            PatternType.MISSING_SETUP_TEARDOWN: "Structure",
            PatternType.UNREACHABLE_CODE: "Structure",
            PatternType.HARDCODED_VALUE: "Variables",
            PatternType.UNUSED_VARIABLE: "Variables",
            PatternType.GLOBAL_VARIABLE_MISUSE: "Variables",
            PatternType.UNUSED_IMPORT: "Imports",
            PatternType.WILDCARD_IMPORT: "Imports",
            PatternType.CIRCULAR_IMPORT: "Imports",
        }
        return categories.get(self.type, "Other")
