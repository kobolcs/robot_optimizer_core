"""Domain events for the Robot Framework Optimizer."""
from pathlib import Path
from typing import List, Dict, Any
from uuid import UUID
from pydantic import Field
from .base import DomainEvent
from .value_objects.finding import Finding


class FileAnalyzedEvent(DomainEvent):
    """Event emitted when a file analysis is completed."""

    analysis_id: UUID = Field(..., description="Analysis ID")
    file_path: Path = Field(..., description="Path to analyzed file")
    finding_count: int = Field(..., ge=0, description="Number of findings")
    duration_seconds: float = Field(..., ge=0, description="Analysis duration")

    @property
    def event_name(self) -> str:
        """Get the event name."""
        return "file_analyzed"


class OptimizationAppliedEvent(DomainEvent):
    """Event emitted when an optimization is applied to a file."""

    analysis_id: UUID = Field(..., description="Analysis ID")
    finding_id: UUID = Field(..., description="Finding ID")
    file_path: Path = Field(..., description="Path to file")
    optimization_type: str = Field(..., description="Type of optimization")
    changes_made: Dict[str, Any] = Field(..., description="Details of changes")

    @property
    def event_name(self) -> str:
        """Get the event name."""
        return "optimization_applied"


class HighSeverityFindingEvent(DomainEvent):
    """Event emitted when a high-severity finding is discovered."""

    analysis_id: UUID = Field(..., description="Analysis ID")
    finding: Finding = Field(..., description="The finding")

    @property
    def event_name(self) -> str:
        """Get the event name."""
        return "high_severity_finding"

    @property
    def file_path(self) -> Path:
        """Get the file path from the finding location."""
        # pylint: disable=no-member
        return self.finding.location.file_path


class AnalysisStartedEvent(DomainEvent):
    """Event emitted when an analysis starts."""

    analysis_id: UUID = Field(..., description="Analysis ID")
    file_path: Path = Field(..., description="Path to file")
    file_size_bytes: int = Field(..., ge=0, description="File size")

    @property
    def event_name(self) -> str:
        """Get the event name."""
        return "analysis_started"


class BatchAnalysisCompletedEvent(DomainEvent):
    """Event emitted when a batch of files has been analyzed."""

    batch_id: UUID = Field(..., description="Batch ID")
    file_count: int = Field(..., ge=0, description="Number of files")
    total_findings: int = Field(..., ge=0, description="Total findings")
    total_duration_seconds: float = Field(..., ge=0, description="Total duration")
    files_with_errors: List[Path] = Field(
        default_factory=list,
        description="Files with errors"
    )

    @property
    def event_name(self) -> str:
        """Get the event name."""
        return "batch_analysis_completed"

    @property
    def average_duration_seconds(self) -> float:
        """Calculate average analysis time per file."""
        if self.file_count == 0:
            return 0.0
        return self.total_duration_seconds / self.file_count


class OptimizationFailedEvent(DomainEvent):
    """Event emitted when an optimization attempt fails."""

    analysis_id: UUID = Field(..., description="Analysis ID")
    finding_id: UUID = Field(..., description="Finding ID")
    file_path: Path = Field(..., description="Path to file")
    error_message: str = Field(..., description="Error message")
    error_type: str = Field(..., description="Type of error")

    @property
    def event_name(self) -> str:
        """Get the event name."""
        return "optimization_failed"
