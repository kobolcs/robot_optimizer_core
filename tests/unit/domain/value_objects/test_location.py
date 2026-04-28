# tests/unit/domain/value_objects/test_location.py
"""Unit tests for Location value object.

Comprehensive tests for the Location value object including edge cases,
validation, and all methods to ensure mutation testing resilience.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from robot_optimizer_core.domain.value_objects import Location


@pytest.mark.unit
class TestLocation:
    """Test the Location value object."""

    def test_create_basic_location(self) -> None:
        """Test creating a basic location with only required fields."""
        loc = Location(file_path=Path("test.robot"), line=10)

        assert loc.file_path == Path("test.robot")
        assert loc.line == 10
        assert loc.column is None
        assert loc.end_line is None
        assert loc.end_column is None

    def test_create_location_with_column(self) -> None:
        """Test creating a location with line and column."""
        loc = Location(file_path=Path("test.robot"), line=10, column=5)

        assert loc.line == 10
        assert loc.column == 5
        assert loc.end_line is None
        assert loc.end_column is None

    def test_create_location_with_range(self) -> None:
        """Test creating a location with full range."""
        loc = Location(
            file_path=Path("test.robot"), line=10, column=5, end_line=15, end_column=20
        )

        assert loc.line == 10
        assert loc.column == 5
        assert loc.end_line == 15
        assert loc.end_column == 20

    def test_path_string_conversion(self) -> None:
        """Test that string paths are converted to Path objects."""
        loc = Location(file_path="test.robot", line=1)
        assert isinstance(loc.file_path, Path)
        assert loc.file_path == Path("test.robot")

        # Test with nested path
        loc2 = Location(file_path="tests/suite/test.robot", line=1)
        assert loc2.file_path == Path("tests/suite/test.robot")

    def test_invalid_line_numbers(self) -> None:
        """Test validation of line numbers."""
        # Zero line
        with pytest.raises(ValidationError) as exc_info:
            Location(file_path=Path("test.robot"), line=0)
        assert "greater than or equal to 1" in str(exc_info.value)

        # Negative line
        with pytest.raises(ValidationError):
            Location(file_path=Path("test.robot"), line=-5)

    def test_invalid_column_numbers(self) -> None:
        """Test validation of column numbers."""
        # Zero column
        with pytest.raises(ValidationError) as exc_info:
            Location(file_path=Path("test.robot"), line=1, column=0)
        assert "greater than or equal to 1" in str(exc_info.value)

        # Negative column
        with pytest.raises(ValidationError):
            Location(file_path=Path("test.robot"), line=1, column=-1)

    def test_end_line_validation(self) -> None:
        """Test end line validation rules."""
        # End line before start line
        with pytest.raises(ValidationError) as exc_info:
            Location(file_path=Path("test.robot"), line=10, end_line=5)
        assert "cannot be before start line" in str(exc_info.value)

        # End line equal to start line is valid
        loc = Location(file_path=Path("test.robot"), line=10, end_line=10)
        assert loc.end_line == 10

    def test_end_column_validation(self) -> None:
        """Test end column validation rules."""
        # End column without start column
        with pytest.raises(ValidationError) as exc_info:
            Location(file_path=Path("test.robot"), line=1, end_column=10)
        assert "Cannot have end_column without column" in str(exc_info.value)

        # End column before start column on same line
        with pytest.raises(ValidationError) as exc_info:
            Location(
                file_path=Path("test.robot"),
                line=10,
                column=20,
                end_line=10,
                end_column=15,
            )
        assert "cannot be before start column" in str(exc_info.value)

        # End column before start column on different lines is valid
        loc = Location(
            file_path=Path("test.robot"), line=10, column=20, end_line=11, end_column=5
        )
        assert loc.end_column == 5

    def test_range_str_formatting(self) -> None:
        """Test range string representation for all formats."""
        # Basic location
        loc1 = Location(file_path=Path("test.robot"), line=10)
        assert loc1.range_str == "test.robot:10"

        # With column
        loc2 = Location(file_path=Path("test.robot"), line=10, column=5)
        assert loc2.range_str == "test.robot:10:5"

        # With end line only
        loc3 = Location(file_path=Path("test.robot"), line=10, end_line=15)
        assert loc3.range_str == "test.robot:10-15:"

        # With full range
        loc4 = Location(
            file_path=Path("test.robot"), line=10, column=5, end_line=15, end_column=20
        )
        assert loc4.range_str == "test.robot:10:5-15:20"

        # With end line but no end column
        loc5 = Location(file_path=Path("test.robot"), line=10, column=5, end_line=15)
        assert loc5.range_str == "test.robot:10:5-15:"

    def test_is_range_and_is_point(self) -> None:
        """Test range and point detection."""
        # Point location
        point = Location(file_path=Path("test.robot"), line=10)
        assert point.is_point
        assert not point.is_range

        # Range location
        range_loc = Location(file_path=Path("test.robot"), line=10, end_line=15)
        assert range_loc.is_range
        assert not range_loc.is_point

    def test_contains_same_file(self) -> None:
        """Test contains method for locations in the same file."""
        # Range contains point
        outer = Location(file_path=Path("test.robot"), line=10, end_line=20)
        inner = Location(file_path=Path("test.robot"), line=15)
        assert outer.contains(inner)

        # Point doesn't contain other point
        point1 = Location(file_path=Path("test.robot"), line=10)
        point2 = Location(file_path=Path("test.robot"), line=10)
        assert point1.contains(point2)  # Same location

        # Line outside range
        before = Location(file_path=Path("test.robot"), line=5)
        after = Location(file_path=Path("test.robot"), line=25)
        assert not outer.contains(before)
        assert not outer.contains(after)

        # With column checks
        col_outer = Location(
            file_path=Path("test.robot"), line=10, column=5, end_line=10, end_column=20
        )

        col_inner = Location(file_path=Path("test.robot"), line=10, column=10)
        col_before = Location(file_path=Path("test.robot"), line=10, column=3)
        col_after = Location(file_path=Path("test.robot"), line=10, column=25)

        assert col_outer.contains(col_inner)
        assert not col_outer.contains(col_before)
        assert not col_outer.contains(col_after)

    def test_contains_different_files(self) -> None:
        """Test that locations in different files don't contain each other."""
        loc1 = Location(file_path=Path("test1.robot"), line=10, end_line=20)
        loc2 = Location(file_path=Path("test2.robot"), line=15)

        assert not loc1.contains(loc2)
        assert not loc2.contains(loc1)

    def test_overlaps(self) -> None:
        """Test overlap detection between locations."""
        # Same file, overlapping ranges
        loc1 = Location(file_path=Path("test.robot"), line=10, end_line=20)
        loc2 = Location(file_path=Path("test.robot"), line=15, end_line=25)
        assert loc1.overlaps(loc2)
        assert loc2.overlaps(loc1)

        # Non-overlapping ranges
        loc3 = Location(file_path=Path("test.robot"), line=1, end_line=5)
        loc4 = Location(file_path=Path("test.robot"), line=10, end_line=15)
        assert not loc3.overlaps(loc4)
        assert not loc4.overlaps(loc3)

        # Different files
        loc5 = Location(file_path=Path("test1.robot"), line=10, end_line=20)
        loc6 = Location(file_path=Path("test2.robot"), line=10, end_line=20)
        assert not loc5.overlaps(loc6)

        # Edge case: touching ranges with columns
        loc7 = Location(
            file_path=Path("test.robot"), line=10, column=1, end_line=10, end_column=10
        )
        loc8 = Location(
            file_path=Path("test.robot"), line=10, column=11, end_line=10, end_column=20
        )
        assert not loc7.overlaps(loc8)  # Adjacent but not overlapping

    def test_merge(self) -> None:
        """Test merging locations."""
        # Simple merge
        loc1 = Location(file_path=Path("test.robot"), line=10, end_line=15)
        loc2 = Location(file_path=Path("test.robot"), line=12, end_line=20)

        merged = loc1.merge(loc2)
        assert merged.line == 10
        assert merged.end_line == 20

        # Merge with columns
        loc3 = Location(
            file_path=Path("test.robot"), line=10, column=5, end_line=10, end_column=15
        )
        loc4 = Location(
            file_path=Path("test.robot"), line=10, column=10, end_line=10, end_column=20
        )

        merged2 = loc3.merge(loc4)
        assert merged2.line == 10
        assert merged2.column == 5
        assert merged2.end_line == 10
        assert merged2.end_column == 20

        # Different files - should raise error
        loc5 = Location(file_path=Path("test1.robot"), line=10)
        loc6 = Location(file_path=Path("test2.robot"), line=10)

        with pytest.raises(ValueError) as exc_info:
            loc5.merge(loc6)
        assert "different files" in str(exc_info.value)

    def test_offset(self) -> None:
        """Test offsetting locations."""
        # Basic offset
        loc = Location(file_path=Path("test.robot"), line=10, column=5)

        offset1 = loc.offset(lines=5, columns=3)
        assert offset1.line == 15
        assert offset1.column == 8

        # Negative offset
        offset2 = loc.offset(lines=-2, columns=-1)
        assert offset2.line == 8
        assert offset2.column == 4

        # Invalid negative offset
        with pytest.raises(ValueError) as exc_info:
            loc.offset(lines=-10)  # Would make line 0
        assert "invalid line number" in str(exc_info.value).lower()

        with pytest.raises(ValueError) as exc_info:
            loc.offset(columns=-5)  # Would make column 0
        assert "invalid column number" in str(exc_info.value).lower()

        # Offset range
        range_loc = Location(
            file_path=Path("test.robot"), line=10, column=5, end_line=15, end_column=20
        )

        offset3 = range_loc.offset(lines=2, columns=3)
        assert offset3.line == 12
        assert offset3.column == 8
        assert offset3.end_line == 17
        assert offset3.end_column == 23

    def test_location_equality_and_hash(self) -> None:
        """Test location equality and hashing."""
        loc1 = Location(file_path=Path("test.robot"), line=10, column=5)
        loc2 = Location(file_path=Path("test.robot"), line=10, column=5)
        loc3 = Location(file_path=Path("test.robot"), line=10, column=6)
        loc4 = Location(file_path=Path("test2.robot"), line=10, column=5)

        # Same location
        assert loc1 == loc2
        assert hash(loc1) == hash(loc2)

        # Different column
        assert loc1 != loc3
        assert hash(loc1) != hash(loc3)

        # Different file
        assert loc1 != loc4
        assert hash(loc1) != hash(loc4)

        # Different type
        assert loc1 != "test.robot:10:5"
        assert loc1 != 10

    def test_location_immutability(self) -> None:
        """Test that Location is immutable."""
        loc = Location(file_path=Path("test.robot"), line=10)

        with pytest.raises(ValidationError):
            loc.line = 20

        with pytest.raises(ValidationError):
            loc.file_path = Path("other.robot")
