# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2025-11-05

### Added
- Initial public release of Robot Framework Optimizer Core
- **Dead Code Analyzer**: Detects unused keywords, duplicate definitions, and unreachable code
- **Sleep Pattern Detector**: Identifies inefficient `Sleep` usage that should be replaced with proper waits
- **Flakiness Analyzer**: Detects tests that fail intermittently based on historical data
- **Plugin System**: Extensible architecture for custom analyzers with entry point discovery
- **High-level API**: Easy-to-use functions (`analyze_file`, `analyze_directory`, `analyze_suite`)
- **Domain-Driven Design**: Clean architecture with proper separation of concerns
  - Domain models (TestFile, Finding, Location, Pattern, Severity)
  - Value objects with Pydantic v2 validation
  - Repository pattern for data access
  - Aggregate roots and domain events
- **Type Safety**: Full type hints throughout codebase with strict mypy checking
- **Modern Python**: Python 3.13+ features including PEP 695 type parameters and PEP 698 @override decorators
- **Production Features**:
  - Structured logging with context
  - GDPR-compliant metrics collection
  - Thread-safe dependency injection container with circular dependency detection
  - Configurable settings via environment variables or code
- **Comprehensive Testing**:
  - 99%+ test coverage with branch coverage
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

### Technical Details
- Minimal core dependencies: Pydantic v2, Robot Framework 7.1+
- Modern build system using Hatchling
- Source layout (`src/robot_optimizer_core`) for proper packaging
- Entry points for analyzer plugin discovery
- Fully typed with py.typed marker

[1.0.0]: https://github.com/kobolcs/robot_optimizer_core/releases/tag/v1.0.0
[Unreleased]: https://github.com/kobolcs/robot_optimizer_core/compare/v1.0.0...HEAD
