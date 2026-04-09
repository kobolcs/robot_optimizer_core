# CLAUDE.md

## Repo context
This is a **WSL-first QA automation repo** built around:
- Robot Framework
- Python custom libraries and helpers
- Playwright directly and/or Robot Framework Browser / Browser Library
- VS Code + WSL as the normal development workflow

Treat this as production test infrastructure. Priorities:
1. reliability
2. debuggability
3. maintainability
4. minimal-risk changes

## Environment rules
- Prefer **WSL/Linux** execution.
- Prefer **bash** and Linux paths.
- Do **not** switch to PowerShell or cmd unless explicitly requested.
- Prefer the repo's existing tools and wrappers before inventing commands.
- The repo may use `uv`, `.venv`, `mise`, `direnv`, `npm`, or `pnpm`.

## Inspect first
Before changing anything, inspect the real workflow from files such as:
- `pyproject.toml`
- `uv.lock`
- `requirements*.txt`
- `package.json`
- `playwright.config.*`
- `robot.toml`
- `Makefile`
- `README*`
- CI config files

## Command preference order
Use commands in this order:
1. repo-documented command
2. Makefile / task runner / CI command
3. `uv run ...`
4. active `.venv` command
5. direct Python / Robot / Playwright invocation

Fallback examples only when the repo has no wrapper:
- `uv sync`
- `uv run pytest -q`
- `uv run python -m robot -d results tests/`
- `uv run robot -d results tests/`
- `uv run rfbrowser init`
- `npx playwright test`

## Editing rules
- Make the **smallest change that solves the problem**.
- Preserve naming patterns, folder layout, and existing test style.
- Prefer fixing shared keywords, page objects, resource files, or Python helpers instead of patching many tests individually.
- Keep diffs reviewable.
- Do not silently rewrite unrelated files.

## Robot Framework rules
- Keep tests readable and business-oriented.
- Prefer reusable user keywords over duplicated steps.
- Keep keyword names stable unless rename is explicitly requested.
- Avoid `Sleep` unless it is the last resort; prefer state-based waiting.
- When a test fails, decide whether the fault belongs in test data, keyword logic, Python library code, locator/wait logic, or environment setup.

## Playwright / Browser Library rules
- Prefer stable selectors: `data-testid`, roles, stable ids, semantic hooks.
- Avoid brittle selectors like `nth-child(...)`, long CSS chains, or unstable text.
- Prefer synchronization tied to actual UI readiness instead of longer raw timeouts.
- If a test is flaky, first check:
  1. locator instability
  2. missing wait / race condition
  3. overlay / animation / detached element
  4. test data state
  5. environment issue

## Python rules
- Keep helpers explicit, reusable, and easy to debug.
- Preserve interfaces used by Robot unless change is requested.
- Prefer useful exceptions and good diagnostics.
- Follow the repo's style before introducing new patterns.

## Validation rules
After changes, validate at the **smallest meaningful scope first**:
1. lint / syntax / formatting if configured
2. targeted Python test
3. targeted Robot suite / test
4. broader run only if needed

Do not claim something is fixed unless you ran a meaningful validation step or explicitly state why you could not.

## Safety
- Never expose secrets from `.env`, CI vars, auth files, or browser storage.
- Do not edit files outside the workspace unless explicitly requested.
- Be careful with destructive commands.

## Good final output
When finishing a task, provide:
- root cause
- files changed
- what changed and why
- commands run
- validation result
- remaining risk or blocker
