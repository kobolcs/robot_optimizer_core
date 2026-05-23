# tests/unit/domain/test_events.py
"""Tests for domain events.

Skipped: robot_optimizer_core.domain.events module is planned but not yet
implemented.  Remove pytestmark once the module exists.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="robot_optimizer_core.domain.events module not yet implemented"
)

try:
    from datetime import datetime
    from pathlib import Path
    from uuid import uuid4

    from pydantic import ValidationError

    from robot_optimizer_core.domain.events import (
        AnalysisStartedEvent,
        BatchAnalysisCompletedEvent,
        FileAnalyzedEvent,
        HighSeverityFindingEvent,
        OptimizationAppliedEvent,
        OptimizationFailedEvent,
    )
    from robot_optimizer_core.domain.value_objects import (
        Finding,
        Location,
        Pattern,
        Severity,
    )
except ImportError:
    pass  # pytestmark covers all items; bodies never execute


class TestDomainEvents:
    """Test domain events."""

    def test_file_analyzed_event(self):
        """Test FileAnalyzedEvent creation and properties."""
        analysis_id = uuid4()
        event = FileAnalyzedEvent(
            analysis_id=analysis_id,
            file_path=Path("test.robot"),
            finding_count=5,
            duration_seconds=1.5
        )

        assert event.analysis_id == analysis_id
        assert event.file_path == Path("test.robot")
        assert event.finding_count == 5
        assert event.duration_seconds == 1.5
        assert event.event_name == "file_analyzed"
        assert event.event_id is not None
        assert isinstance(event.occurred_at, datetime)

    def test_event_validation_errors(self):
        """Test validation errors for events."""
        with pytest.raises(ValidationError) as exc_info:
            FileAnalyzedEvent(
                analysis_id=uuid4(),
                file_path=Path("test.robot"),
                finding_count=-1,
                duration_seconds=1.0
            )
        assert "greater than or equal to 0" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            FileAnalyzedEvent(
                analysis_id=uuid4(),
                file_path=Path("test.robot"),
                finding_count=1,
                duration_seconds=-1.0
            )
        assert "greater than or equal to 0" in str(exc_info.value)

    def test_optimization_applied_event(self):
        """Test OptimizationAppliedEvent creation."""
        analysis_id = uuid4()
        finding_id = uuid4()

        event = OptimizationAppliedEvent(
            analysis_id=analysis_id,
            finding_id=finding_id,
            file_path=Path("test.robot"),
            optimization_type="replace_sleep",
            changes_made={
                "original": "Sleep    2s",
                "replacement": "Wait Until Element Is Visible    ${element}    2s",
                "line": 25
            }
        )

        assert event.analysis_id == analysis_id
        assert event.finding_id == finding_id
        assert event.optimization_type == "replace_sleep"
        assert event.event_name == "optimization_applied"

    def test_high_severity_finding_event(self):
        """Test HighSeverityFindingEvent creation."""
        analysis_id = uuid4()
        finding = Finding.create(
            pattern=Pattern.duplicate_keyword("Login"),
            severity=Severity.ERROR,
            location=Location(file_path=Path("test.robot"), line=10),
            message="Duplicate keyword found"
        )

        event = HighSeverityFindingEvent(
            analysis_id=analysis_id,
            finding=finding
        )

        assert event.analysis_id == analysis_id
        assert event.finding == finding
        assert event.event_name == "high_severity_finding"
        assert event.file_path == Path("test.robot")

    def test_analysis_started_event(self):
        """Test AnalysisStartedEvent creation."""
        analysis_id = uuid4()
        event = AnalysisStartedEvent(
            analysis_id=analysis_id,
            file_path=Path("suite.robot"),
            file_size_bytes=2048
        )

        assert event.analysis_id == analysis_id
        assert event.file_path == Path("suite.robot")
        assert event.file_size_bytes == 2048
        assert event.event_name == "analysis_started"

    def test_batch_analysis_completed_event(self):
        """Test BatchAnalysisCompletedEvent creation."""
        batch_id = uuid4()
        event = BatchAnalysisCompletedEvent(
            batch_id=batch_id,
            file_count=10,
            total_findings=45,
            total_duration_seconds=15.5,
            files_with_errors=[Path("test1.robot"), Path("test2.robot")]
        )

        assert event.batch_id == batch_id
        assert event.file_count == 10
        assert event.total_findings == 45
        assert event.total_duration_seconds == 15.5
        assert len(event.files_with_errors) == 2
        assert event.event_name == "batch_analysis_completed"
        assert event.average_duration_seconds == 1.55

    def test_batch_analysis_zero_files(self):
        """Test BatchAnalysisCompletedEvent with zero files."""
        event = BatchAnalysisCompletedEvent(
            batch_id=uuid4(),
            file_count=0,
            total_findings=0,
            total_duration_seconds=0.0,
            files_with_errors=[]
        )
        assert event.average_duration_seconds == 0.0

    def test_optimization_failed_event(self):
        """Test OptimizationFailedEvent creation."""
        analysis_id = uuid4()
        finding_id = uuid4()
        event = OptimizationFailedEvent(
            analysis_id=analysis_id,
            finding_id=finding_id,
            file_path=Path("test.robot"),
            error_message="Permission denied",
            error_type="PermissionError"
        )

        assert event.error_message == "Permission denied"
        assert event.error_type == "PermissionError"
        assert event.event_name == "optimization_failed"

    def test_event_auto_generated_fields(self):
        """Test that event ID and timestamp are auto-generated."""
        event1 = FileAnalyzedEvent(
            analysis_id=uuid4(),
            file_path=Path("test.robot"),
            finding_count=1,
            duration_seconds=0.5
        )
        event2 = FileAnalyzedEvent(
            analysis_id=uuid4(),
            file_path=Path("test.robot"),
            finding_count=1,
            duration_seconds=0.5
        )

        assert event1.event_id != event2.event_id
        time_diff = abs((event2.occurred_at - event1.occurred_at).total_seconds())
        assert time_diff < 1.0

    def test_event_immutability(self):
        """Test that events are immutable."""
        event = FileAnalyzedEvent(
            analysis_id=uuid4(),
            file_path=Path("test.robot"),
            finding_count=5,
            duration_seconds=1.0
        )

        with pytest.raises(ValidationError):
            event.finding_count = 10

    def test_custom_event_id_and_timestamp(self):
        """Test providing custom event ID and timestamp."""
        custom_id = uuid4()
        custom_time = datetime(2024, 1, 1, 12, 0, 0)

        event = FileAnalyzedEvent(
            event_id=custom_id,
            occurred_at=custom_time,
            analysis_id=uuid4(),
            file_path=Path("test.robot"),
            finding_count=1,
            duration_seconds=0.5
        )

        assert event.event_id == custom_id
        assert event.occurred_at == custom_time

    def test_path_string_conversion(self):
        """Test that string paths are converted to Path objects."""
        event = FileAnalyzedEvent(
            analysis_id=uuid4(),
            file_path="test.robot",
            finding_count=1,
            duration_seconds=0.5
        )

        assert isinstance(event.file_path, Path)
        assert event.file_path == Path("test.robot")
