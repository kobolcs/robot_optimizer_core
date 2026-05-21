# Technical Debt Analysis Report
**Robot Optimizer Core Codebase**
**Analysis Date:** May 14, 2026
**Last Updated:** May 21, 2026

---

## How to Keep This Document Current

Run the following whenever a significant refactor lands or a new debt item is
discovered:

1. **Grep for the file/symbol referenced** in the item before marking it
   resolved.  A commit message that says "fix X" does not prove X is gone —
   read the code.
2. **Update the summary table** — change `Status` and `Remediation Effort`.
3. **Move resolved items** in the Detailed Findings from ⚠️ to ✅, add a
   one-line note of what changed and when.
4. **Add new items** if a refactor reveals a previously hidden problem.
5. **Bump "Last Updated"** at the top of this file in the same commit.

Suggested cadence: review after every sprint boundary or release cut.
The CI mutation-testing gate (≥ 80 % survival rate, enforced since May 2026)
surfaces under-tested paths early — poor mutation scores are a proxy for
structural debt that tests cannot see.

---

## Executive Summary

The codebase shows **moderate, declining technical debt** across ~28 K lines of
Python.  Since the initial analysis (May 14, 2026) six structural items have
been fully resolved and three are partially resolved, reducing the original
three major risk areas to two.

**Remaining primary risks:** global state management and tight coupling in the
analyzer framework.  **No critical blockers** — current code is production-ready.

---

## Technical Debt Summary Table

| **Area** | **Issue** | **Severity** | **Status** | **Remediation Effort** |
|----------|-----------|-------------|------------|------------------------|
| Global State | `_global_container` (di.py:350) | MEDIUM | ⚠️ Open | 3–4 days |
| Global State | `_global_metrics` (metrics.py:422) | MEDIUM | ⚠️ Open | 2–3 days |
| Global State | `logging_context` ContextVar (logging.py:42) | LOW | ⚠️ Open | 1 day |
| Global State | `get_container()` auto-init instead of fail-fast | LOW | ⚠️ Open | 2 hours |
| Tight Coupling | api.py ↔ analyzers (10+ imports) | MEDIUM | ⚠️ Open | 3–4 days |
| Tight Coupling | api.py ↔ config (settings singleton) | MEDIUM | ⚠️ Open | 2 days |
| Tight Coupling | metrics ↔ logging (circular concern) | LOW | ⚠️ Open | 1 day |
| Tight Coupling | cli submodules ↔ api.py | LOW | 🔄 Improved | 1 day |
| Naming | `_UnreachableState` private class (dead_code.py:48) | LOW | ⚠️ Open | < 1 day |
| Naming | `_CategoryInfo` TypedDict casing (_html.py:26) | LOW | ⚠️ Open | < 1 day |
| Missing Abstraction | FileProvider interface absent | LOW | ⚠️ Open | 2–3 days |
| Missing Abstraction | Error handling not unified | LOW | ⚠️ Open | 1–2 days |
| HTML Rendering | Jinja2 optional; legacy renderer still present | LOW | 🔄 Improved | 1 day |
| AST Migration | `test_documentation.py` still uses line scanning | LOW | ⚠️ Open | 1 day |
| Package Layout | `repositories/` shadowed `infrastructure/` | MEDIUM | ✅ Resolved (May 21) | — |
| DirectoryResults | Was a `dict` subclass antipattern | MEDIUM | ✅ Resolved (May 20) | — |
| AnalysisService | No service-layer facade | MEDIUM | ✅ Resolved (May 20) | — |
| CLI Structure | Monolithic cli.py | MEDIUM | ✅ Resolved (May 20) | — |
| Context API | `ThreadSafeContainer` was public | LOW | ✅ Resolved (May 21) | — |
| Analyzer Strategy | `DeadCodeAnalyzer` had no strategy abstraction | LOW | ✅ Resolved (May 21) | — |
| Coverage | No per-file floor; aggregate masked gaps | MEDIUM | ✅ Resolved (May 21) | — |

---

## Detailed Findings

---

### 1. Global State Abuse ⚠️ PRIMARY DEBT (unchanged since May 14)

All three global singletons identified in the original analysis remain:

| Component | Location | Pattern |
|-----------|----------|---------|
| `_global_container` | di.py:350–390 | Module-level with RLock; double-check init |
| `_global_metrics` | metrics.py:422–447 | Module-level with cleanup thread |
| `logging_context` | logging.py:42–43 | `ContextVar`; can leak between async tasks |

`ApplicationContext` (context.py:74) is now the **sole public surface** for
lifecycle management (resolved May 21), which reduces accidental direct access.
But the underlying globals remain and `get_container()` is still importable and
still auto-initializes.

#### Sub-item: `get_container()` auto-initializes instead of failing fast

The original analysis listed "add explicit initialization checks in
`get_container()` to fail fast" as a Quick Win.  It was not implemented.
`get_container()` (di.py:364–374) silently creates a default container if
called before `ApplicationContext.initialize()`:

