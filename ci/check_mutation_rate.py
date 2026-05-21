#!/usr/bin/env python3
"""Enforce a maximum mutant survival rate after a mutmut run.

Reads the .mutmut-cache SQLite database written by mutmut and exits
non-zero when the survival rate exceeds MAX_SURVIVAL_RATE.

Usage:
    python ci/check_mutation_rate.py [--max-rate 0.20]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_DEFAULT_MAX_RATE = 0.20
_CACHE_FILE = Path(".mutmut-cache")

# Statuses that count as "tested" mutations (not skipped/untested).
_TESTED_STATUSES = {"survived", "killed", "timeout", "suspicious"}
# Statuses that count against us.
_BAD_STATUSES = {"survived", "timeout"}


def _load_counts(db: Path) -> dict[str, int]:
    if not db.exists():
        print(f"error: {db} not found — run mutmut first", file=sys.stderr)
        sys.exit(2)
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) FROM mutant GROUP BY status"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        print(f"error: cannot read {db}: {exc}", file=sys.stderr)
        sys.exit(2)
    finally:
        conn.close()
    return {row[0]: row[1] for row in rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-rate",
        type=float,
        default=_DEFAULT_MAX_RATE,
        metavar="RATE",
        help=f"Maximum allowed survival rate (default: {_DEFAULT_MAX_RATE:.0%})",
    )
    args = parser.parse_args(argv)

    counts = _load_counts(_CACHE_FILE)

    tested = sum(counts.get(s, 0) for s in _TESTED_STATUSES)
    bad = sum(counts.get(s, 0) for s in _BAD_STATUSES)
    killed = counts.get("killed", 0)
    survived = counts.get("survived", 0)
    timeout = counts.get("timeout", 0)
    suspicious = counts.get("suspicious", 0)
    skipped = counts.get("skipped", 0)

    print(f"Mutation results:")
    print(f"  Killed:     {killed}")
    print(f"  Survived:   {survived}")
    print(f"  Timeout:    {timeout}")
    print(f"  Suspicious: {suspicious}")
    print(f"  Skipped:    {skipped}")
    print(f"  Total tested: {tested}")

    if tested == 0:
        print("warning: no mutants were tested", file=sys.stderr)
        return 0

    rate = bad / tested
    threshold = args.max_rate
    print(f"\nSurvival rate: {rate:.1%}  (threshold: {threshold:.0%})")

    if rate > threshold:
        print(
            f"\nFAIL: {rate:.1%} survival rate exceeds {threshold:.0%} threshold",
            file=sys.stderr,
        )
        return 1

    print(f"OK: survival rate within threshold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
