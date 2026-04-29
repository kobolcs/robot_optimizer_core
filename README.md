# Robot Framework Optimizer Core

[![Python Version](https://img.shields.io/pypi/pyversions/robot-framework-optimizer-core.svg)](https://pypi.org/project/robot-framework-optimizer-core/)
[![PyPI Version](https://img.shields.io/pypi/v/robot-framework-optimizer-core.svg)](https://pypi.org/project/robot-framework-optimizer-core/)
[![License](https://img.shields.io/pypi/l/robot-framework-optimizer-core.svg)](https://github.com/kobolcs/robot_optimizer_core/blob/main/LICENSE)
[![Coverage](https://img.shields.io/codecov/c/github/kobolcs/robot_optimizer_core)](https://codecov.io/gh/kobolcs/robot_optimizer_core)
[![Documentation](https://img.shields.io/badge/docs-mkdocs-blue)](https://kobolcs.github.io/robot_optimizer_core)
[![CI](https://github.com/kobolcs/robot_optimizer_core/actions/workflows/ci.yml/badge.svg)](https://github.com/kobolcs/robot_optimizer_core/actions/workflows/ci.yml)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/kobolcs/robot_optimizer_core/main.svg)](https://results.pre-commit.ci/latest/github/kobolcs/robot_optimizer_core/main)

Core analysis engine for Robot Framework test suite optimization. This package provides the foundation for analyzing Robot Framework test suites and identifying optimization opportunities.

## 🚀 Features

- **Dead Code Detection**: Find unused keywords and duplicate definitions
- **Sleep Pattern Analysis**: Identify slow Sleep usage that should be replaced with proper waits
- **Flakiness Detection**: Detect tests that fail intermittently
- **Extensible Architecture**: Plugin system for custom analyzers
- **Type-Safe**: Full type hints and Pydantic v2 models
- **Python 3.11+**: Compatible with Python 3.11, 3.12, and 3.13
- **High Quality**: Comprehensive test coverage with property-based testing

## 📦 Installation

**Requirements:** Python 3.11+

```bash
pip install robot-framework-optimizer-core
```

### With uv

```bash
uv add robot-framework-optimizer-core
```

### With pipx (CLI only)

```bash
pipx install robot-framework-optimizer-core
robot-optimizer --version
```

### With conda / mamba

```bash
# Install from conda-forge (once available) or fall back to pip:
conda run pip install robot-framework-optimizer-core
```

## 🎯 Quick Start

### Basic Usage

```bash
robot-optimizer analyze tests/
```

### Try the demo suite

```bash
robot-optimizer analyze examples/bad_robot_suite --format text --no-fail
robot-optimizer analyze examples/bad_robot_suite --format json --no-fail
```

Expected findings include Sleep usage, unused or duplicate keywords, hardcoded URLs/localhost values, and naming/documentation/tag consistency issues across suites and resources.

```python
from robot_optimizer_core import analyze_file, analyze_directory

# Analyze a single file
findings = analyze_file("tests/login.robot")
for finding in findings:
    print(f"{finding.severity.name}: {finding.message}")

# Analyze a directory
results = analyze_directory("tests/", recursive=True)
for file_path, findings in results.items():
    print(f"{file_path}: {len(findings)} issues found")
```

### Using Specific Analyzers

```python
from robot_optimizer_core import TestFile, DeadCodeAnalyzer, SleepDetector

# Load a test file
test_file = TestFile.from_path("tests/suite.robot")

# Run specific analyzers
dead_code_analyzer = DeadCodeAnalyzer()
findings = dead_code_analyzer.analyze(test_file)

sleep_detector = SleepDetector()
sleep_findings = sleep_detector.analyze(test_file)
```

### Custom Configuration

```python
from robot_optimizer_core import Settings, analyze_file

# Configure settings
settings = Settings(
    max_file_size_mb=20.0,
    max_acceptable_sleep_seconds=0.5,
    exclude_patterns=["**/generated/*", "**/temp/*"]
)

# Use custom settings
findings = analyze_file("test.robot", settings=settings)
```

## 🏗️ Architecture

The Core package follows Domain-Driven Design principles:

```
┌─────────────────────────────────────────┐
│          High-Level API                 │
│   (analyze_file, analyze_directory)     │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────┴───────────────────────┐
│           Analyzers                     │
│  (DeadCode, Sleep, Flakiness, Custom)  │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────┴───────────────────────┐
│         Domain Models                   │
│  (TestFile, Finding, Pattern, Location) │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────┴───────────────────────┐
│        Infrastructure                   │
│  (Parser, Discovery, Repositories)      │
└─────────────────────────────────────────┘
```

## 🔌 Plugin System

Create custom analyzers by extending the base analyzer:

```python
from robot_optimizer_core import BaseAnalyzer, Finding, Pattern, TestFile, register_analyzer

class MyCustomAnalyzer(BaseAnalyzer):
    @property
    def name(self) -> str:
        return "custom_analyzer"

    @property
    def description(self) -> str:
        return "My custom analysis rules"

    @property
    def tags(self) -> list[str]:
        return ["custom", "quality"]

    def analyze(self, test_file: TestFile) -> list[Finding]:
        findings = []
        # Your analysis logic here
        return findings

# Register the analyzer
register_analyzer("custom", MyCustomAnalyzer)
```

## 🎨 Domain Models

### Core Value Objects

- **Finding**: Represents an issue found in the code
- **Location**: File location with line and column information
- **Pattern**: Type of issue detected
- **Severity**: ERROR, WARNING, or INFO

### Example

```python
from robot_optimizer_core import Finding, Location, Pattern, Severity
from pathlib import Path

finding = Finding.create(
    pattern=Pattern.sleep_in_test("5 seconds"),
    severity=Severity.WARNING,
    location=Location(Path("test.robot"), line=42),
    message="Sleep makes tests slow and fragile",
    duration="5",
    unit="seconds"
)
```

## ⚙️ Configuration

Configure via environment variables or code:

```bash
# Environment variables
export ROBOT_OPTIMIZER_MAX_FILE_SIZE_MB=10
export ROBOT_OPTIMIZER_LOG_LEVEL=DEBUG
export ROBOT_OPTIMIZER_ENABLE_METRICS=true
```

```python
# In code
from robot_optimizer_core import Settings

settings = Settings(
    max_file_size_mb=10,
    log_level="DEBUG",
    enable_metrics=True
)
```

## 📊 Metrics and Logging

The Core package includes GDPR-compliant metrics collection and structured logging:

```python
from robot_optimizer_core import get_logger, get_metrics

# Structured logging
logger = get_logger(__name__)
logger.info("Analysis started", extra={"file": "test.robot"})

# Metrics collection
metrics = get_metrics()
with metrics.timer("analysis.duration"):
    findings = analyze_file("test.robot")
```

## 🧪 Testing

The Core package enforces an 80%+ coverage gate in CI:

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests with coverage
pytest

# Run mutation testing
mutmut run

# Run specific test types
pytest -m unit        # Fast unit tests
pytest -m integration # Integration tests
pytest -m component   # End-to-end tests
```

## 📚 Documentation

Full documentation is available at [https://kobolcs.github.io/robot_optimizer_core](https://kobolcs.github.io/robot_optimizer_core)

To build docs locally:

```bash
pip install -e ".[docs]"
mkdocs serve
```


## 🔐 Security

If you discover a vulnerability, please follow our private disclosure process in [SECURITY.md](SECURITY.md).

## 🗺️ Roadmap

See [ROADMAP.md](ROADMAP.md) for always-free core features, upcoming community work, and Pro previews.

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/kobolcs/robot_optimizer_core.git
cd robot_optimizer_core

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install in development mode
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Robot Framework community for the excellent testing framework
- Contributors and users of Robot Framework Optimizer

## 🔗 Related Projects

- [robot-framework-optimizer](https://github.com/kobolcs/robot_optimizer_core) - Free CLI tool
- [robot-framework-optimizer-pro](https://github.com/kobolcs/robot_optimizer_core) - Professional edition with advanced features

---

Made with ❤️ by the Robot Framework Optimizer Team