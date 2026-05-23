# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0] - 2026-05-23

### Breaking Changes

- **`analyze_file()` now returns `FileAnalysisResult`** instead of `list[Finding]`.
  `FileAnalysisResult` is iterable and length-aware (`for f in result` / `len(result)` still work),
  but `isinstance(result, list)` is now `False`.
- **JSON CLI output** changed from a bare array to `{"schema_version": "1", "findings": [...]}`.
  Callers that do `json.loads(out)[0]` must switch to `json.loads(out)["findings"][0]`.
- **`analyze_file()` `severity_filter` parameter removed** (was deprecated).
- **`analyze_directory()` `fail_fast` parameter removed** (was deprecated).
  Use `error_handling="raise"` instead; it collects all file errors and raises `ExceptionGroup`.
- **`Finding.to_dict()` output** now includes `schema_version`, `fingerprint`, `confidence`,
  `tags`, and `remediation` keys.
- **`exceptions.py`**: every exception's `__str__()` now always includes a `[CODE]` prefix.

### Added

- `FileAnalysisResult` dataclass: wraps `list[Finding]` + `AnalysisMeta`; drop-in iterable
  replacement for the old bare list returned by `analyze_file()`.
- `AnalysisMeta` dataclass: `schema_version`, `duration_ms`, `analyzer_names`,
  `cache_hits`, `cache_misses`.
- `Finding.fingerprint`: stable 16-hex SHA-256 digest for baseline diffing across re-analyses.
- `Finding.confidence` (float 0–1) and `Finding.tags` (`frozenset[str]`) fields.
- `RemediationHint` frozen dataclass: structured guidance (`summary`, `effort`, `steps`,
  `docs_url`, `auto_fixable`, `related_rule_ids`).
- `ErrorCategory` enum (`INPUT`, `ANALYSIS`, `PARSE`, `CONFIG`, `PLUGIN`, `INTERNAL`) and
  `StructuredError` frozen dataclass on every exception via `.structured` property.
- `extensions.py`: stable public import surface for third-party plugin/analyzer authors;
  exports `RemediationHint`, `AnalysisMeta`, `FileAnalysisResult`, `ErrorCategory`,
  `StructuredError`, and all existing extension types.
- New domain port interfaces: `IAnalyzerRegistry`, `IAnalysisCache`, `IFileDiscovery`.
- `Plugin.contribute_analyzers()` default hook: plugins may now register custom analyzers.
- `--baseline` and `--update-baseline` flags on the `analyze` subcommand for persisting and
  comparing findings across runs.
- Watch mode for the CLI: re-runs analysis automatically on file changes.
- JUnit XML output format (`--format junit` / `--output-file`).
- SHA-256 file-hash cache for `analyze_directory` to skip unchanged files.
- Hypothesis property-based tests for all core value objects.
- Integration tests for `FlakinessListener` V3 callback sequences.
- Direct unit tests for the `__main__` entry point (no subprocess).
- Mutation testing (mutmut) wired into CI with a 20% survival-rate gate.
- Dedicated SonarCloud scan workflow.

### Changed

- Architecture: all layer dependency violations resolved; imports now flow
  domain → application → infrastructure → entrypoints only.
- `IAnalysisCache` injected into `AnalysisService` via constructor; CLI `clear-cache`
  routes through the service instead of instantiating `AnalysisCache` directly.
- `repositories/` package renamed to `infrastructure/` to make DDD layering explicit.
- `ApplicationContext` is now the sole public context API; `ThreadSafeContainer` is internal.
- All dev and runtime dependencies bumped to 2026 latest stable versions.
- `DeadCodeAnalyzer` split into explicit AST and regex strategy classes.
- CLI refactored from a single `cli.py` into `_parser`, `_commands`, `_formatters`,
  and `_html` submodules.
