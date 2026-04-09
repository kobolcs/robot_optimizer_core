# AGENTS.md

## Purpose
This repository is a **WSL-first test automation project** centered on:
- Robot Framework
- Python support code and custom keyword libraries
- Playwright directly and/or Robot Framework Browser / Browser Library
- VS Code + WSL as the standard local workflow

Treat the repository like production test infrastructure. Reliability and maintainability matter more than cleverness.

## Operating assumptions
- Prefer **Linux/WSL** execution.
- Use **bash** and Linux paths.
- Do **not** switch to Windows-native commands unless explicitly requested.
- If both Windows and WSL are available, prefer the **WSL environment** for repo work.

## Before you change anything
Inspect the project and discover the real workflow from:
- `pyproject.toml`
- `uv.lock`
- `requirements*.txt`
- `package.json`
- `playwright.config.*`
- `robot.toml`
- `Makefile`
- `README*`
- CI definitions

Prefer repo-defined commands over guessed commands.

## Project-specific rules
### Robot Framework
- Keep tests readable and business-oriented.
- Prefer fixing shared keywords, resource files, page objects, or Python libraries instead of patching many tests one by one.
- Preserve keyword names unless a rename is explicitly requested.
- Avoid `Sleep` unless truly necessary; prefer condition/state-based waiting.

### Playwright / Browser Library
- Prefer stable selectors: `data-testid`, roles, stable ids, semantic hooks.
- Avoid brittle selectors based on layout, long CSS chains, or unstable text.
- Prefer synchronization tied to actual UI readiness, not longer raw timeouts.
- For flaky tests, first determine whether the cause is locator instability, missing wait/synchronization, test data/state, environment issue, or an application defect.

### Python libraries
- Keep helper code small, explicit, and reusable.
- Preserve interfaces used by Robot unless change is requested.
- Prefer meaningful exceptions and diagnostics.

## Command discovery order
Use commands in this order:
1. repo-documented command
2. Makefile or task runner command
3. CI command as truth source
4. fallback commands below

Fallback examples only when the repo lacks wrappers:
- `uv sync`
- `uv run pytest -q`
- `uv run python -m robot -d results tests/`
- `uv run robot -d results tests/`
- `uv run rfbrowser init`
- `npx playwright test`

## Validation policy
Validate the smallest meaningful surface first:
1. syntax / formatting / lint for touched files
2. targeted Python tests for touched helper code
3. targeted Robot test or suite for affected keyword flow
4. broader run only if necessary

Never say a fix is complete without either:
- running meaningful validation, or
- explicitly stating what prevented validation

## Parallelization guidance
Use agent parallelism for:
- patterned repo-wide updates
- repeated locator refactors
- doc cleanup
- broad search/explain tasks

Do **not** do broad parallel edits until the canonical fix pattern is proven in one or two representative files.

## Done criteria
A task is not done until you provide:
- concise root cause
- files changed
- what changed and why
- commands run
- validation status
- remaining risk, assumptions, or blockers
