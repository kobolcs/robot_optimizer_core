# src/robot_optimizer_core/domain/value_objects/location.py
"""Location value object for representing positions in Robot Framework files.

This module provides the Location value object that represents a position
or range within a Robot Framework test file, including line and column
information.

Example:
    Creating locations::

        from robot_optimizer_core import Location
        from pathlib import Path

        # Simple location
        loc = Location(Path("test.robot"), line=10)

        # Location with column
        loc = Location(Path("test.robot"), line=10, column=5)

        # Location range
        loc = Location(
            Path("test.robot"),
            line=10, column=5,
            end_line=15, end_column=20
        )
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator

from ..base import ValueObject


class Location(ValueObject):
    """Represents a location in a Robot Framework test file.

    A location can be a single point (line, optional column) or a range
    (start and end positions). This is used to precisely identify where
    findings occur in test files.

    Attributes:
        file_path: Path to the file.
        line: Line number (1-based).
        column: Column number (1-based, optional).
        end_line: End line for ranges (optional).
        end_column: End column for ranges (optional).

    Example:
        >>> loc = Location(Path("test.robot"), line=42)
        >>> print(loc.range_str)
        test.robot:42

        >>> # Positional arguments also work for convenience
        >>> loc = Location(Path("test.robot"), 42)
        >>> loc = Location(Path("test.robot"), 42, 5)  # with column

        >>> range_loc = Location(
        ...     Path("test.robot"),
        ...     line=10, column=5,
        ...     end_line=12, end_column=15
        ... )
        >>> print(range_loc.range_str)
        test.robot:10:5-12:15
    """

    file_path: Path = Field(..., description="Path to the file")
    line: int = Field(..., ge=1, description="Line number (1-based)")
    column: int | None = Field(None, ge=1, description="Column number (1-based)")
    end_line: int | None = Field(None, ge=1, description="End line for ranges")
    end_column: int | None = Field(None, ge=1, description="End column for ranges")

    def __init__(
        self,
        file_path: Path | str | None = None,
        line: int | None = None,
        column: int | None = None,
        end_line: int | None = None,
        end_column: int | None = None,
        **data: Any,
    ):
        """Initialize Location with flexible argument handling.

        Supports both positional and keyword arguments for convenience.

        Args:
            file_path: Path to the file (positional or keyword)
            line: Line number (positional or keyword)
            column: Column number (positional or keyword, optional)
            end_line: End line for ranges (keyword only, optional)
            end_column: End column for ranges (keyword only, optional)
            **data: Additional keyword arguments passed to Pydantic
        """
        # Build kwargs dict for Pydantic
        init_data = data.copy()
        if file_path is not None:
            init_data["file_path"] = file_path
        if line is not None:
            init_data["line"] = line
        if column is not None:
            init_data["column"] = column
        if end_line is not None:
            init_data["end_line"] = end_line
        if end_column is not None:
            init_data["end_column"] = end_column

        super().__init__(**init_data)

    @field_validator("file_path", mode="before")
    @classmethod
    def ensure_path_object(cls, v: Any) -> Path:
        """Ensure file_path is a Path object.

        Args:
            v: Value to convert (string or Path).

        Returns:
            Path object.
        """
        return Path(v) if not isinstance(v, Path) else v

    @field_validator("end_line")
    @classmethod
    def validate_end_line(cls, v: int | None, info: Any) -> int | None:
        """Validate end line is not before start line.

        Args:
            v: End line value.
            info: Validation context.

        Returns:
            Validated end line.

        Raises:
            ValueError: If end line is before start line.
        """
        if v is not None and "line" in info.data and v < info.data["line"]:
            raise ValueError(
                f"End line ({v}) cannot be before start line ({info.data['line']})"
            )
        return v

    @field_validator("end_column")
    @classmethod
    def validate_end_column(cls, v: int | None, info: Any) -> int | None:
        """Validate end column constraints.

        End column requires a start column, and if on the same line,
        must be after the start column.

        Args:
            v: End column value.
            info: Validation context.

        Returns:
            Validated end column.

        Raises:
            ValueError: If validation fails.
        """
        if v is not None:
            # Must have start column
            if "column" not in info.data or info.data.get("column") is None:
                raise ValueError("Cannot have end_column without column")

            # If on same line, end must be after start
            if (
                "end_line" in info.data
                and "line" in info.data
                and info.data.get("end_line") == info.data["line"]
                and "column" in info.data
                and v < info.data["column"]
            ):
                raise ValueError(
                    f"End column ({v}) cannot be before start column "
                    f"({info.data['column']}) on the same line"
                )
        return v

    @property
    def range_str(self) -> str:
        """Get a string representation of the location range.

        Format:
        - Simple: "file.robot:10"
        - With column: "file.robot:10:5"
        - Range: "file.robot:10:5-15:20"

        Returns:
            Human-readable location string.
        """
        # Start with file and line
        match (self.column, self.end_line, self.end_column):
            case (None, None, _):
                return f"{self.file_path}:{self.line}"
            case (column, None, _):
                return f"{self.file_path}:{self.line}:{column}"
            case (None, end_line, None):
                return f"{self.file_path}:{self.line}-{end_line}:"
            case (None, end_line, end_col):
                return f"{self.file_path}:{self.line}-{end_line}:{end_col}"
            case (column, end_line, None):
                return f"{self.file_path}:{self.line}:{column}-{end_line}:"
            case (column, end_line, end_col):
                return f"{self.file_path}:{self.line}:{column}-{end_line}:{end_col}"

    @property
    def is_range(self) -> bool:
        """Check if this location represents a range.

        Returns:
            True if end_line is specified.
        """
        return self.end_line is not None

    @property
    def is_point(self) -> bool:
        """Check if this location represents a single point.

        Returns:
            True if no end position is specified.
        """
        return self.end_line is None

    def contains(self, other: Location) -> bool:
        """Check if this location contains another location."""
        if self.file_path != other.file_path:
            return False

        if not self._lines_contain(other):
            return False

        if not self._start_column_contains(other):
            return False

        if not self._end_column_contains(other):
            return False

        return True

    def _lines_contain(self, other: Location) -> bool:
        """Check if this location's lines contain the other location's lines."""
        self_end_line = self.end_line or self.line
        other_end_line = other.end_line or other.line
        return not (other.line < self.line or other_end_line > self_end_line)

    def _start_column_contains(self, other: Location) -> bool:
        """Check if start columns are properly contained."""
        if self.column is None or other.line != self.line:
            return True
        return other.column is not None and other.column >= self.column

    def _end_column_contains(self, other: Location) -> bool:
        """Check if end columns are properly contained."""
        self_end_line = self.end_line or self.line
        other_end_line = other.end_line or other.line
        if self.end_column is None or other_end_line != self_end_line:
            return True
        # Determine other's effective end column
        if other.end_column is not None:
            other_end_column: int | None = other.end_column
        elif other.end_line is None or other.end_line == other.line:
            # Point or single-line location: end column is the start column
            other_end_column = other.column
        else:
            # Multi-line range without explicit end column: be conservative
            return True
        return other_end_column is not None and other_end_column <= self.end_column

    def overlaps(self, other: Location) -> bool:
        """Check if this location overlaps with another location.

        Two locations overlap if they share any common positions.

        Args:
            other: Location to check.

        Returns:
            True if locations overlap.
        """
        # Must be same file
        if self.file_path != other.file_path:
            return False

        # Get effective ranges
        self_end_line = self.end_line or self.line
        other_end_line = other.end_line or other.line

        # Check line overlap
        if self.line > other_end_line or self_end_line < other.line:
            return False

        # Lines overlap, check columns if on same line
        if self.line == other_end_line or self_end_line == other.line:
            # Need column info for precise check
            match (
                self.line == other_end_line,
                self.column,
                other.column,
                other.end_column,
            ):
                case (True, start_col, _, other_end_col) if (
                    start_col is not None and other_end_col is not None
                ):
                    # Check if other ends before we start
                    if other_end_col < start_col:
                        return False

            match (self_end_line == other.line, self.end_column, other.column):
                case (True, self_end_col, other_col) if (
                    self_end_col is not None and other_col is not None
                ):
                    # Check if we end before other starts
                    if self_end_col < other_col:
                        return False

        return True

    def merge(self, other: Location) -> Location:
        """Merge this location with another to create a combined range.

        The result spans from the earliest position to the latest position.

        Args:
            other: Location to merge with.

        Returns:
            New location covering both ranges.

        Raises:
            ValueError: If locations are in different files.
        """
        if self.file_path != other.file_path:
            raise ValueError("Cannot merge locations from different files")

        # Find earliest start
        match (self.line, other.line):
            case (self_line, other_line) if self_line < other_line:
                start_line = self_line
                start_column = self.column
            case (self_line, other_line) if self_line > other_line:
                start_line = other_line
                start_column = other.column
            case _:  # Same line
                start_line = self.line
                start_column = (
                    None
                    if self.column is None or other.column is None
                    else min(self.column, other.column)
                )

        # Find latest end
        self_end_line = self.end_line or self.line
        other_end_line = other.end_line or other.line

        match (self_end_line, other_end_line):
            case (self_end, other_end) if self_end > other_end:
                end_line = self_end
                end_column = self.end_column
            case (self_end, other_end) if self_end < other_end:
                end_line = other_end
                end_column = other.end_column
            case _:  # Same end line
                end_line = self_end_line
                end_column = (
                    None
                    if self.end_column is None or other.end_column is None
                    else max(self.end_column, other.end_column)
                )

        return Location(
            file_path=self.file_path,
            line=start_line,
            column=start_column,
            end_line=end_line,
            end_column=end_column,
        )

    def offset(self, lines: int = 0, columns: int = 0) -> Location:
        """Create a new location offset by the given amount.

        Args:
            lines: Number of lines to offset (can be negative).
            columns: Number of columns to offset (can be negative).

        Returns:
            New location with adjusted position.

        Raises:
            ValueError: If offset would create invalid position.
        """
        new_line = self.line + lines
        if new_line < 1:
            raise ValueError(f"Offset would create invalid line number: {new_line}")

        new_column = None
        if self.column is not None:
            new_column = self.column + columns
            if new_column < 1:
                raise ValueError(
                    f"Offset would create invalid column number: {new_column}"
                )

        new_end_line = None
        if self.end_line is not None:
            new_end_line = self.end_line + lines
            if new_end_line < 1:
                raise ValueError(
                    f"Offset would create invalid end line: {new_end_line}"
                )

        new_end_column = None
        if self.end_column is not None:
            new_end_column = self.end_column + columns
            if new_end_column < 1:
                raise ValueError(
                    f"Offset would create invalid end column: {new_end_column}"
                )

        return Location(
            file_path=self.file_path,
            line=new_line,
            column=new_column,
            end_line=new_end_line,
            end_column=new_end_column,
        )
