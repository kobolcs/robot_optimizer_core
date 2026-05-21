# tests/domain/test_value_objects.py
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from robot_optimizer_core.domain.value_objects import (
    Finding,
    Location,
    Pattern,
    PatternType,
    Severity,
)


class TestSeverity:
    """Test the Severity enum."""

    def test_severity_ordering(self):
        """Test that severities are properly ordered."""
        assert Severity.ERROR < Severity.WARNING
        assert Severity.WARNING < Severity.INFO
        assert Severity.ERROR < Severity.INFO

    def test_severity_emoji(self):
        """Test emoji representations."""
        assert Severity.ERROR.emoji == "❌"
        assert Severity.WARNING.emoji == "⚠️"
        assert Severity.INFO.emoji == "ℹ️"

    def test_severity_color(self):
        """Test color representations."""
        assert Severity.ERROR.color == "red"
        assert Severity.WARNING.color == "yellow"
        assert Severity.INFO.color == "blue"


class TestLocation:
    """Test the Location value object."""

    def test_create_basic_location(self):
        """Test creating a basic location."""
        loc = Location(file_path=Path("test.robot"), line=10)
        assert loc.file_path == Path("test.robot")
        assert loc.line == 10
        assert loc.column is None
        assert loc.end_line is None
        assert loc.end_column is None

    def test_create_location_with_range(self):
        """Test creating a location with full range."""
        loc = Location(
            file_path=Path("test.robot"), line=10, column=5, end_line=15, end_column=20
        )
        assert loc.line == 10
        assert loc.column == 5
        assert loc.end_line == 15
        assert loc.end_column == 20

    def test_location_converts_string_path(self):
        """Test that string paths are converted to Path objects."""
        loc = Location(file_path="test.robot", line=1)
        assert isinstance(loc.file_path, Path)
        assert loc.file_path == Path("test.robot")

    def test_invalid_line_number(self):
        """Test that invalid line numbers raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Location(file_path=Path("test.robot"), line=0)
        assert "greater than or equal to 1" in str(exc_info.value)

    def test_invalid_column_number(self):
        """Test that invalid column numbers raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Location(file_path=Path("test.robot"), line=1, column=0)
        assert "greater than or equal to 1" in str(exc_info.value)

    def test_end_line_before_start_line(self):
        """Test that end line cannot be before start line."""
        with pytest.raises(ValidationError) as exc_info:
            Location(file_path=Path("test.robot"), line=10, end_line=5)
        assert "cannot be before start line" in str(exc_info.value)

    def test_end_column_without_start_column(self):
        """Test that end column requires start column."""
        with pytest.raises(ValidationError) as exc_info:
            Location(file_path=Path("test.robot"), line=1, end_column=10)
        assert "Cannot have end_column without column" in str(exc_info.value)

    def test_end_column_before_start_column_same_line(self):
        """Test that end column cannot be before start column on same line."""
        with pytest.raises(ValidationError) as exc_info:
            Location(
                file_path=Path("test.robot"),
                line=10,
                column=20,
                end_line=10,
                end_column=15,
            )
        assert "cannot be before start column" in str(exc_info.value)

    def test_range_str_basic(self):
        """Test range string representation for basic location."""
        loc = Location(file_path=Path("test.robot"), line=10)
        assert loc.range_str == "test.robot:10"

    def test_range_str_with_column(self):
        """Test range string representation with column."""
        loc = Location(file_path=Path("test.robot"), line=10, column=5)
        assert loc.range_str == "test.robot:10:5"

    def test_range_str_with_full_range(self):
        """Test range string representation with full range."""
        loc = Location(
            file_path=Path("test.robot"), line=10, column=5, end_line=15, end_column=20
        )
        assert loc.range_str == "test.robot:10:5-15:20"

    def test_contains_same_location(self):
        """Test that a location contains itself."""
        loc = Location(file_path=Path("test.robot"), line=10, column=5)
        assert loc.contains(loc)

    def test_contains_different_file(self):
        """Test that locations in different files don't contain each other."""
        loc1 = Location(file_path=Path("test1.robot"), line=10)
        loc2 = Location(file_path=Path("test2.robot"), line=10)
        assert not loc1.contains(loc2)

    def test_contains_within_range(self):
        """Test location containment within range."""
        outer = Location(file_path=Path("test.robot"), line=10, end_line=20)
        inner = Location(file_path=Path("test.robot"), line=15)
        assert outer.contains(inner)

    def test_location_equality(self):
        """Test location equality."""
        loc1 = Location(file_path=Path("test.robot"), line=10, column=5)
        loc2 = Location(file_path=Path("test.robot"), line=10, column=5)
        loc3 = Location(file_path=Path("test.robot"), line=10, column=6)

        assert loc1 == loc2
        assert loc1 != loc3
        assert hash(loc1) == hash(loc2)
        assert hash(loc1) != hash(loc3)

    def test_location_immutability(self):
        """Test that Location is immutable."""
        loc = Location(file_path=Path("test.robot"), line=10)

        with pytest.raises(ValidationError):
            loc.line = 20  # Pydantic frozen models raise ValidationError

    def test_range_str_end_line_no_column(self):
        loc = Location(file_path=Path("test.robot"), line=5, end_line=10)
        s = loc.range_str
        assert "5" in s
        assert "10" in s

    def test_range_str_column_and_end_line_no_end_column(self):
        loc = Location(file_path=Path("test.robot"), line=5, column=3, end_line=10)
        s = loc.range_str
        assert "5" in s
        assert "3" in s
        assert "10" in s

    def test_merge_self_starts_earlier(self):
        a = Location(file_path=Path("f.robot"), line=1, end_line=5)
        b = Location(file_path=Path("f.robot"), line=3, end_line=8)
        merged = a.merge(b)
        assert merged.line == 1
        assert merged.end_line == 8

    def test_merge_other_starts_earlier(self):
        a = Location(file_path=Path("f.robot"), line=5, end_line=10)
        b = Location(file_path=Path("f.robot"), line=2, end_line=7)
        merged = a.merge(b)
        assert merged.line == 2
        assert merged.end_line == 10

    def test_merge_different_files_raises(self):
        a = Location(file_path=Path("a.robot"), line=1)
        b = Location(file_path=Path("b.robot"), line=1)
        with pytest.raises(ValueError, match="different files"):
            a.merge(b)

    def test_merge_same_end_line(self):
        a = Location(file_path=Path("f.robot"), line=1, column=1, end_line=5, end_column=3)
        b = Location(file_path=Path("f.robot"), line=1, column=2, end_line=5, end_column=8)
        merged = a.merge(b)
        assert merged.end_line == 5
        assert merged.end_column == 8

    def test_offset_with_column(self):
        loc = Location(file_path=Path("f.robot"), line=5, column=3)
        shifted = loc.offset(lines=2, columns=1)
        assert shifted.line == 7
        assert shifted.column == 4

    def test_offset_with_end_line(self):
        loc = Location(file_path=Path("f.robot"), line=5, end_line=10)
        shifted = loc.offset(lines=1)
        assert shifted.end_line == 11

    def test_offset_invalid_line_raises(self):
        loc = Location(file_path=Path("f.robot"), line=1)
        with pytest.raises(ValueError, match="invalid line"):
            loc.offset(lines=-5)

    def test_offset_invalid_column_raises(self):
        loc = Location(file_path=Path("f.robot"), line=5, column=1)
        with pytest.raises(ValueError, match="invalid column"):
            loc.offset(columns=-10)

    def test_offset_with_end_column(self):
        loc = Location(
            file_path=Path("f.robot"), line=1, column=5, end_line=2, end_column=10
        )
        shifted = loc.offset(columns=2)
        assert shifted.end_column == 12

    def test_offset_invalid_end_column_raises(self):
        loc = Location(
            file_path=Path("f.robot"), line=1, column=10, end_line=2, end_column=3
        )
        with pytest.raises(ValueError, match="invalid end column"):
            loc.offset(columns=-9)

    def test_overlaps_different_files(self):
        a = Location(file_path=Path("a.robot"), line=1, end_line=5)
        b = Location(file_path=Path("b.robot"), line=1, end_line=5)
        assert a.overlaps(b) is False

    def test_overlaps_non_overlapping_ranges(self):
        a = Location(file_path=Path("f.robot"), line=1, end_line=5)
        b = Location(file_path=Path("f.robot"), line=10, end_line=15)
        assert a.overlaps(b) is False

    def test_overlaps_overlapping_ranges(self):
        a = Location(file_path=Path("f.robot"), line=1, end_line=10)
        b = Location(file_path=Path("f.robot"), line=5, end_line=15)
        assert a.overlaps(b) is True

    def test_is_range_and_is_point(self):
        point = Location(file_path=Path("f.robot"), line=5)
        rng = Location(file_path=Path("f.robot"), line=5, end_line=10)
        assert point.is_point is True
        assert point.is_range is False
        assert rng.is_range is True
        assert rng.is_point is False


