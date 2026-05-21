#!/usr/bin/env python3
"""Enforce per-file line-coverage minimums.

Reads the coverage.xml produced by pytest-cov and exits non-zero if any
tracked file falls below its configured threshold.  Thresholds are declared
in THRESHOLDS below; files not listed fall back to DEFAULT_MIN.

Usage:
    python ci/check_per_file_coverage.py              # uses coverage.xml at repo root
    python ci/check_per_file_coverage.py path/to/coverage.xml
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parent.parent

# Minimum line-coverage percentage applied to every file unless overridden.
DEFAULT_MIN = 80

# Per-file floor overrides.  Keys are forward-slash paths relative to the
# repo root.  Set to 0 to exclude a file entirely from the per-file check
# (it still counts toward the aggregate).
THRESHOLDS: dict[str, int] = {
    # Two-line entry-point shim — not meaningful to test in isolation.
    "src/robot_optimizer_core/__main__.py": 0,
}


def main(xml_path: Path) -> int:
    if not xml_path.exists():
        print(
            f"ERROR: {xml_path} not found — run 'pytest --cov' first",
            file=sys.stderr,
        )
        return 1

    tree = ET.parse(xml_path)  # noqa: S314
    root = tree.getroot()

    failures: list[tuple[str, float, int]] = []
    checked = 0

    for cls in root.iter("class"):
        filename = cls.get("filename", "")
        if not filename.startswith("src/"):
            continue
        key = filename.replace("\\", "/")
        minimum = THRESHOLDS.get(key, DEFAULT_MIN)
        if minimum == 0:
            continue
        checked += 1
        actual = float(cls.get("line-rate", "0")) * 100
        if actual < minimum:
            failures.append((key, actual, minimum))

    if not failures:
        lines_valid = int(root.get("lines-valid", 0))
        lines_covered = int(root.get("lines-covered", 0))
        print(
            f"OK  per-file coverage ({checked} files checked, "
            f"all >= {DEFAULT_MIN}%,  "
            f"{lines_covered}/{lines_valid} lines covered overall)"
        )
        return 0

    failures.sort(key=lambda t: t[1])
    col = max(len(p) for p, _, _ in failures)
    print("FAIL  per-file coverage — files below their minimum threshold:\n")
    print(f"  {'File':<{col}}   {'Actual':>7}   {'Min':>5}")
    print(f"  {'-' * col}   {'-' * 7}   {'-' * 5}")
    for path, actual, minimum in failures:
        print(f"  {path:<{col}}   {actual:>6.1f}%   {minimum:>4}%")
    print(
        f"\n{len(failures)} file(s) failed.  "
        "Raise coverage or lower the threshold in ci/check_per_file_coverage.py."
    )
    return 1


if __name__ == "__main__":
    xml = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "coverage.xml"
    sys.exit(main(xml))
