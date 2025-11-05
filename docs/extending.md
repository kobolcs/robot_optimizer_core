# Extending Robot Framework Optimizer Core

This guide shows you how to create custom analyzers and plugins for Robot Framework Optimizer Core.

## Creating Custom Analyzers

### Basic Analyzer

Create a custom analyzer by inheriting from `BaseAnalyzer`:

```python
from robot_optimizer_core import BaseAnalyzer, TestFile, Finding, Location, Pattern, Severity

# Import override decorator (compatible with Python 3.11+)
try:
    from typing import override
except ImportError:
    from typing_extensions import override

class CustomAnalyzer(BaseAnalyzer):
    """Example custom analyzer."""

    @property
    @override
    def name(self) -> str:
        """Unique analyzer name."""
        return "custom"

    @property
    @override
    def description(self) -> str:
        """Human-readable description."""
        return "Detects custom issues in Robot Framework files"

    @property
    @override
    def tags(self) -> list[str]:
        """Tags for categorization."""
        return ["custom", "quality"]

    @override
    def analyze(self, test_file: TestFile) -> list[Finding]:
        """Analyze a test file and return findings."""
        findings = []

        # Your analysis logic here
        lines = test_file.content.splitlines()
        for line_num, line in enumerate(lines, 1):
            if "FIXME" in line:
                from robot_optimizer_core.domain.value_objects import PatternType
                finding = Finding(
                    pattern=Pattern(
                        type=PatternType.CUSTOM,
                        name="fixme_comment",
                        description="FIXME comment detected"
                    ),
                    severity=Severity.INFO,
                    location=Location(file_path=test_file.path, line_number=line_num),
                    message=f"FIXME comment found: {line.strip()}",
                    context={"text": line.strip()}
                )
                findings.append(finding)

        return findings
```

### Register and Use

```python
from robot_optimizer_core import register_analyzer

# Register your analyzer
register_analyzer("custom", CustomAnalyzer)

# Now it can be used
from robot_optimizer_core import get_analyzer

analyzer = get_analyzer("custom")
findings = analyzer.analyze(test_file)
```

## Advanced Analyzer Features

### Configurable Analyzer

```python
class ConfigurableAnalyzer(BaseAnalyzer):
    def __init__(self, config: dict | None = None):
        super().__init__(config)
        # Get config values with defaults
        self.max_length = self.get_config_value("max_length", 100)
        self.check_keywords = self.get_config_value("check_keywords", True)

    @override
    def validate_config(self) -> None:
        """Validate configuration."""
        if self.max_length < 1:
            raise ConfigurationError("max_length must be positive")

# Use with custom config
analyzer = ConfigurableAnalyzer(config={
    "max_length": 120,
    "check_keywords": False
})
```

### Auto-Fixable Patterns

```python
@override
def analyze(self, test_file: TestFile) -> list[Finding]:
    findings = []

    for line_num, line in enumerate(test_file.content.splitlines(), 1):
        if "Sleep    " in line:
            # Extract sleep duration
            match = re.search(r'Sleep\s+(\d+(?:\.\d+)?)', line)
            if match:
                duration = float(match.group(1))

                # Create auto-fixable pattern
                pattern = Pattern(
                    type="sleep_usage",
                    details={"duration": duration},
                    auto_fixable=True,
                    suggested_fix=f"Replace with 'Wait Until Element Is Visible'"
                )

                finding = Finding.create(
                    pattern=pattern,
                    severity=Severity.WARNING,
                    location=Location(test_file.path, line_num),
                    message=f"Sleep detected ({duration}s), consider using explicit wait"
                )
                findings.append(finding)

    return findings
```

## Creating Plugins

Plugins allow you to package multiple analyzers and distribute them independently.

### Plugin Structure

```python
from robot_optimizer_core import Plugin, PluginMetadata, BaseAnalyzer
from typing import override

class MyCustomAnalyzer(BaseAnalyzer):
    @property
    @override
    def name(self) -> str:
        return "my_custom"

    @property
    @override
    def description(self) -> str:
        return "My custom analyzer"

    @override
    def analyze(self, test_file):
        # Analysis logic
        return []

class MyPlugin(Plugin):
    @property
    @override
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my-custom-plugin",
            version="1.0.0",
            description="Custom analyzers for my project",
            author="Your Name"
        )

    @override
    def activate(self) -> None:
        """Called when plugin is loaded."""
        from robot_optimizer_core import register_analyzer
        register_analyzer("my_custom", MyCustomAnalyzer)

    @override
    def deactivate(self) -> None:
        """Called when plugin is unloaded."""
        # Cleanup if needed
        pass
```

### Load Plugin

```python
from robot_optimizer_core.plugin import SecurePluginManager

manager = SecurePluginManager()

# Load plugin from file
manager.load_plugin_from_file("path/to/my_plugin.py")

# Now use the analyzer
from robot_optimizer_core import get_analyzer

analyzer = get_analyzer("my_custom")
```

## Real-World Examples

### Example 1: Keyword Complexity Analyzer

