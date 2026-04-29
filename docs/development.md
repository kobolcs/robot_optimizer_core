# Development Guide

## Local setup

See the [Installation and Upgrade Guide](install.md) for contributor setup paths using pip, pipx, uv, and source checkouts.

## Contributor environment setup

For full contributor setup (including docs build tooling):

```bash
uv sync --extra dev
uv run mkdocs build --strict
```

For documentation-only setup:

```bash
uv sync --extra docs
uv run mkdocs build --strict
```

If you intentionally want both extras:

```bash
uv sync --extra dev --extra docs
```

## Dependency lockfile policy

This repository does not track `uv.lock` because it is a reusable Python library/CLI. `pyproject.toml` is the dependency source of truth. Contributors may use uv locally, but generated lockfile changes should not be committed.

## Quality gates

```bash
tox -e lint,type,build
tox -e py
```

## Code style

- Code should follow the project Ruff/mypy configuration.
- Public modules, public classes, and public functions should use Google-style Python docstrings.
- Internal helpers should have docstrings when behavior is non-obvious.
- Keep comments about why code exists, not historical task numbers.
- Prefer typed return values and explicit domain types.
- Keep CLI thin; move reporting/business logic into dedicated modules.

## Google-style docstring examples

Function:

```python
def analyze_file(path: Path) -> list[Finding]:
    """Analyze a Robot Framework file and return findings.

    Args:
        path: Path to a Robot Framework .robot or .resource file.

    Returns:
        Findings detected by the configured analyzers.

    Raises:
        AnalysisError: If the file cannot be loaded or analyzed.
    """
```

Class:

```python
class SleepDetector(BaseAnalyzer):
    """Detects fixed Sleep keyword usage in Robot Framework suites.

    The analyzer reports Sleep calls that may increase execution time or
    introduce flakiness when explicit waits would be safer.
    """
```

## Documentation generation

Developer/API documentation is generated from typed code and docstrings using mkdocstrings.

- Google-style docstrings are required for public API documentation.
- Avoid implementation-history comments.
- Keep examples short and executable where practical.
- Adopt docstring improvements incrementally: pilot on visible public APIs first, then expand as modules are touched.
