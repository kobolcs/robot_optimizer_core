# src/robot_optimizer_core/entrypoints/cli/_baseline.py
"""Baseline support for the analyze subcommand.

A baseline is a JSON file that records a snapshot of findings.  On
subsequent runs, any finding whose (file_path, pattern_type, line) triple
matches a baseline entry is suppressed so only *new* regressions are
reported.
"""

from __future__ import annotations

import json
from pathlib import Path

from ...domain.value_objects import Finding

# Uniquely identifies a finding for suppression: (posix file path, pattern type name, line).
BaselineKey = tuple[str, str, int]


def _finding_key(f: Finding) -> BaselineKey:
    return (
        f.location.file_path.as_posix(),
        f.pattern.type.name,
        f.location.line,
    )


def load_baseline(path: Path) -> set[BaselineKey]:
    """Load baseline keys from a JSON file.

    Returns an empty set when the file does not exist yet (first run).

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
        try:
            keys.add((entry["file_path"], entry["pattern_type"], int(entry["line"])))
        except (KeyError, TypeError, ValueError):
            continue
    return keys


def save_baseline(findings: list[Finding], path: Path) -> None:
    """Write *findings* to a baseline JSON file, creating it if necessary."""
    entries = [
        {
            "file_path": f.location.file_path.as_posix(),
            "pattern_type": f.pattern.type.name,
            "line": f.location.line,
        }
        for f in findings
    ]
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def filter_baseline(
    findings: list[Finding],
    baseline: set[BaselineKey],
) -> tuple[list[Finding], list[Finding]]:
    """Partition *findings* into (new_findings, suppressed_findings).

    A finding is *suppressed* when its key matches an entry in the baseline.
    """
    new: list[Finding] = []
    suppressed: list[Finding] = []
    for f in findings:
        if _finding_key(f) in baseline:
            suppressed.append(f)
        else:
            new.append(f)
    return new, suppressed
