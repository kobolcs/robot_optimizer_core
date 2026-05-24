# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **`Finding.id` is now deterministic** — replaced `uuid4()` (random per-call) with
  `uuid5(_FINDING_NS, fingerprint)` so the same finding content always maps to the same
  UUID. JSON and SARIF output are now byte-identical across repeated `analyze_file()`
  calls on the same input. This was a silent violation of the documented "stable external
  referencing" contract for SARIF result IDs.

### Added

- **Contract test suite** (`tests/contracts/`) — 68 tests that pin the public-facing
  API, plugin, and output-schema surfaces. A failure here signals a breaking change
  before it reaches consumers:
  - `test_public_api_contract.py` — `analyze_file`, `analyze_directory`, `analyze_suite`
    parameter names/defaults/return types and `__all__` exports.
  - `test_plugin_contract.py` — `Plugin`, `PluginMetadata`, `PluginRegistry`,
    `ValidatedPluginManager` interfaces for external plugin authors.
  - `test_output_schema_contract.py` — JSON and SARIF structural keys validated against
    committed schema artifacts (`tests/contracts/schemas/`); output determinism asserted.

- **Analyzer determinism test suite** (`tests/component/test_analyzer_determinism.py`) —
  28 tests verifying that `analyze_file()` and `analyze_directory()` produce
  byte-identical results across 5 sequential runs, 20 concurrent threads, repeated
  directory runs, and with cache on/off.

- **Performance baseline tests** (`tests/component/test_performance_baselines.py`) —
  6 `@pytest.mark.performance` tests asserting finding-count stability at 1000-test
  scale, memory footprint <10 KB/finding, sub-linear scaling (<20× for 10× input
  growth), and cache warm-path overhead bounds. No wall-clock gates.

- **Parser property tests** (`tests/unit/parsers/test_robot_ast_parser_property.py`) —
  10 Hypothesis property tests covering `RobotASTParser` invariants: determinism,
  keyword/test-case count preservation, line-number ordering, name round-trip, and
  no-crash robustness over generated Robot content.

- **CI fast lane** (`.github/workflows/pr_fast.yml`) — runs on every PR push in <3 min:
  determinism check + contract tests + unit/integration smoke. Does not duplicate the
  lint/type checks already in `ci.yml`.

- **Nightly deep lane** (`.github/workflows/nightly.yml`) — runs at 02:00 UTC:
  quarantine suite execution, performance tests, and schema-drift detection. Mutation
  testing and compat matrix remain in their dedicated workflows to avoid duplication.

- **PR template** (`.github/pull_request_template.md`) — determinism checklist and
  contract-change checklist enforced at review time.

- **Determinism pre-commit hook** — `ci/check_test_determinism.py` (AST-based scanner
  for `datetime.now()` without timezone and `time.sleep()` in test files) runs on every
  commit touching `test_*.py` files.

- **Quarantine age check** — `ci/check_quarantine_age.py` flags `@pytest.mark.quarantine`
  tests older than 14 days; runs in the nightly lane and produces an artifact.

- **New `pytest` markers**: `contract` (API/schema stability tests, always run) and
  `quarantine` (flaky tests under investigation, skipped in PR gates, included in
  nightly via `--run-quarantine`).

- **New `Makefile` targets**: `test-contracts`, `test-smoke`, `test-nightly`,
  `check-determinism`, `check-quarantine`.

### Changed

- **`ci.yml` optimized**:
  - Draft PRs now skip the 12-runner compat matrix (fast lane handles them instead).
  - `paths-ignore` added — docs/markdown edits no longer trigger any CI job.
  - Quality job consolidated to a single `pip install` pass; tox environments
    (`lint`, `type`, `build`, `docs`) now run in parallel (`-p 4`).
  - Contract tests in quality job now install `.[test]` instead of `.[dev]`,
    avoiding mkdocs/mutmut/pre-commit overhead.
  - `uv.lock` added to tox cache key for correct cache invalidation on lock-file changes.
  - Uploads `coverage.xml` artifact (consumed by `sonar.yml` without re-running tests).

- **`sonar.yml` optimized** — now triggers via `workflow_run` after CI completes and
  downloads the `coverage.xml` artifact instead of re-running the full test suite
  (~70 s saved per PR push).

- **`mutation.yml` path filter corrected** — was pointing to the non-existent
  `src/robot_optimizer_core/analyzers/` path; now correctly targets
  `application/analyzers/` and `domain/`.

- **All `datetime.now()` (naive) calls in tests replaced with `datetime.now(UTC)`**
  across 11 test files — eliminates DST/timezone-sensitivity in test fixtures.

- **`tests/conftest.py`**: added `fixed_utc_now` fixture (stable
  `datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)` sentinel for domain object
  construction), `quarantine` skip mechanism, and removed duplicate
  `pytest_collection_modifyitems` stub.

