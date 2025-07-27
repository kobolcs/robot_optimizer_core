# src/robot_optimizer/domain/base.py
"""Domain base classes for value objects, entities, aggregate roots, and events.

100% Pydantic v2 compliant implementation.
"""

from abc import ABC
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar, List
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, ConfigDict, computed_field


class ValueObject(BaseModel, ABC):
    """Base class for value objects using Pydantic v2.

    Value objects are immutable and compared by their attributes.
    All value objects are frozen and validate assignment.
    """

    model_config = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid',
        use_enum_values=True,
    )

    def __eq__(self, other: Any) -> bool:
        """Compare value objects by their attributes."""
        if not isinstance(other, self.__class__):
            return False
        return self.model_dump() == other.model_dump()

    def __hash__(self) -> int:
        """Hash based on all attributes."""
        return hash(tuple(sorted(self.model_dump().items())))


T = TypeVar('T')


class Entity(BaseModel, ABC, Generic[T]):
    """Base class for entities using Pydantic v2.

    Entities have identity and are compared by their ID.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True,
        extra='forbid',
        use_enum_values=True,
        from_attributes=True,
    )

    id: T

    def __eq__(self, other: Any) -> bool:
        """Compare entities by their ID."""
        if not isinstance(other, self.__class__):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        """Hash based on entity ID."""
        return hash(self.id)


class AggregateRoot(Entity[T], ABC):
    """Base class for aggregate roots using Pydantic v2.

    Aggregate roots are entities that serve as the entry point to an aggregate.
    They can emit domain events.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True,
        extra='forbid',
        use_enum_values=True,
        from_attributes=True,
    )

    # Regular instance attribute - initialized in __init__
    def __init__(self, **data: Any) -> None:
        """Initialize with events list."""
        super().__init__(**data)
        self._events: List[DomainEvent] = []

    def add_event(self, event: 'DomainEvent') -> None:
        """Add a domain event to be dispatched."""
        self._events.append(event)

    def pull_events(self) -> List['DomainEvent']:
        """Pull all pending events and clear the list."""
        events = self._events[:]  # Use list slicing instead of .copy() for v2 compliance
        self._events.clear()
        return events

    @computed_field  # type: ignore[misc]
    @property
    def has_events(self) -> bool:
        """Check if there are pending events."""
        return len(self._events) > 0

    @computed_field  # type: ignore[misc]
    @property
    def event_count(self) -> int:
        """Get the count of pending events."""
        return len(self._events)


def create_event_id() -> UUID:
    """Create a new event ID."""
    return uuid4()


def create_timestamp() -> datetime:
    """Create a timestamp in UTC."""
    return datetime.now(timezone.utc)


class DomainEvent(BaseModel, ABC):
    """Base class for domain events using Pydantic v2."""

    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "event_id": "123e4567-e89b-12d3-a456-426614174000",
                "occurred_at": "2024-01-01T00:00:00Z"
            }
        }
    )

    event_id: UUID = Field(default_factory=create_event_id)
    occurred_at: datetime = Field(default_factory=create_timestamp)

    @computed_field  # type: ignore[misc]
    @property
    def event_name(self) -> str:
        """Get the event name (computed from class name)."""
        return self.__class__.__name__.replace('Event', '').lower()

    def model_dump_json(self, **kwargs: Any) -> str:
        """Override to ensure proper datetime serialization."""
        kwargs.setdefault('mode', 'json')
        return super().model_dump_json(**kwargs)
