# src/robot_optimizer_core/domain/base.py
"""Domain base classes for DDD patterns using Pydantic v2.

This module provides the foundation for Domain-Driven Design patterns
including Value Objects, Entities, Aggregate Roots, and Domain Events.

Example:
    Creating domain objects::
    
        from robot_optimizer_core.domain.base import ValueObject, Entity
        from pydantic import Field
        
        class Money(ValueObject):
            amount: Decimal = Field(ge=0)
            currency: str = Field(regex="^[A-Z]{3}$")
        
        class User(Entity[UUID]):
            id: UUID
            name: str
            email: EmailStr
"""
from __future__ import annotations

from abc import ABC
from datetime import UTC, datetime
from typing import Any, ClassVar, Generic, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field

T = TypeVar("T")
TEntity = TypeVar("TEntity", bound="Entity")
TValueObject = TypeVar("TValueObject", bound="ValueObject")


class ValueObject(BaseModel, ABC):
    """Base class for value objects using Pydantic v2.
    
    Value objects are immutable domain objects that are defined by their
    attributes rather than identity. They are compared by value equality.
    
    Features:
        - Immutable (frozen=True)
        - Value equality comparison
        - Automatic whitespace stripping
        - No extra fields allowed
        - Enum values used directly
    
    Example:
        >>> class Address(ValueObject):
        ...     street: str
        ...     city: str
        ...     country: str
        >>> 
        >>> addr1 = Address(street="123 Main", city="NYC", country="USA")
        >>> addr2 = Address(street="123 Main", city="NYC", country="USA")
        >>> assert addr1 == addr2  # Value equality
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
        use_enum_values=True,
        json_schema_extra={
            "title": "ValueObject",
            "description": "Immutable value object"
        }
    )

    def __eq__(self, other: Any) -> bool:
        """Compare value objects by their attributes.
        
        Args:
            other: Object to compare with.
            
        Returns:
            True if all attributes are equal.
        """
        if not isinstance(other, self.__class__):
            return False
        return self.model_dump() == other.model_dump()

    def __hash__(self) -> int:
        """Generate hash based on all attributes.
        
        Returns:
            Hash value for the object.
        """
        # Create a hashable representation of the model data
        data = self.model_dump()
        hashable_items = []

        for key, value in sorted(data.items()):
            if isinstance(value, list):
                hashable_items.append((key, tuple(value)))
            elif isinstance(value, dict):
                hashable_items.append((key, tuple(sorted(value.items()))))
            else:
                hashable_items.append((key, value))

        return hash(tuple(hashable_items))

    def __repr__(self) -> str:
        """Return a detailed string representation.
        
        Returns:
            String representation with all fields.
        """
        fields = ", ".join(
            f"{k}={v!r}" for k, v in self.model_dump().items()
        )
        return f"{self.__class__.__name__}({fields})"


class Entity(BaseModel, ABC, Generic[T]):
    """Base class for entities using Pydantic v2.
    
    Entities have identity and are compared by their ID, not by their
    attributes. They can change over time while maintaining identity.
    
    Type Parameters:
        T: Type of the entity ID (e.g., UUID, str, int).
    
    Features:
        - Identity-based equality
        - Mutable attributes
        - Arbitrary types allowed
        - Can be created from ORM objects
    
    Example:
        >>> class Product(Entity[UUID]):
        ...     id: UUID = Field(default_factory=uuid4)
        ...     name: str
        ...     price: Decimal
        >>> 
        >>> p1 = Product(name="Laptop", price=Decimal("999.99"))
        >>> p2 = Product(id=p1.id, name="Gaming Laptop", price=Decimal("1299.99"))
        >>> assert p1 == p2  # Same ID = same entity
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True,
        extra="forbid",
        use_enum_values=True,
        from_attributes=True,  # Support ORM mode
        json_schema_extra={
            "title": "Entity",
            "description": "Domain entity with identity"
        }
    )

    id: T = Field(..., description="Unique identifier for the entity")

    def __eq__(self, other: Any) -> bool:
        """Compare entities by their ID.
        
        Args:
            other: Object to compare with.
            
        Returns:
            True if both have the same ID.
        """
        if not isinstance(other, self.__class__):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        """Hash based on entity ID.
        
        Returns:
            Hash of the entity ID.
        """
        return hash(self.id)

    def __repr__(self) -> str:
        """Return string representation with ID.
        
        Returns:
            String representation.
        """
        return f"{self.__class__.__name__}(id={self.id!r})"

    def same_identity(self, other: Entity[T]) -> bool:
        """Check if two entities have the same identity.
        
        Args:
            other: Another entity.
            
        Returns:
            True if same identity.
        """
        return self.id == other.id


