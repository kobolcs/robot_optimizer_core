# src/robot_optimizer_core/domain/entities/test_file.py
"""Timezone-aware test file entity with proper datetime handling."""
from __future__ import annotations

from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo  # Python 3.9+ for timezone support

from pydantic import Field, computed_field, field_validator

from ...logging import get_logger
from ..base import DomainEvent as BaseDomainEvent
from ..base import Entity
from ..value_objects.test_result import TestResult as BaseTestResult

logger = get_logger(__name__)


def utc_now() -> datetime:
    """Get current UTC time with timezone info."""
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime is in UTC timezone."""
    if dt.tzinfo is None:
        dt = dt.astimezone()  # attaches local system timezone
    return dt.astimezone(UTC)


class TZAwareTestFile(Entity[UUID]):
    """Test file entity with proper timezone handling (timezone-aware).

    All datetime fields are stored in UTC with timezone information.
    """

    id: UUID = Field(default_factory=uuid4)
    path: Path = Field(..., description="Path to the test file")
    content: str = Field(..., description="Full content of the file")
    size_bytes: int = Field(..., ge=0, description="File size in bytes")
    last_modified_utc: datetime = Field(..., description="Last modification time in UTC")
    created_at_utc: datetime = Field(default_factory=utc_now, description="Entity creation time in UTC")
    encoding: str = Field(default="utf-8", description="File encoding")
    test_cases: list[str] = Field(default_factory=list, description="List of test case names")
    keywords: list[str] = Field(default_factory=list, description="List of keyword names")

    # Optional timezone for display purposes
    display_timezone: str = Field(default="UTC", description="Timezone for display purposes")

    @field_validator("path", mode="before")
    @classmethod
    def ensure_path_object(cls, v: Any) -> Path:
        """Ensure path is a Path object."""
        return Path(v) if not isinstance(v, Path) else v

    @field_validator("last_modified_utc", mode="before")
    @classmethod
    def ensure_utc_timezone(cls, v: Any) -> datetime:
        """Ensure datetime has UTC timezone."""
        if isinstance(v, datetime):
            return ensure_utc(v)
        if isinstance(v, (int, float)):
            # Assume timestamp
            return datetime.fromtimestamp(v, tz=UTC)
        if isinstance(v, str):
            # Parse ISO format
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return ensure_utc(dt)
        raise ValueError(f"Cannot convert {type(v)} to datetime")

    @field_validator("encoding")
    @classmethod
    def validate_encoding(cls, v: str) -> str:
        """Normalize and validate supported encodings."""
        value = v.lower()
        supported = {"utf-8", "utf-16", "ascii", "latin-1"}
        if value not in supported:
            raise ValueError(f"Unsupported encoding: {v}")
        return value

    @field_validator("display_timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Validate timezone string."""
        try:
            ZoneInfo(v)  # Validate timezone exists
            return v
        except Exception:
            logger.warning(f"Invalid timezone '{v}', using UTC")
            return "UTC"

    @classmethod
    def from_path(cls, file_path: Path, content: str | None = None) -> TZAwareTestFile:
        """Create TestFile from path with UTC timestamps."""
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if content is None:
            raw = path.read_bytes()

            if b"\x00" in raw:
                raise ValueError(f"File appears to be binary or invalid text: {path}")

            content = raw.decode("utf-8")

            control_chars = sum(
                1 for ch in content
                if ord(ch) < 32 and ch not in "\n\r\t"
            )
            if control_chars > max(1, len(content) // 20):
                raise ValueError(f"File contains too many control characters: {path}")

        stats = path.stat()

        # Convert to UTC timestamps
        last_modified = datetime.fromtimestamp(stats.st_mtime, tz=UTC)

        return cls.model_validate({
            "path": path,
            "content": content,
            "size_bytes": stats.st_size,
            "last_modified_utc": last_modified,
            "encoding": "utf-8"
        })


    @property
    def last_modified(self) -> datetime:
        """Backward-compatible alias for last_modified_utc."""
        return self.last_modified_utc

    @property
    def name(self) -> str:
        """Return the file stem without extension."""
        return self.path.stem

    @property
    def extension(self) -> str:
        """Return the file extension."""
        return self.path.suffix

    @property
    def size_kb(self) -> float:
        """Return file size in kilobytes."""
        return self.size_bytes / 1024

    @property
    def has_content(self) -> bool:
        """Return whether the file has non-empty content."""
        return bool(self.content.strip())

    @property
    def is_resource_file(self) -> bool:
        """Return whether this Robot file looks like a resource file."""
        return (
            self.path.suffix.lower() == ".resource"
            or "resource" in self.path.stem.lower()
        )

    @property
    def line_count(self) -> int:
        """Return the number of logical lines in the file content."""
        return len(self.content.split("\n"))

    def get_lines(self, start_line: int = 1, end_line: int | None = None) -> list[str]:
        """Return 1-based inclusive line range from content."""
        lines = self.content.splitlines()
        start = max(start_line, 1)
        end = start if end_line is None else end_line
        if start > end:
            return []
        return lines[start - 1:end]

    @classmethod
    def get_schema(cls) -> dict[str, Any]:
        """Return JSON schema with backward-compatible aliases."""
        schema = cls.model_json_schema()
        schema.setdefault("properties", {})
        schema["properties"].setdefault(
            "last_modified",
            schema["properties"].get("last_modified_utc", {"type": "string"}),
        )
        return schema

    @computed_field  # type: ignore[prop-decorator]
    @property
    def last_modified_local(self) -> datetime:
        """Get last modified time in display timezone."""
        tz = ZoneInfo(self.display_timezone)
        return self.last_modified_utc.astimezone(tz)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def age_hours(self) -> float:
        """Get file age in hours."""
        age = utc_now() - self.last_modified_utc
        return age.total_seconds() / 3600

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_recently_modified(self) -> bool:
        """Check if file was modified in last 24 hours."""
        return self.age_hours < 24

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Override to handle datetime serialization."""
        data = super().model_dump(**kwargs)

        # Ensure ISO format with timezone for JSON
        if kwargs.get("mode") == "json":
            data["path"] = str(data["path"])
            data["last_modified_utc"] = self.last_modified_utc.isoformat()
            data["created_at_utc"] = self.created_at_utc.isoformat()

            # Add computed fields
            data["last_modified_local"] = self.last_modified_local.isoformat()
            data["age_hours"] = self.age_hours

        return data



class TimezoneAwareDomainEvent(BaseDomainEvent):
    """Domain event with proper UTC timezone handling."""

    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the event occurred (always UTC)"
    )

    @field_validator("occurred_at", mode="before")
    @classmethod
    def ensure_utc(cls, v: Any) -> datetime:
        """Ensure occurred_at is in UTC."""
        if isinstance(v, datetime):
            return ensure_utc(v)
        return v  # type: ignore[no-any-return]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def occurred_at_iso(self) -> str:
        """Get ISO format timestamp with timezone."""
        return self.occurred_at.isoformat()

    def to_message(self) -> dict[str, Any]:
        """Convert to message with proper timestamp."""
        return {
            "event_id": str(self.event_id),
            "event_name": self.event_name,
            "event_version": self.event_version,
            "occurred_at": self.occurred_at.isoformat(),
            "occurred_at_unix": int(self.occurred_at.timestamp()),
            "data": self.model_dump(
                exclude={"event_id", "occurred_at"},
                mode="json"
            )
        }



class TimezoneAwareTestResult(BaseTestResult):
    """Test result with UTC timestamp."""

    timestamp: datetime = Field(..., description="Test execution timestamp (UTC)")

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_utc(cls, v: Any) -> datetime:
        """Ensure timestamp is UTC."""
        if isinstance(v, datetime):
            return ensure_utc(v)
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v, tz=UTC)
        if isinstance(v, str):
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return ensure_utc(dt)
        raise ValueError(f"Cannot convert {type(v)} to datetime")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def age_days(self) -> float:
        """Get result age in days."""
        age = datetime.now(UTC) - self.timestamp
        return age.total_seconds() / 86400

    @computed_field  # type: ignore[prop-decorator]
    @property
    def timestamp_iso(self) -> str:
        """Get ISO format timestamp."""
        return self.timestamp.isoformat()


# Utility functions for timezone handling
def parse_datetime_safe(dt_str: str, default_tz: timezone = UTC) -> datetime:
    """Safely parse datetime string with timezone handling."""
    try:
        # Try parsing with timezone
        if "T" in dt_str:
            # ISO format
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        else:
            # Other formats
            from dateutil import parser  # type: ignore[import-untyped]
            dt = parser.parse(dt_str)

        # Ensure timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=default_tz)

        return dt

    except Exception as e:
        raise ValueError(f"Invalid datetime string: {dt_str}") from e


def format_datetime_local(dt: datetime, tz_name: str = "UTC") -> str:
    """Format datetime in specified timezone."""
    try:
        tz = ZoneInfo(tz_name)
        local_dt = dt.astimezone(tz)
        return local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        # Fallback to UTC
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


# Export alias for backward compatibility
TestFile = TZAwareTestFile
