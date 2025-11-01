# Plugins API Reference

Complete reference for the plugin system.

## Plugin Base Class

### Plugin

Abstract base class for all plugins.

```python
from robot_optimizer_core import Plugin, PluginMetadata
from typing import override

class MyPlugin(Plugin):
    @property
    @override
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my-plugin",
            version="1.0.0",
            description="My custom plugin",
            author="Your Name"
        )

    @override
    def activate(self) -> None:
        """Called when plugin is loaded."""
        from robot_optimizer_core import register_analyzer
        register_analyzer("my_analyzer", MyAnalyzer)

    @override
    def deactivate(self) -> None:
        """Called when plugin is unloaded."""
        # Cleanup resources
        pass
```

### PluginMetadata

Plugin metadata information.

```python
from robot_optimizer_core import PluginMetadata

metadata = PluginMetadata(
    name="my-plugin",
    version="1.0.0",
    description="Plugin description",
    author="Author Name"
)
```

**Fields:**
- `name: str` - Plugin name (alphanumeric, hyphens)
- `version: str` - Semantic version
- `description: str` - Human-readable description
- `author: str` - Author name

## Plugin Manager

### SecurePluginManager

Manages plugin loading with security validation.

```python
from robot_optimizer_core.plugin import SecurePluginManager
from pathlib import Path

manager = SecurePluginManager()

# Load plugin from file
manager.load_plugin_from_file(Path("my_plugin.py"))

# Add trusted plugin hash (skip validation)
manager.add_trusted_plugin_hash("sha256_hash_here")

# Unload plugin
manager.unload_plugin("my-plugin")
```

**Methods:**

#### `load_plugin_from_file(file_path: Path, force: bool = False)`

Load a plugin from a Python file.

**Parameters:**
- `file_path`: Path to plugin file
- `force`: Skip security validation (NOT RECOMMENDED)

**Raises:**
- `PluginError`: If plugin fails validation or loading

#### `add_trusted_plugin_hash(file_hash: str)`

Add a trusted plugin SHA-256 hash.

**Parameters:**
- `file_hash`: SHA-256 hash of trusted plugin file

#### `unload_plugin(name: str)`

Unload a plugin by name.

**Parameters:**
- `name`: Plugin name from metadata

## Security

### PluginSecurityValidator

Validates plugin code for security issues.

```python
from robot_optimizer_core.plugin import PluginSecurityValidator
from pathlib import Path

validator = PluginSecurityValidator()
is_safe, violations = validator.validate_file(Path("plugin.py"))

if not is_safe:
    print("Security violations:")
    for violation in violations:
        print(f"  - {violation}")
```

**Validation Checks:**
- Allowed imports only
- No dangerous function calls (`eval`, `exec`, etc.)
- No file system operations
- No network access
- No subprocess execution
- File permissions check

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

- `eval()`, `exec()`, `compile()`
- `__import__()`
- `open()`, file I/O
- `os`, `sys`, `subprocess`
- `socket`, `urllib`, `requests`
- Access to `__dict__`, `__globals__`, `__builtins__`

## Plugin Registry

### get_plugin_registry()

Get the global plugin registry instance.

```python
from robot_optimizer_core.plugin import get_plugin_registry

registry = get_plugin_registry()

# Register plugin class
registry.register("my-plugin", MyPlugin)

# Get plugin class
plugin_class = registry.get("my-plugin")

# List all plugins
plugin_names = registry.list()
```

## Example Plugin

Complete working example:

```python
# my_plugin.py
from robot_optimizer_core import (
    Plugin,
    PluginMetadata,
    BaseAnalyzer,
    TestFile,
    Finding,
    Pattern,
    Severity,
    Location
)
from typing import override

class MyAnalyzer(BaseAnalyzer):
    @property
    @override
    def name(self) -> str:
        return "my_analyzer"

    @property
    @override
    def description(self) -> str:
        return "Custom analyzer from plugin"

    @property
    @override
    def tags(self) -> list[str]:
        return ["custom"]

    @override
    def analyze(self, test_file: TestFile) -> list[Finding]:
        # Analysis logic
        return []

class MyPlugin(Plugin):
    @property
    @override
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my-plugin",
            version="1.0.0",
            description="Example plugin",
            author="Developer"
        )

    @override
    def activate(self) -> None:
        from robot_optimizer_core import register_analyzer
        register_analyzer("my_analyzer", MyAnalyzer)

    @override
    def deactivate(self) -> None:
        pass
```

## Distribution

### Package Structure

```
my-plugin/
├── src/
│   └── my_plugin/
│       ├── __init__.py
│       ├── analyzers.py
│       └── plugin.py
├── tests/
│   └── test_plugin.py
├── pyproject.toml
├── README.md
└── LICENSE
```

### pyproject.toml

```toml
[project]
name = "robot-optimizer-my-plugin"
version = "1.0.0"
dependencies = [
    "robot-framework-optimizer-core>=1.0.0"
]

[project.entry-points."robot_optimizer_core.plugins"]
my_plugin = "my_plugin.plugin:MyPlugin"
```

## See Also

- [Extending Guide](../extending.md) - How to create plugins
- [Analyzers API](analyzers.md) - Analyzer framework
- [Security Best Practices](../extending.md#plugin-security)
