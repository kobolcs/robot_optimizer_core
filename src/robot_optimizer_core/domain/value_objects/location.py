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
from typing import Any, Optional

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
        
        >>> range_loc = Location(
        ...     Path("test.robot"),
        ...     line=10, column=5,
        ...     end_line=12, end_column=15
        ... )
        >>> print(range_loc.range_str)
        test.robot:10:5-12:15
    """
    
    file_path: Path = Field(
        ...,
        description="Path to the file"
    )
    line: int = Field(
        ...,
        ge=1,
        description="Line number (1-based)"
    )
    column: Optional[int] = Field(
        None,
        ge=1,
        description="Column number (1-based)"
    )
    end_line: Optional[int] = Field(
        None,
        ge=1,
        description="End line for ranges"
    )
    end_column: Optional[int] = Field(
        None,
        ge=1,
        description="End column for ranges"
    )
    
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
    def validate_end_line(cls, v: Optional[int], info: Any) -> Optional[int]:
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
    def validate_end_column(cls, v: Optional[int], info: Any) -> Optional[int]:
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
        if self.column is None:
            location = f"{self.file_path}:{self.line}"
        else:
            location = f"{self.file_path}:{self.line}:{self.column}"
        
        # Add end position if range
        if self.end_line is not None:
            if self.end_column is not None:
                location += f"-{self.end_line}:{self.end_column}"
            else:
                location += f"-{self.end_line}:"
        
        return location
    
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
    
    def contains(self, other: "Location") -> bool:
        """Check if this location contains another location.
        
        A location contains another if:
        - They are in the same file
        - The other location's position is within this location's range
        
        Args:
            other: Location to check.
            
        Returns:
            True if this location contains the other.
        
        Example:
            >>> range_loc = Location(Path("test.robot"), line=10, end_line=20)
            >>> point_loc = Location(Path("test.robot"), line=15)
            >>> assert range_loc.contains(point_loc)
        """
        # Must be same file
        if self.file_path != other.file_path:
            return False
        
        # Check line boundaries
        if other.line < self.line:
            return False
        
        if self.end_line is not None and other.line > self.end_line:
            return False
        
        # Check column boundaries if specified
        if self.column is not None and other.column is not None:
            # Check start column on same line
            if other.line == self.line and other.column < self.column:
                return False
            
            # Check end column on same line
            if (
                self.end_line == other.line
                and self.end_column is not None
                and other.column > self.end_column
            ):
                return False
        
        return True
    
    def overlaps(self, other: "Location") -> bool:
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
            if self.column is not None and other.column is not None:
                if self.line == other_end_line:
                    # Check if other ends before we start
                    other_end_col = other.end_column or other.column
                    if other_end_col < self.column:
                        return False
                
                if self_end_line == other.line:
                    # Check if we end before other starts
                    self_end_col = self.end_column or self.column
                    if self_end_col < other.column:
                        return False
        
        return True
    
    def merge(self, other: "Location") -> "Location":
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
        if self.line < other.line:
            start_line = self.line
            start_column = self.column
        elif self.line > other.line:
            start_line = other.line
            start_column = other.column
        else:  # Same line
            start_line = self.line
            if self.column is None or other.column is None:
                start_column = None
            else:
                start_column = min(self.column, other.column)
        
        # Find latest end
        self_end_line = self.end_line or self.line
        other_end_line = other.end_line or other.line
        
        if self_end_line > other_end_line:
            end_line = self_end_line
            end_column = self.end_column
        elif self_end_line < other_end_line:
            end_line = other_end_line
            end_column = other.end_column
        else:  # Same end line
            end_line = self_end_line
            if self.end_column is None or other.end_column is None:
                end_column = None
            else:
                end_column = max(self.end_column, other.end_column)
        
        return Location(
            file_path=self.file_path,
            line=start_line,
            column=start_column,
            end_line=end_line if end_line != start_line else None,
            end_column=end_column
        )
    
    def offset(self, lines: int = 0, columns: int = 0) -> "Location":
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
                raise ValueError(f"Offset would create invalid column number: {new_column}")
        
        new_end_line = None
        if self.end_line is not None:
            new_end_line = self.end_line + lines
            if new_end_line < 1:
                raise ValueError(f"Offset would create invalid end line: {new_end_line}")
        
        new_end_column = None
        if self.end_column is not None:
            new_end_column = self.end_column + columns
            if new_end_column < 1:
                raise ValueError(f"Offset would create invalid end column: {new_end_column}")
        
        return Location(
            file_path=self.file_path,
            line=new_line,
            column=new_column,
            end_line=new_end_line,
            end_column=new_end_column
        )