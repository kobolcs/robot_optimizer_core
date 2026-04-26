# CI integration

This repository uses GitHub Actions and tox as the primary automation layer.

## Workflows
- `CI` runs the Python test matrix and quality checks.
- `Docs` builds MkDocs.

## Recommended tox environments
- `py`
- `lint`
- `type`
- `docs`
- `build`

## Agent expectations
Codex agents should:
- prefer the narrowest relevant tox env first
- run `tox -e py` for behavior verification
- run `tox -e lint,type,build` after meaningful changes
- update docs when contracts or APIs change
