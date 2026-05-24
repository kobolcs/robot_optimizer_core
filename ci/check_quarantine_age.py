#!/usr/bin/env python3
"""Report quarantined tests and flag any that have been quarantined more than MAX_DAYS.

Reads all test_*.py files looking for @pytest.mark.quarantine decorators and
extracts the 'reason' string. Reasons must contain a GitHub issue URL or ticket
reference for tracking. Tests older than MAX_DAYS (measured from 'since:' tag
in the reason) are flagged as overdue.

Exit 0 if all quarantined tests are within budget.
Exit 1 if any test exceeds the maximum quarantine age.

Usage:
    python ci/check_quarantine_age.py tests/
"""

from __future__ import annotations

import ast
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path

MAX_DAYS = 14
_SINCE_PATTERN = re.compile(r"since:(\d{4}-\d{2}-\d{2})")
_TODAY = date.today()


def _extract_quarantine_reasons(path: Path) -> list[tuple[int, str]]:
    """Return (line, reason) for every @pytest.mark.quarantine decorator in path."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    results = []
    for node in ast.walk(tree):
        decorators = getattr(node, "decorator_list", [])
        for dec in decorators:
            if not isinstance(dec, ast.Call):
                continue
            func = dec.func
            is_quarantine = (
                (isinstance(func, ast.Attribute) and func.attr == "quarantine")
                or (isinstance(func, ast.Name) and func.id == "quarantine")
            )
            if not is_quarantine:
                continue
            reason = ""
            for kw in dec.keywords:
                if kw.arg == "reason" and isinstance(kw.value, ast.Constant):
                    reason = str(kw.value.value)
            results.append((dec.lineno, reason))

    return results


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if not args:
        print("usage: check_quarantine_age.py <test-dir> [...]", file=sys.stderr)
        return 2

    report_lines: list[str] = ["Quarantine Report", "=" * 40]
    overdue: list[str] = []
    total = 0

    for arg in args:
        root = Path(arg)
        files = sorted(root.rglob("test_*.py")) if root.is_dir() else [root]
        for f in files:
            for line, reason in _extract_quarantine_reasons(f):
                total += 1
                since_match = _SINCE_PATTERN.search(reason)
                if since_match:
                    since = datetime.strptime(since_match.group(1), "%Y-%m-%d").replace(tzinfo=UTC).date()
                    age = (_TODAY - since).days
                    status = f"OVERDUE ({age}d)" if age > MAX_DAYS else f"ok ({age}d)"
                    if age > MAX_DAYS:
                        overdue.append(f"{f}:{line}")
                else:
                    status = "NO since: date — add 'since:YYYY-MM-DD' to reason"
                    overdue.append(f"{f}:{line}")

                report_lines.append(f"  {f}:{line}  [{status}]  {reason[:80]}")

    report_lines.append("")
    report_lines.append(f"Total quarantined: {total}")
    report_lines.append(f"Overdue (>{MAX_DAYS}d): {len(overdue)}")

    report_text = "\n".join(report_lines)
    print(report_text)

    Path("quarantine-report.txt").write_text(report_text, encoding="utf-8")

    if overdue:
        print(f"\nERROR: {len(overdue)} test(s) exceed the {MAX_DAYS}-day quarantine limit.")
        print("Delete them or fix and promote. Keeping indefinitely quarantined tests")
        print("defeats the quarantine budget policy.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