```python
# di.py:364-374 — still auto-initializes silently
if _global_container is None:
    with _global_container_lock:
        if _global_container is None:
            container = ThreadSafeContainer()
            _register_defaults(container)
            _global_container = container
return _global_container
```

Consequence: plugins or callers that forget to call `initialize()` get a
default container rather than an informative error.

**Remediation (2 hours):** behind a `ROBOT_OPTIMIZER_STRICT_DI=1` environment
flag, raise `RuntimeError("ApplicationContext not initialized")` instead of
auto-creating.  Existing tests are unaffected unless they set the flag.

---

### 2. Tight Coupling Between Modules ⚠️ PRIMARY DEBT (partially improved)

#### What Changed
- `AnalysisService` facade added in `service.py` (May 20, commit `ccc30eb`).
- CLI refactored into submodules (May 20), reducing `cli → api` surface.

#### Still Open

| Couple | Where | Risk |
|--------|-------|------|
| api.py → analyzers | 10+ direct imports, `BaseAnalyzer` usage | Changing analyzer base class ripples into api.py |
| api.py → config | `container.resolve("settings")` in three places | Settings cannot be injected without a container |
| metrics ↔ logging | logging.py:28 `from .metrics import get_metrics` | Circular concern; log events drive metric counters |

The `metrics ↔ logging` item is the lowest-effort of the three: extract the
metric increment into a `MetricsLogHandler` subclass that callers opt into
explicitly, removing the unconditional import.

---

### 3. HTML Rendering — Jinja2 Optional, Legacy Renderer Parallel 🔄 IMPROVED

#### What Changed (May 20)
`cli.py` was split into submodules.  `_html.py` now tries Jinja2 first
(`resources/report.html.j2`) with `autoescape=True`.

#### Remaining Debt
`jinja2` is **not declared** in `[project.dependencies]` or any optional
dependency group.  `_render_html_template()` (`_html.py:444`) falls back
silently to `_format_html_legacy()` when `jinja2` is absent:

```python
try:
    from jinja2 import Environment, FileSystemLoader
    from markupsafe import Markup
except ImportError:
    return _format_html_legacy(context)   # silent, untested fallback
```

Two parallel renderers must now be kept in sync.  The 350-line f-string legacy
renderer remains the default for core installs.

**Remediation (1 day):**
1. Add `jinja2>=3.0` to `[project.dependencies]` (or a `[report]` optional
   group) and remove `_format_html_legacy`.
2. Add `resources/report.html.j2` to the wheel `include` list in
   `pyproject.toml` (currently absent from `[tool.hatch.build.targets.wheel]`).

---

### 4. Analyzer AST Migration — Incomplete 🔄 IMPROVED

#### What Changed (May 20–21)
`hardcoded_value`, `naming_convention`, `setup_teardown`, `sleep_detector`,
and `tag_consistency` were migrated to `RobotASTParser`.  `DeadCodeAnalyzer`
now uses an explicit `_ASTDeadCodeStrategy` / `_RegexDeadCodeStrategy` pair
(commit `52af778`), with the regex path as a documented fallback for files that
fail AST parsing.

#### Remaining Debt: `test_documentation.py`
`TestDocumentationAnalyzer` still uses `test_file.content.splitlines()` for
its primary analysis (test_documentation.py:142).  It is the only analyzer not
on the AST path.

**Risk:** Robot Framework version upgrades may change keyword or section
structure in ways that break the regex path silently — no parse error, just
silently wrong findings.

**Remediation (1 day):** migrate `TestDocumentationAnalyzer.analyze()` to call
`RobotASTParser().parse_suite()`, matching the seven other analyzers.

---

### 5. Package Layout ✅ RESOLVED (May 21, commit `78f21d3`)

`src/robot_optimizer_core/repositories/` (concrete implementations) and
`src/robot_optimizer_core/domain/repositories/` (interfaces) had confusingly
similar names that made the DDD boundary invisible in the folder structure.

**Resolution:** `repositories/` renamed to `infrastructure/`.  All five
import sites updated.  `domain/repositories/` (interfaces/protocols) unchanged.

---

### 6. `DirectoryResults` dict Subclass ✅ RESOLVED (May 20, commit `93d93dd`)

`DirectoryResults` was a `dict` subclass that mixed iteration semantics with
named fields and confused static type analysis.

**Resolution:** Replaced with `@dataclasses.dataclass` at api.py:64.
`findings` and `errors` are now explicit typed fields.

---

### 7. No Service-Layer Facade ✅ RESOLVED (May 20, commit `ccc30eb`)

No stable facade existed; callers had to interact directly with the analyzer
registry, metrics, and logging machinery.

**Resolution:** `service.py` exports `AnalysisService`, `AnalysisResult`, and
`DirectoryAnalysisResult`.  The service layer provides a DI-friendly entry
point that hides internal machinery.

---

