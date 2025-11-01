# Analyzers API Reference

Complete reference for the analyzer framework.

## BaseAnalyzer

Abstract base class for all analyzers.

```python
from robot_optimizer_core import BaseAnalyzer
from typing import override

class MyAnalyzer(BaseAnalyzer):
    @property
    @override
    def name(self) -> str:
        """Unique analyzer identifier."""
        return "my_analyzer"

    @property
    @override
    def description(self) -> str:
        """Human-readable description."""
        return "Analyzer description"

    @property
    @override
    def tags(self) -> list[str]:
        """Tags for categorization."""
        return ["quality", "custom"]

    @override
    def analyze(self, test_file: TestFile) -> list[Finding]:
        """Main analysis logic."""
        return []
```

### Methods

#### `__init__(config: dict | None = None)`

Initialize analyzer with optional configuration.

**Parameters:**
- `config`: Optional configuration dictionary

**Example:**
```python
analyzer = MyAnalyzer(config={
    "threshold": 10,
    "strict_mode": True
})
```

#### `analyze(test_file: TestFile) -> list[Finding]` 

**Required override.** Analyze a test file and return findings.

**Parameters:**
- `test_file`: TestFile entity to analyze

**Returns:**
- List of Finding objects

#### `validate_config() -> None`

Validate analyzer configuration. Override to add custom validation.

**Raises:**
- `ConfigurationError`: If configuration is invalid

**Example:**
```python
@override
def validate_config(self) -> None:
    threshold = self.get_config_value("threshold")
    if threshold and threshold < 0:
        raise ConfigurationError("threshold must be non-negative")
```

#### `get_config_value(key: str, default: Any = None) -> Any`

Get configuration value with fallback.

**Parameters:**
- `key`: Configuration key
- `default`: Default value if not found

**Returns:**
- Configuration value or default

### Properties

#### `name: str` *(abstract)*

Unique analyzer identifier (e.g., "dead_code", "sleep_detector").

#### `description: str` *(abstract)*

Human-readable description of what the analyzer does.

#### `tags: list[str]` *(abstract)*

Tags for categorization (e.g., ["performance", "reliability"]).

#### `supports_auto_fix: bool`

Whether analyzer supports automatic fixes. Default: `False`

## Built-in Analyzers

### DeadCodeAnalyzer

Detects unused keywords and duplicate definitions.

```python
from robot_optimizer_core import DeadCodeAnalyzer

analyzer = DeadCodeAnalyzer(config={
    "check_unused": True,
    "check_duplicates": True,
    "check_unreachable": True
})
```

**Configuration:**
- `check_unused` (bool): Check for unused keywords (default: True)
- `check_duplicates` (bool): Check for duplicate definitions (default: True)
- `check_unreachable` (bool): Check for unreachable code (default: True)

**Detected Patterns:**
- `duplicate_keyword`: Same keyword defined multiple times
- `unused_keyword`: Keyword defined but never called
- `unreachable_code`: Code after RETURN statement

### SleepDetector

Finds Sleep keyword usage that should be replaced with explicit waits.

```python
from robot_optimizer_core import SleepDetector

analyzer = SleepDetector(config={
    "max_acceptable_sleep_seconds": 0.5
})
```

**Configuration:**
- `max_acceptable_sleep_seconds` (float): Maximum acceptable sleep duration (default: 1.0)

**Detected Patterns:**
- `sleep_in_test`: Sleep used in test case
- `sleep_in_keyword`: Sleep used in keyword
- `long_sleep`: Sleep duration exceeds threshold

**Auto-fix:** ✅ Yes - suggests explicit wait alternatives

### FlakinessAnalyzer

Detects tests that fail intermittently based on historical data.

```python
from robot_optimizer_core import FlakinessAnalyzer

analyzer = FlakinessAnalyzer(config={
    "min_executions": 5,
    "flakiness_threshold": 0.1
})
```

**Configuration:**
- `min_executions` (int): Minimum test executions required (default: 5)
- `flakiness_threshold` (float): Flakiness rate threshold 0.0-1.0 (default: 0.1)

**Detected Patterns:**
- `flaky_test`: Test fails intermittently
- `unstable_keyword`: Keyword causes flakiness

**Requires:** Test result repository with historical data

## Registry Functions

### `register_analyzer(name: str, analyzer_class: type[BaseAnalyzer])`

Register a custom analyzer.

```python
from robot_optimizer_core import register_analyzer

register_analyzer("my_analyzer", MyAnalyzer)
```

### `get_analyzer(name: str) -> BaseAnalyzer`

Get analyzer instance by name.

```python
from robot_optimizer_core import get_analyzer

analyzer = get_analyzer("dead_code")
```

### `list_analyzers() -> dict[str, type[BaseAnalyzer]]`

Get all registered analyzers.

```python
from robot_optimizer_core import list_analyzers

for name, analyzer_class in list_analyzers().items():
    print(f"{name}: {analyzer_class.__doc__}")
```

## AnalyzerRegistry

Singleton registry for managing analyzers.

```python
from robot_optimizer_core import AnalyzerRegistry

registry = AnalyzerRegistry()

# Register
registry.register("my_analyzer", MyAnalyzer)

# Get
analyzer_class = registry.get("my_analyzer")

# List all
names = registry.list_analyzers()
```

## See Also

- [Extending Guide](../extending.md) - How to create custom analyzers
- [Domain API](domain.md) - Domain model reference
- [Getting Started](../getting-started.md) - Basic usage examples
