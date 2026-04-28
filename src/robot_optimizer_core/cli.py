# src/robot_optimizer_core/cli.py
"""Command-line interface for robot-optimizer.

Usage::

    robot-optimizer analyze path/to/suite/
    robot-optimizer analyze tests/login.robot --format json
    robot-optimizer analyze tests/ --analyzers dead_code,sleep_detector
    robot-optimizer analyze tests/ --no-fail   # always exit 0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

from .api import analyze_directory, analyze_file
from .domain.value_objects import Finding, Severity
from .exceptions import AnalysisError
from .logging import get_logger

__all__ = ["main"]

logger = get_logger(__name__)

# Exit codes
_EXIT_OK = 0
_EXIT_FINDINGS = 1
_EXIT_ERROR = 2

# ANSI colour helpers (disabled when not a tty)
_COLOURS = {
    Severity.ERROR: "\033[31m",    # red
    Severity.WARNING: "\033[33m",  # yellow
    Severity.INFO: "\033[36m",     # cyan
}
_RESET = "\033[0m"


def _colour(text: str, severity: Severity) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{_COLOURS.get(severity, '')}{text}{_RESET}"


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _format_text(findings: list[Finding], path: Path) -> str:
    if not findings:
        return f"No findings in {path}\n"

    lines: list[str] = [f"\nAnalysis results for {path}  ({len(findings)} finding(s))\n"]
    for f in sorted(findings, key=lambda x: (str(x.location.file_path), x.location.line)):
        sev_label = _colour(f.severity.name.upper(), f.severity)
        loc = f"{f.location.file_path}:{f.location.line}"
        lines.append(f"  {sev_label}  {loc}")
        lines.append(f"    {f.pattern.name}: {f.message}")
        if f.pattern.recommendation != f.message:
            lines.append(f"    → {f.pattern.recommendation}")
        lines.append("")
    return "\n".join(lines)


def _format_json(findings: list[Finding]) -> str:
    records = [f.to_dict() for f in findings]
    # Pydantic objects aren't JSON-serialisable by default; use a custom encoder
    return json.dumps(records, indent=2, default=str)


# ---------------------------------------------------------------------------
# analyse subcommand
# ---------------------------------------------------------------------------

def _run_analyze(args: argparse.Namespace) -> int:
    path = Path(args.path)
    from .analyzers import BaseAnalyzer  # local import avoids circular import at module level

    analyzer_names: list[str | BaseAnalyzer] | None = (
        [a.strip() for a in args.analyzers.split(",") if a.strip()]
        if args.analyzers
        else None
    )

    try:
        if path.is_dir():
            results = analyze_directory(path, analyzers=analyzer_names)
            all_findings: list[Finding] = [f for fs in results.values() for f in fs]
        elif path.is_file():
            all_findings = analyze_file(path, analyzers=analyzer_names)
        else:
            print(f"error: path does not exist: {path}", file=sys.stderr)
            return _EXIT_ERROR

    except AnalysisError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_ERROR
    except ExceptionGroup as eg:
        for sub_exc in eg.exceptions:
            print(f"error: {sub_exc}", file=sys.stderr)
        return _EXIT_ERROR

    # Output
    output = (
        _format_json(all_findings)
        if args.format == "json"
        else _format_text(all_findings, path)
    )

    if args.output_file:
        Path(args.output_file).write_text(output, encoding="utf-8")
        print(f"Results written to {args.output_file}")
    else:
        print(output, end="")

    # Summary line on stderr so it doesn't pollute --format json stdout
    _print_summary(all_findings)

    if all_findings and not args.no_fail:
        return _EXIT_FINDINGS
    return _EXIT_OK


def _print_summary(findings: list[Finding]) -> None:
    if not findings:
        return
    counts: dict[str, int] = {}
    for f in findings:
        key = f.severity.name.upper()
        counts[key] = counts.get(key, 0) + 1
    parts = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    print(f"Summary: {len(findings)} finding(s)  [{parts}]", file=sys.stderr)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="robot-optimizer",
        description="Robot Framework test-suite analyser",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"%(prog)s {_get_version()}"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    analyze_cmd = sub.add_parser(
        "analyze",
        help="Analyse a Robot Framework file or directory",
    )
    analyze_cmd.add_argument(
        "path",
        help="Path to a .robot file or directory to analyse",
    )
    analyze_cmd.add_argument(
        "--analyzers",
        metavar="NAMES",
        help="Comma-separated list of analyser names (default: all built-in)",
        default=None,
    )
    analyze_cmd.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    analyze_cmd.add_argument(
        "--output-file",
        metavar="PATH",
        default=None,
        help="Write output to a file instead of stdout",
    )
    analyze_cmd.add_argument(
        "--no-fail",
        action="store_true",
        default=False,
        help="Always exit 0 even when findings are present",
    )

    return parser


def _get_version() -> str:
    try:
        from importlib.metadata import version
        return version("robot-framework-optimizer-core")
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> NoReturn:
    """Entry point registered as ``robot-optimizer`` in pyproject.toml."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    match args.command:
        case "analyze":
            code = _run_analyze(args)
        case _:
            parser.print_help()
            code = _EXIT_ERROR

    sys.exit(code)