- All analyzers migrated from line-by-line regex to `RobotASTParser`.
- `DirectoryResults` changed from a `dict` subclass to a proper dataclass.
- `Pattern.type` field renamed to `pattern_type` to avoid shadowing the Python built-in.
- `SleepPattern` serialisation replaced manual `model_dump` override with `field_serializer`.
- `SleepPattern` hard max-cap of 3600 s removed; threshold ownership moved to analyzer config.
- Service layer extracted from the API module for improved testability.
- Significant cognitive-complexity reduction across analyzers, `Location`, and `RobotASTParser`.

### Fixed

- Removed all `type: ignore` suppressions in `src/`; underlying type errors corrected.
- Resolved all open SonarCloud code-quality, reliability, and security issues.
- Plugin loader: restored `__import__` and `__build_class__` in the restricted
  `exec()` environment so third-party plugins can import standard-library modules.

## [1.0.0b1] - 2026-04-29

### Fixed
- SARIF output: removed local filesystem path from rule `helpUri`; `helpUri` is now only
  included when a pattern has a `documentation_url` (prevents path leakage in GHAS artifacts)
- Pre-commit.ci badge URL: corrected from `main` to `master` branch
- CHANGELOG project URL in `pyproject.toml`: corrected from `blob/main` to `blob/master`
- Clone URL in `docs/getting-started.md`: corrected from wrong organisation to
  `https://github.com/kobolcs/robot_optimizer_core.git`
- Python 3.14 CI: added `allow-prereleases: true` so the 3.14 matrix leg is not silently
  skipped when only a pre-release interpreter is available on the runner

### Changed
- Version bumped to `1.0.0b1` (public beta); `Development Status :: 4 - Beta` classifier
  now matches the version string
- `ci/check_version.py`: extended to compare the full PEP 440 version string including
  pre-release suffix, not just `major.minor.patch`
- ROADMAP.md: Python 3.14 support marked as shipped in 1.0b1

### Technical Details
- Minimal core dependencies: Pydantic v2, Robot Framework 7.1+
- Modern build system using Hatchling
- Source layout (`src/robot_optimizer_core`) for proper packaging
- Entry points for analyzer plugin discovery
- Fully typed with py.typed marker
- 80%+ enforced coverage gate with branch coverage enabled

## [1.0.0] - 2025-11-05

### Added
- Initial internal release of Robot Framework Optimizer Core
- **Dead Code Analyzer**: Detects unused keywords, duplicate definitions, and unreachable code
- **Sleep Pattern Detector**: Identifies inefficient `Sleep` usage that should be replaced with proper waits
- **Flakiness Analyzer**: Detects tests that fail intermittently based on historical data
- **Plugin System**: Extensible architecture for custom analyzers with entry point discovery
- **High-level API**: Easy-to-use functions (`analyze_file`, `analyze_directory`, `analyze_suite`)
- **Domain-Driven Design**: Clean architecture with proper separation of concerns
  - Domain models (TestFile, Finding, Location, Pattern, Severity)
  - Value objects with Pydantic v2 validation
  - Repository pattern for data access
- **Type Safety**: Full type hints throughout codebase with strict mypy checking
- **Production Features**:
  - Structured logging with context
  - Privacy-preserving, in-memory metrics collection
  - Thread-safe dependency injection container with circular dependency detection
  - Configurable settings via environment variables or code
- **Comprehensive Testing**:
  - 80%+ enforced coverage gate with branch coverage
  - Unit, integration, and component tests
  - Property-based testing with Hypothesis
  - Mutation testing support
- **Documentation**:
  - Comprehensive README with examples
  - API documentation
  - Architecture guide
  - Extension/plugin development guide
- **Developer Tools**:
  - Ruff for fast linting and formatting
  - Mypy for strict type checking
  - Pre-commit hooks support
  - MkDocs documentation generation

[1.0.0b1]: https://github.com/kobolcs/robot_optimizer_core/releases/tag/v1.0.0b1
[1.0.0]: https://github.com/kobolcs/robot_optimizer_core/releases/tag/v1.0.0
[Unreleased]: https://github.com/kobolcs/robot_optimizer_core/compare/v1.0.0b1...HEAD
