# Getting Started

This guide will help you get started with Robot Framework Optimizer Core quickly.

## Installation

### Requirements

- **Python 3.13+** (Required)
- **Robot Framework 7.1+** (Optional, for parsing)

### Install from PyPI

```bash
pip install robot-framework-optimizer-core
```

### Install from Source

```bash
git clone https://github.com/rf-optimizer/robot-framework-optimizer-core.git
cd robot-framework-optimizer-core
pip install -e ".[dev]"
```

### Verify Installation

```python
import robot_optimizer_core
print(robot_optimizer_core.__version__)
```

## Basic Usage

### 1. Analyze a Single File

The simplest way to analyze a Robot Framework file:

```python
from robot_optimizer_core import analyze_file
from pathlib import Path

# Analyze a file
findings = analyze_file(Path("tests/login.robot"))

# Print results
for finding in findings:
    print(f"{finding.severity.name}: {finding.message}")
    print(f"  File: {finding.location.file_path}")
    print(f"  Line: {finding.location.line_number}")
    print(f"  Pattern: {finding.pattern.type}")
    print()
```

**Output:**
```
WARNING: Sleep usage detected (2.0s)
  File: tests/login.robot
  Line: 34
  Pattern: sleep_in_test

ERROR: Duplicate keyword definition 'Login User'
  File: tests/login.robot
  Line: 45
  Pattern: duplicate_keyword
```

### 2. Analyze a Directory

Analyze all Robot Framework files in a directory:

```python
from robot_optimizer_core import analyze_directory
from pathlib import Path

# Analyze directory recursively
results = analyze_directory(
    Path("tests/"),
    recursive=True,
    patterns=["*.robot", "*.resource"]
)

# Print summary
total_findings = 0
for file_path, findings in results.items():
    if findings:
        print(f"\n{file_path}:")
        for finding in findings:
            print(f"  {finding.severity.name}: {finding.message}")
        total_findings += len(findings)

print(f"\nTotal issues found: {total_findings}")
```

### 3. Filter by Severity

Only show errors and warnings:

```python
from robot_optimizer_core import analyze_file, Severity

findings = analyze_file("tests/suite.robot")

# Filter by severity
errors = [f for f in findings if f.severity == Severity.ERROR]
warnings = [f for f in findings if f.severity == Severity.WARNING]

print(f"Errors: {len(errors)}")
print(f"Warnings: {len(warnings)}")

# Show only critical issues
critical = [f for f in findings if f.severity in [Severity.ERROR, Severity.WARNING]]
for finding in critical:
    print(f"{finding.severity.name}: {finding.message}")
```

## Working with Analyzers

### Using Specific Analyzers

Instead of running all analyzers, use specific ones:

```python
from robot_optimizer_core import TestFile, DeadCodeAnalyzer, SleepDetector

# Load test file
test_file = TestFile.from_path("tests/suite.robot")

# Run dead code analyzer
dead_code_analyzer = DeadCodeAnalyzer()
dead_code_findings = dead_code_analyzer.analyze(test_file)

# Run sleep detector
sleep_detector = SleepDetector()
sleep_findings = sleep_detector.analyze(test_file)

print(f"Dead code issues: {len(dead_code_findings)}")
print(f"Sleep issues: {len(sleep_findings)}")
```

### Configure Analyzers

Pass configuration to analyzers:

```python
from robot_optimizer_core import SleepDetector

# Custom configuration
sleep_detector = SleepDetector(config={
    "max_acceptable_sleep_seconds": 0.5,  # Stricter than default (1.0)
    "check_keyword_sleeps": True,
    "suggest_alternatives": True
})

findings = sleep_detector.analyze(test_file)
```

### List Available Analyzers

```python
from robot_optimizer_core import list_analyzers

# Get all registered analyzers
analyzers = list_analyzers()

for name, analyzer_class in analyzers.items():
    analyzer = analyzer_class()
    print(f"{name}: {analyzer.description}")
    print(f"  Tags: {', '.join(analyzer.tags)}")
    print()
```

## Configuration

### Using Settings Object

```python
from robot_optimizer_core import Settings, analyze_file

# Create custom settings
settings = Settings(
    max_file_size_mb=20.0,
    max_acceptable_sleep_seconds=0.5,
    file_patterns=["*.robot", "*.resource"],
    exclude_patterns=[
        "**/build/**",
        "**/generated/**",
        "**/.git/**"
    ],
    enable_metrics=True,
    log_level="INFO"
)

# Use in analysis
findings = analyze_file("test.robot", settings=settings)
```

### Environment Variables

Set configuration via environment variables:

```bash
export ROBOT_OPTIMIZER_MAX_FILE_SIZE_MB=20.0
export ROBOT_OPTIMIZER_LOG_LEVEL=DEBUG
export ROBOT_OPTIMIZER_ENABLE_METRICS=true
```

```python
from robot_optimizer_core import get_settings

# Settings automatically loaded from environment
settings = get_settings()
print(f"Log level: {settings.log_level}")
print(f"Max file size: {settings.max_file_size_mb}MB")
```

### Configuration File

Create `.env` file:

```ini
# File handling
ROBOT_OPTIMIZER_MAX_FILE_SIZE_MB=20.0
ROBOT_OPTIMIZER_FILE_PATTERNS=*.robot,*.resource

# Analysis settings
ROBOT_OPTIMIZER_MAX_ACCEPTABLE_SLEEP_SECONDS=0.5
ROBOT_OPTIMIZER_MAX_LINE_LENGTH=120

# System settings
ROBOT_OPTIMIZER_ENABLE_METRICS=false
ROBOT_OPTIMIZER_LOG_LEVEL=INFO
ROBOT_OPTIMIZER_LOG_FORMAT_JSON=false
```

The library will automatically load from `.env` in the current directory.

## Working with Findings

### Finding Structure

Each finding has:

```python
from robot_optimizer_core import analyze_file

findings = analyze_file("test.robot")

for finding in findings:
    # Basic info
    print(f"Message: {finding.message}")
    print(f"Severity: {finding.severity}")  # ERROR, WARNING, or INFO

    # Location
    print(f"File: {finding.location.file_path}")
    print(f"Line: {finding.location.line_number}")
    print(f"Column: {finding.location.column_number}")

    # Pattern info
    print(f"Pattern: {finding.pattern.type}")
    print(f"Details: {finding.pattern.details}")

    # Context (optional)
    if finding.context:
        print(f"Context: {finding.context}")
```

### Group Findings by File

```python
from collections import defaultdict

findings = analyze_file("test.robot")

# Group by file
by_file = defaultdict(list)
for finding in findings:
    by_file[finding.location.file_path].append(finding)

# Print grouped
for file_path, file_findings in by_file.items():
    print(f"\n{file_path} ({len(file_findings)} issues):")
    for f in file_findings:
        print(f"  Line {f.location.line_number}: {f.message}")
```

## Next Steps

- **[Extending](extending.md)** - Learn how to create custom analyzers
- **[API Reference](api/)** - Detailed API documentation

## Getting Help

- **Documentation**: [https://rf-optimizer.github.io/robot-framework-optimizer-core](https://rf-optimizer.github.io/robot-framework-optimizer-core)
- **Issues**: [https://github.com/rf-optimizer/robot-framework-optimizer-core/issues](https://github.com/rf-optimizer/robot-framework-optimizer-core/issues)
