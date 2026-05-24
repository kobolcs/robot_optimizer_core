# tests/unit/domain/entities/test_test_file.py
"""Unit tests for TestFile entity.

Comprehensive tests for the TestFile entity including factory methods,
computed properties, and validation.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from robot_optimizer_core.domain.entities import TestFile


@pytest.mark.unit
class TestTestFile:
    """Test the TestFile entity."""

    def test_create_test_file(self) -> None:
        """Test creating a test file entity."""
        file_id = uuid4()
        now = datetime.now(UTC)

        test_file = TestFile(
            id=file_id,
            path=Path("tests/sample.robot"),
            content="*** Test Cases ***\nTest Case 1\n    Log    Hello",
            size_bytes=1024,
            last_modified_utc=now,
        )

        assert test_file.id == file_id
        assert test_file.path == Path("tests/sample.robot")
        assert test_file.content.startswith("*** Test Cases ***")
        assert test_file.size_bytes == 1024
        assert test_file.last_modified == now
        assert test_file.encoding == "utf-8"
        assert test_file.test_cases == []
        assert test_file.keywords == []

    def test_auto_generate_id(self) -> None:
        """Test that ID is auto-generated if not provided."""
        test_file = TestFile(
            path=Path("test.robot"),
            content="content",
            size_bytes=100,
            last_modified_utc=datetime.now(UTC),
        )

        assert test_file.id is not None
        assert isinstance(test_file.id, UUID)

    def test_path_string_conversion(self) -> None:
        """Test that string paths are converted to Path objects."""
        test_file = TestFile(
            path="tests/sample.robot",  # String
            content="content",
            size_bytes=100,
            last_modified_utc=datetime.now(UTC),
        )

        assert isinstance(test_file.path, Path)
        assert test_file.path == Path("tests/sample.robot")

        # Nested path
        test_file2 = TestFile(
            path="tests/suite/subsuite/test.robot",
            content="content",
            size_bytes=100,
            last_modified_utc=datetime.now(UTC),
        )
        assert test_file2.path == Path("tests/suite/subsuite/test.robot")

    def test_encoding_validation(self) -> None:
        """Test encoding validation."""
        # Valid encodings (case insensitive)
        for encoding in [
            "utf-8",
            "UTF-8",
            "utf-16",
            "UTF-16",
            "ascii",
            "ASCII",
            "latin-1",
            "LATIN-1",
        ]:
            test_file = TestFile(
                path=Path("test.robot"),
                content="content",
                size_bytes=100,
                last_modified_utc=datetime.now(UTC),
                encoding=encoding,
            )
            assert test_file.encoding == encoding.lower()

        # Invalid encoding
        with pytest.raises(ValidationError) as exc_info:
            TestFile(
                path=Path("test.robot"),
                content="content",
                size_bytes=100,
                last_modified_utc=datetime.now(UTC),
                encoding="invalid-encoding",
            )
        assert "Unsupported encoding" in str(exc_info.value)

    def test_size_validation(self) -> None:
        """Test that negative size raises error."""
        with pytest.raises(ValidationError) as exc_info:
            TestFile(
                path=Path("test.robot"),
                content="content",
                size_bytes=-1,
                last_modified_utc=datetime.now(UTC),
            )
        assert "greater than or equal to 0" in str(exc_info.value)

        # Zero size is valid
        test_file = TestFile(
            path=Path("test.robot"),
            content="",
            size_bytes=0,
            last_modified_utc=datetime.now(UTC),
        )
        assert test_file.size_bytes == 0

    def test_content_size_validation(self) -> None:
        """Test content size validation logic."""
        # The validator allows some variance for encoding differences
        # This test ensures it doesn't fail for reasonable differences
        content = "Test content with special chars: é ñ ü"
        test_file = TestFile(
            path=Path("test.robot"),
            content=content,
            size_bytes=len(content.encode("utf-8")),
            last_modified_utc=datetime.now(UTC),
        )

        # Should validate successfully
        assert test_file.content == content

    def test_from_path_factory(self) -> None:
        """Test creating TestFile from an actual file."""
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".robot", delete=False) as f:
            content = "*** Test Cases ***\nSample Test\n    Log    Hello World"
            f.write(content.encode("utf-8"))
            temp_path = Path(f.name)

        try:
            test_file = TestFile.from_path(temp_path)

            assert test_file.id is not None
            assert test_file.path == temp_path
            assert test_file.content == content
            assert test_file.size_bytes > 0
            assert isinstance(test_file.last_modified, datetime)
            assert test_file.encoding == "utf-8"
        finally:
            temp_path.unlink()

    def test_from_path_with_content_override(self) -> None:
        """Test from_path with content parameter."""
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".robot", delete=False) as f:
            f.write(b"Original content")
            temp_path = Path(f.name)

        try:
            custom_content = "*** Test Cases ***\nCustom content"
            test_file = TestFile.from_path(temp_path, content=custom_content)

            assert test_file.content == custom_content  # Uses provided content
            assert test_file.path == temp_path
        finally:
            temp_path.unlink()

    def test_from_path_file_not_found(self) -> None:
        """Test that from_path raises error for non-existent file."""
        with pytest.raises(FileNotFoundError) as exc_info:
            TestFile.from_path(Path("non_existent.robot"))
        assert "File not found" in str(exc_info.value)

    def test_computed_properties(self) -> None:
        """Test all computed properties."""
        test_file = TestFile(
            path=Path("tests/login_suite.robot"),
            content="Line 1\nLine 2\nLine 3\n",
            size_bytes=2048,
            last_modified_utc=datetime.now(UTC),
        )

        # name property
        assert test_file.name == "login_suite"

        # extension property
        assert test_file.extension == ".robot"

        # is_resource_file property
        assert test_file.is_resource_file is False

        # line_count property
        assert test_file.line_count == 3  # splitlines() does not count trailing newline

        # has_content property
        assert test_file.has_content is True

        # size_kb property
        assert test_file.size_kb == pytest.approx(2.0)

    def test_resource_file_detection(self) -> None:
        """Test resource file detection logic."""
        # By extension
        resource1 = TestFile(
            path=Path("keywords.resource"),
            content="*** Keywords ***",
            size_bytes=100,
            last_modified_utc=datetime.now(UTC),
        )
        assert resource1.is_resource_file is True

        # By name containing 'resource'
        resource2 = TestFile(
            path=Path("common_resources.robot"),
            content="*** Keywords ***",
            size_bytes=100,
            last_modified_utc=datetime.now(UTC),
        )
        assert resource2.is_resource_file is True

        # Not a resource file
        test_file = TestFile(
            path=Path("test_suite.robot"),
            content="*** Test Cases ***",
            size_bytes=100,
            last_modified_utc=datetime.now(UTC),
        )
        assert test_file.is_resource_file is False

    def test_empty_content_properties(self) -> None:
        """Test properties with empty content."""
        test_file = TestFile(
            path=Path("empty.robot"),
            content="",
            size_bytes=0,
            last_modified_utc=datetime.now(UTC),
        )

        assert test_file.line_count == 1  # Empty string is still 1 "line"
        assert test_file.has_content is False
        assert test_file.size_kb == pytest.approx(0.0)

    def test_get_lines(self) -> None:
        """Test getting specific lines from content."""
        content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
        test_file = TestFile(
            path=Path("test.robot"),
            content=content,
            size_bytes=100,
            last_modified_utc=datetime.now(UTC),
        )

        # Single line (default)
        assert test_file.get_lines(2) == ["Line 2"]

        # Range of lines
        assert test_file.get_lines(2, 4) == ["Line 2", "Line 3", "Line 4"]

        # Beyond end
        assert test_file.get_lines(4, 10) == ["Line 4", "Line 5"]

        # Before start (0 or negative becomes 1)
        assert test_file.get_lines(0, 2) == ["Line 1", "Line 2"]
        assert test_file.get_lines(-5, 2) == ["Line 1", "Line 2"]

        # Invalid range (start > end) - gets single line
        assert test_file.get_lines(3, 1) == []  # Empty slice

    def test_entity_equality(self) -> None:
        """Test that entities are compared by ID."""
        id1 = uuid4()
        id2 = uuid4()

        file1 = TestFile(
            id=id1,
            path=Path("test1.robot"),
            content="content1",
            size_bytes=100,
            last_modified_utc=datetime.now(UTC),
        )

        file2 = TestFile(
            id=id1,  # Same ID
            path=Path("test2.robot"),  # Different attributes
            content="content2",
            size_bytes=200,
            last_modified_utc=datetime.now(UTC),
        )

        file3 = TestFile(
            id=id2,  # Different ID
            path=Path("test1.robot"),  # Same attributes as file1
            content="content1",
            size_bytes=100,
            last_modified_utc=datetime.now(UTC),
        )

        # Same ID = same entity
        assert file1 == file2
        assert hash(file1) == hash(file2)
        assert file1.same_identity(file2)

        # Different ID = different entity
        assert file1 != file3
        assert hash(file1) != hash(file3)
        assert not file1.same_identity(file3)

        # Different type
        assert file1 != "not an entity"
        assert file1 != id1

    def test_entity_mutability(self) -> None:
        """Test that entities are mutable."""
        test_file = TestFile(
            path=Path("test.robot"),
            content="original",
            size_bytes=100,
            last_modified_utc=datetime.now(UTC),
        )

        # Should be able to change attributes
        test_file.content = "modified content"
        test_file.test_cases = ["Test 1", "Test 2"]
        test_file.keywords = ["Keyword 1"]

        assert test_file.content == "modified content"
        assert test_file.test_cases == ["Test 1", "Test 2"]
        assert test_file.keywords == ["Keyword 1"]

    def test_model_dump_json_mode(self) -> None:
        """Test model_dump with JSON mode."""
        test_file = TestFile(
            path=Path("test.robot"),
            content="content",
            size_bytes=100,
            last_modified_utc=datetime.now(UTC),
        )

        # Normal mode - Path remains as Path
        normal_data = test_file.model_dump()
        assert isinstance(normal_data["path"], Path)

        # JSON mode - Path becomes string
        json_data = test_file.model_dump(mode="json")
        assert isinstance(json_data["path"], str)
        assert json_data["path"] == "test.robot"

    def test_get_schema(self) -> None:
        """Test that get_schema returns JSON schema."""
        schema = TestFile.get_schema()

        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "path" in schema["properties"]
        assert "content" in schema["properties"]
        assert "size_bytes" in schema["properties"]
        assert "last_modified" in schema["properties"]

    def test_large_content(self) -> None:
        """Test handling large content."""
        # Generate 1MB of content
        large_content = "x" * (1024 * 1024)

        test_file = TestFile(
            path=Path("large.robot"),
            content=large_content,
            size_bytes=len(large_content),
            last_modified_utc=datetime.now(UTC),
        )

        assert len(test_file.content) == 1024 * 1024
        assert test_file.size_kb == pytest.approx(1024.0)
        assert test_file.has_content is True

    def test_unicode_content(self) -> None:
        """Test handling unicode content."""
        unicode_content = """
*** Test Cases ***
Test With Unicode
    Log    Hello 世界 🌍
    Log    Café ñoño
    Log    Здравствуй мир
"""

        test_file = TestFile(
            path=Path("unicode.robot"),
            content=unicode_content,
            size_bytes=len(unicode_content.encode("utf-8")),
            last_modified_utc=datetime.now(UTC),
        )

        assert "世界" in test_file.content
        assert "🌍" in test_file.content
        assert test_file.has_content is True