class TestPattern:
    """Test the Pattern value object."""

    def test_create_pattern(self):
        """Test creating a basic pattern."""
        pattern = Pattern(
            type=PatternType.DUPLICATE_KEYWORD,
            name="Duplicate Keyword",
            description="Found duplicate keyword",
            recommendation="Remove duplicates",
        )
        assert pattern.type == PatternType.DUPLICATE_KEYWORD
        assert pattern.name == "Duplicate Keyword"
        assert pattern.description == "Found duplicate keyword"
        assert pattern.recommendation == "Remove duplicates"
        assert pattern.documentation_url is None
        assert pattern.auto_fixable is False

    def test_empty_name_raises_error(self):
        """Test that empty pattern name raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Pattern(
                type=PatternType.DUPLICATE_KEYWORD,
                name="",
                description="Description",
                recommendation="Recommendation",
            )
        assert "at least 1 character" in str(exc_info.value)

    def test_empty_description_raises_error(self):
        """Test that empty description raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Pattern(
                type=PatternType.DUPLICATE_KEYWORD,
                name="Name",
                description="  ",
                recommendation="Recommendation",
            )
        assert "Field cannot be empty" in str(exc_info.value)

    def test_duplicate_keyword_factory(self):
        """Test the duplicate keyword factory method."""
        pattern = Pattern.duplicate_keyword("Login")
        assert pattern.type == PatternType.DUPLICATE_KEYWORD
        assert "Login" in pattern.description
        assert pattern.auto_fixable is False

    def test_sleep_in_test_factory(self):
        """Test the sleep in test factory method."""
        pattern = Pattern.sleep_in_test("5 seconds")
        assert pattern.type == PatternType.SLEEP_IN_TEST
        assert "5 seconds" in pattern.description
        assert pattern.auto_fixable is True
        assert pattern.documentation_url is not None

    def test_fragile_xpath_factory(self):
        """Test the fragile XPath factory method."""
        pattern = Pattern.fragile_xpath("//div[3]/span[1]")
        assert pattern.type == PatternType.FRAGILE_XPATH
        assert "//div[3]/span[1]" in pattern.description
        assert pattern.auto_fixable is False

    def test_long_test_case_factory(self):
        """Test the long test case factory method."""
        pattern = Pattern.long_test_case(75, threshold=50)
        assert pattern.type == PatternType.LONG_TEST_CASE
        assert "75" in pattern.description
        assert "50" in pattern.description
        assert pattern.auto_fixable is False

    def test_pattern_categories(self):
        """Test pattern category classification."""
        assert Pattern.duplicate_keyword("test").category == "Keywords"
        assert Pattern.sleep_in_test("1s").category == "Waits"
        assert Pattern.fragile_xpath("//div").category == "Locators"
        assert Pattern.long_test_case(100).category == "Structure"

    def test_pattern_equality(self):
        """Test pattern equality."""
        p1 = Pattern.duplicate_keyword("Login")
        p2 = Pattern.duplicate_keyword("Login")
        p3 = Pattern.duplicate_keyword("Logout")

        # Same factory calls should produce equal patterns
        assert p1 == p2
        assert p1 != p3

    def test_pattern_immutability(self):
        """Test that Pattern is immutable."""
        pattern = Pattern.duplicate_keyword("Test")

        with pytest.raises(ValidationError):
            pattern.name = "New Name"


