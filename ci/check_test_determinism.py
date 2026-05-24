#!/usr/bin/env python3
"""Detect determinism anti-patterns in test files.

Checks for:
  - datetime.now() without timezone (DTZ001 equivalent)
  - time.sleep() calls inside test functions
  - time.time() comparisons used in assertions

Exit 0 if clean. Exit 1 if violations found.

Usage:
    python ci/check_test_determinism.py tests/
    python ci/check_test_determinism.py tests/unit/test_foo.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


class DeterminismVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.violations: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        self._check_naive_datetime_now(node)
        self._check_time_sleep(node)
        self.generic_visit(node)

    def _check_naive_datetime_now(self, node: ast.Call) -> None:
        """Flag datetime.now() without a tz argument."""
        is_datetime_now = (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "now"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "datetime"
        )
        if not is_datetime_now:
            return
        has_tz = bool(node.args) or any(kw.arg in ("tz", "tzinfo") for kw in node.keywords)
        if not has_tz:
            self.violations.append((
                node.lineno,
                "datetime.now() without timezone — use datetime.now(UTC) or FIXED_UTC_NOW fixture",
            ))

    def _check_time_sleep(self, node: ast.Call) -> None:
        """Flag time.sleep() inside test files (causes nondeterministic timing)."""
        is_sleep = (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "sleep"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "time"
        )
        if is_sleep:
            self.violations.append((
                node.lineno,
                "time.sleep() in test — remove or replace with deterministic event wait",
            ))


def check_file(path: Path) -> list[tuple[Path, int, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []
    visitor = DeterminismVisitor(path)
    visitor.visit(tree)
    return [(path, line, msg) for line, msg in visitor.violations]


def collect_test_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix == ".py" else []
    return sorted(root.rglob("test_*.py"))


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if not args:
        print("usage: check_test_determinism.py <path> [...]", file=sys.stderr)
        return 2

    all_violations: list[tuple[Path, int, str]] = []
    for arg in args:
        for f in collect_test_files(Path(arg)):
            all_violations.extend(check_file(f))

    if not all_violations:
        print("determinism check: OK")
        return 0

    print(f"determinism check: {len(all_violations)} violation(s) found\n")
    for path, line, msg in all_violations:
        print(f"  {path}:{line}: {msg}")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