- `refactor`: 21-issue source maintainability pass + 5-issue test-suite cleanup:

  **Source fixes (21 issues)**

  - `sleep_detector.py`: removed ~130 lines of orphaned regex detection path
    (`_compile_sleep_patterns`, `_detect_sleep`, `_detect_evaluate_sleep`,
    `_detect_pattern_sleep`, `_EVALUATE_SLEEP_RE`); replaced `sleep_info` dict
    with typed `_SleepDetection` dataclass; extracted `_resolve_sleep_threshold`
    (logs WARNING on fallback); removed trivial boilerplate docstrings from
    property overrides.
  - `dead_code.py`: replaced `assert` guard with explicit `AnalysisError` raise
    (safe under `-O`); moved `Iterable` import to module level as `_Iterable`;
    extracted `_unused_keyword_pattern(display_name, *, suite_level)` factory to
    deduplicate two identical `Pattern(PatternType.UNUSED_KEYWORD, …)` constructions.
  - `base.py`: simplified `safe_analyze` `try/except/else` — moved `return` into
    `try` body, removed the redundant `else` clause.
  - `_commands.py`: fixed unreachable `"Created"` branch in `_run_with_baseline`
    (capture `was_new` before `save_baseline`); extracted `_FEATURES` feature-matrix
    constant from `_run_upgrade`; replaced defensive `getattr(args, …)` calls with
    direct attribute access (argparse always sets these); replaced
    `hasattr(args, "analyzers")` guard in `_parse_analyzers` with unconditional access.
  - `_parser.py`: `--min-severity` now uses `choices=["INFO","WARNING","ERROR"]` so
    argparse rejects invalid values at parse time; `_parse_severity` simplified to a
    single-`None` return path.
  - `analysis_service.py`: `_run_file_analysis` now returns
    `tuple[list[Finding], tuple[str, …]]` — `analyze_file_with_meta` unpacks both in
    one call, eliminating the double `_get_analyzer_instances` per-file call;
    introduced `DirectoryAnalysisOptions` dataclass to reduce `run_directory_analysis`
    from 14 positional params to 5; added public `analyze_file_with_meta` and
    `resolve_analyzer_instances` wrappers so `public_api` no longer calls private
    methods directly.
  - `public_api.py`: added `pattern_filter` parameter to `analyze_suite` (API parity
    with `analyze_file`); extracted `_partition_analyzers` helper replacing an inline
    6-line loop; replaced all `container.resolve("…")` calls with typed accessor
    functions from `context.py`; removed `get_container` import.
  - `context.py`: added typed DI accessor functions `get_settings()`,
    `get_metrics()`, `get_file_discovery()`, `get_parser()`,
    `get_analyzer_registry()` — replace untyped `resolve()` returns at call sites.
  - `plugins/manager.py`, `analyzers/registry.py`: replaced
    `# type: ignore[no-any-return]` on untyped `resolve()` returns with explicit
    `cast(PluginRegistry, …)` / `cast(AnalyzerRegistry, …)`.

  **Test-suite fixes (5 issues)**

  - Consolidated four divergent `_make_finding()` / `_make_pattern()` factory
    functions into `tests/unit/helpers.py`; added `pythonpath = ["tests"]` to
    `pyproject.toml` so `from unit.helpers import …` resolves cleanly.
  - Extracted `_SIMPLE_ROBOT` constant (34 inline repetitions of
    `b"*** Test Cases ***\nT\n    Log    ok\n"`) to `tests/unit/helpers.py`;
    updated all four test files.
  - Deleted 6 unused fixtures and helper classes from `tests/conftest.py`
    (`empty_robot_file`, `flaky_test_stats`, `di_container`, `test_results`,
    `PerformanceTimer`, `TestData`, `MockFactory`).
  - Moved `large_robot_file` fixture from `tests/conftest.py` to
    `tests/integration/conftest.py` where it is actually used.
  - Added module docstring to `tests/unit/test_cli.py` documenting the
    mocked-analysis scope boundary (contrast with `test_cli_direct.py`'s full
    end-to-end pipeline).

