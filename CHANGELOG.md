# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- _No unreleased changes yet._

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
