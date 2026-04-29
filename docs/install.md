# Installation and Upgrade Guide

## Requirements

- Python 3.11+ (tested on Python 3.11, 3.12, 3.13, and 3.14)
- Robot Framework dependency is installed automatically
- CLI command: `robot-optimizer`

## Install with pip

```bash
python -m pip install robot-framework-optimizer-core
robot-optimizer --version
```

## Upgrade with pip

```bash
python -m pip install --upgrade robot-framework-optimizer-core
robot-optimizer --version
```

## Install CLI with pipx

```bash
pipx install robot-framework-optimizer-core
robot-optimizer --version
```

## Upgrade CLI with pipx

```bash
pipx upgrade robot-framework-optimizer-core
robot-optimizer --version
```

## Install CLI with uv tool

```bash
uv tool install robot-framework-optimizer-core
robot-optimizer --version
```

## Upgrade CLI with uv tool

```bash
uv tool upgrade robot-framework-optimizer-core
robot-optimizer --version
```

If `uv tool upgrade` is not available in the installed uv version, use this safe fallback:

```bash
uv tool install --force robot-framework-optimizer-core
```

## Add as a project dependency with uv

```bash
uv add robot-framework-optimizer-core
```

## Upgrade project dependency with uv

```bash
uv add --upgrade robot-framework-optimizer-core
```

If that command is not supported by older uv versions, run:

```bash
uv remove robot-framework-optimizer-core
uv add robot-framework-optimizer-core
```

## Run from source with uv

```bash
git clone https://github.com/kobolcs/robot_optimizer_core.git
cd robot_optimizer_core
uv sync --extra dev
uv run robot-optimizer --version
uv run tox -e lint,type,build
uv run tox -e py
```

## Run from source with pip and venv

### Linux/macOS

```bash
git clone https://github.com/kobolcs/robot_optimizer_core.git
cd robot_optimizer_core
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
tox -e lint,type,build
tox -e py
```

### Windows PowerShell

```powershell
git clone https://github.com/kobolcs/robot_optimizer_core.git
cd robot_optimizer_core
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
tox -e lint,type,build
tox -e py
```

## Verify installation

```bash
robot-optimizer --version
robot-optimizer list-analyzers
robot-optimizer analyze examples/bad_robot_suite --format text --no-fail
robot-optimizer analyze examples/bad_robot_suite --format html --output-file demo-report.html --no-fail
```

## Troubleshooting

- `robot-optimizer: command not found`
  - Ensure your environment or tool shim paths are active.
  - Fallback command: `python -m robot_optimizer_core --version`
- `pipx` path issues
  - Run `pipx ensurepath`, then restart your shell.
- `uv` local environment issues
  - Recreate environment with `uv sync --extra dev`.
- Stale editable installs
  - Reinstall with `python -m pip install -e ".[dev]" --force-reinstall`.
- Generated local files (for example `demo-report.html`)
  - Remove generated artifacts before committing if they are not part of source docs.
