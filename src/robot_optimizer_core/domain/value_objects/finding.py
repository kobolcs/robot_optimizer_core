# src/robot_optimizer_core/domain/value_objects/finding.py
"""Finding value object for representing optimization findings.

100% Pydantic v2 compliant implementation with modern Python features.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from pydantic import ConfigDict, Field, computed_field, field_validator

from ..base import ValueObject
from .location import Location
from .pattern import Pattern
from .severity import Severity


class Finding(ValueObject):
    """Represents a single optimization finding in a test file.

    A finding is an immutable record of a detected pattern in a Robot Framework
    file, including its location, severity, and contextual information.
    """

    model_config = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
        use_enum_values=False,
    )

    id: UUID = Field(default_factory=uuid4, description="Unique finding ID")
    pattern: Pattern = Field(..., description="The pattern that was matched")
    severity: Severity = Field(..., description="Severity level")
    location: Location = Field(..., description="Location in the file")
    message: str = Field(..., min_length=1, description="Human-readable message")
    context: dict[str, Any] | None = Field(
        default=None, description="Additional context"
    )

    @field_validator("message", mode="before")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Ensure message is not empty.

        Args:
            v: The message to validate

        Returns:
            The validated message

        Raises:
            ValueError: If message is empty or only whitespace
        """
        if v == "":
            return v
        if not v.strip():
            raise ValueError("Finding message cannot be empty")
        return v.strip()

    @field_validator("context")
    @classmethod
    def ensure_context_copy(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        """Ensure context is a copy to maintain immutability.

        Args:
            v: The context dictionary

        Returns:
            A copy of the context dict or None
        """
        return dict(v) if v is not None else None

    @classmethod
    def create(
        cls,
        pattern: Pattern,
        severity: Severity,
        location: Location,
        message: str,
        **context: Any,
    ) -> Finding:
        """Factory method to create a finding with context.

        Uses Pydantic v2 model_validate for construction.

        Args:
            pattern: The pattern that was matched
            severity: Severity level of the finding
            location: Location in the file
            message: Human-readable message
            **context: Additional context as keyword arguments

        Returns:
            A new Finding instance
        """
        return cls.model_validate(
            {
                "pattern": pattern,
                "severity": severity,
                "location": location,
                "message": message,
                "context": context if context else None,
            }
        )

    # Pydantic v2: computed fields for derived properties
    @computed_field  # type: ignore[prop-decorator]
    @property
    def file_path(self) -> str:
        """Get the file path as a string."""
        return str(self.location.file_path)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def line_number(self) -> int:
        """Get the line number."""
        return self.location.line

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_auto_fixable(self) -> bool:
        """Check if this finding can be automatically fixed."""
        return self.pattern.auto_fixable

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_context(self) -> bool:
        """Check if finding has additional context."""
        return self.context is not None and len(self.context) > 0

    def format_for_console(self) -> str:
        """Format the finding for console output.

        Returns:
            A formatted string suitable for console display
        """
        location = self.location.range_str
        severity_emoji = self.severity.emoji

        # Build the main message
        lines = [
            f"{severity_emoji} {self.pattern.name}",
            f"   {location}",
            f"   {self.message}",
        ]

        # Add recommendation if different from message
        if self.pattern.recommendation != self.message:
            lines.append(f"   💡 {self.pattern.recommendation}")

        # Add context if available
        if self.context:
            for key, value in self.context.items():
                lines.append(f"   {key}: {value}")

        return "\n".join(lines)

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Dump model while preserving Python objects in default mode."""
        if kwargs.get("mode") == "json":
            return super().model_dump(**kwargs)
        return {
            "id": self.id,
            "pattern": self.pattern,
            "severity": self.severity,
            "location": self.location,
            "message": self.message,
            "context": self.context,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert finding to a dictionary for serialization."""
        return {
            "id": str(self.id),
            "file": self.location.file_path.name,
            "file_path": self.file_path,
            "line": self.location.line,
            "line_number": self.line_number,
            "column": self.location.column,
            "location": self.location.model_dump(),
            "severity": self.severity.name,
            "message": self.message,
            "pattern": self.pattern.model_dump() | {"type": self.pattern.type},
            "pattern_type": self.pattern.type.name,  # type: ignore[attr-defined]
            "pattern_name": self.pattern.name,
            "recommendation": self.pattern.recommendation,
            "is_auto_fixable": self.is_auto_fixable,
            "auto_fixable": self.is_auto_fixable,
            "context": self.context,
        }

    def to_sarif(self) -> dict[str, Any]:
        """Return a SARIF-compatible result dict (Task 23).

        The returned dict conforms to the SARIF 2.1.0 ``result`` object schema
        (https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html).
        It can be embedded inside a ``runs[].results`` array.

        Severity mapping:
            - ERROR   → "error"
            - WARNING → "warning"
            - INFO    → "note"

        Returns:
            SARIF result dictionary.
        """
        _SARIF_LEVEL: dict[Severity, str] = {
            Severity.ERROR: "error",
            Severity.WARNING: "warning",
            Severity.INFO: "note",
        }
        pattern_type = self.pattern.type
        if hasattr(pattern_type, "name"):
            rule_id: str = pattern_type.name  # type: ignore[union-attr]
        else:
            rule_id = str(pattern_type)

        physical_location: dict[str, Any] = {
            "artifactLocation": {
                "uri": self.file_path.replace("\\", "/"),
                "uriBaseId": "%SRCROOT%",
            },
            "region": {
                "startLine": self.location.line,
            },
        }
        if self.location.column is not None:
            physical_location["region"]["startColumn"] = self.location.column
        if self.location.end_line is not None:
            physical_location["region"]["endLine"] = self.location.end_line
        if self.location.end_column is not None:
            physical_location["region"]["endColumn"] = self.location.end_column

        return {
            "ruleId": rule_id,
            "level": _SARIF_LEVEL.get(self.severity, "warning"),
            "message": {"text": self.message},
            "locations": [{"physicalLocation": physical_location}],
            "properties": {
                "pattern_name": self.pattern.name,
                "recommendation": self.pattern.recommendation,
                "auto_fixable": self.is_auto_fixable,
                "finding_id": str(self.id),
            },
        }

    def is_suppressed_by(self, source_line: str) -> bool:
        """Check whether *source_line* carries a suppression comment (Task 24).

        Supported inline comment syntax::

            Some Keyword    # robot-optimizer: ignore
            Some Keyword    # robot-optimizer: ignore[dead_code]
            Some Keyword    # robot-optimizer: ignore[dead_code,sleep_detector]

        The check is case-insensitive on the tag names and the ``ignore``
        keyword.

        Args:
            source_line: The raw source line at this finding's location.

        Returns:
            True when the line carries a suppression that covers this finding.
        """
        import re

        pattern_str = r"#\s*robot-optimizer\s*:\s*ignore(?:\[([^\]]*)\])?"
        m = re.search(pattern_str, source_line, re.IGNORECASE)
        if not m:
            return False

        tags_str = m.group(1)
        if not tags_str:
            # Bare ``ignore`` → suppress all findings on this line
            return True

        tags = {t.strip().lower() for t in tags_str.split(",")}
        rule_id = (
            self.pattern.type.name.lower()  # type: ignore[attr-defined]
            if hasattr(self.pattern.type, "name")
            else str(self.pattern.type).lower()
        )
        return rule_id in tags

    @classmethod
    def filter_suppressed(
        cls, findings: list[Finding], source_lines: list[str]
    ) -> list[Finding]:
        """Filter out findings that are suppressed by inline comments (Task 24).

        Args:
            findings: Findings to filter.
            source_lines: All source lines of the file (1-based: index 0 = line 1).

        Returns:
            Findings not suppressed by any inline comment.
        """
        result: list[Finding] = []
        for finding in findings:
            line_idx = finding.location.line - 1  # convert to 0-based
            if 0 <= line_idx < len(source_lines):
                if finding.is_suppressed_by(source_lines[line_idx]):
                    continue
            result.append(finding)
        return result
