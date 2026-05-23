# src/robot_optimizer_core/entrypoints/cli/_baseline.py
"""Baseline support for the analyze subcommand.

A baseline is a JSON file that records a snapshot of findings.  On subsequent
runs, any finding whose fingerprint matches a baseline entry is suppressed so
only *new* regressions are reported.

Identity model
--------------
Baseline entries store ``Finding.fingerprint`` (SHA-256 of pattern_type +
file_path + line + message[:120], truncated to 16 hex chars).  This is the
same stable identity used by watch-mode diffs so both subsystems agree on
what constitutes "the same finding."

Legacy files (pre-fingerprint format) stored
``(relative_file_path, pattern_type_name, line)`` triples.  They are
read-compatible via :func:`_legacy_key`; new writes always use fingerprints.

The ``base`` parameter on :func:`save_baseline` and :func:`load_baseline`
controls the working directory used for path relativisation.  It defaults to
``Path.cwd()`` so existing callers are unaffected, but tests can inject a
stable path instead of monkeypatching ``os.getcwd``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...domain.value_objects import Finding

# A baseline key is a fingerprint string.
BaselineKey = str


def _legacy_key(entry: dict) -> str | None:
    """Convert an old-format baseline entry to a fingerprint-compatible string.

    Old entries stored ``(file_path, pattern_type, line)``; we emit a
    synthetic key that won't collide with any real fingerprint so legacy
    entries stay harmlessly inactive rather than crashing.
    """
    try:
        return f"legacy:{entry['file_path']}:{entry['pattern_type']}:{entry['line']}"
    except (KeyError, TypeError):
        return None


def load_baseline(path: Path, base: Path | None = None) -> set[BaselineKey]:
    """Load baseline keys from a JSON file.

    Args:
        path: Path to the baseline JSON file.
        base: Base directory for resolving relative paths stored in legacy
            entries.  Defaults to ``Path.cwd()``.

    Returns:
        Set of fingerprint strings.  Empty when the file does not exist yet.

    Raises:
        ValueError: If the file exists but cannot be parsed.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return set()
    except OSError as exc:
        raise ValueError(f"Cannot read baseline '{path}': {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cannot parse baseline '{path}': {exc}") from exc

    keys: set[BaselineKey] = set()
    for entry in data:
        if not isinstance(entry, dict):
            continue
        if "fingerprint" in entry:
            keys.add(str(entry["fingerprint"]))
        else:
            # Legacy format migration: synthesise a non-colliding key.
            legacy = _legacy_key(entry)
            if legacy:
                keys.add(legacy)
    return keys


def save_baseline(
    findings: list[Finding], path: Path, base: Path | None = None
) -> None:
    """Write *findings* to a baseline JSON file (creating it if necessary).

    Each entry stores ``fingerprint`` plus human-readable context fields so
    the file remains diffable in code review.  Paths are stored relative to
    *base* (default: ``Path.cwd()``) for portability across machines and CI.
    """
    base = base or Path.cwd()
    entries = [
        {
            "fingerprint": f.fingerprint,
            "file_path": _relative_posix(f.location.file_path, base),
            "pattern_type": f.pattern.type.name,
            "line": f.location.line,
        }
        for f in findings
    ]
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _relative_posix(file_path: Path, base: Path) -> str:
    """Return *file_path* as a POSIX string relative to *base*, or absolute."""
    try:
        return file_path.relative_to(base).as_posix()
    except ValueError:
        return file_path.as_posix()


def filter_baseline(
    findings: list[Finding],
    baseline: set[BaselineKey],
) -> tuple[list[Finding], list[Finding]]:
    """Partition *findings* into ``(new_findings, suppressed_findings)``.

    A finding is suppressed when its fingerprint matches a baseline entry.
    """
    new: list[Finding] = []
    suppressed: list[Finding] = []
    for f in findings:
        if f.fingerprint in baseline:
            suppressed.append(f)
        else:
            new.append(f)
    return new, suppressed
