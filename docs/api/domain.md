# Domain Models API Reference

Core domain objects following Domain-Driven Design principles.

## Base Classes

### ValueObject

Immutable objects compared by their attributes.

```python
from robot_optimizer_core.domain.base import ValueObject
from pydantic import Field

class Price(ValueObject):
    amount: float = Field(ge=0)
    currency: str = Field(pattern="^[A-Z]{3}$")

# Value equality
price1 = Price(amount=10.0, currency="USD")
price2 = Price(amount=10.0, currency="USD")
assert price1 == price2  # True - same values
```

**Features:**
- Immutable (`frozen=True`)
- Value-based equality
- Hashable (can use in sets/dicts)
- Pydantic v2 validation

### Entity[T]

Objects with identity, compared by ID.

```python
from robot_optimizer_core.domain.base import Entity
from uuid import UUID, uuid4
from pydantic import Field

class Product(Entity[UUID]):
    id: UUID = Field(default_factory=uuid4)
    name: str
    price: float

# Identity equality
p1 = Product(name="Laptop", price=999.0)
p2 = Product(id=p1.id, name="Gaming Laptop", price=1299.0)
assert p1 == p2  # True - same ID
```

**Type Parameter:**
- `T`: Type of entity ID (UUID, str, int, etc.)

### AggregateRoot[T]

Entity that serves as transaction boundary with domain events.

```python
from robot_optimizer_core.domain.base import AggregateRoot, DomainEvent

class Order(AggregateRoot[UUID]):
    id: UUID = Field(default_factory=uuid4)
    items: list[str] = Field(default_factory=list)

    def add_item(self, item: str) -> None:
        self.items.append(item)
        self.add_event(ItemAddedEvent(order_id=self.id, item=item))

# Event management
order = Order()
order.add_item("Laptop")
events = order.pull_events()  # Get and clear events
```

**Features:**
- Event sourcing support
- Transaction boundary marker
- Event collection and dispatch

### DomainEvent

Base class for domain events.

```python
from robot_optimizer_core.domain.base import DomainEvent
from uuid import UUID

class ItemAddedEvent(DomainEvent):
    order_id: UUID
    item: str

event = ItemAddedEvent(order_id=uuid4(), item="Laptop")
print(event.event_id)  # Auto-generated UUID
print(event.occurred_at)  # Auto-generated timestamp
print(event.event_name)  # "item_added" (derived from class name)
```

## Core Entities

### TestFile

Represents a Robot Framework test file.

```python
from robot_optimizer_core import TestFile
from pathlib import Path

# Load from file
test_file = TestFile.from_path(Path("tests/login.robot"))

# Access properties
print(test_file.id)  # UUID
print(test_file.path)  # Path
print(test_file.content)  # File content
print(test_file.size_bytes)  # File size
print(test_file.last_modified_utc)  # Modification time (UTC)
```

**Fields:**
- `id: UUID` - Unique identifier
- `path: Path` - File path
- `content: str` - File content
- `size_bytes: int` - File size
- `last_modified_utc: datetime` - Last modification time (timezone-aware)

**Methods:**
- `from_path(file_path: Path) -> TestFile` - Factory method to load from file
- `get_lines(start: int, end: int | None = None) -> list[str]` - Get line range

**Properties:**
- `name: str` - File name without extension
- `extension: str` - File extension
- `line_count: int` - Number of lines
- `is_resource_file: bool` - Whether file is a resource file

## Value Objects

### Finding

Represents an analysis finding (issue/suggestion).

```python
from robot_optimizer_core import Finding, Pattern, Severity, Location

finding = Finding.create(
    pattern=Pattern.sleep_in_test("2.0"),
    severity=Severity.WARNING,
    location=Location(Path("test.robot"), 34),
    message="Sleep detected: 2.0s"
)
```

**Fields:**
- `id: UUID` - Finding ID
- `pattern: Pattern` - Issue pattern
- `severity: Severity` - ERROR, WARNING, or INFO
- `location: Location` - Where the issue was found
- `message: str` - Human-readable message
- `context: dict | None` - Additional context

### Pattern

Describes the type of issue found.

```python
from robot_optimizer_core import Pattern, PatternType

pattern = Pattern(
    type=PatternType.SLEEP_IN_TEST,
    details={"duration": 2.0},
    auto_fixable=True,
    suggested_fix="Wait Until Element Is Visible    id=login"
)
```

**Fields:**
- `type: PatternType` - Pattern category
- `details: dict` - Pattern-specific data
- `auto_fixable: bool` - Whether auto-fix is possible
- `suggested_fix: str | None` - Suggested fix

**Factory Methods:**
- `Pattern.sleep_in_test(duration: str) -> Pattern`
- `Pattern.duplicate_keyword(name: str) -> Pattern`
- `Pattern.unused_keyword(name: str) -> Pattern`
- `Pattern.long_test_case(step_count: int) -> Pattern`

### Location

Represents a location in a file.

```python
from robot_optimizer_core import Location
from pathlib import Path

location = Location(
    file_path=Path("tests/login.robot"),
    line_number=34,
    column_number=12
)
```

**Fields:**
- `file_path: Path` - File path
- `line_number: int` - Line number (1-indexed)
- `column_number: int | None` - Column number (1-indexed)

### Severity

Enumeration of finding severity levels.

```python
from robot_optimizer_core import Severity

severity = Severity.ERROR  # Critical issues
severity = Severity.WARNING  # Important but not critical
severity = Severity.INFO  # Suggestions
```

**Values:**
- `ERROR = 1` - Critical issues that break best practices
- `WARNING = 2` - Important issues, suboptimal but works
- `INFO = 3` - Minor suggestions and improvements

### SleepPattern

Specialized value object for Sleep pattern details.

```python
from robot_optimizer_core import SleepPattern

pattern = SleepPattern(
    duration_seconds=2.0,
    suggested_alternative="Wait Until Element Is Visible"
)
```

### FlakinessStats

Statistics about test flakiness.

```python
from robot_optimizer_core import FlakinessStats

stats = FlakinessStats(
    total_executions=100,
    failures=10,
    flakiness_rate=0.1
)
```

### TestResult

Represents a test execution result.

```python
from robot_optimizer_core import TestResult

result = TestResult(
    test_name="Login Test",
    status="PASS",
    duration_seconds=2.5,
    executed_at=datetime.now(UTC)
)
```

## Repositories

### TestResultRepository (Interface)

Abstract repository for test result persistence.

```python
from robot_optimizer_core.domain.repositories import TestResultRepository

class MyTestResultRepo(TestResultRepository):
    def get_test_history(
        self,
        test_name: str,
        limit: int = 100
    ) -> list[TestResult]:
        # Implementation
        pass

    def save_test_result(self, result: TestResult) -> None:
        # Implementation
        pass
```

## See Also

- [Analyzers API](analyzers.md) - Analyzer framework
- [Getting Started](../getting-started.md) - Usage examples
- [Extending](../extending.md) - Creating custom analyzers
