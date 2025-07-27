# tests/unit/domain/test_entities.py
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
import tempfile
from pydantic import ValidationError

from robot_optimizer.domain.entities import DomainTestFile as DomainTestFile, Analysis
from robot_optimizer.domain.value_objects import (
    Finding, Pattern, PatternType, Severity, Location
)
from robot_optimizer.domain.events import (
    FileAnalyzedEvent, HighSeverityFindingEvent
)


class TestTestFile:
    """Test the DomainTestFile entity."""

    def test_create_test_file(self):
        """Test creating a test file entity."""
        file_id = uuid4()
        now = datetime.utcnow()
        test_file = DomainTestFile(
            id=file_id,
            path=Path("tests/sample.robot"),
            content="*** Test Cases ***\nTest Case 1\n    Log    Hello",
            size_bytes=1024,
            last_modified=now
        )

        assert test_file.id == file_id
        assert test_file.path == Path("tests/sample.robot")
        assert test_file.content.startswith("*** Test Cases ***")
        assert test_file.size_bytes == 1024
        assert test_file.encoding == "utf-8"
        assert test_file.test_cases == []
        assert test_file.keywords == []

    def test_path_conversion(self):
        """Test that string paths are converted to Path objects."""
        test_file = DomainTestFile(
            path="tests/sample.robot",
            content="content",
            size_bytes=100,
            last_modified=datetime.utcnow()
        )
        assert isinstance(test_file.path, Path)

    def test_auto_generate_id(self):
        """Test that ID is auto-generated if not provided."""
        test_file = DomainTestFile(
            path=Path("test.robot"),
            content="content",
            size_bytes=100,
            last_modified=datetime.utcnow()
        )
        assert test_file.id is not None

    def test_from_path_factory(self):
        """Test creating DomainTestFile from an actual file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.robot', delete=False) as f:
            f.write("*** Test Cases ***\nSample Test\n    Log    Hello World")
            temp_path = Path(f.name)

        try:
            test_file = DomainTestFile.from_path(temp_path)

            assert test_file.id is not None
            assert test_file.path == temp_path
            assert "Sample Test" in test_file.content
            assert test_file.size_bytes > 0
            assert isinstance(test_file.last_modified, datetime)
        finally:
            temp_path.unlink()

    def test_from_path_file_not_found(self):
        """Test that from_path raises error for non-existent file."""
        with pytest.raises(FileNotFoundError):
            DomainTestFile.from_path(Path("non_existent.robot"))

    def test_file_properties(self):
        """Test DomainTestFile properties."""
        test_file = DomainTestFile(
            path=Path("tests/login_suite.robot"),
            content="content",
            size_bytes=100,
            last_modified=datetime.utcnow()
        )

        assert test_file.name == "login_suite"
        assert test_file.extension == ".robot"
        assert test_file.is_resource_file is False

    def test_resource_file_detection(self):
        """Test resource file detection."""
        # By extension
        resource1 = DomainTestFile(
            path=Path("keywords.resource"),
            content="",
            size_bytes=0,
            last_modified=datetime.utcnow()
        )
        assert resource1.is_resource_file is True

        # By name
        resource2 = DomainTestFile(
            path=Path("common_resources.robot"),
            content="",
            size_bytes=0,
            last_modified=datetime.utcnow()
        )
        assert resource2.is_resource_file is True

    def test_line_count(self):
        """Test line counting."""
        test_file = DomainTestFile(
            path=Path("test.robot"),
            content="Line 1\nLine 2\nLine 3\n",
            size_bytes=100,
            last_modified=datetime.utcnow()
        )
        assert test_file.line_count == 4  # Including empty line at end

    def test_get_lines(self):
        """Test getting specific lines from content."""
        content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
        test_file = DomainTestFile(
            path=Path("test.robot"),
            content=content,
            size_bytes=100,
            last_modified=datetime.utcnow()
        )

        # Single line
        assert test_file.get_lines(2) == ["Line 2"]

        # Range of lines
        assert test_file.get_lines(2, 4) == ["Line 2", "Line 3", "Line 4"]

        # Beyond end
        assert test_file.get_lines(4, 10) == ["Line 4", "Line 5"]

        # Before start
        assert test_file.get_lines(0, 2) == ["Line 1", "Line 2"]

    def test_entity_equality(self):
        """Test that entities are compared by ID."""
        id1 = uuid4()
        id2 = uuid4()

        file1 = DomainTestFile(
            id=id1,
            path=Path("test1.robot"),
            content="content1",
            size_bytes=100,
            last_modified=datetime.utcnow()
        )

        file2 = DomainTestFile(
            id=id1,  # Same ID
            path=Path("test2.robot"),  # Different path
            content="content2",
            size_bytes=200,
            last_modified=datetime.utcnow()
        )

        file3 = DomainTestFile(
            id=id2,  # Different ID
            path=Path("test1.robot"),
            content="content1",
            size_bytes=100,
            last_modified=datetime.utcnow()
        )

        assert file1 == file2  # Same ID
        assert file1 != file3  # Different ID
        assert hash(file1) == hash(file2)
        assert hash(file1) != hash(file3)

    def test_size_validation(self):
        """Test that negative size raises error."""
        with pytest.raises(ValidationError) as exc_info:
            DomainTestFile(
                path=Path("test.robot"),
                content="content",
                size_bytes=-1,
                last_modified=datetime.utcnow()
            )
        assert "greater than or equal to 0" in str(exc_info.value)


class TestAnalysis:
    """Test the Analysis aggregate root."""

    @pytest.fixture
    def test_file(self):
        """Create a test file for analysis."""
        return DomainTestFile(
            path=Path("test.robot"),
            content="*** Test Cases ***\nTest\n    Sleep    2s",
            size_bytes=100,
            last_modified=datetime.utcnow()
        )

    @pytest.fixture
    def sample_finding(self):
        """Create a sample finding."""
        return Finding.create(
            pattern=Pattern.sleep_in_test("2s"),
            severity=Severity.WARNING,
            location=Location(Path("test.robot"), 3),
            message="Sleep usage detected"
        )

    def test_create_analysis(self, test_file):
        """Test creating an analysis."""
        analysis_id = uuid4()
        analysis = Analysis(
            id=analysis_id,
            test_file=test_file
        )

        assert analysis.id == analysis_id
        assert analysis.test_file == test_file
        assert analysis.findings == []
        assert analysis.completed_at is None
        assert analysis.analyzer_version == "0.1.0"
        assert not analysis.is_completed

    def test_auto_generate_id(self, test_file):
        """Test that analysis ID is auto-generated."""
        analysis = Analysis(test_file=test_file)
        assert analysis.id is not None

    def test_add_finding(self, test_file, sample_finding):
        """Test adding findings to analysis."""
        analysis = Analysis(test_file=test_file)

        analysis.add_finding(sample_finding)

        assert len(analysis.findings) == 1
        assert analysis.findings[0] == sample_finding
        assert analysis.finding_count == 1

    def test_high_severity_finding_emits_event(self, test_file):
        """Test that adding ERROR finding emits event."""
        analysis = Analysis(test_file=test_file)

        error_finding = Finding.create(
            pattern=Pattern.duplicate_keyword("Login"),
            severity=Severity.ERROR,
            location=Location(Path("test.robot"), 10),
            message="Duplicate keyword definition"
        )

        analysis.add_finding(error_finding)

        events = analysis.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], HighSeverityFindingEvent)
        assert events[0].finding == error_finding
        assert events[0].analysis_id == analysis.id

    def test_complete_analysis(self, test_file, sample_finding):
        """Test completing an analysis."""
        analysis = Analysis(test_file=test_file)
        analysis.add_finding(sample_finding)

        # Complete the analysis
        analysis.complete()

        assert analysis.is_completed
        assert analysis.completed_at is not None
        assert analysis.duration_seconds is not None
        assert analysis.duration_seconds >= 0

        # Check event was emitted
        events = analysis.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], FileAnalyzedEvent)
        assert events[0].analysis_id == analysis.id
        assert events[0].file_path == test_file.path
        assert events[0].finding_count == 1

    def test_finding_counts(self, test_file):
        """Test counting findings by severity."""
        analysis = Analysis(test_file=test_file)

        # Add findings of different severities
        error_finding = Finding.create(
            pattern=Pattern.duplicate_keyword("Test"),
            severity=Severity.ERROR,
            location=Location(Path("test.robot"), 1),
            message="Error"
        )

        warning_finding = Finding.create(
            pattern=Pattern.sleep_in_test("1s"),
            severity=Severity.WARNING,
            location=Location(Path("test.robot"), 2),
            message="Warning"
        )

        info_finding = Finding.create(
            pattern=Pattern.long_test_case(60),
            severity=Severity.INFO,
            location=Location(Path("test.robot"), 3),
            message="Info"
        )

        analysis.add_finding(error_finding)
        analysis.add_finding(warning_finding)
        analysis.add_finding(info_finding)
        analysis.add_finding(warning_finding)  # Add another warning

        assert analysis.finding_count == 4
        assert analysis.error_count == 1
        assert analysis.warning_count == 2
        assert analysis.info_count == 1

    def test_auto_fixable_count(self, test_file):
        """Test counting auto-fixable findings."""
        analysis = Analysis(test_file=test_file)

        # Auto-fixable finding
        fixable = Finding.create(
            pattern=Pattern.sleep_in_test("2s"),
            severity=Severity.WARNING,
            location=Location(Path("test.robot"), 1),
            message="Fixable"
        )

        # Non-fixable finding
        non_fixable = Finding.create(
            pattern=Pattern.duplicate_keyword("Test"),
            severity=Severity.ERROR,
            location=Location(Path("test.robot"), 2),
            message="Not fixable"
        )

        analysis.add_finding(fixable)
        analysis.add_finding(non_fixable)

        assert analysis.auto_fixable_count == 1

    @pytest.mark.asyncio
    async def test_async_add_finding(self, test_file, sample_finding):
        """Test async finding addition."""
        analysis = Analysis(test_file=test_file)

        await analysis.add_finding_async(sample_finding)

        assert len(analysis.findings) == 1
        assert analysis.findings[0] == sample_finding

    @pytest.mark.asyncio
    async def test_async_complete(self, test_file):
        """Test async completion."""
        analysis = Analysis(test_file=test_file)

        await analysis.complete_async()

        assert analysis.is_completed

    def test_get_findings_by_severity(self, test_file):
        """Test filtering findings by severity."""
        analysis = Analysis(test_file=test_file)

        warning1 = Finding.create(
            pattern=Pattern.sleep_in_test("1s"),
            severity=Severity.WARNING,
            location=Location(Path("test.robot"), 1),
            message="Warning 1"
        )

        warning2 = Finding.create(
            pattern=Pattern.sleep_in_test("2s"),
            severity=Severity.WARNING,
            location=Location(Path("test.robot"), 2),
            message="Warning 2"
        )

        error = Finding.create(
            pattern=Pattern.duplicate_keyword("Test"),
            severity=Severity.ERROR,
            location=Location(Path("test.robot"), 3),
            message="Error"
        )

        analysis.add_finding(warning1)
        analysis.add_finding(warning2)
        analysis.add_finding(error)

        warnings = analysis.get_findings_by_severity(Severity.WARNING)
        assert len(warnings) == 2
        assert warning1 in warnings
        assert warning2 in warnings

        errors = analysis.get_findings_by_severity(Severity.ERROR)
        assert len(errors) == 1
        assert errors[0] == error

    def test_aggregate_root_event_management(self, test_file):
        """Test event management in aggregate root."""
        analysis = Analysis(test_file=test_file)

        # Initially no events
        assert analysis.pull_events() == []

        # Add high severity finding (emits event)
        error_finding = Finding.create(
            pattern=Pattern.duplicate_keyword("Test"),
            severity=Severity.ERROR,
            location=Location(Path("test.robot"), 1),
            message="Error"
        )
        analysis.add_finding(error_finding)

        # Pull events
        events = analysis.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], HighSeverityFindingEvent)

        # Events are cleared after pulling
        assert analysis.pull_events() == []

        # Complete analysis (emits another event)
        analysis.complete()
        events = analysis.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], FileAnalyzedEvent)

    def test_get_schema(self):
        """Test that get_schema returns JSON schema."""
        schema = DomainTestFile.get_schema()
        assert isinstance(schema, dict)
        assert 'properties' in schema
        assert 'path' in schema['properties']
        assert 'content' in schema['properties']