class TestFinding:
    """Test the Finding value object."""

    @pytest.fixture
    def sample_pattern(self):
        """Create a sample pattern for testing."""
        return Pattern.sleep_in_test("2 seconds")

    @pytest.fixture
    def sample_location(self):
        """Create a sample location for testing."""
        return Location(file_path=Path("test.robot"), line=25, column=10)

    def test_create_finding(self, sample_pattern, sample_location):
        """Test creating a finding."""
        finding_id = uuid4()
        finding = Finding(
            id=finding_id,
            pattern=sample_pattern,
            severity=Severity.WARNING,
            location=sample_location,
            message="Using Sleep makes tests fragile",
        )

        assert finding.id == finding_id
        assert finding.pattern == sample_pattern
        assert finding.severity == Severity.WARNING
        assert finding.location == sample_location
        assert finding.message == "Using Sleep makes tests fragile"
        assert finding.context is None

    def test_create_finding_with_factory(self, sample_pattern, sample_location):
        """Test creating a finding with factory method."""
        finding = Finding.create(
            pattern=sample_pattern,
            severity=Severity.WARNING,
            location=sample_location,
            message="Using Sleep makes tests fragile",
            sleep_duration="2 seconds",
            suggested_wait="Wait Until Element Is Visible",
        )

        assert finding.id is not None
        assert finding.context == {
            "sleep_duration": "2 seconds",
            "suggested_wait": "Wait Until Element Is Visible",
        }

    def test_auto_generated_id(self, sample_pattern, sample_location):
        """Test that ID is auto-generated if not provided."""
        finding = Finding(
            pattern=sample_pattern,
            severity=Severity.WARNING,
            location=sample_location,
            message="Test message",
        )
        assert finding.id is not None

    def test_empty_message_raises_error(self, sample_pattern, sample_location):
        """Test that empty message raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Finding(
                pattern=sample_pattern,
                severity=Severity.WARNING,
                location=sample_location,
                message="  ",
            )
        assert "cannot be empty" in str(exc_info.value)

    def test_finding_properties(self, sample_pattern, sample_location):
        """Test finding properties."""
        finding = Finding.create(
            pattern=sample_pattern,
            severity=Severity.WARNING,
            location=sample_location,
            message="Test message",
        )

        assert finding.file_path == "test.robot"
        assert finding.line_number == 25
        assert finding.is_auto_fixable is True  # Because sleep pattern is auto-fixable

    def test_format_for_console(self, sample_location):
        """Test console formatting."""
        pattern = Pattern(
            type=PatternType.SLEEP_IN_TEST,
            name="Sleep in Test",
            description="Sleep usage detected",
            recommendation="Use explicit waits instead",
        )
        finding = Finding.create(
            pattern=pattern,
            severity=Severity.WARNING,
            location=sample_location,
            message="Found Sleep 2 seconds",
            duration="2 seconds",
        )

        output = finding.format_for_console()
        assert "⚠️ Sleep in Test" in output
        assert "test.robot:25:10" in output
        assert "Found Sleep 2 seconds" in output
        assert "💡 Use explicit waits instead" in output
        assert "duration: 2 seconds" in output

    def test_to_dict(self, sample_pattern, sample_location):
        """Test dictionary conversion."""
        finding = Finding.create(
            pattern=sample_pattern,
            severity=Severity.WARNING,
            location=sample_location,
            message="Test message",
            extra_info="test",
        )

        data = finding.to_dict()
        assert data["pattern_type"] == "SLEEP_IN_TEST"
        assert data["severity"] == "WARNING"
        assert data["file"] == "test.robot"
        assert data["line"] == 25
        assert data["column"] == 10
        assert data["message"] == "Test message"
        assert data["is_auto_fixable"] is True
        assert data["context"]["extra_info"] == "test"

    def test_finding_immutability(self, sample_pattern, sample_location):
        """Test that findings are immutable."""
        finding = Finding.create(
            pattern=sample_pattern,
            severity=Severity.WARNING,
            location=sample_location,
            message="Test message",
        )

        with pytest.raises(ValidationError):
            finding.severity = Severity.ERROR

    def test_context_is_copied(self, sample_pattern, sample_location):
        """Test that context dictionary is copied to ensure immutability."""
        original_context = {"key": "value"}
        finding = Finding(
            pattern=sample_pattern,
            severity=Severity.WARNING,
            location=sample_location,
            message="Test",
            context=original_context,
        )

        # Modifying original should not affect finding
        original_context["key"] = "modified"
        assert finding.context["key"] == "value"