```python
class KeywordComplexityAnalyzer(BaseAnalyzer):
    """Detects overly complex keywords."""

    @override
    def analyze(self, test_file: TestFile) -> list[Finding]:
        findings = []

        # Parse the file
        from robot_optimizer_core import RobotASTParser
        parser = RobotASTParser()
        ast = parser.parse(test_file.content)

        for keyword in ast.keywords:
            step_count = len(keyword.steps)

            if step_count > 20:
                finding = Finding.create(
                    pattern=Pattern(
                        type="complex_keyword",
                        details={"step_count": step_count}
                    ),
                    severity=Severity.WARNING,
                    location=Location(test_file.path, keyword.lineno),
                    message=f"Keyword '{keyword.name}' has {step_count} steps (max recommended: 20)"
                )
                findings.append(finding)

        return findings
```

### Example 2: Naming Convention Checker

```python
import re

class NamingConventionAnalyzer(BaseAnalyzer):
    """Checks Robot Framework naming conventions."""

    @override
    def analyze(self, test_file: TestFile) -> list[Finding]:
        findings = []

        lines = test_file.content.splitlines()
        in_keywords = False

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            # Check if we're in keywords section
            if stripped.startswith("***") and "keyword" in stripped.lower():
                in_keywords = True
                continue
            elif stripped.startswith("***"):
                in_keywords = False
                continue

            if in_keywords and stripped and not stripped.startswith("#"):
                # Check if line starts keyword (not indented)
                if not line.startswith(" ") and not line.startswith("\t"):
                    keyword_name = stripped

                    # Check naming convention (Title Case With Spaces)
                    if not re.match(r'^[A-Z][a-z]*( [A-Z][a-z]*)*$', keyword_name):
                        finding = Finding.create(
                            pattern=Pattern(
                                type="naming_convention",
                                details={"keyword": keyword_name}
                            ),
                            severity=Severity.INFO,
                            location=Location(test_file.path, line_num),
                            message=f"Keyword '{keyword_name}' doesn't follow Title Case convention"
                        )
                        findings.append(finding)

        return findings
```

## Best Practices

### 1. Use Proper Severity Levels

- **ERROR**: Issues that will cause test failures or incorrect results
- **WARNING**: Issues that reduce reliability or maintainability
- **INFO**: Suggestions and style improvements

### 2. Provide Actionable Messages

```python
# L Bad
message = "Issue found"

#  Good
message = f"Keyword '{keyword_name}' has {count} steps. Consider splitting into smaller keywords (max recommended: 20)"
```

### 3. Add Context

```python
finding = Finding.create(
    pattern=pattern,
    severity=severity,
    location=location,
    message=message,
    keyword_name=keyword_name,  # Extra context
    actual_value=actual,
    expected_value=expected
)
```

### 4. Make Patterns Auto-Fixable When Possible

```python
pattern = Pattern(
    type="sleep_usage",
    auto_fixable=True,
    suggested_fix="Wait Until Element Is Visible    id=element"
)
```

### 5. Validate Configuration

```python
@override
def validate_config(self) -> None:
    """Validate analyzer configuration."""
    max_value = self.get_config_value("max_value")

    if max_value is not None and max_value < 0:
        raise ConfigurationError("max_value must be non-negative")
```

## Testing Custom Analyzers

```python
import pytest
from robot_optimizer_core import TestFile, Severity

def test_custom_analyzer():
    # Create test file
    content = '''*** Keywords ***
Login User
    Sleep    2s
    Input Text    username    admin
'''

    test_file = TestFile(
        path=Path("test.robot"),
        content=content
    )

    # Run analyzer
    analyzer = CustomAnalyzer()
    findings = analyzer.analyze(test_file)

    # Assertions
    assert len(findings) > 0
    assert any(f.severity == Severity.WARNING for f in findings)
    assert any("Sleep" in f.message for f in findings)
```

## Plugin Security

The plugin system includes security validation:

### Allowed Imports

Plugins can only import from:
- `robot_optimizer_core`
- `pathlib`
- `typing`
- `dataclasses`
- `enum`
- `abc`
- `collections`

### Forbidden Operations

- No `eval()`, `exec()`, or `compile()`
- No file system operations (`open()`, file I/O)
- No network access
- No subprocess execution
- No access to `__dict__`, `__globals__`, etc.

### Security Best Practices

```python
#  Safe plugin
class SafePlugin(Plugin):
    def activate(self):
        register_analyzer("safe", SafeAnalyzer)

# L Unsafe - will be rejected
class UnsafePlugin(Plugin):
    def activate(self):
        import os  # Forbidden
        os.system("rm -rf /")  # Will never execute
```

## Packaging and Distribution

### Package Structure

```
my-optimizer-plugin/
   src/
      my_optimizer_plugin/
          __init__.py
          analyzers.py
          plugin.py
   tests/
      test_analyzers.py
   pyproject.toml
   README.md
```

### pyproject.toml

```toml
[project]
name = "my-optimizer-plugin"
version = "1.0.0"
dependencies = [
    "robot-framework-optimizer-core>=1.0.0"
]
```

### Distribution

```bash
python -m build
python -m twine upload dist/*
```

## Next Steps

- See [API Reference](api/analyzers.md) for complete analyzer API
- Check [API Plugins](api/plugins.md) for plugin system details
- Review built-in analyzers source code for examples

## Getting Help

- **Issues**: [Report bugs or request features](https://github.com/rf-optimizer/robot-framework-optimizer-core/issues)
- **Discussions**: [Ask questions](https://github.com/rf-optimizer/robot-framework-optimizer-core/discussions)
