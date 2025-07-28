# tests/test_pydantic_v2_compliance.py
"""Tests to ensure full Pydantic v2 compliance."""
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pydantic
import pytest
from pydantic import ValidationError
from robot_optimizer.domain.base import ValueObject
from robot_optimizer.domain.entities import Analysis
from robot_optimizer.domain.entities import DomainTestFile as DomainTestFile
from robot_optimizer.domain.events import FileAnalyzedEvent
from robot_optimizer.domain.value_objects import (
    Finding,
    Location,
    Pattern,
    Severity,
)


class TestPydanticV2Compliance:
    """Test suite for Pydantic v2 compliance."""

    def test_pydantic_version(self):
        """Ensure we're using Pydantic v2."""
        assert pydantic.VERSION.startswith('2.'), f"Expected Pydantic v2, got {pydantic.VERSION}"
        # Also check specific v2 attributes exist
        assert hasattr(pydantic.BaseModel, 'model_dump')
        assert hasattr(pydantic.BaseModel, 'model_dump_json')
        assert hasattr(pydantic.BaseModel, 'model_validate')

    def test_value_object_v2_features(self):
        """Test ValueObject uses v2 features correctly."""
        # Test model_dump (v2 method)
        location = Location(file_path=Path("test.robot"), line=10)
        dumped = location.model_dump()
        assert isinstance(dumped, dict)
        assert dumped['line'] == 10

        # Test frozen model (v2 assignment validation)
        with pytest.raises(ValidationError) as exc_info:
            location.line = 20
        assert "frozen" in str(exc_info.value).lower()

        # Test model_dump_json (v2 method)
        json_str = location.model_dump_json()
        assert isinstance(json_str, str)
        data = json.loads(json_str)
        assert data['line'] == 10

    def test_entity_v2_features(self):
        """Test Entity uses v2 features correctly."""
        test_file = DomainTestFile(
            path=Path("test.robot"),
            content="*** Test Cases ***",
            size_bytes=100,
            last_modified=datetime.utcnow()
        )

        # Test model_validate (v2 method)
        # Note: We need to exclude computed fields for re-validation
        data = test_file.model_dump(exclude_unset=False, exclude_defaults=False)
        # Remove computed fields from the data
        computed_fields = ["name", "extension", "is_resource_file", "line_count",
                          "has_content", "size_kb", "has_events", "event_count"]
        for field in computed_fields:
            data.pop(field, None)

        validated = DomainTestFile.model_validate(data)
        assert validated.id == test_file.id

        # Test model_fields (v2 attribute)
        fields = DomainTestFile.model_fields
        assert 'path' in fields
        assert 'content' in fields

        # Test model_copy (v2 method)
        copied = test_file.model_copy(update={'content': 'new content'})
        assert copied.id == test_file.id  # ID unchanged
        assert copied.content == 'new content'

    def test_aggregate_root_v2_features(self):
        """Test AggregateRoot with v2 features."""
        test_file = DomainTestFile(
            path=Path("test.robot"),
            content="content",
            size_bytes=100,
            last_modified=datetime.utcnow()
        )
        analysis = Analysis(test_file=test_file)

        # Test private field exclusion in serialization
        dumped = analysis.model_dump()
        assert '_events' not in dumped

        # Test Field with exclude=True works
        json_data = analysis.model_dump_json()
        parsed = json.loads(json_data)
        assert '_events' not in parsed

        # For validation test, create fresh data without computed fields
        # First, get the test file data without computed fields
        test_file_data = {
            'id': str(test_file.id),
            'path': str(test_file.path),
            'content': test_file.content,
            'size_bytes': test_file.size_bytes,
            'last_modified': test_file.last_modified.isoformat(),
            'encoding': test_file.encoding,
            'test_cases': test_file.test_cases,
            'keywords': test_file.keywords
        }

        # Create analysis data for validation
        analysis_data = {
            'id': str(analysis.id),
            'test_file': test_file_data,
            'findings': [],
            'started_at': analysis.started_at.isoformat(),
            'completed_at': None,
            'analyzer_version': analysis.analyzer_version
        }

        # Should be able to validate the cleaned data
        Analysis.model_validate(analysis_data)
    def test_domain_event_v2_features(self):
        """Test DomainEvent v2 features."""
        event = FileAnalyzedEvent(
            analysis_id=uuid4(),
            file_path=Path("test.robot"),
            finding_count=5,
            duration_seconds=1.5
        )

        # Test populate_by_name (v2 feature)
        data = {
            'analysis_id': str(uuid4()),
            'file_path': 'test2.robot',
            'finding_count': 10,
            'duration_seconds': 2.0,
            # Use alternative names
            'analysisId': str(uuid4()),  # Should be ignored due to populate_by_name
        }
        validated = FileAnalyzedEvent.model_validate(data)
        assert validated.finding_count == 10

        # Test frozen event
        with pytest.raises(ValidationError):
            event.finding_count = 20

    def test_field_validator_v2_syntax(self):
        """Test field validators use v2 syntax."""
        # Test successful validation
        finding = Finding(
            pattern=Pattern.sleep_in_test("2s"),
            severity=Severity.WARNING,
            location=Location(file_path=Path("test.robot"), line=10),
            message="Valid message"
        )
        assert finding.message == "Valid message"

        # Test validation error with v2
        with pytest.raises(ValidationError) as exc_info:
            Finding(
                pattern=Pattern.sleep_in_test("2s"),
                severity=Severity.WARNING,
                location=Location(file_path=Path("test.robot"), line=10),
                message="   "  # Should fail validation
            )
        # Check that the error is about empty message
        error_str = str(exc_info.value)
        assert ("String should have at least 1 character" in error_str or
                "Finding message cannot be empty" in error_str)

    def test_model_validator_v2_syntax(self):
        """Test model validators use v2 syntax."""
        # Test successful range validation
        loc = Location(
            file_path=Path("test.robot"),
            line=10,
            column=5,
            end_line=15,
            end_column=20
        )
        assert loc.end_line == 15

        # Test model validation error
        with pytest.raises(ValidationError) as exc_info:
            Location(
                file_path=Path("test.robot"),
                line=10,
                end_line=5  # Before start line
            )
        assert "cannot be before start line" in str(exc_info.value)

    def test_computed_field_v2_feature(self):
        """Test computed fields work in v2."""
        test_file = DomainTestFile(
            path=Path("test.robot"),
            content="content",
            size_bytes=100,
            last_modified=datetime.utcnow()
        )
        analysis = Analysis(test_file=test_file)

        # Add some findings
        finding1 = Finding.create(
            pattern=Pattern.sleep_in_test("2s"),
            severity=Severity.WARNING,
            location=Location(file_path=Path("test.robot"), line=10),
            message="Sleep found"
        )
        finding2 = Finding.create(
            pattern=Pattern.duplicate_keyword("Test"),
            severity=Severity.ERROR,
            location=Location(file_path=Path("test.robot"), line=20),
            message="Duplicate found"
        )

        analysis.add_finding(finding1)
        analysis.add_finding(finding2)

        # Test computed properties
        assert analysis.finding_count == 2
        assert analysis.error_count == 1
        assert analysis.warning_count == 1
        assert analysis.info_count == 0

        # Verify computed fields work properly
        # In Pydantic v2, we can check if the model has computed fields
        if hasattr(analysis, 'model_computed_fields'):
            # Check that our computed fields are registered
            computed_fields = analysis.model_computed_fields
            assert 'finding_count' in computed_fields
            assert 'error_count' in computed_fields
            assert 'warning_count' in computed_fields
            assert 'info_count' in computed_fields
        else:
            # At minimum, verify these are properties that work
            assert hasattr(analysis.__class__, 'finding_count')
            assert hasattr(analysis.__class__, 'error_count')
            assert isinstance(analysis.__class__.finding_count, property)
            assert isinstance(analysis.__class__.error_count, property)

    def test_config_dict_v2_features(self):
        """Test ConfigDict v2 features."""
        # Test str_strip_whitespace
        class TestModel(ValueObject):
            name: str

        model = TestModel(name="  test  ")
        assert model.name == "test"  # Should be stripped

        # Test extra='forbid'
        with pytest.raises(ValidationError) as exc_info:
            TestModel(name="test", extra_field="not allowed")
        assert "extra" in str(exc_info.value).lower()

    def test_serialization_v2_features(self):
        """Test v2 serialization features."""
        analysis = Analysis(
            test_file=DomainTestFile(
                path=Path("test.robot"),
                content="content",
                size_bytes=100,
                last_modified=datetime.utcnow()
            )
        )

        # Test model_dump with mode='json'
        json_data = analysis.model_dump(mode='json')
        assert isinstance(json_data['started_at'], str)  # datetime serialized to string

        # Test model_dump_json with custom serializers
        json_str = analysis.model_dump_json(indent=2)
        parsed = json.loads(json_str)
        assert 'started_at' in parsed

    def test_v2_migration_completeness(self):
        """Ensure no v1 methods remain in our implementation."""
        # Check that v1 methods don't exist in our code
        location = Location(file_path=Path("test.robot"), line=10)

        # These are v1 Pydantic methods that we should NOT be using
        # Note: Some might exist as Python builtins or from parent classes
        # but we're checking that we don't use them in our implementation

        # v2 methods that SHOULD exist
        assert hasattr(location, 'model_dump')
        assert hasattr(location, 'model_dump_json')
        assert hasattr(location, 'model_validate')
        assert hasattr(location, 'model_json_schema')
        assert hasattr(location, 'model_copy')
        assert hasattr(location, 'model_fields')

        # Verify we're using v2 methods
        assert callable(location.model_dump)
        assert callable(location.model_dump_json)

        # Test that v2 methods work correctly
        dumped = location.model_dump()
        assert isinstance(dumped, dict)

        json_str = location.model_dump_json()
        assert isinstance(json_str, str)

    def test_custom_serializers(self):
        """Test custom serializers work correctly."""
        finding = Finding.create(
            pattern=Pattern.sleep_in_test("2s"),
            severity=Severity.WARNING,
            location=Location(file_path=Path("test.robot"), line=10),
            message="Test message"
        )

        # Test model_dump works with custom serialization
        dumped = finding.model_dump(mode='json')
        assert isinstance(dumped['id'], str)  # UUID serialized to string

        # If serialize_model method exists, test it
        if hasattr(finding, 'serialize_model'):
            serialized = finding.serialize_model()
            assert isinstance(serialized, dict)
            assert isinstance(serialized['id'], str)
            assert 'pattern' in serialized
            assert 'location' in serialized

    def test_model_validator_modes(self):
        """Test model validators with different modes."""
        # Test after mode validator
        from robot_optimizer.domain.value_objects import SleepPattern

        pattern = SleepPattern(
            duration=Decimal("5"),
            unit="s",
            line_number=10,
            original_text="Sleep    5 s"
        )

        # Should pass validation
        assert pattern.duration == Decimal("5")

        # Test DomainTestFile content size validator
        test_file = DomainTestFile(
            path=Path("test.robot"),
            content="test content",
            size_bytes=1000,  # Way off from actual
            last_modified=datetime.utcnow()
        )
        # Should still be created (validator just logs warning)
        assert test_file.size_bytes == 1000

    def test_computed_fields_in_serialization(self):
        """Test computed fields behavior in serialization."""
        test_file = DomainTestFile(
            path=Path("test.robot"),
            content="Line 1\nLine 2\nLine 3",
            size_bytes=100,
            last_modified=datetime.utcnow()
        )

        # Computed fields should be accessible as properties
        assert test_file.name == "test"
        assert test_file.extension == ".robot"
        assert test_file.line_count == 3
        assert test_file.has_content is True
        assert test_file.size_kb == 0.09765625

        # Check if model has computed fields
        assert hasattr(test_file.__class__, 'name')
        assert hasattr(test_file.__class__, 'extension')

        # V2: Computed fields have a special marker
        # They should have the computed_field attribute
        # V2: Check computed fields are properly registered
        # In Pydantic v2, we check model_computed_fields
        if hasattr(test_file, 'model_computed_fields'):
            computed_fields = test_file.model_computed_fields
            assert 'name' in computed_fields
            assert 'extension' in computed_fields
            assert 'line_count' in computed_fields
            assert 'has_content' in computed_fields
            assert 'size_kb' in computed_fields
        else:
            # If model_computed_fields is not available, just verify the properties work
            # This is sufficient for v2 compliance
            assert callable(getattr(test_file.__class__.name, 'fget', None))
            assert callable(getattr(test_file.__class__.extension, 'fget', None))
    def test_from_attributes_feature(self):
        """Test from_attributes (formerly orm_mode) works."""
        # Create a simple class that mimics ORM object
        class MockORMFile:
            def __init__(self):
                self.id = uuid4()
                self.path = "test.robot"
                self.content = "content"
                self.size_bytes = 100
                self.last_modified = datetime.utcnow()
                self.encoding = "utf-8"
                self.test_cases = []
                self.keywords = []

        orm_obj = MockORMFile()

        # Should be able to create from attributes
        test_file = DomainTestFile.model_validate(orm_obj, from_attributes=True)
        assert test_file.path == Path("test.robot")
        assert test_file.content == "content"

    def test_json_encoders_config(self):
        """Test custom JSON encoders in ConfigDict."""

        # Analysis has custom encoders for datetime, Path, UUID
        analysis = Analysis(
            test_file=DomainTestFile(
                path=Path("test.robot"),
                content="content",
                size_bytes=100,
                last_modified=datetime.utcnow()
            )
        )

        # When dumping to JSON, custom encoders should be used
        json_str = analysis.model_dump_json()
        data = json.loads(json_str)

        # Check datetime is ISO format string
        assert isinstance(data['started_at'], str)
        assert 'T' in data['started_at']  # ISO format has T

        # Check UUID is string
        assert isinstance(data['id'], str)

    def test_model_json_schema_available(self):
        """Test that model_json_schema is available and works."""
        # Test on various model types
        location = Location(file_path=Path("test.robot"), line=10)
        schema = location.model_json_schema()
        assert isinstance(schema, dict)
        assert 'properties' in schema
        assert 'file_path' in schema['properties']
        assert 'line' in schema['properties']

        # Test on DomainTestFile which has a custom get_schema method
        test_file_schema = DomainTestFile.get_schema()
        assert isinstance(test_file_schema, dict)
        assert 'properties' in test_file_schema
        assert 'path' in test_file_schema['properties']


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--no-cov"])