class AggregateRoot(Entity[T], ABC):
    """Base class for aggregate roots using Pydantic v2.
    
    Aggregate roots are entities that serve as the entry point to an
    aggregate. They maintain consistency boundaries and emit domain events.
    
    Features:
        - Event sourcing support
        - Consistency boundary enforcement
        - Domain event emission
        - Transaction boundary marker
    
    Example:
        >>> class Order(AggregateRoot[UUID]):
        ...     id: UUID = Field(default_factory=uuid4)
        ...     items: List[OrderItem] = Field(default_factory=list)
        ...     
        ...     def add_item(self, item: OrderItem) -> None:
        ...         self.items.append(item)
        ...         self.add_event(ItemAddedEvent(order_id=self.id, item=item))
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True,
        extra="forbid",
        use_enum_values=True,
        from_attributes=True,
        json_schema_extra={
            "title": "AggregateRoot",
            "description": "Aggregate root entity"
        }
    )

    def __init__(self, **data: Any) -> None:
        """Initialize aggregate root with event list.
        
        Args:
            **data: Field values for the aggregate.
        """
        super().__init__(**data)
        # Initialize events list as instance attribute
        self._events: list[DomainEvent] = []

    def add_event(self, event: DomainEvent) -> None:
        """Add a domain event to be dispatched.
        
        Events are collected and can be retrieved using pull_events().
        They represent important state changes in the domain.
        
        Args:
            event: Domain event to add.
        """
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        """Pull all pending events and clear the list.
        
        This method is typically called by the infrastructure layer
        after persisting the aggregate to dispatch events.
        
        Returns:
            List of pending domain events.
        """
        events = self._events.copy()
        self._events.clear()
        return events

    @computed_field  # type: ignore[misc]
    @property
    def has_events(self) -> bool:
        """Check if there are pending events.
        
        Returns:
            True if events are pending.
        """
        return len(self._events) > 0

    @computed_field  # type: ignore[misc]
    @property
    def event_count(self) -> int:
        """Get the count of pending events.
        
        Returns:
            Number of pending events.
        """
        return len(self._events)

    def mark_events_committed(self) -> None:
        """Mark all events as committed.
        
        This clears the events list without returning them,
        useful when events have been persisted separately.
        """
        self._events.clear()


def create_event_id() -> UUID:
    """Create a new event ID.
    
    Returns:
        New UUID for event identification.
    """
    return uuid4()


def create_timestamp() -> datetime:
    """Create a timestamp in UTC.
    
    Returns:
        Current UTC timestamp.
    """
    return datetime.now(UTC)


class DomainEvent(BaseModel, ABC):
    """Base class for domain events using Pydantic v2.
    
    Domain events represent something that has happened in the domain
    that domain experts care about. They are immutable records of
    past occurrences.
    
    Features:
        - Immutable (frozen=True)
        - Automatic ID and timestamp
        - JSON serializable
        - Event name derivation
    
    Example:
        >>> class UserRegisteredEvent(DomainEvent):
        ...     user_id: UUID
        ...     email: str
        ...     registered_at: datetime
        >>> 
        >>> event = UserRegisteredEvent(
        ...     user_id=uuid4(),
        ...     email="user@example.com",
        ...     registered_at=datetime.now(timezone.utc)
        ... )
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        populate_by_name=True,
        str_strip_whitespace=True,
        json_schema_extra={
            "title": "DomainEvent",
            "description": "Immutable domain event",
            "example": {
                "event_id": "123e4567-e89b-12d3-a456-426614174000",
                "occurred_at": "2024-01-01T00:00:00Z"
            }
        }
    )

    event_id: UUID = Field(
        default_factory=create_event_id,
        description="Unique event identifier"
    )
    occurred_at: datetime = Field(
        default_factory=create_timestamp,
        description="When the event occurred (UTC)"
    )

    @computed_field  # type: ignore[misc]
    @property
    def event_name(self) -> str:
        """Get the event name derived from class name.
        
        Converts class name from PascalCase to snake_case,
        removing 'Event' suffix if present.
        
        Returns:
            Event name in snake_case.
        """
        name = self.__class__.__name__

        # Remove Event suffix if present
        if name.endswith("Event"):
            name = name[:-5]

        # Convert PascalCase to snake_case
        import re
        name = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()

        return name

    @computed_field  # type: ignore[misc]
    @property
    def event_version(self) -> str:
        """Get the event version.
        
        Subclasses can override this to provide versioning.
        
        Returns:
            Event version (default: "1.0").
        """
        return "1.0"

    def to_message(self) -> dict[str, Any]:
        """Convert event to a message format.
        
        Useful for event buses and message queues.
        
        Returns:
            Dictionary with event data and metadata.
        """
        return {
            "event_id": str(self.event_id),
            "event_name": self.event_name,
            "event_version": self.event_version,
            "occurred_at": self.occurred_at.isoformat(),
            "data": self.model_dump(
                exclude={"event_id", "occurred_at"},
                mode="json"
            )
        }

    def __repr__(self) -> str:
        """Return string representation of event.
        
        Returns:
            String representation.
        """
        return (
            f"{self.__class__.__name__}("
            f"event_id={self.event_id}, "
            f"occurred_at={self.occurred_at.isoformat()})"
        )
