# src/robot_optimizer_core/config/toml_loader.py
"""Robot Framework TOML configuration loader (Task 21).

Detects ``robot.toml`` (or ``pyproject.toml``) in the project root and merges
the ``[tool.robot-optimizer]`` table into ``Settings``.  This is consistent
with how other RF tooling (robocop, robotidy) loads configuration.

Usage::

    from robot_optimizer_core.config.toml_loader import load_settings_from_toml

    settings = load_settings_from_toml()          # auto-detects root
    settings = load_settings_from_toml("/my/project")

The loader is non-mandatory: if no TOML file is found or the relevant section
is absent, it falls back to the standard ``Settings()`` behaviour.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .settings import Settings

__all__ = ["load_settings_from_toml", "load_settings_from_toml_file"]

# Section key searched in robot.toml and pyproject.toml
_PYPROJECT_KEY = "tool.robot-optimizer"

# Candidate TOML filenames, in search order
_CANDIDATE_FILES = ("robot.toml", "pyproject.toml")


def _find_toml_root(start: Path) -> Path | None:
    """Walk upward from *start* to find a directory containing a TOML file.

    Returns the first parent directory that contains ``robot.toml`` or
    ``pyproject.toml``, or ``None`` if none found.
    """
    for directory in [start, *start.parents]:
        for name in _CANDIDATE_FILES:
            if (directory / name).is_file():
                return directory
    return None


def _read_optimizer_section(toml_path: Path) -> dict[str, Any] | None:
    """Read ``[tool.robot-optimizer]`` from a TOML file.

    Returns the section dict or ``None`` when not found / not parseable.
    """
    try:
        with open(toml_path, "rb") as fh:
            data = tomllib.load(fh)
    except Exception:
        return None

    # Navigate nested keys: "tool" → "robot-optimizer"
    section: Any = data
    for key in ["tool", "robot-optimizer"]:
        if not isinstance(section, dict) or key not in section:
            return None
        section = section[key]

    return section if isinstance(section, dict) else None


def load_settings_from_toml(
    project_root: str | Path | None = None,
    **overrides: Any,
) -> Settings:
    """Create a ``Settings`` instance, merging values from TOML config.

    Priority order (highest to lowest):
    1. ``**overrides`` kwargs (direct Python arguments)
    2. Environment variables (``ROBOT_OPTIMIZER_*``)
    3. ``[tool.robot-optimizer]`` section in ``robot.toml`` / ``pyproject.toml``
    4. Built-in defaults

    Args:
        project_root: Directory to search for TOML config.  Defaults to the
            current working directory.
        **overrides: Additional keyword arguments forwarded to ``Settings``.

    Returns:
        Configured :class:`Settings` instance.
    """
    if project_root is None:
        project_root = Path.cwd()
    else:
        project_root = Path(project_root)

    toml_config: dict[str, Any] = {}

    root = _find_toml_root(project_root)
    if root is not None:
        for name in _CANDIDATE_FILES:
            section = _read_optimizer_section(root / name)
            if section:
                toml_config = section
                break

    # Merge: overrides win over TOML, TOML wins over defaults
    merged = {**toml_config, **overrides}
    settings = Settings(**merged)
    settings.validate_settings()
    return settings


def load_settings_from_toml_file(
    file_path: str | Path,
    **overrides: Any,
) -> Settings:
    """Load ``Settings`` from an explicit TOML file.

    Unlike ``load_settings_from_toml``, this function loads config from the
    exact file specified, not by searching a directory. Useful for CLI --config
    arguments where the user provides an explicit file path.

    Args:
        file_path: Path to the TOML config file.
        **overrides: Additional keyword arguments forwarded to ``Settings``.

    Returns:
        Configured :class:`Settings` instance.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is invalid TOML or missing the config section.
    """
    file_path = Path(file_path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Config file not found: {file_path}")

    try:
        with open(file_path, "rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML in config file {file_path}: {exc}") from exc

    toml_config: dict[str, Any] = {}
    section: Any = data
    for key in ["tool", "robot-optimizer"]:
        if not isinstance(section, dict) or key not in section:
            break
        section = section[key]

    if isinstance(section, dict):
        toml_config = section

    # Merge: overrides win over TOML, TOML wins over defaults
    merged = {**toml_config, **overrides}
    settings = Settings(**merged)
    settings.validate_settings()
    return settings
