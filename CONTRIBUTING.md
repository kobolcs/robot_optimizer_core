# Contributing to robot_optimizer_core

Welcome! This guide explains how to contribute to `robot_optimizer_core` — including how to write a custom analyzer, run the test suite, and get your changes merged.

---

## Table of Contents

1. [Development Setup](#development-setup)
2. [How to Write a Custom Analyzer](#how-to-write-a-custom-analyzer)
   - [The `BaseAnalyzer` Contract](#the-baseanalyzer-contract)
   - [Lifecycle Hooks](#lifecycle-hooks)
   - [Configuration](#configuration)
   - [Security Requirements for Plugins](#security-requirements-for-plugins)
   - [Registering via Entry Points](#registering-via-entry-points)
3. [Running Tests](#running-tests)
4. [Coding Standards](#coding-standards)
5. [Pull Request Checklist](#pull-request-checklist)

---

## Development Setup

```bash
# Clone the repo
git clone https://github.com/kobolcs/robot_optimizer_core.git
cd robot_optimizer_core

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e ".[dev]"
```

Run the full test suite:

```bash
uv run pytest -q
```

---

## How to Write a Custom Analyzer

Custom analyzers extend the `BaseAnalyzer` abstract class and are
discovered automatically via Python entry points.

### The `BaseAnalyzer` Contract

Every analyzer must implement the following interface:

```python
from robot_optimizer_core.analyzers.base import BaseAnalyzer
from robot_optimizer_core.domain.entities import TestFile
from robot_optimizer_core.domain.value_objects import Finding

class MyAnalyzer(BaseAnalyzer):
    """One-line description shown in robot-optimizer list-analyzers."""

    @property
    def name(self) -> str:
        """Unique snake_case identifier, e.g. 'my_analyzer'."""
        return "my_analyzer"

    @property
    def description(self) -> str:
        """Human-readable description shown in list output."""
        return "Detects <problem> in Robot Framework files."

    @property
    def tags(self) -> list[str]:
        """Free-form tags for discovery and filtering."""
        return ["quality", "naming"]

    @property
    def supports_auto_fix(self) -> bool:
        """Return True only when the analyzer can emit auto-fixable findings."""
        return False

    def analyze(self, test_file: TestFile) -> list[Finding]:
        """Main analysis entry point.

        Iterate the file content, detect the pattern, and return
        a list of :class:`Finding` value objects.
        Never raise — return an empty list on unexpected input.
        """
        findings = []
        for line_num, line in enumerate(test_file.content.splitlines(), 1):
            if "TODO" in line:
                from robot_optimizer_core.domain.value_objects import (
                    Finding, Location, Pattern, PatternType, Severity
                )
                pattern = Pattern(
                    type=PatternType.HARDCODED_VALUE,
                    name="TODO Comment",
                    description="TODO left in test file",
                    recommendation="Resolve the TODO before committing",
                    documentation_url=None,
                    auto_fixable=False,
                )
                findings.append(Finding.create(
                    pattern=pattern,
                    severity=Severity.INFO,
                    location=Location(file_path=test_file.path, line=line_num),
                    message="TODO comment found",
                ))
        return findings
```

### Lifecycle Hooks

`BaseAnalyzer` exposes three optional hooks that are called around `analyze()`:

| Method | When called | Typical use |
|--------|-------------|-------------|
| `validate_config()` | After `__init__`, before any analysis | Raise `ConfigurationError` on bad config values |
| `pre_analyze(test_file)` | Before `analyze()` | Reset per-file state |
| `post_analyze(findings, test_file)` | After `analyze()` | Log summaries, metrics |

Example:

```python
def validate_config(self) -> None:
    threshold = self.get_config_value("threshold", 0.5)
    if not (0 < threshold <= 1):
        raise ConfigurationError(
            "threshold must be between 0 and 1",
            config_key="threshold",
        )

def pre_analyze(self, test_file: TestFile) -> None:
    self._seen_names: set[str] = set()

def post_analyze(self, findings: list[Finding], test_file: TestFile) -> None:
    self._logger.info(f"Found {len(findings)} issues in {test_file.path.name}")
```

### Configuration

Configuration is passed as a `dict[str, Any]` to the constructor, or read
from the global `Settings.analyzer_config` dict:

```toml
# robot.toml
[tool.robot-optimizer.analyzer_config.my_analyzer]
threshold = 0.8
strict = true
```

Retrieve values inside your analyzer with:

```python
threshold = self.get_config_value("threshold", default=0.5)
```

### Security Requirements for Plugins

Third-party analyzers are loaded via Python entry points and run **inside the
user's process with full permissions**.  Follow these rules:

1. **No network access** — analyzers must work offline; never make HTTP
   requests to external services.
2. **No file writes** — analyzers are read-only; never write to the file
   system inside `analyze()`.
3. **No `eval` / `exec`** — never execute arbitrary code from analyzed files.
4. **Handle exceptions gracefully** — catch all exceptions inside `analyze()`
   and return an empty list (or a partial list) rather than propagating.
5. **Declare `requires_external_repo = True`** on the class when your analyzer
   needs a `TestResultRepository` — this prevents the default
   `analyze_file()` flow from failing when no repository is configured.

### Registering via Entry Points

Declare your analyzer in `pyproject.toml`:

```toml
[project.entry-points."robot_optimizer_core.analyzers"]
my_analyzer = "my_package.my_module:MyAnalyzer"
```

After `pip install -e .`, the analyzer will appear in:

```bash
robot-optimizer list-analyzers
```

And be available by name:

```python
from robot_optimizer_core import analyze_file

findings = analyze_file("tests/login.robot", analyzers=["my_analyzer"])
```

---

## Running Tests

```bash
# All tests
uv run pytest -q

# Only unit tests (fast)
uv run pytest -q -m unit

# With coverage
uv run pytest --cov=robot_optimizer_core --cov-report=term-missing

# Property-based tests (Hypothesis)
uv run pytest tests/unit/analyzers/test_dead_code_property.py -v

# Mutation testing
uv run mutmut run
uv run mutmut results
```

---

## Coding Standards

- Python ≥ 3.11, type-annotated throughout (`from __future__ import annotations`).
- Pydantic v2 for domain value objects and entities.
- `ruff` for linting and formatting; `mypy` for static type checking.
- Every public symbol must have a docstring.
- New analyzers must ship with unit tests covering at least the happy path and
  one edge case.

---

## Pull Request Checklist

- [ ] `uv run pytest -q` passes with coverage ≥ 80 %
- [ ] New code is type-annotated and passes `mypy`
- [ ] New analyzers are registered in `src/robot_optimizer_core/analyzers/__init__.py`
- [ ] `CHANGELOG.md` updated with a short entry
- [ ] PR title follows [Conventional Commits](https://www.conventionalcommits.org/)

---

*This guide is linked from the [MkDocs site](docs/extending.md) and the
[README](README.md#contributing).*