- `refactor`: 25-issue maintainability pass across core domain, service layer, and CLI:
  - `Location`: removed custom `__init__` (all callers use keyword args); collapsed two
    `field_validator` validators into a single `model_validator(mode="after")`; rewrote
    `contains()` with tuple interval arithmetic (5 lines, replacing 30); fixed two trailing-colon
    bugs in `range_str` output.
  - `Finding`: removed `model_dump()` override that incorrectly returned live Python objects
    instead of Pydantic-standard primitives; documented three-level identity hierarchy
    (`__eq__`/`__hash__`, `fingerprint`, `BaselineKey`).
  - `Baseline`: keys are now SHA-256 `fingerprint` strings (stable cross-run identity) instead
    of `(relative_file_path, pattern_type_name, line)` tuples; legacy format read-compatible
    via synthetic `legacy:…` keys; both `save_baseline` and `load_baseline` accept an explicit
    `base: Path` for hermetic testing without monkeypatching.
  - `AnalysisService`: constructor now requires all dependencies explicitly (`settings`,
    `metrics`, `file_discovery`, `registry`); `from_container()` classmethod is the wiring
    point; `analyze_file` exception narrowed from bare `except Exception` to
    `except (AnalysisError, RobotFileNotFoundError)`.
  - `public_api.analyze_file` / `analyze_suite`: removed ~80-line duplicate analysis pipeline;
    both now delegate to `service._run_file_analysis()` and `service._get_analyzer_instances()`.
  - `run_directory_analysis`: return type corrected from `Any` to `DirectoryResults`; `metrics`
    param typed as `IMetrics`; `IFileDiscovery` and `IParser` replace `Any` for `discovery`
    and `parser` container resolves in `analyze_suite`; `Any` removed from `public_api` imports.
  - `_load_test_files`: now returns `(list[TestFile], list[tuple[Path, Exception]])` so load
    failures are surfaced in `SuiteAnalysisResult.errors` instead of being silently dropped.
  - `_FileChangeHandler`: extracted from nested class inside `_run_watch_mode` to module level;
    inherits from `watchdog.FileSystemEventHandler` via optional `try/except` import at module
    scope; `_run_watch_mode` body reduced by ~50 lines.
- `perf`: moved 79 type-annotation-only imports under `if TYPE_CHECKING:` across 30 source files
  (TC001/TC003), eliminating redundant runtime import overhead with no behaviour change.
  `[tool.ruff.lint.flake8-type-checking] runtime-evaluated-base-classes` added to pyproject.toml
  so Pydantic/ValueObject subclass fields are correctly excluded from TC001.
- `test`: PT012 nested-`with` collapses and RUF012 `ClassVar` annotations applied across unit
  tests; `match=` argument added to bare `pytest.raises` calls (PT011).

### Fixed

- Watch mode scope correctness: `_run_watch_mode` now maintains state as `dict[Path, list[Finding]]`
  instead of a flat `list[Finding]`. Previously, re-analysing a single changed file replaced the
  entire N-file state, causing all subsequent diffs to compare wrong scopes (false "resolved" for
  every other file's findings, false "new" for the next changed file). Each event now snapshots the
  full prev state, applies its per-file update, and diffs against the new full state — keeping scope
  consistent across modified, deleted, and moved events.
- Watch mode diff key switched from `(file_path, line, pattern_type)` to `Finding.fingerprint`
  (the same SHA-256-based stable identity used by baseline diffing), making the two mechanisms
  consistent and catching same-location findings that differ only in message.
- Watch mode now handles `FileDeletedEvent` and `FileMovedEvent` in addition to `FileModifiedEvent`.
  Deleted files are removed from state (all their findings become resolved); moved/renamed files
  remove the old entry and analyse the destination (findings at the new path appear as new).
- Watch mode: analysis error on a changed file no longer corrupts global state — the previous
  per-file entry is kept intact and the event is silently skipped.

- Cache correctness: severity filter now applied **after** cache writes so the cache always stores
  full findings; a subsequent filtered run no longer receives truncated cached results.
- Cache correctness: analyzer scope (e.g. `--analyzers sleep_detector`) is now encoded in the
  cache key via `_analyzer_scope_key()` (8-hex SHA-256 of sorted names), preventing a
  scoped run from serving results cached by a different analyzer set.
- Missing `TYPE_CHECKING` import in `application/analyzers/base.py` after TC001 moves.
- Coverage gate (≥95%) restored after TC001 moves: added `# pragma: no cover` to version-gated
  `typing_extensions` fallback, exhaustive-enum `match` wildcard arms, and two unreachable
  defensive guards; added 13 targeted tests for previously uncovered paths in `analyze_file`,
  `analyze_suite`, `_gather_suite_structure`, `_analyze_with_other_analyzers`,
  `_run_suite_analysis`, and the `infrastructure` lazy-import `__getattr__`.

### Changed (pre-existing)

- `tox.ini`: `[testenv]` now sets `package = wheel` so tox builds a wheel directly instead of
  the sdist→wheel path that silently dropped package files (hatchling strips `src/` in sdists,
  which broke `packages = ["src/robot_optimizer_core"]` during wheel rebuild from the sdist).

### Added

- Functional black-box test suite (`tests/functional/test_functional.py`): 33 tests that invoke
  the installed `robot-optimizer` entry-point as an end-user would, covering exit codes, JSON
  schema, known finding counts/fingerprints, severity filtering, and analyzer selection.
  Includes a slow `TestInstalledWheel` class that builds the wheel, installs into an isolated
  venv, and asserts the full pipeline works end-to-end.
- `cliff.toml` for automated changelog generation; `publish.yml` gains a conditional `changelog`
  CI job that prepends the unreleased section on tag push (skipped if the section already exists).

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
