# Repository capability analysis (code-only)

## 1) Core capabilities (current)

- Exposes high-level APIs to analyze a single file, a directory, or a suite and return findings.
- Detects dead code patterns in Robot Framework files (unused keywords, duplicate keyword definitions, unreachable code after RETURN).
- Detects sleep usage patterns (builtin, qualified, custom wait/pause/delay forms, and variable-based sleep) and classifies severity.
- Detects flaky tests from historical test-result statistics provided by a repository abstraction.
- Parses Robot Framework files with `robot.parsing` into suite/test/keyword/variable/import structures.
- Discovers files by include/exclude glob patterns through an optimized discovery service.
- Provides plugin loading with AST-based security validation and restricted builtins/imports.
- Provides dependency injection, structured logging, and in-process metrics collection.

## 2) Inputs and outputs

### Inputs
- File paths / directory paths for analysis APIs.
- Optional analyzer selection by name or instance.
- Optional settings (`Settings`) for thresholds, file patterns, exclusions, plugin behavior, logging, and metrics.
- For flakiness analysis: a `TestResultRepository` implementation (or DI registration) that supplies historical results / flakiness stats.
- For plugin loading: plugin Python file path(s), optionally trusted file hashes.

### Outputs
- `analyze_file(...)` returns `list[Finding]`.
- `analyze_directory(...)` returns `dict[Path, list[Finding]]` and may raise `ExceptionGroup` when file-level errors occur.
- `analyze_suite(...)` returns a dict with:
  - `findings`
  - `file_findings`
  - `suite_info`
  - `statistics`
- `Finding` carries pattern, severity, location, message, and optional context.

## 3) Main workflows

1. **Single file workflow**
   - Validate file exists.
   - Load `TestFile` from disk.
   - Resolve analyzers (all registered if none specified).
   - Run analyzers and aggregate findings.
   - Emit logs/metrics.

2. **Directory workflow**
   - Validate directory.
   - Discover matching files with include/exclude patterns.
   - Analyze each file via `analyze_file`.
   - Aggregate results and track per-file failures.

3. **Suite workflow**
   - Discover files (if directory input).
   - Parse each file into AST-derived suite components.
   - Run analyzers per file.
   - Return suite-level aggregates/statistics.

4. **Flakiness workflow**
   - Call repository for flakiness stats.
   - Apply minimum-run and threshold rules.
   - Emit findings for tests with intermittent failures.

5. **Plugin workflow**
   - Validate plugin code via AST checks and file permissions.
   - Compile/execute in restricted globals.
   - Locate plugin class, validate metadata, activate, and register.

## 4) Key abstractions

- **Analyzers**: `BaseAnalyzer` contract + concrete analyzers (`DeadCodeAnalyzer`, `SleepDetector`, `FlakinessAnalyzer`).
- **Registry**: `AnalyzerRegistry` for registration, discovery, default set, and instance caching.
- **Findings model**: `Finding` + `Pattern`/`PatternType` + `Severity` + `Location`.
- **Domain entity**: `TestFile` (timezone-aware variant in code).
- **Repositories**: `RobotParserRepository` and `TestResultRepository` interfaces.
- **Parser**: `RobotASTParser` producing `RobotSuite`-related value objects.
- **Infrastructure**: DI container, file discovery service, plugin manager/security validator, metrics collector.

## 5) Problems it solves

- Surfaces maintainability issues in Robot Framework suites (dead/duplicate/unreachable keyword code).
- Surfaces performance/stability issues from hard sleeps and wait-style delays.
- Flags intermittently failing tests (flakiness) when historical execution data is available.
- Provides reusable typed models and extension points so analysis logic can be integrated into other tools.
- Provides secure-ish plugin loading controls (import/function restrictions, file permission/hash checks).

## 6) What it does NOT do (as implemented)

- Does **not** automatically modify/fix `.robot` files; analyzers return findings only.
- Does **not** include a concrete persistence backend for test results; flakiness depends on an external repository implementation.
- Does **not** execute Robot tests itself.
- Does **not** provide a built-in CLI entrypoint in this repository.
- Does **not** perform broad static analysis categories implied by many `PatternType` values (e.g., xpath/css/long-test detection) unless corresponding analyzers are added.
- Does **not** guarantee plugin sandbox isolation beyond AST/rule checks and restricted globals.
