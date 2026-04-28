# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-11-05

### Added
- Initial public release of Robot Framework Optimizer Core
- **Dead Code Analyzer**: Detects unused keywords, duplicate definitions, and unreachable code
- **Sleep Pattern Detector**: Identifies inefficient `Sleep` usage with severity thresholds
- **Flakiness Analyzer**: Detects tests that fail intermittently based on historical data
- **Plugin System**: Extensible architecture for custom analyzers with entry point discovery
- **High-level API**: `analyze_file`, `analyze_directory`, `analyze_suite`
- **Domain-Driven Design**: Clean architecture — domain models, value objects, repository pattern
- **Type Safety**: Full type hints with Pydantic v2 validation and strict mypy
- **Production Features**: Structured logging, GDPR-compliant metrics, thread-safe DI container
- **Comprehensive Testing**: Unit, integration, and component tests with branch coverage

[1.0.0]: https://github.com/kobolcs/robot_optimizer_core/releases/tag/v1.0.0
