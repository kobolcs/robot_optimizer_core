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
        loc = Location(file_path=Path("test.robot"), line=10)

        # Location with column
        loc = Location(file_path=Path("test.robot"), line=10, column=5)

        # Location range
        loc = Location(
            file_path=Path("test.robot"),
            line=10, column=5,
            end_line=15, end_column=20
        )
"""

from __future__ import annotations

import sys
from pathlib import Path

from pydantic import Field, field_validator, model_validator

from ..base import ValueObject


class Location(ValueObject):
    """Represents a location in a Robot Framework test file.

    A location can be a single point (line, optional column) or a range
    (start and end positions). This is used to precisely identify where
    findings occur in test files.

    All arguments must be passed as keyword arguments.

    Attributes:
        file_path: Path to the file.
        line: Line number (1-based).
        column: Column number (1-based, optional).
        end_line: End line for ranges (optional).
        end_column: End column for ranges (optional).

    Example:
        >>> loc = Location(file_path=Path("test.robot"), line=42)
        >>> print(loc.range_str)
        test.robot:42

        >>> range_loc = Location(
        ...     file_path=Path("test.robot"),
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

    @field_validator("file_path", mode="before")
    @classmethod
    def ensure_path_object(cls, v: object) -> Path:
        """Coerce string file_path to Path."""
        return Path(v) if not isinstance(v, Path) else v  # type: ignore[arg-type]

    @model_validator(mode="after")
    def validate_range_consistency(self) -> "Location":
        """Validate all cross-field range constraints in one place."""
        if self.end_line is not None and self.end_line < self.line:
            raise ValueError(
                f"End line ({self.end_line}) cannot be before start line ({self.line})"
            )
        if self.end_column is not None and self.column is None:
            raise ValueError("Cannot have end_column without column")
        if (
            self.end_column is not None
            and self.end_line == self.line
            and self.end_column < self.column  # type: ignore[operator]  # column not None (checked above)
        ):
            raise ValueError(
                f"End column ({self.end_column}) cannot be before start column "
                f"({self.column}) on the same line"
            )
        return self

    @property
    def range_str(self) -> str:
        """Human-readable location string.

        Formats:
        - ``file.robot:10``            — line only
        - ``file.robot:10:5``          — line + column
        - ``file.robot:10-12``         — line range, no columns
        - ``file.robot:10-12:20``      — line range, end column only
        - ``file.robot:10:5-12``       — line range with start column
        - ``file.robot:10:5-12:20``    — full range
        """
        match (self.column, self.end_line, self.end_column):
            case (None, None, _):
                return f"{self.file_path}:{self.line}"
            case (column, None, _):
                return f"{self.file_path}:{self.line}:{column}"
            case (None, end_line, None):
                return f"{self.file_path}:{self.line}-{end_line}"
            case (None, end_line, end_col):
                return f"{self.file_path}:{self.line}-{end_line}:{end_col}"
            case (column, end_line, None):
                return f"{self.file_path}:{self.line}:{column}-{end_line}"
            case (column, end_line, end_col):
                return f"{self.file_path}:{self.line}:{column}-{end_line}:{end_col}"

    @property
    def is_range(self) -> bool:
        """True if this location covers a range of lines."""
        return self.end_line is not None

    @property
    def is_point(self) -> bool:
        """True if this location is a single point (no end position)."""
        return self.end_line is None

    def contains(self, other: "Location") -> bool:
        """Return True if *self* fully contains *other*.

        Uses tuple interval arithmetic.  For the *self* range, a missing
        end_column means "unbounded" (sys.maxsize).  For a *point* other
        (no end_line), the end equals the start so only the start position
        is checked against *self*'s bounds.
        """
        if self.file_path != other.file_path:
            return False
        self_start = (self.line, self.column or 0)
        self_end = (self.end_line or self.line, self.end_column or sys.maxsize)
        other_start = (other.line, other.column or 0)
        # Point location: end == start so only start is checked.
        if other.end_line is None:
            other_end = other_start
        else:
            other_end = (other.end_line, other.end_column or sys.maxsize)
        return self_start <= other_start and other_end <= self_end

    def overlaps(self, other: "Location") -> bool:
        """Return True if *self* and *other* share any common position.

        Two locations overlap when neither ends strictly before the other starts.
        """
        if self.file_path != other.file_path:
            return False

        self_end_line = self.end_line or self.line
        other_end_line = other.end_line or other.line

        if self.line > other_end_line or self_end_line < other.line:
            return False

        # Lines overlap; for shared boundary lines check column intervals.
        if self.line == other_end_line or self_end_line == other.line:
            match (
                self.line == other_end_line,
                self.column,
                other.column,
                other.end_column,
            ):
                case (True, start_col, _, other_end_col) if (
                    start_col is not None and other_end_col is not None
                ):
                    if other_end_col < start_col:
                        return False

            match (self_end_line == other.line, self.end_column, other.column):
                case (True, self_end_col, other_col) if (
                    self_end_col is not None and other_col is not None
                ):
                    if self_end_col < other_col:
                        return False

        return True

    def merge(self, other: "Location") -> "Location":
        """Return a new Location spanning the union of *self* and *other*.

        Raises:
            ValueError: If the two locations are in different files.
        """
        if self.file_path != other.file_path:
            raise ValueError("Cannot merge locations from different files")

        match (self.line, other.line):
            case (self_line, other_line) if self_line < other_line:
                start_line = self_line
                start_column = self.column
            case (self_line, other_line) if self_line > other_line:
                start_line = other_line
                start_column = other.column
            case _:
                start_line = self.line
                start_column = (
                    None
                    if self.column is None or other.column is None
                    else min(self.column, other.column)
                )

        self_end_line = self.end_line or self.line
        other_end_line = other.end_line or other.line

        match (self_end_line, other_end_line):
            case (self_end, other_end) if self_end > other_end:
                end_line = self_end
                end_column = self.end_column
            case (self_end, other_end) if self_end < other_end:
                end_line = other_end
                end_column = other.end_column
            case _:
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

    def offset(self, lines: int = 0, columns: int = 0) -> "Location":
        """Return a new Location shifted by *lines* and *columns*.

        Raises:
            ValueError: If the resulting position would be invalid (line < 1).
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
            if new_end_line < 1:  # pragma: no cover
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
