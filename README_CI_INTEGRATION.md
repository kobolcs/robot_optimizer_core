# robot_optimizer_core Codex + CI integration pack

This pack is designed as an **overlay** for your existing `robot_optimizer_core` repo.

It adds:
- GitHub Actions CI workflow
- GitHub Actions docs build workflow
- suggested `tox.ini` integration snippet
- suggested `pyproject.toml` additions for API and test extras
- CI documentation for Codex agents

## Recommended merge order
1. Copy `.github/workflows/*.yml` into your repo
2. Review `ci/tox.ini.snippet`
3. Review `ci/pyproject.optional-deps.snippet.toml`
4. Add `docs/architecture/ci.md` and link it from MkDocs if desired

## Assumptions
This pack assumes the repo already has:
- `tox.ini`
- `pyproject.toml`
- `tests/`
- `src/robot_optimizer_core/`
- Python 3.11+ support

If your existing env names differ, update the workflow matrix commands to match your `tox.ini`.
