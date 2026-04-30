# CLAUDE.md

## Scope
This file applies to `src/robot_optimizer_core/`.

This subtree is the **core analysis engine**. Treat it as stable library code, not ad hoc automation scripting.

## What matters here
- Preserve API stability where practical.
- Favor correctness, type safety, and predictable findings over convenience.
- Keep domain logic cleanly separated from infrastructure and tooling.
- Changes here can affect analyzers, plugins, metrics, and downstream packages.

## Repo-specific cues from current config
- Package name: `robot-framework-optimizer-core`
- Python: 3.11+
- Package path: `src/robot_optimizer_core`
- Entry-point group: `robot_optimizer.analyzers`
- Current enforced coverage gate: `--cov-fail-under=80` (see `pyproject.toml`)
  - TODO: raise to 99% as the test suite grows (long-term roadmap target, not current CI policy)
- Ruff and Mypy are configured strictly

## Validation preference order
When changing this subtree, prefer:
1. focused pytest for the impacted module/analyzer
2. broader pytest run if contracts changed
3. lint/type validation when relevant

## Editing rules for this subtree
- Do not weaken domain modeling casually.
- Keep findings, locations, patterns, severity, and parser contracts internally coherent.
- Avoid mixing experimental product ideas into core abstractions without clear boundaries.
- If touching plugin discovery or analyzer registration, state downstream impact explicitly.