### 8. Monolithic cli.py ✅ RESOLVED (May 20, commit `1ff4223`)

`cli.py` was a single 800+ line file mixing argument parsing, business
dispatch, text formatting, and HTML generation.

**Resolution:** Split into `_parser.py`, `_commands.py`, `_formatters.py`,
`_html.py`, and `__init__.py`.

---

### 9. `ThreadSafeContainer` Public API ✅ RESOLVED (May 21, commit `16171d3`)

`ThreadSafeContainer` was re-exported from `__init__.py`, creating an
accidental public API.

**Resolution:** `ThreadSafeContainer` is now internal to `di.py`.
`ApplicationContext` is the sole public lifecycle interface.

---

### 10. `DeadCodeAnalyzer` Strategy Abstraction ✅ RESOLVED (May 21, commit `52af778`)

`DeadCodeAnalyzer` mixed AST walking and regex fallback in a single class with
no explicit strategy boundary.

**Resolution:** Refactored into `_ASTDeadCodeStrategy` and
`_RegexDeadCodeStrategy`, both implementing the `_DeadCodeStrategy` protocol
(dead_code.py:117–356).  The analyzer delegates to AST first and falls back
to regex on parse failure.

---

### 11. Aggregate Coverage Masking Per-File Gaps ✅ RESOLVED (May 21, commit `9328ba8`)

The 95 % aggregate passed because small, fully-tested value-object files
inflated the average, masking modules as low as 84 %.

**Resolution:** `ci/check_per_file_coverage.py` enforces an 80 % floor per
source file after every test run.  Wired into the `tox` `[testenv]` and the
Makefile.  Thresholds are documented in `CONTRIBUTING.md`.

---

### 12. Naming Inconsistencies ⚠️ STILL OPEN (LOW)

| File | Item | Issue |
|------|------|-------|
| dead_code.py:48 | `class _UnreachableState` | Private class named `_Class`; private functions use `_function()` style |
| cli/_html.py:26 | `class _CategoryInfo(TypedDict)` | CamelCase private; inconsistent with surrounding `_format_*()` functions |

---

### 13. Missing Abstractions ⚠️ STILL OPEN (LOW)

#### FileProvider interface
`TestFile.from_path()` hardcodes `Path` I/O.  Tests use `tmp_path`
fixtures rather than in-memory providers.  No `FileProvider` protocol exists.

#### Error handling
`AnalysisError`, `ConfigurationError`, `PluginError`, and `RepositoryError`
share no common base class and carry no `error_code` attribute.  Recovery
strategy (log-and-continue vs. raise) varies per module.

---

## Codebase Metrics

| Metric | Original (May 14) | Current (May 21) | Delta |
|--------|-------------------|------------------|-------|
| Python lines (approx.) | ~25 K | ~28 K | +3 K |
| Modules | 9 core + 8 subpackages | 10 core + 9 subpackages | +2 |
| Test count | ~1 022 | 1 292 | +270 |
| Coverage gate (aggregate) | 80 % target | 95 % enforced | +15 pp |
| Coverage gate (per-file floor) | None | 80 % enforced | New |
| Global singletons | 4 | 3 | −1 |
| Open debt items | 20 | 13 | −7 |

---

## Risk Prioritization

### 🔴 High Priority (Refactor Soon)
1. **Global DI Container / auto-init** — blocks reliable isolated testing;
   silent initialization hides misconfiguration.
2. **API-Analyzer Coupling** — 10+ direct imports make `analyze_file()`
   hard to evolve; slows plugin development.

### 🟡 Medium Priority (Refactor When Convenient)
3. **Jinja2 not declared / legacy renderer** — core installs silently produce
   a lower-quality HTML report; two renderers must be kept in sync.
4. **`test_documentation.py` line scanning** — only analyzer not on the AST
   path; Robot Framework version upgrades are a silent breakage risk.
5. **metrics ↔ logging** — circular concern; low blast radius but easy to fix.

### 🟢 Low Priority (Nice to Have)
6. **`get_container()` fail-fast** — add a strict-mode env flag; 2-hour effort.
7. **Naming inconsistencies** — cosmetic; draft a naming guide and apply once.
8. **FileProvider abstraction** — defer unless custom file sources are planned.
9. **Error handling unification** — worth addressing in next major version.

---

## Conclusion

Six structural improvements landed in the week following the initial analysis:
the `infrastructure/` rename clarified DDD layering, `AnalysisService` gave
consumers a stable facade, `DirectoryResults` became a proper dataclass, the
CLI was modularised, coverage enforcement was tightened, and the
`DeadCodeAnalyzer` gained a clean strategy abstraction.

**Two primary risks remain:** global state management and API-analyzer
coupling.  Both require targeted but non-trivial refactoring (3–4 days each).
All other open items are low-severity with clear, bounded remediation paths.

**Estimated remaining effort for all open items: ~2 weeks.**
**Blocking severity: None** — codebase is production-ready.
