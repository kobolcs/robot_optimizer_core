# src/robot_optimizer/domain/value_objects/location.py
"""Location value object for representing positions in Robot Framework files."""
from pathlib import Path
from typing import Any, Optional

from pydantic import Field, field_validator

from ..base import ValueObject


class Location(ValueObject):
    """Represents a location in a Robot Framework test file."""

    file_path: Path = Field(..., description="Path to the file")
    line: int = Field(..., ge=1, description="Line number (1-based)")
    column: Optional[int] = Field(None, ge=1, description="Column number (1-based)")
    end_line: Optional[int] = Field(None, ge=1, description="End line for ranges")
    end_column: Optional[int] = Field(None, ge=1, description="End column for ranges")

    @field_validator('file_path', mode='before')
    @classmethod
    def ensure_path_object(cls, v: Any) -> Path:
        """Ensure file_path is a Path object."""
        return Path(v) if not isinstance(v, Path) else v

    @field_validator('end_line')
    @classmethod
    def validate_end_line(cls, v: Optional[int], info: Any) -> Optional[int]:
        """Validate end line is not before start line."""
        if v is not None and 'line' in info.data and v < info.data['line']:
            raise ValueError(f"End line ({v}) cannot be before start line ({info.data['line']})")
        return v

    @field_validator('end_column')
    @classmethod
    def validate_end_column(cls, v: Optional[int], info: Any) -> Optional[int]:
        """Validate end column constraints."""
        if v is not None:
            if 'column' not in info.data or info.data.get('column') is None:
                raise ValueError("Cannot have end_column without column")

            # If on the same line, end column must be after start column
            if ('end_line' in info.data and 'line' in info.data and
                info.data.get('end_line') == info.data['line'] and
                'column' in info.data and v < info.data['column']):
                raise ValueError(
                    f"End column ({v}) cannot be before start column "
                    f"({info.data['column']}) on the same line"
                )
        return v

    @property
    def range_str(self) -> str:
        """Get a string representation of the location range."""
        if self.column is None:
            return f"{self.file_path}:{self.line}"

        start = f"{self.line}:{self.column}"
        if self.end_line is None:
            return f"{self.file_path}:{start}"

        end = f"{self.end_line}:{self.end_column or ''}"
        return f"{self.file_path}:{start}-{end}"

    def contains(self, other: 'Location') -> bool:
        """Check if this location contains another location."""
        if self.file_path != other.file_path:
            return False

        # Check line boundaries
        if other.line < self.line:
            return False
        if self.end_line is not None and other.line > self.end_line:
            return False

        # Check column boundaries if on the same line
        if self.column is not None and other.column is not None:
            if other.line == self.line and other.column < self.column:
                return False
            if (self.end_line == other.line and
                self.end_column is not None and
                other.column > self.end_column):
                return False

        return True
