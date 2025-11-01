# src/robot_optimizer_core/domain/entities/test_file.py
"""Timezone-aware test file entity with proper datetime handling."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo  # Python 3.9+ for timezone support

from pydantic import Field, computed_field, field_validator, model_validator

from ...logging import get_logger
from ..base import Entity

logger = get_logger(__name__)


def utc_now() -> datetime:
    """Get current UTC time with timezone info."""
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime is in UTC timezone."""
    if dt.tzinfo is None:
        # Assume naive datetime is in system timezone
        import time
        is_dst = time.daylight and time.localtime().tm_isdst > 0
        utc_offset = time.altzone if is_dst else time.timezone
        local_tz = timezone(timedelta(seconds=-utc_offset))
        dt = dt.replace(tzinfo=local_tz)
    
    # Convert to UTC
    return dt.astimezone(timezone.utc)


class TimezoneAwareTestFile(Entity[UUID]):
    """Test file entity with proper timezone handling.
    
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
    
    @field_validator('path', mode='before')
    @classmethod
    def ensure_path_object(cls, v: Any) -> Path:
        """Ensure path is a Path object."""
        return Path(v) if not isinstance(v, Path) else v
    
    @field_validator('last_modified_utc', mode='before')
    @classmethod
    def ensure_utc_timezone(cls, v: Any) -> datetime:
        """Ensure datetime has UTC timezone."""
        if isinstance(v, datetime):
            return ensure_utc(v)
        elif isinstance(v, (int, float)):
            # Assume timestamp
            return datetime.fromtimestamp(v, tz=timezone.utc)
        elif isinstance(v, str):
            # Parse ISO format
            dt = datetime.fromisoformat(v.replace('Z', '+00:00'))
            return ensure_utc(dt)
        else:
            raise ValueError(f"Cannot convert {type(v)} to datetime")
    
    @field_validator('display_timezone')
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
    def from_path(cls, file_path: Path, content: str | None = None) -> TimezoneAwareTestFile:
        """Create TestFile from path with UTC timestamps."""
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        
        if content is None:
            content = path.read_text(encoding='utf-8')
        
        stats = path.stat()
        
        # Convert to UTC timestamps
        last_modified = datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc)
        
        return cls.model_validate({
            'path': path,
            'content': content,
            'size_bytes': stats.st_size,
            'last_modified_utc': last_modified,
            'encoding': 'utf-8'
        })
    
    @computed_field  # type: ignore[misc]
    @property
    def last_modified_local(self) -> datetime:
        """Get last modified time in display timezone."""
        tz = ZoneInfo(self.display_timezone)
        return self.last_modified_utc.astimezone(tz)
    
    @computed_field  # type: ignore[misc]
    @property
    def age_hours(self) -> float:
        """Get file age in hours."""
        age = utc_now() - self.last_modified_utc
        return age.total_seconds() / 3600
    
    @computed_field  # type: ignore[misc]
    @property
    def is_recently_modified(self) -> bool:
        """Check if file was modified in last 24 hours."""
        return self.age_hours < 24
    
    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Override to handle datetime serialization."""
        data = super().model_dump(**kwargs)
        
        # Ensure ISO format with timezone for JSON
        if kwargs.get('mode') == 'json':
            data['path'] = str(data['path'])
            data['last_modified_utc'] = self.last_modified_utc.isoformat()
            data['created_at_utc'] = self.created_at_utc.isoformat()
            
            # Add computed fields
            data['last_modified_local'] = self.last_modified_local.isoformat()
            data['age_hours'] = self.age_hours
            
        return data


# Fix for domain events with timezone
from ..base import DomainEvent as BaseDomainEvent


class TimezoneAwareDomainEvent(BaseDomainEvent):
    """Domain event with proper UTC timezone handling."""
    
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the event occurred (always UTC)"
    )
    
    @field_validator('occurred_at', mode='before')
    @classmethod
    def ensure_utc(cls, v: Any) -> datetime:
        """Ensure occurred_at is in UTC."""
        if isinstance(v, datetime):
            return ensure_utc(v)
        return v
    
    @computed_field  # type: ignore[misc]
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


# Fix for test results with timezone
from ..value_objects.test_result import TestResult as BaseTestResult


class TimezoneAwareTestResult(BaseTestResult):
    """Test result with UTC timestamp."""
    
    timestamp: datetime = Field(..., description="Test execution timestamp (UTC)")
    
    @field_validator('timestamp', mode='before')
    @classmethod
    def ensure_utc(cls, v: Any) -> datetime:
        """Ensure timestamp is UTC."""
        if isinstance(v, datetime):
            return ensure_utc(v)
        elif isinstance(v, (int, float)):
            return datetime.fromtimestamp(v, tz=timezone.utc)
        elif isinstance(v, str):
            dt = datetime.fromisoformat(v.replace('Z', '+00:00'))
            return ensure_utc(dt)
        else:
            raise ValueError(f"Cannot convert {type(v)} to datetime")
    
    @computed_field  # type: ignore[misc]
    @property
    def age_days(self) -> float:
        """Get result age in days."""
        age = datetime.now(timezone.utc) - self.timestamp
        return age.total_seconds() / 86400
    
    @computed_field  # type: ignore[misc]
    @property
    def timestamp_iso(self) -> str:
        """Get ISO format timestamp."""
        return self.timestamp.isoformat()


# Utility functions for timezone handling
def parse_datetime_safe(dt_str: str, default_tz: timezone = timezone.utc) -> datetime:
    """Safely parse datetime string with timezone handling."""
    try:
        # Try parsing with timezone
        if 'T' in dt_str:
            # ISO format
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        else:
            # Other formats
            from dateutil import parser
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


# Example usage
def example_timezone_usage():
    """Example of using timezone-aware entities."""
    # Create test file with UTC timestamps
    test_file = TimezoneAwareTestFile.from_path(Path("test.robot"))
    
    print(f"Last modified (UTC): {test_file.last_modified_utc}")
    print(f"Last modified (Local): {test_file.last_modified_local}")
    print(f"Age: {test_file.age_hours:.1f} hours")
    
    # Create event with UTC timestamp
    event = TimezoneAwareDomainEvent(
        event_name="test_completed",
        # occurred_at is automatically UTC
    )
    
    print(f"Event occurred at: {event.occurred_at_iso}")
    
    # Parse datetime safely
    dt = parse_datetime_safe("2024-01-01 12:00:00")  # Assumes UTC
    dt2 = parse_datetime_safe("2024-01-01T12:00:00+02:00")  # Has timezone
    
    # Format for display
    formatted = format_datetime_local(dt, "America/New_York")
    print(f"NY Time: {formatted}")