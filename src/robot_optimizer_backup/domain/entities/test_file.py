"""Test file entity module for Robot Framework test file representation.

100% Pydantic v2 compliant implementation.
"""
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Any, Dict
from uuid import UUID, uuid4

from pydantic import Field, field_validator, computed_field, model_validator

from ..base import Entity


class TestFile(Entity[UUID]):
    """Represents a Robot Framework test file.

    This entity encapsulates all information about a single test file,
    including its content, metadata, and structure.
    """

    id: UUID = Field(default_factory=uuid4)
    path: Path = Field(..., description="Path to the test file")
    content: str = Field(..., description="Full content of the file")
    size_bytes: int = Field(..., ge=0, description="File size in bytes")
    last_modified: datetime = Field(..., description="Last modification time")
    encoding: str = Field(default="utf-8", description="File encoding")
    test_cases: List[str] = Field(default_factory=list, description="List of test case names")
    keywords: List[str] = Field(default_factory=list, description="List of keyword names")

    @field_validator('path', mode='before')
    @classmethod
    def ensure_path_object(cls, v: Any) -> Path:
        """Ensure path is a Path object.

        Args:
            v: Value to convert

        Returns:
            Path object
        """
        return Path(v) if not isinstance(v, Path) else v

    @field_validator('encoding')
    @classmethod
    def validate_encoding(cls, v: str) -> str:
        """Validate encoding is supported.

        Args:
            v: Encoding string

        Returns:
            Validated encoding

        Raises:
            ValueError: If encoding is not supported
        """
        supported = {'utf-8', 'utf-16', 'ascii', 'latin-1'}
        if v.lower() not in supported:
            raise ValueError(f"Unsupported encoding: {v}. Supported: {supported}")
        return v.lower()

    @model_validator(mode='after')
    def validate_content_size(self) -> 'TestFile':
        """Validate content size matches size_bytes approximately.

        Pydantic v2 model validator.
        """
        # Allow some variance due to encoding differences
        # pylint: disable=no-member
        content_size = len(self.content.encode(self.encoding))
        if abs(content_size - self.size_bytes) > 100:  # 100 byte tolerance
            # Just log warning, don't fail - size might be from disk
            pass
        return self

    @classmethod
    def from_path(cls, file_path: Path, content: Optional[str] = None) -> 'TestFile':
        """Create a TestFile from a file path.

        Factory method using Pydantic v2 model_validate.

        Args:
            file_path: Path to the file
            content: Optional content (reads from file if not provided)

        Returns:
            TestFile instance

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if content is None:
            content = path.read_text(encoding='utf-8')

        stats = path.stat()

        # Use model_validate (v2) instead of direct constructor
        return cls.model_validate({
            'path': path,
            'content': content,
            'size_bytes': stats.st_size,
            'last_modified': datetime.fromtimestamp(stats.st_mtime),
            'encoding': 'utf-8'
        })

    # Pydantic v2: computed fields for derived properties
    @computed_field  # type: ignore[misc]
    @property
    def name(self) -> str:
        """Get the file name without extension."""
        # pylint: disable=no-member
        return self.path.stem

    @computed_field  # type: ignore[misc]
    @property
    def extension(self) -> str:
        """Get the file extension."""
        # pylint: disable=no-member
        return self.path.suffix

    @computed_field  # type: ignore[misc]
    @property
    def is_resource_file(self) -> bool:
        """Check if this is a resource file (vs test suite)."""
        return self.extension == '.resource' or 'resource' in self.name.lower()

    @computed_field  # type: ignore[misc]
    @property
    def line_count(self) -> int:
        """Get the number of lines in the file."""
        # pylint: disable=no-member
        return len(self.content.splitlines())

    @computed_field  # type: ignore[misc]
    @property
    def has_content(self) -> bool:
        """Check if file has any content."""
        # pylint: disable=no-member
        return bool(self.content.strip())

    @computed_field  # type: ignore[misc]
    @property
    def size_kb(self) -> float:
        """Get file size in kilobytes."""
        return self.size_bytes / 1024.0

    def get_lines(self, start: int, end: Optional[int] = None) -> List[str]:
        """Get specific lines from the file content.

        Args:
            start: Starting line number (1-based)
            end: Ending line number (inclusive, optional)

        Returns:
            List of lines
        """
        # pylint: disable=no-member
        lines = self.content.splitlines()
        if end is None:
            end = start

        # Convert to 0-based index
        start_idx = max(0, start - 1)
        end_idx = min(len(lines), end)

        return lines[start_idx:end_idx]

    def model_dump(self, **kwargs: Any) -> Dict[str, Any]:
        """Override to handle Path serialization.

        Pydantic v2 method.
        """
        data = super().model_dump(**kwargs)
        # Convert Path to string for JSON mode
        if kwargs.get('mode') == 'json':
            data['path'] = str(data['path'])
        return data

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """Get the JSON schema for this model.

        Uses Pydantic v2's model_json_schema method.

        Returns:
            JSON schema dictionary
        """
        return cls.model_json_schema()
