# tests/unit/domain/value_objects/test_finding.py
"""Unit tests for Finding value object.

Comprehensive tests for the Finding value object including validation,
factory methods, and all properties to ensure mutation testing resilience.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from robot_optimizer_core.domain.value_objects import (
    Finding,
    Location,
    Pattern,
    PatternType,
    Severity,
)


@pytest.mark.unit
class TestFinding:
    """Test the Finding value object."""

    @pytest.fixture
    def sample_pattern(self) -> Pattern:
        """Create a sample pattern for testing."""
        return Pattern.sleep_in_test("2 seconds")

    @pytest.fixture
    def sample_location(self) -> Location:
        """Create a sample location for testing."""
        return Location(file_path=Path("test.robot"), line=25, column=10)

    def test_create_finding(
        self, sample_pattern: Pattern, sample_location: Location
    ) -> None:
        """Test creating a finding with all required fields."""
        finding_id = uuid4()
        finding = Finding(
            id=finding_id,
            pattern=sample_pattern,
            severity=Severity.WARNING,
            location=sample_location,
            message="Using Sleep makes tests slow and fragile",
        )

        assert finding.id == finding_id
        assert finding.pattern == sample_pattern
        assert finding.severity == Severity.WARNING
        assert finding.location == sample_location
        assert finding.message == "Using Sleep makes tests slow and fragile"
        assert finding.context is None

    def test_auto_generate_id(
        self, sample_pattern: Pattern, sample_location: Location
    ) -> None:
        """Test that ID is auto-generated if not provided."""
        finding = Finding(
            pattern=sample_pattern,
            severity=Severity.WARNING,
            location=sample_location,
            message="Test message",
        )

        assert finding.id is not None
        assert isinstance(finding.id, UUID)

    def test_create_with_context(
        self, sample_pattern: Pattern, sample_location: Location
    ) -> None:
        """Test creating finding with context."""
        context = {"duration": "2 seconds", "line_text": "Sleep    2 seconds"}
        finding = Finding(
            pattern=sample_pattern,
            severity=Severity.WARNING,
            location=sample_location,
            message="Sleep detected",
            context=context,
        )

        assert finding.context == context
        assert finding.context["duration"] == "2 seconds"

        # Verify context is copied (immutability)
        context["duration"] = "modified"
        assert finding.context["duration"] == "2 seconds"

    def test_create_factory_method(
        self, sample_pattern: Pattern, sample_location: Location
    ) -> None:
        """Test the create factory method with kwargs as context."""
        finding = Finding.create(
            pattern=sample_pattern,
            severity=Severity.WARNING,
            location=sample_location,
            message="Sleep usage detected",
            duration="2 seconds",
            suggested_wait="Wait Until Element Is Visible",
            line_number=25,
        )

        assert finding.id is not None
        assert finding.pattern == sample_pattern
        assert finding.severity == Severity.WARNING
        assert finding.location == sample_location
        assert finding.message == "Sleep usage detected"
        assert finding.context == {
            "duration": "2 seconds",
            "suggested_wait": "Wait Until Element Is Visible",
            "line_number": 25,
        }

    def test_message_validation(
        self, sample_pattern: Pattern, sample_location: Location
    ) -> None:
        """Test message field validation."""
        # Empty message
        with pytest.raises(ValidationError) as exc_info:
            Finding(
                pattern=sample_pattern,
                severity=Severity.WARNING,
                location=sample_location,
                message="",
            )
        assert "at least 1 character" in str(exc_info.value)

        # Whitespace-only message
        with pytest.raises(ValidationError) as exc_info:
            Finding(
                pattern=sample_pattern,
                severity=Severity.WARNING,
                location=sample_location,
                message="   \t\n   ",
            )
        assert "Finding message cannot be empty" in str(exc_info.value)

    def test_computed_properties(self, sample_location: Location) -> None:
        """Test all computed properties."""
        pattern = Pattern(
            type=PatternType.SLEEP_IN_TEST,
            name="Sleep Pattern",
            description="Sleep found",
            recommendation="Use waits",
            auto_fixable=True,
        )

        finding = Finding(
            pattern=pattern,
            severity=Severity.ERROR,
            location=sample_location,
            message="Test message",
        )

        # file_path property
        assert finding.file_path == "test.robot"

        # line_number property
        assert finding.line_number == 25

        # is_auto_fixable property
        assert finding.is_auto_fixable is True

        # has_context property
        assert finding.has_context is False

        # With context
        finding_with_context = Finding(
            pattern=pattern,
            severity=Severity.ERROR,
            location=sample_location,
            message="Test message",
            context={"key": "value"},
        )
        assert finding_with_context.has_context is True

    def test_format_for_console(self, sample_location: Location) -> None:
        """Test console formatting output."""
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
            suggestion="Wait Until Element Is Visible",
        )

        output = finding.format_for_console()

        # Check all parts are included
        assert "⚠️ Sleep in Test" in output
        assert "test.robot:25:10" in output
        assert "Found Sleep 2 seconds" in output
        assert "💡 Use explicit waits instead" in output
        assert "duration: 2 seconds" in output
        assert "suggestion: Wait Until Element Is Visible" in output

    def test_format_console_no_recommendation_duplicate(self) -> None:
        """Test format doesn't duplicate message as recommendation."""
        pattern = Pattern(
            type=PatternType.DUPLICATE_KEYWORD,
            name="Duplicate",
            description="Duplicate found",
            recommendation="Duplicate found",  # Same as message
        )

        location = Location(Path("test.robot"), 10)
        finding = Finding(
            pattern=pattern,
            severity=Severity.ERROR,
            location=location,
            message="Duplicate found",
        )

        output = finding.format_for_console()

        # Should only appear once
        assert output.count("Duplicate found") == 1
        # No recommendation emoji
        assert "💡" not in output

    def test_to_dict_conversion(self) -> None:
        """Test converting finding to dictionary."""
        pattern = Pattern.sleep_in_test("3s")
        location = Location(Path("suite/test.robot"), 42, 15)

        finding = Finding.create(
            pattern=pattern,
            severity=Severity.ERROR,
            location=location,
            message="Critical sleep usage",
            duration="3s",
            impact="High",
        )

        data = finding.to_dict()

        # Check all expected fields
        assert isinstance(data["id"], str)
        assert data["file_path"] == "suite/test.robot"
        assert data["line_number"] == 42
        assert data["is_auto_fixable"] is True
        assert data["pattern_type"] == "SLEEP_IN_TEST"
        assert data["pattern_name"] == pattern.name
        assert data["recommendation"] == pattern.recommendation
        assert data["pattern"]["type"] == PatternType.SLEEP_IN_TEST
        assert data["severity"] == Severity.ERROR
        assert data["location"]["line"] == 42
        assert data["location"]["column"] == 15
        assert data["message"] == "Critical sleep usage"
        assert data["context"]["duration"] == "3s"
        assert data["context"]["impact"] == "High"

    def test_model_serialization(self) -> None:
        """Test custom model serialization."""
        pattern = Pattern.duplicate_keyword("Test")
        location = Location(Path("test.robot"), 10)

        finding = Finding(
            pattern=pattern,
            severity=Severity.WARNING,
            location=location,
            message="Duplicate keyword",
        )

        # Test model_dump (inherited from ValueObject)
        dumped = finding.model_dump()
        assert isinstance(dumped["id"], UUID)
        assert dumped["pattern"] == pattern
        assert dumped["severity"] == Severity.WARNING

        # Test model_dump with mode='json'
        json_data = finding.model_dump(mode="json")
        assert isinstance(json_data["id"], str)  # UUID serialized to string
        assert isinstance(json_data["pattern"], dict)
        assert json_data["severity"] == 2  # Enum value

    def test_finding_equality(self) -> None:
        """Test finding equality comparison."""
        pattern = Pattern.sleep_in_test("1s")
        location = Location(Path("test.robot"), 10)

        id1 = uuid4()
        finding1 = Finding(
            id=id1,
            pattern=pattern,
            severity=Severity.WARNING,
            location=location,
            message="Test",
        )

        finding2 = Finding(
            id=id1,
            pattern=pattern,
            severity=Severity.WARNING,
            location=location,
            message="Test",
        )

        finding3 = Finding(
            id=uuid4(),  # Different ID
            pattern=pattern,
            severity=Severity.WARNING,
            location=location,
            message="Test",
        )

        # Same ID and content
        assert finding1 == finding2
        assert hash(finding1) == hash(finding2)

        # Different ID
        assert finding1 != finding3
        assert hash(finding1) != hash(finding3)

        # Different type
        assert finding1 != "finding"
        assert finding1 != 42

    def test_finding_immutability(self) -> None:
        """Test that findings are immutable."""
        pattern = Pattern.sleep_in_test("1s")
        location = Location(Path("test.robot"), 10)

        finding = Finding(
            pattern=pattern,
            severity=Severity.WARNING,
            location=location,
            message="Test",
        )

        with pytest.raises(ValidationError):
            finding.severity = Severity.ERROR

        with pytest.raises(ValidationError):
            finding.message = "Changed"

        with pytest.raises(ValidationError):
            finding.pattern = Pattern.duplicate_keyword("New")

    def test_finding_with_all_severity_levels(self) -> None:
        """Test findings with all severity levels."""
        pattern = Pattern.sleep_in_test("1s")
        location = Location(Path("test.robot"), 10)

        for severity in [Severity.ERROR, Severity.WARNING, Severity.INFO]:
            finding = Finding(
                pattern=pattern,
                severity=severity,
                location=location,
                message=f"Test with {severity.name}",
            )

            assert finding.severity == severity

            # Test console formatting includes correct emoji
            output = finding.format_for_console()
            assert severity.emoji in output
