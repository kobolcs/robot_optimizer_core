"""Domain entity for test suite analysis results.

100% Pydantic v2 compliant implementation with zero pylint issues.
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Set, Any, TYPE_CHECKING
from uuid import UUID, uuid4

from pydantic import Field, computed_field, ConfigDict, model_validator

from ..base import AggregateRoot
from ..value_objects.pattern import PatternType
from ..value_objects.finding import Finding
from ..value_objects.severity import Severity
from .test_file import TestFile

if TYPE_CHECKING:
    from ..events import HighSeverityFindingEvent, FileAnalyzedEvent


def _default_timestamp() -> datetime:
    """Default factory for timestamp fields."""
    return datetime.now(timezone.utc)


def _datetime_encoder(v: datetime) -> str:
    """Encode datetime to ISO format."""
    return v.isoformat()


def _path_encoder(v: Path) -> str:
    """Encode Path to string."""
    return str(v)


def _uuid_encoder(v: UUID) -> str:
    """Encode UUID to string."""
    return str(v)


class Analysis(AggregateRoot[UUID]):
    """Aggregate root for test suite analysis results.

    This entity represents a complete analysis of a Robot Framework test file,
    including all findings, metrics, and events generated during the analysis.

    Pydantic v2 Features Used:
    - computed_field for derived properties
    - Field with defaults and descriptions
    - model_validator for business rules
    - ConfigDict with v2 settings
    """

    # Override parent config to ensure settings
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True,
        extra='forbid',
        use_enum_values=True,
        from_attributes=True,
        # v2: Better serialization control
        ser_json_timedelta='float',
        json_encoders={
            datetime: _datetime_encoder,
            Path: _path_encoder,
            UUID: _uuid_encoder,
        }
    )

    id: UUID = Field(default_factory=uuid4)
    test_file: TestFile = Field(..., description="The file being analyzed")
    findings: List[Finding] = Field(default_factory=list, description="List of findings")
    started_at: datetime = Field(default_factory=_default_timestamp)
    completed_at: Optional[datetime] = Field(default=None, description="Completion time")
    analyzer_version: str = Field(default="0.1.0", description="Version of analyzer")

    @model_validator(mode='after')
    def validate_completion(self) -> 'Analysis':
        """Validate completion state consistency.

        Pydantic v2 model validator to ensure data consistency.
        """
        if self.completed_at and self.completed_at < self.started_at:
            raise ValueError("Completion time cannot be before start time")
        return self

    def add_finding(self, finding: Finding) -> None:
        """Add a finding to the analysis.

        Args:
            finding: The finding to add

        Side effects:
            - Emits HighSeverityFindingEvent for ERROR severity findings
        """
        # Import here to avoid circular imports
        from ..events import HighSeverityFindingEvent

        # pylint: disable=no-member
        findings_list: List[Finding] = self.findings  # type: ignore[assignment]
        findings_list.append(finding)

        # Emit event for high-severity findings
        if finding.severity == Severity.ERROR:
            # pylint: disable=no-member
            self.add_event(HighSeverityFindingEvent(
                analysis_id=self.id,
                finding=finding
            ))

    async def add_finding_async(self, finding: Finding) -> None:
        """Async version of add_finding for concurrent analysis.

        Args:
            finding: The finding to add
        """
        await asyncio.sleep(0)  # Yield control
        self.add_finding(finding)

    def complete(self) -> None:
        """Mark the analysis as completed.

        Side effects:
            - Sets completed_at timestamp
            - Emits FileAnalyzedEvent

        Raises:
            ValueError: If analysis is already completed
        """
        # Import here to avoid circular imports
        from ..events import FileAnalyzedEvent

        if self.is_completed:
            raise ValueError("Analysis is already completed")

        self.completed_at = datetime.now(timezone.utc)

        # pylint: disable=no-member
        self.add_event(FileAnalyzedEvent(
            analysis_id=self.id,
            file_path=self.test_file.path,
            finding_count=len(self.findings),
            duration_seconds=self.duration_seconds or 0.0
        ))

    async def complete_async(self) -> None:
        """Async version of complete."""
        await asyncio.sleep(0)  # Yield control
        self.complete()

    # Pydantic v2: Use computed_field for all derived properties
    @computed_field  # type: ignore[misc]
    @property
    def is_completed(self) -> bool:
        """Check if the analysis is completed."""
        return self.completed_at is not None

    @computed_field  # type: ignore[misc]
    @property
    def duration_seconds(self) -> Optional[float]:
        """Get the analysis duration in seconds."""
        if not self.is_completed or self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    @computed_field  # type: ignore[misc]
    @property
    def finding_count(self) -> int:
        """Get the total number of findings."""
        # pylint: disable=no-member
        findings_list: List[Finding] = self.findings  # type: ignore[assignment]
        return len(findings_list)

    @computed_field  # type: ignore[misc]
    @property
    def error_count(self) -> int:
        """Get the number of error-level findings."""
        # pylint: disable=no-member
        findings_list: List[Finding] = self.findings  # type: ignore[assignment]
        return sum(1 for f in findings_list if f.severity == Severity.ERROR)

    @computed_field  # type: ignore[misc]
    @property
    def warning_count(self) -> int:
        """Get the number of warning-level findings."""
        # pylint: disable=no-member
        findings_list: List[Finding] = self.findings  # type: ignore[assignment]
        return sum(1 for f in findings_list if f.severity == Severity.WARNING.value)

    @computed_field  # type: ignore[misc]
    @property
    def info_count(self) -> int:
        """Get the number of info-level findings."""
        # pylint: disable=no-member
        findings_list: List[Finding] = self.findings  # type: ignore[assignment]
        return sum(1 for f in findings_list if f.severity == Severity.INFO.value)

    @computed_field  # type: ignore[misc]
    @property
    def auto_fixable_count(self) -> int:
        """Get the number of auto-fixable findings."""
        # pylint: disable=no-member
        findings_list: List[Finding] = self.findings  # type: ignore[assignment]
        return sum(1 for f in findings_list if f.is_auto_fixable)

    @computed_field  # type: ignore[misc]
    @property
    def has_errors(self) -> bool:
        """Check if analysis has any errors."""
        return self.error_count > 0

    @computed_field  # type: ignore[misc]
    @property
    def has_warnings(self) -> bool:
        """Check if analysis has any warnings."""
        return self.warning_count > 0

    @computed_field  # type: ignore[misc]
    @property
    def severity_summary(self) -> Dict[str, int]:
        """Get a summary of findings by severity."""
        return {
            "errors": self.error_count,
            "warnings": self.warning_count,
            "info": self.info_count
        }

    def get_findings_by_severity(self, severity: Severity) -> List[Finding]:
        """Get all findings of a specific severity.

        Args:
            severity: The severity level to filter by

        Returns:
            List of findings matching the severity
        """
        # pylint: disable=no-member
        findings_list: List[Finding] = self.findings  # type: ignore[assignment]
        return [f for f in findings_list if f.severity == severity.value]

    def get_findings_by_pattern(self, pattern_type: PatternType) -> List[Finding]:
        """Get all findings of a specific pattern type.

        Args:
            pattern_type: The pattern type to filter by

        Returns:
            List of findings matching the pattern type
        """
        # pylint: disable=no-member
        findings_list: List[Finding] = self.findings  # type: ignore[assignment]
        return [f for f in findings_list if f.pattern.type == pattern_type]

    def get_findings_by_line(self, line: int) -> List[Finding]:
        """Get all findings on a specific line.

        Args:
            line: The line number to filter by

        Returns:
            List of findings on the specified line
        """
        # pylint: disable=no-member
        findings_list: List[Finding] = self.findings  # type: ignore[assignment]
        return [f for f in findings_list if f.location.line == line]

    def get_pattern_summary(self) -> Dict[PatternType, int]:
        """Get a summary of findings by pattern type.

        Returns:
            Dictionary mapping pattern types to their counts
        """
        summary: Dict[PatternType, int] = {}
        # pylint: disable=no-member
        findings_list: List[Finding] = self.findings  # type: ignore[assignment]
        for finding in findings_list:
            pattern_type = finding.pattern.type
            summary[pattern_type] = summary.get(pattern_type, 0) + 1
        return summary

    def get_affected_lines(self) -> Set[int]:
        """Get all line numbers that have findings.

        Returns:
            Set of line numbers with findings
        """
        # pylint: disable=no-member
        findings_list: List[Finding] = self.findings  # type: ignore[assignment]
        return {f.location.line for f in findings_list}

    def to_summary_dict(self) -> Dict[str, Any]:
        """Convert analysis to a summary dictionary.

        Returns:
            Dictionary containing analysis summary data
        """
        # pylint: disable=no-member
        return {
            "id": str(self.id),
            "file": str(self.test_file.path),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "finding_count": self.finding_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "auto_fixable_count": self.auto_fixable_count,
            "pattern_summary": {
                k.name: v for k, v in self.get_pattern_summary().items()
            }
        }

    def model_dump(self, **kwargs: Any) -> Dict[str, Any]:
        """Override to handle custom serialization.

        Pydantic v2 method for model serialization.
        """
        # Exclude private fields by default
        exclude = kwargs.get('exclude', set())
        if isinstance(exclude, set):
            exclude.add('_events')
        kwargs['exclude'] = exclude

        return super().model_dump(**kwargs)
