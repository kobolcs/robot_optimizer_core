# AGENTS.md

## Scope
Applies to `src/robot_optimizer_core/` only.

This subtree is the stable core engine for Robot Framework analysis.

## Subtree-specific rules
- Protect core contracts first.
- Prefer precise domain changes with tests over broad refactors.
- Keep analyzers, domain models, parser behavior, and plugin registration understandable and testable.
- Do not introduce customer-specific assumptions into core abstractions.
- Be explicit when a change affects downstream packages or analyzer discovery.

## Command hints
Use the repo's Python package workflow. Current repo signals include:
- editable install with extras
- tests under `tests/`
- strict coverage expectations
- strict Ruff/Mypy setup

## Done criteria for this subtree
A change here is not done until you state:
- whether public/core behavior changed
- whether analyzer/plugin contracts changed
- what targeted tests were run
- whether coverage/type/lint expectations were considered
