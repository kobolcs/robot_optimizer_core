# tests/unit/domain/test_complete_coverage.py
"""Additional tests to ensure 100% coverage of domain layer."""
import pytest
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from robot_optimizer.domain.value_objects import (
    Severity, Location, Pattern, PatternType, Finding,
    SleepPattern, OptimizationSuggestion, OptimizationType
)
from robot_optimizer.domain.entities import DomainTestFile as DomainTestFile, Analysis
from robot_optimizer.domain.base import ValueObject, Entity, AggregateRoot, DomainEvent


class TestCompleteCoverage:
    """Additional tests for 100% coverage."""

    def test_severity_all_comparisons(self):
        """Test all severity comparison combinations."""
        assert Severity.ERROR < Severity.WARNING < Severity.INFO
        assert not (Severity.INFO < Severity.WARNING)
        assert not (Severity.WARNING < Severity.ERROR)

        # Test with non-Severity type
        assert not (Severity.ERROR < "string")

    def test_location_edge_cases(self):
        """Test Location edge cases."""
        # Test contains with column boundaries
        outer = Location(
            file_path=Path("test.robot"),
            line=10,
            column=5,
            end_line=10,
            end_column=20
        )

        # Same line, column before range
        inner1 = Location(
            file_path=Path("test.robot"),
            line=10,
            column=3
        )
        assert not outer.contains(inner1)

        # Same line, column after range
        inner2 = Location(
            file_path=Path("test.robot"),
            line=10,
            column=25
        )
        assert not outer.contains(inner2)

        # Different file
        different = Location(
            file_path=Path("other.robot"),
            line=10,
            column=10
        )
        assert not outer.contains(different)

        # Line before range
        before = Location(
            file_path=Path("test.robot"),
            line=5
        )
        assert not outer.contains(before)

    def test_pattern_all_types(self):
        """Test all pattern type categories."""
        # Test all pattern types have categories
        for pattern_type in PatternType:
            pattern = Pattern(
                type=pattern_type,
                name="Test Pattern",
                description="Test",
                recommendation="Fix it"
            )
            assert pattern.category in [
                "Keywords", "Waits", "Locators",
                "Structure", "Variables", "Imports", "Other"
            ]

    def test_sleep_pattern_complete(self):
        """Test SleepPattern value object completely."""
        # Test all time units
        units = ['s', 'seconds', 'second', 'm', 'minutes', 'minute', 'ms', 'milliseconds']
        for unit in units:
            pattern = SleepPattern(
                duration=Decimal("5"),
                unit=unit,
                line_number=10,
                original_text=f"Sleep    5 {unit}"
            )
            assert pattern.duration_in_seconds > 0

        # Test invalid unit
        with pytest.raises(ValueError, match="Invalid time unit"):
            SleepPattern(
                duration=Decimal("5"),
                unit="hours",
                line_number=10,
                original_text="Sleep    5 hours"
            )

        # Test negative duration
        with pytest.raises(ValueError, match="must be positive"):
            SleepPattern(
                duration=Decimal("-5"),
                unit="s",
                line_number=10,
                original_text="Sleep    -5 s"
            )

        # Test excessive duration
        with pytest.raises(ValueError, match="unreasonably long"):
            SleepPattern(
                duration=Decimal("3601"),
                unit="s",
                line_number=10,
                original_text="Sleep    3601 s"
            )

        # Test equality and hash
        p1 = SleepPattern(
            duration=Decimal("5"),
            unit="s",
            line_number=10,
            original_text="Sleep    5 s"
        )
        p2 = SleepPattern(
            duration=Decimal("5"),
            unit="s",
            line_number=10,
            original_text="Sleep    5 s"
        )
        p3 = SleepPattern(
            duration=Decimal("10"),
            unit="s",
            line_number=10,
            original_text="Sleep    10 s"
        )

        assert p1 == p2
        assert p1 != p3
        assert p1 != "not a sleep pattern"
        assert hash(p1) == hash(p2)
        assert hash(p1) != hash(p3)

    def test_optimization_suggestion_complete(self):
        """Test OptimizationSuggestion completely."""
        finding = Finding.create(
            pattern=Pattern.sleep_in_test("2s"),
            severity=Severity.WARNING,
            location=Location(Path("test.robot"), 10),
            message="Sleep found"
        )

        # Test factory methods
        sleep_suggestion = OptimizationSuggestion.for_sleep_replacement(
            finding=finding,
            original="Sleep    2s",
            replacement="Wait Until Element Is Visible    ${element}    2s"
        )
        assert sleep_suggestion.optimization_type == OptimizationType.REPLACE_SLEEP
        assert sleep_suggestion.is_high_confidence
        assert sleep_suggestion.requires_prerequisites

        xpath_suggestion = OptimizationSuggestion.for_xpath_simplification(
            finding=finding,
            original_xpath="//div[3]/span[1]",
            simplified_xpath="//*[@id='element']",
            confidence=0.6
        )
        assert xpath_suggestion.optimization_type == OptimizationType.SIMPLIFY_XPATH
        assert not xpath_suggestion.is_high_confidence
        assert not xpath_suggestion.is_safe

        # Test equality
        s1 = OptimizationSuggestion.for_sleep_replacement(
            finding=finding,
            original="Sleep    2s",
            replacement="Wait"
        )
        s2 = OptimizationSuggestion.for_sleep_replacement(
            finding=finding,
            original="Sleep    2s",
            replacement="Wait"
        )
        assert s1 == s2
        assert s1 != "not a suggestion"
        assert hash(s1) == hash(s2)

    def test_base_classes_complete(self):
        """Test base classes completely."""
        # Test ValueObject equality with non-ValueObject
        class TestVO(ValueObject):
            value: str

        vo1 = TestVO(value="test")
        assert vo1 != "not a value object"

        # Test Entity with generic type
        class TestEntity(Entity[str]):
            id: str
            name: str

        e1 = TestEntity(id="1", name="Test")
        assert e1 != "not an entity"

        # Test AggregateRoot event handling
        class TestAggregate(AggregateRoot[str]):
            id: str

        agg = TestAggregate(id="1")
        event = DomainEvent()

        # Test event management
        agg.add_event(event)
        assert agg.has_events
        assert agg.event_count == 1
        events = agg.pull_events()
        assert len(events) == 1
        assert not agg.has_events
        assert agg.event_count == 0

    def test_analysis_edge_cases(self):
        """Test Analysis entity edge cases."""
        test_file = DomainTestFile(
            path=Path("test.robot"),
            content="content",
            size_bytes=100,
            last_modified=datetime.utcnow()
        )

        analysis = Analysis(test_file=test_file)

        # Test duration when not completed
        assert analysis.duration_seconds is None

        # Test get methods with empty findings
        assert analysis.get_findings_by_severity(Severity.ERROR) == []
        assert analysis.get_findings_by_pattern(PatternType.SLEEP_IN_TEST) == []
        assert analysis.get_findings_by_line(10) == []
        assert analysis.get_pattern_summary() == {}
        assert analysis.get_affected_lines() == set()

        # Test pattern summary with multiple findings
        pattern1 = Pattern.sleep_in_test("2s")
        pattern2 = Pattern.duplicate_keyword("Test")

        analysis.add_finding(Finding.create(
            pattern=pattern1,
            severity=Severity.WARNING,
            location=Location(Path("test.robot"), 10),
            message="Sleep 1"
        ))
        analysis.add_finding(Finding.create(
            pattern=pattern1,
            severity=Severity.WARNING,
            location=Location(Path("test.robot"), 20),
            message="Sleep 2"
        ))
        analysis.add_finding(Finding.create(
            pattern=pattern2,
            severity=Severity.ERROR,
            location=Location(Path("test.robot"), 30),
            message="Duplicate"
        ))

        summary = analysis.get_pattern_summary()
        assert summary[PatternType.SLEEP_IN_TEST] == 2
        assert summary[PatternType.DUPLICATE_KEYWORD] == 1

    def test_finding_validation_edge_cases(self):
        """Test Finding validation edge cases."""
        # Test whitespace-only message
        with pytest.raises(ValueError, match="cannot be empty"):
            Finding(
                pattern=Pattern.sleep_in_test("1s"),
                severity=Severity.WARNING,
                location=Location(Path("test.robot"), 1),
                message="   \t\n   "
            )

    def test_all_optimization_types(self):
        """Test all optimization types are covered."""
        # Ensure all types can be created
        for opt_type in OptimizationType:
            suggestion = OptimizationSuggestion(
                finding_id="test-id",
                optimization_type=opt_type,
                description="Test description",
                original_code="original",
                suggested_code="suggested",
                confidence=0.8,
                estimated_impact="High impact"
            )
            assert suggestion.optimization_type == opt_type

    def test_test_file_edge_cases(self):
        """Test DomainTestFile entity edge cases."""
        # Test empty content
        test_file = DomainTestFile(
            path=Path("empty.robot"),
            content="",
            size_bytes=0,
            last_modified=datetime.utcnow()
        )
        assert test_file.line_count == 1  # Empty string still has 1 "line"

        # Test get_lines with negative indices
        test_file2 = DomainTestFile(
            path=Path("test.robot"),
            content="Line 1\nLine 2\nLine 3",
            size_bytes=100,
            last_modified=datetime.utcnow()
        )

        # Start before beginning
        lines = test_file2.get_lines(-5, 1)
        assert lines == ["Line 1"]

        # End beyond file
        lines = test_file2.get_lines(3, 100)
        assert lines == ["Line 3"]

    def test_pattern_type_coverage(self):
        """Ensure all PatternType values are tested."""
        # Create a pattern for each type to ensure coverage
        pattern_configs = {
            PatternType.UNUSED_KEYWORD: ("Unused Keyword", "Keyword not used"),
            PatternType.COMPLEX_KEYWORD: ("Complex Keyword", "Too complex"),
            PatternType.MISSING_DOCUMENTATION: ("Missing Docs", "No docs"),
            PatternType.HARD_CODED_WAIT: ("Hard Wait", "Fixed wait time"),
            PatternType.INEFFICIENT_WAIT: ("Bad Wait", "Inefficient waiting"),
            PatternType.ABSOLUTE_XPATH: ("Absolute XPath", "Uses absolute path"),
            PatternType.COMPLEX_CSS: ("Complex CSS", "CSS too complex"),
            PatternType.ID_OVER_XPATH: ("Use ID", "ID available"),
            PatternType.NO_TAGS: ("No Tags", "Missing tags"),
            PatternType.DUPLICATE_TEST: ("Duplicate Test", "Test duplicated"),
            PatternType.MISSING_SETUP_TEARDOWN: ("No Setup", "Missing setup"),
            PatternType.HARDCODED_VALUE: ("Hardcoded", "Value hardcoded"),
            PatternType.UNUSED_VARIABLE: ("Unused Var", "Variable not used"),
            PatternType.GLOBAL_VARIABLE_MISUSE: ("Global Misuse", "Bad global"),
            PatternType.UNUSED_IMPORT: ("Unused Import", "Import not used"),
            PatternType.WILDCARD_IMPORT: ("Wildcard Import", "Uses *"),
            PatternType.CIRCULAR_IMPORT: ("Circular Import", "Circular ref"),
        }

        for pattern_type, (name, desc) in pattern_configs.items():
            pattern = Pattern(
                type=pattern_type,
                name=name,
                description=desc,
                recommendation="Fix it"
            )
            assert pattern.type == pattern_type
            assert pattern.category != "Other"  # Should have proper category

    def test_analysis_completion_error(self):
        """Test analysis completion when already completed."""
        test_file = DomainTestFile(
            path=Path("test.robot"),
            content="content",
            size_bytes=100,
            last_modified=datetime.utcnow()
        )

        analysis = Analysis(test_file=test_file)
        analysis.complete()

        # Try to complete again
        with pytest.raises(ValueError, match="already completed"):
            analysis.complete()

    def test_optimization_suggestion_validation(self):
        """Test OptimizationSuggestion validation."""
        # Test empty description
        with pytest.raises(ValueError, match="cannot be empty"):
            OptimizationSuggestion(
                finding_id="test",
                optimization_type=OptimizationType.REPLACE_SLEEP,
                description="  ",
                original_code="old",
                suggested_code="new",
                confidence=0.5,
                estimated_impact="test"
            )

        # Test same original and suggested code
        with pytest.raises(ValueError, match="must be different"):
            OptimizationSuggestion(
                finding_id="test",
                optimization_type=OptimizationType.REPLACE_SLEEP,
                description="Test",
                original_code="same",
                suggested_code="same",
                confidence=0.5,
                estimated_impact="test"
            )

    def test_test_file_encoding_validation(self):
        """Test DomainTestFile encoding validation."""
        # Test invalid encoding
        with pytest.raises(ValueError, match="Unsupported encoding"):
            DomainTestFile(
                path=Path("test.robot"),
                content="content",
                size_bytes=100,
                last_modified=datetime.utcnow(),
                encoding="invalid-encoding"
            )

        # Test valid encodings
        for encoding in ['utf-8', 'utf-16', 'ascii', 'latin-1']:
            test_file = DomainTestFile(
                path=Path("test.robot"),
                content="content",
                size_bytes=100,
                last_modified=datetime.utcnow(),
                encoding=encoding.upper()  # Test case insensitive
            )
            assert test_file.encoding == encoding.lower()

    def test_location_model_dump_json_mode(self):
        """Test Location model_dump with json mode."""
        loc = Location(file_path=Path("test.robot"), line=10)

        # Test normal mode - Path remains as Path
        data = loc.model_dump()
        assert isinstance(data['file_path'], Path)

        # Test json mode - Path becomes string
        json_data = loc.model_dump(mode='json')
        assert isinstance(json_data['file_path'], str)
        assert json_data['file_path'] == "test.robot"

    def test_sleep_pattern_model_dump_json_mode(self):
        """Test SleepPattern model_dump with json mode."""
        pattern = SleepPattern(
            duration=Decimal("5.5"),
            unit="s",
            line_number=10,
            original_text="Sleep    5.5 s"
        )

        # Test json mode includes computed fields
        json_data = pattern.model_dump(mode='json')
        assert isinstance(json_data['duration'], float)
        assert json_data['duration'] == 5.5
        assert 'duration_in_seconds' in json_data
        assert 'is_excessive' in json_data
        assert 'normalized_unit' in json_data
        assert 'severity_hint' in json_data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=robot_optimizer.domain", "--cov-report=term-missing"])