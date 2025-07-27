# tests/unit/domain/test_base.py
"""Unit tests for domain base classes.

Tests cover ValueObject, Entity, AggregateRoot, and DomainEvent
with comprehensive branch coverage and mutation testing resilience.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import Field, ValidationError

from robot_optimizer_core.domain.base import (
    AggregateRoot,
    DomainEvent,
    Entity,
    ValueObject,
    create_event_id,
    create_timestamp,
)


# Test implementations
class Money(ValueObject):
    """Test value object."""
    amount: Decimal = Field(ge=0)
    currency: str = Field(regex="^[A-Z]{3}$")


class Address(ValueObject):
    """Another test value object."""
    street: str
    city: str
    country: str = "USA"


class Product(Entity[UUID]):
    """Test entity."""
    id: UUID = Field(default_factory=uuid4)
    name: str
    price: Money


class Order(AggregateRoot[UUID]):
    """Test aggregate root."""
    id: UUID = Field(default_factory=uuid4)
    customer_id: UUID
    items: list[Product] = Field(default_factory=list)
    total: Money = Field(default_factory=lambda: Money(amount=Decimal("0"), currency="USD"))
    
    def add_item(self, product: Product) -> None:
        """Add item and emit event."""
        self.items.append(product)
        self.add_event(ItemAddedEvent(
            order_id=self.id,
            product_id=product.id,
            product_name=product.name,
            price=product.price
        ))


class ItemAddedEvent(DomainEvent):
    """Test domain event."""
    order_id: UUID
    product_id: UUID
    product_name: str
    price: Money


class OrderCompletedEvent(DomainEvent):
    """Another test event."""
    order_id: UUID
    total_amount: Decimal


@pytest.mark.unit
class TestValueObject:
    """Test ValueObject base class."""
    
    def test_create_value_object(self) -> None:
        """Test creating a value object."""
        money = Money(amount=Decimal("100.50"), currency="USD")
        
        assert money.amount == Decimal("100.50")
        assert money.currency == "USD"
    
    def test_value_object_immutability(self) -> None:
        """Test that value objects are immutable."""
        money = Money(amount=Decimal("100"), currency="USD")
        
        with pytest.raises(ValidationError) as exc_info:
            money.amount = Decimal("200")
        
        assert "frozen" in str(exc_info.value).lower()
    
    def test_value_object_equality(self) -> None:
        """Test value equality comparison."""
        money1 = Money(amount=Decimal("100"), currency="USD")
        money2 = Money(amount=Decimal("100"), currency="USD")
        money3 = Money(amount=Decimal("100"), currency="EUR")
        money4 = Money(amount=Decimal("200"), currency="USD")
        
        # Same values
        assert money1 == money2
        assert hash(money1) == hash(money2)
        
        # Different currency
        assert money1 != money3
        assert hash(money1) != hash(money3)
        
        # Different amount
        assert money1 != money4
        assert hash(money1) != hash(money4)
        
        # Different type
        assert money1 != "100 USD"
        assert money1 != 100
    
    def test_value_object_validation(self) -> None:
        """Test value object validation."""
        # Valid
        money = Money(amount=Decimal("0"), currency="USD")
        assert money.amount == 0
        
        # Invalid amount (negative)
        with pytest.raises(ValidationError) as exc_info:
            Money(amount=Decimal("-10"), currency="USD")
        assert "greater than or equal to 0" in str(exc_info.value)
        
        # Invalid currency format
        with pytest.raises(ValidationError) as exc_info:
            Money(amount=Decimal("100"), currency="US")
        errors = exc_info.value.errors()
        assert any("string does not match regex" in str(e) for e in errors)
        
        with pytest.raises(ValidationError):
            Money(amount=Decimal("100"), currency="usd")  # Lowercase
    
    def test_value_object_whitespace_stripping(self) -> None:
        """Test automatic whitespace stripping."""
        addr = Address(
            street="  123 Main St  ",
            city="  New York  ",
            country="  USA  "
        )
        
        assert addr.street == "123 Main St"
        assert addr.city == "New York"
        assert addr.country == "USA"
    
    def test_value_object_no_extra_fields(self) -> None:
        """Test that extra fields are forbidden."""
        with pytest.raises(ValidationError) as exc_info:
            Money(
                amount=Decimal("100"),
                currency="USD",
                extra_field="not allowed"  # type: ignore
            )
        assert "extra" in str(exc_info.value).lower()
    
    def test_value_object_hash_with_collections(self) -> None:
        """Test hashing with list and dict fields."""
        class ComplexVO(ValueObject):
            name: str
            tags: list[str]
            metadata: dict[str, Any]
        
        vo1 = ComplexVO(
            name="test",
            tags=["a", "b"],
            metadata={"key": "value"}
        )
        vo2 = ComplexVO(
            name="test",
            tags=["a", "b"],
            metadata={"key": "value"}
        )
        
        assert vo1 == vo2
        assert hash(vo1) == hash(vo2)
        
        # Different list order
        vo3 = ComplexVO(
            name="test",
            tags=["b", "a"],
            metadata={"key": "value"}
        )
        assert vo1 != vo3
    
    def test_value_object_repr(self) -> None:
        """Test string representation."""
        money = Money(amount=Decimal("100.50"), currency="USD")
        repr_str = repr(money)
        
        assert "Money" in repr_str
        assert "amount=Decimal('100.50')" in repr_str
        assert "currency='USD'" in repr_str


@pytest.mark.unit
class TestEntity:
    """Test Entity base class."""
    
    def test_create_entity(self) -> None:
        """Test creating an entity."""
        money = Money(amount=Decimal("99.99"), currency="USD")
        product = Product(name="Laptop", price=money)
        
        assert isinstance(product.id, UUID)
        assert product.name == "Laptop"
        assert product.price == money
    
    def test_entity_identity_equality(self) -> None:
        """Test that entities are compared by ID."""
        id1 = uuid4()
        money1 = Money(amount=Decimal("100"), currency="USD")
        money2 = Money(amount=Decimal("200"), currency="EUR")
        
        # Same ID, different attributes
        product1 = Product(id=id1, name="Laptop", price=money1)
        product2 = Product(id=id1, name="Desktop", price=money2)
        
        assert product1 == product2  # Same ID
        assert hash(product1) == hash(product2)
        assert product1.same_identity(product2)
        
        # Different ID, same attributes
        product3 = Product(name="Laptop", price=money1)
        assert product1 != product3
        assert hash(product1) != hash(product3)
        assert not product1.same_identity(product3)
        
        # Different type
        assert product1 != id1
        assert product1 != "product"
    
    def test_entity_mutability(self) -> None:
        """Test that entities are mutable."""
        money1 = Money(amount=Decimal("100"), currency="USD")
        money2 = Money(amount=Decimal("200"), currency="USD")
        product = Product(name="Laptop", price=money1)
        
        # Should be able to change attributes
        product.name = "Gaming Laptop"
        product.price = money2
        
        assert product.name == "Gaming Laptop"
        assert product.price.amount == Decimal("200")
    
    def test_entity_from_orm(self) -> None:
        """Test creating entity from ORM-like object."""
        class ORMProduct:
            def __init__(self) -> None:
                self.id = uuid4()
                self.name = "ORM Product"
                self.price = Money(amount=Decimal("50"), currency="EUR")
        
        orm_obj = ORMProduct()
        product = Product.model_validate(orm_obj, from_attributes=True)
        
        assert product.id == orm_obj.id
        assert product.name == orm_obj.name
        assert product.price == orm_obj.price
    
    def test_entity_repr(self) -> None:
        """Test entity string representation."""
        id_val = uuid4()
        product = Product(
            id=id_val,
            name="Test",
            price=Money(amount=Decimal("10"), currency="USD")
        )
        
        repr_str = repr(product)
        assert "Product" in repr_str
        assert str(id_val) in repr_str


@pytest.mark.unit
class TestAggregateRoot:
    """Test AggregateRoot base class."""
    
    def test_create_aggregate_root(self) -> None:
        """Test creating an aggregate root."""
        customer_id = uuid4()
        order = Order(customer_id=customer_id)
        
        assert isinstance(order.id, UUID)
        assert order.customer_id == customer_id
        assert order.items == []
        assert not order.has_events
        assert order.event_count == 0
    
    def test_add_and_pull_events(self) -> None:
        """Test event management."""
        order = Order(customer_id=uuid4())
        product = Product(
            name="Mouse",
            price=Money(amount=Decimal("25"), currency="USD")
        )
        
        # Add item (emits event)
        order.add_item(product)
        
        assert order.has_events
        assert order.event_count == 1
        
        # Pull events
        events = order.pull_events()
        assert len(events) == 1
        assert isinstance(events[0], ItemAddedEvent)
        assert events[0].product_name == "Mouse"
        
        # Events cleared after pulling
        assert not order.has_events
        assert order.event_count == 0
        assert order.pull_events() == []
    
    def test_multiple_events(self) -> None:
        """Test handling multiple events."""
        order = Order(customer_id=uuid4())
        
        # Add multiple items
        for i in range(3):
            product = Product(
                name=f"Product {i}",
                price=Money(amount=Decimal(str(10 * i)), currency="USD")
            )
            order.add_item(product)
        
        assert order.event_count == 3
        
        # Add completion event
        order.add_event(OrderCompletedEvent(
            order_id=order.id,
            total_amount=Decimal("30")
        ))
        
        assert order.event_count == 4
        
        events = order.pull_events()
        assert len(events) == 4
        assert sum(1 for e in events if isinstance(e, ItemAddedEvent)) == 3
        assert sum(1 for e in events if isinstance(e, OrderCompletedEvent)) == 1
    
    def test_mark_events_committed(self) -> None:
        """Test marking events as committed."""
        order = Order(customer_id=uuid4())
        product = Product(
            name="Keyboard",
            price=Money(amount=Decimal("50"), currency="USD")
        )
        
        order.add_item(product)
        assert order.has_events
        
        # Mark committed without pulling
        order.mark_events_committed()
        
        assert not order.has_events
        assert order.event_count == 0


@pytest.mark.unit
class TestDomainEvent:
    """Test DomainEvent base class."""
    
    def test_create_domain_event(self) -> None:
        """Test creating a domain event."""
        order_id = uuid4()
        product_id = uuid4()
        price = Money(amount=Decimal("99.99"), currency="USD")
        
        event = ItemAddedEvent(
            order_id=order_id,
            product_id=product_id,
            product_name="Tablet",
            price=price
        )
        
        assert isinstance(event.event_id, UUID)
        assert isinstance(event.occurred_at, datetime)
        assert event.order_id == order_id
        assert event.product_name == "Tablet"
        assert event.price == price
    
    def test_event_immutability(self) -> None:
        """Test that events are immutable."""
        event = ItemAddedEvent(
            order_id=uuid4(),
            product_id=uuid4(),
            product_name="Test",
            price=Money(amount=Decimal("10"), currency="USD")
        )
        
        with pytest.raises(ValidationError):
            event.product_name = "Changed"
    
    def test_event_name_derivation(self) -> None:
        """Test automatic event name derivation."""
        event1 = ItemAddedEvent(
            order_id=uuid4(),
            product_id=uuid4(),
            product_name="Test",
            price=Money(amount=Decimal("10"), currency="USD")
        )
        assert event1.event_name == "item_added"
        
        event2 = OrderCompletedEvent(
            order_id=uuid4(),
            total_amount=Decimal("100")
        )
        assert event2.event_name == "order_completed"
        
        # Test without Event suffix
        class UserRegistered(DomainEvent):
            user_id: UUID
        
        event3 = UserRegistered(user_id=uuid4())
        assert event3.event_name == "user_registered"
    
    def test_event_version(self) -> None:
        """Test event version."""
        event = ItemAddedEvent(
            order_id=uuid4(),
            product_id=uuid4(),
            product_name="Test",
            price=Money(amount=Decimal("10"), currency="USD")
        )
        assert event.event_version == "1.0"
    
    def test_event_to_message(self) -> None:
        """Test converting event to message format."""
        order_id = uuid4()
        product_id = uuid4()
        event = ItemAddedEvent(
            order_id=order_id,
            product_id=product_id,
            product_name="Monitor",
            price=Money(amount=Decimal("299.99"), currency="USD")
        )
        
        message = event.to_message()
        
        assert message["event_name"] == "item_added"
        assert message["event_version"] == "1.0"
        assert message["event_id"] == str(event.event_id)
        assert message["occurred_at"] == event.occurred_at.isoformat()
        
        # Check data
        data = message["data"]
        assert data["order_id"] == str(order_id)
        assert data["product_id"] == str(product_id)
        assert data["product_name"] == "Monitor"
        assert data["price"]["amount"] == "299.99"
        assert data["price"]["currency"] == "USD"
        
        # Should be JSON serializable
        json_str = json.dumps(message)
        assert isinstance(json_str, str)
    
    def test_custom_event_id_and_timestamp(self) -> None:
        """Test providing custom event ID and timestamp."""
        custom_id = uuid4()
        custom_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        event = ItemAddedEvent(
            event_id=custom_id,
            occurred_at=custom_time,
            order_id=uuid4(),
            product_id=uuid4(),
            product_name="Custom",
            price=Money(amount=Decimal("1"), currency="USD")
        )
        
        assert event.event_id == custom_id
        assert event.occurred_at == custom_time
    
    def test_event_repr(self) -> None:
        """Test event string representation."""
        event = OrderCompletedEvent(
            order_id=uuid4(),
            total_amount=Decimal("500")
        )
        
        repr_str = repr(event)
        assert "OrderCompletedEvent" in repr_str
        assert str(event.event_id) in repr_str
        assert event.occurred_at.isoformat() in repr_str


@pytest.mark.unit
class TestHelperFunctions:
    """Test helper functions."""
    
    def test_create_event_id(self) -> None:
        """Test event ID creation."""
        id1 = create_event_id()
        id2 = create_event_id()
        
        assert isinstance(id1, UUID)
        assert isinstance(id2, UUID)
        assert id1 != id2  # Should be unique
    
    def test_create_timestamp(self) -> None:
        """Test timestamp creation."""
        before = datetime.now(timezone.utc)
        timestamp = create_timestamp()
        after = datetime.now(timezone.utc)
        
        assert isinstance(timestamp, datetime)
        assert timestamp.tzinfo is not None
        assert before <= timestamp <= after