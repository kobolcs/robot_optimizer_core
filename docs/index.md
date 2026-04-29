# Robot Framework Optimizer Core

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code Quality](https://img.shields.io/badge/quality-reviewed-brightgreen.svg)](https://github.com/kobolcs/robot_optimizer_core)

**Beta-quality analysis engine for Robot Framework test suite optimization.**

Robot Framework Optimizer Core is a modern, type-safe Python library that helps you find and fix issues in your Robot Framework test suites. Built with Domain-Driven Design principles and tested compatibility across Python 3.11–3.14.

## Features

### Built-in Analyzers

- **Dead Code Detection** - Find unused keywords and duplicate definitions
- **Sleep Pattern Analysis** - Identify inefficient `Sleep` usage that should be replaced with proper waits
- **Flakiness Detection** - Detect tests that fail intermittently based on historical data
- **Custom Analyzers** - Easy plugin system for domain-specific analyzers

### Architecture Highlights

- **Modern Python 3.11+** - Tested on Python 3.11, 3.12, 3.13, and 3.14 for maintainable analysis workflows
- **Type-Safe** - Full type hints with Pydantic v2 validation
- **Domain-Driven Design** - Clean separation of concerns with proper layering
- **Extensible** - Plugin system for custom analyzers
- **Quality-Gated** - Structured logging, GDPR-compliant metrics, and an 80%+ CI coverage gate
- **Thread-Safe** - Dependency injection container with circular dependency detection

## Installation

```bash
pip install robot-framework-optimizer-core
```

**Requirements:** Python 3.11+

Robot Framework 7.1+ is required. CI tests against the latest compatible Robot Framework release.

## Quick Start

### Analyze a Single File

```python
from robot_optimizer_core import analyze_file
from pathlib import Path

findings = analyze_file(Path("tests/login.robot"))

for finding in findings:
    print(f"{finding.severity.name}: {finding.message}")
    print(f"  Location: {finding.location.file_path}:{finding.location.line_number}")
```

### Analyze a Directory

```python
from robot_optimizer_core import analyze_directory

results = analyze_directory(
    Path("tests/"),
    recursive=True,
    patterns=["*.robot", "*.resource"]
)

for file_path, findings in results.items():
    print(f"{file_path}: {len(findings)} issues found")
    for finding in findings:
        print(f"  - {finding.severity.name}: {finding.message}")
```

### Use Specific Analyzers

```python
from robot_optimizer_core import TestFile, DeadCodeAnalyzer, SleepDetector

test_file = TestFile.from_path(Path("tests/suite.robot"))

dead_code = DeadCodeAnalyzer()
findings = dead_code.analyze(test_file)

sleep_detector = SleepDetector(config={
    "max_acceptable_sleep_seconds": 0.5
})
sleep_findings = sleep_detector.analyze(test_file)
```

### Configure Settings

```python
from robot_optimizer_core import Settings, analyze_file

settings = Settings(
    max_file_size_mb=20.0,
    max_acceptable_sleep_seconds=0.5,
    exclude_patterns=["**/build/**", "**/generated/**"],
    enable_metrics=True,
    log_level="DEBUG"
)

findings = analyze_file("test.robot", settings=settings)
```

## Documentation

- **[Getting Started](getting-started.md)** - Installation, basic usage, and examples
- **[Extending](extending.md)** - Create custom analyzers and plugins
- **[API Reference](api/)** - Complete API documentation
  - [Analyzers API](api/analyzers.md) - Built-in and custom analyzers
  - [Domain Models](api/domain.md) - Core domain objects
  - [Plugins](api/plugins.md) - Plugin development guide

## Architecture

The Core package follows Domain-Driven Design principles:

```
+------------------------------------------+
|           High-Level API                 |
|  (analyze_file, analyze_directory)       |
+------------------------------------------+
                    |
+------------------------------------------+
|              Analyzers                   |
|  (DeadCode, Sleep, Flakiness, Custom)   |
+------------------------------------------+
                    |
+------------------------------------------+
|            Domain Models                 |
|  (TestFile, Finding, Pattern, Location)  |
+------------------------------------------+
                    |
+------------------------------------------+
|           Infrastructure                 |
|  (Parser, Discovery, Repositories)       |
+------------------------------------------+
```

### Key Design Patterns

- **Domain-Driven Design** - Pure domain logic isolated from infrastructure
- **Repository Pattern** - Abstract data access for test results
- **Plugin System** - Extensible analyzer framework with security validation
- **Dependency Injection** - Thread-safe container with lifetime management
- **Event Sourcing** - Domain events for audit trails and integration

## Configuration

Settings can be configured via:

1. **Environment variables** (highest priority)
2. **`.env` file**
3. **Code** (Settings object)
4. **Defaults** (lowest priority)

### Environment Variables

All settings can be overridden with `ROBOT_OPTIMIZER_` prefix:

```bash
export ROBOT_OPTIMIZER_MAX_FILE_SIZE_MB=20.0
export ROBOT_OPTIMIZER_LOG_LEVEL=DEBUG
export ROBOT_OPTIMIZER_ENABLE_METRICS=false
```

### Configuration File

Create `.env` in your project root:

```ini
ROBOT_OPTIMIZER_MAX_FILE_SIZE_MB=20.0
ROBOT_OPTIMIZER_MAX_ACCEPTABLE_SLEEP_SECONDS=0.5
ROBOT_OPTIMIZER_LOG_LEVEL=INFO
```

## Example Output

```
ERROR: Duplicate keyword definition 'Login User'
  Location: tests/login.robot:45
  Pattern: duplicate_keyword

WARNING: Sleep usage detected (2.0s)
  Location: tests/checkout.robot:78
  Suggestion: Replace with 'Wait Until Element Is Visible'

INFO: Long test case (120 steps)
  Location: tests/integration.robot:12
  Suggestion: Consider splitting into smaller tests
```

## Extensibility

Create custom analyzers:

```python
from robot_optimizer_core import BaseAnalyzer, TestFile, Finding

class CustomAnalyzer(BaseAnalyzer):
    @property
    def name(self) -> str:
        return "custom"

    @property
    def description(self) -> str:
        return "Custom analysis rules"

    def analyze(self, test_file: TestFile) -> list[Finding]:
        findings = []
        # Your analysis logic here
        return findings

from robot_optimizer_core import register_analyzer

register_analyzer("custom", CustomAnalyzer)
```

See [Extending](extending.md) for complete plugin development guide.

## Testing

The Core package has **comprehensive test coverage** with:

- **Unit tests** - Fast, isolated tests with mocks
- **Integration tests** - Component interaction tests
- **Component tests** - End-to-end workflow tests
- **Property-based tests** - Hypothesis for edge cases
- **Mutation tests** - Ensure test quality

Run tests:

```bash
pytest tests/
pytest tests/ --cov=robot_optimizer_core --cov-report=html
```

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Ensure all tests pass
5. Submit a pull request

Open an issue or pull request on GitHub to get started.

## License

MIT License - see [LICENSE](../LICENSE) for details.

## Links

- **Source Code**: [https://github.com/kobolcs/robot_optimizer_core](https://github.com/kobolcs/robot_optimizer_core)
- **Issue Tracker**: [https://github.com/kobolcs/robot_optimizer_core/issues](https://github.com/kobolcs/robot_optimizer_core/issues)
- **PyPI**: [https://pypi.org/project/robot-framework-optimizer-core](https://pypi.org/project/robot-framework-optimizer-core)

## Acknowledgments

Built with modern Python best practices:

- **Pydantic v2** - Data validation and settings
- **Robot Framework** - Test automation framework
- **Domain-Driven Design** - Eric Evans
- **Clean Architecture** - Robert C. Martin

---

**Made with care for the Robot Framework community**


## Known Limitations

- Findings are static-analysis hints, not proof of defects.
- Dynamic Robot Framework keyword usage can require manual review.
- Dead-code detection is more reliable at suite level than single-file level.
- False positives are still possible in heavily dynamic suites.
- The Core HTML report is static and local; it does not include historical trend views.
- PDF export, dashboards, baseline diffing, and advanced branded reporting are not part of Core.

