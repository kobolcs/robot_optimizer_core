# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Plugin exec sandbox: restore `__import__` and `__build_class__` so plugins with import/class statements load correctly
- `AnalyzerRegistry.get()` was calling `plugin_registry.get("analyzers", name)` with wrong arity; now raises `PluginError` cleanly for unknown analyzers
- `AnalyzerRegistry.list()` no longer scans `PluginRegistry` (which stores `Plugin` classes, not analyzer classes), eliminating names that `get()` could not resolve
- `PluginRegistry.unregister()` added; `AnalyzerRegistry.unregister()` no longer tries to reach into the wrong registry
- `DeadCodeAnalyzer._keyword_display_names` now initialised in `__init__`; removed defensive `getattr` at call site
- `validate_config()` now called at end of each concrete analyzer `__init__` so config errors surface immediately

### Added
- `SuiteAnalysisResult`, `SuiteInfo`, `SuiteStatistics` typed dicts for `analyze_suite` return value
- `requires_external_repo: ClassVar[bool]` on `BaseAnalyzer`; `FlakinessAnalyzer` sets it `True` so the default API skips it when no repository is configured
- `@overload` signatures on `BaseAnalyzer.get_config_value` for type-narrowed return types
- `validate_config()` implementation on `DeadCodeAnalyzer` (bool flags + list type check)
- `PluginRegistry.unregister()` method
- `__all__` declarations in `exceptions`, `logging`, `metrics`, `di`, `plugin`, `analyzers/registry`, `analyzers/base`, `analyzers/dead_code`, `analyzers/sleep_detector`, `analyzers/flakiness`, `api`, `deprecation`
- Unit tests for `MetricsCollector`, `StructuredFormatter`, `get_logger`, `deprecated` decorator, `deprecation_warning`, `deprecated_parameter`, `renamed_parameter`, `PluginRegistry.unregister`
- Complete plugin example moved to `docs/extending.md`

### Removed
- Dead example functions `example_scoped_usage()` (di.py) and `example_optimized_discovery()` (file_finder.py)
- `SAFE_PLUGIN_TEMPLATE` string constant (example source moved to docs)

### Changed
- `_SuiteInfo` / `_SuiteStatistics` renamed to `SuiteInfo` / `SuiteStatistics` (public TypedDicts should not be name-mangled)
- Coverage gate raised from 55% to 65%
- `ConfigurationError` import in `sleep_detector.py` moved to module level

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
