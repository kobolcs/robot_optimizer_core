# src/robot_optimizer_core/cli.py
"""Command-line interface for robot-optimizer.

Usage::

    robot-optimizer analyze path/to/suite/
    robot-optimizer analyze tests/login.robot --format json
    robot-optimizer analyze tests/ --analyzers dead_code,sleep_detector
    robot-optimizer analyze tests/ --no-fail           # always exit 0
    robot-optimizer analyze tests/ --min-severity WARNING
    robot-optimizer analyze tests/ --config robot.toml
    robot-optimizer list-analyzers
    robot-optimizer list-analyzers --format json
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
_EXIT_PARTIAL = 3  # Task 19: partial failure (some files could not be analysed)

# ANSI colour helpers (disabled when not a tty)
_COLOURS = {
    Severity.ERROR: "\033[31m",  # red
    Severity.WARNING: "\033[33m",  # yellow
    Severity.INFO: "\033[36m",  # cyan
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

    lines: list[str] = [
        f"\nAnalysis results for {path}  ({len(findings)} finding(s))\n"
    ]
    for f in sorted(
        findings, key=lambda x: (str(x.location.file_path), x.location.line)
    ):
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


def _format_sarif(findings: list[Finding], path: Path) -> str:
    """Produce a SARIF 2.1.0 JSON string from a list of findings."""
    _SEV_MAP = {
        Severity.ERROR: "error",
        Severity.WARNING: "warning",
        Severity.INFO: "note",
    }

    # Build unique rules list
    seen_rules: dict[str, dict[str, object]] = {}
    for f in findings:
        rule_id = f.pattern.name.replace(" ", "_").lower()
        if rule_id not in seen_rules:
            seen_rules[rule_id] = {
                "id": rule_id,
                "name": f.pattern.name,
                "shortDescription": {"text": f.pattern.name},
                "helpUri": str(path),
            }

    results = []
    for f in findings:
        rule_id = f.pattern.name.replace(" ", "_").lower()
        results.append(
            {
                "ruleId": rule_id,
                "level": _SEV_MAP.get(f.severity, "note"),
                "message": {"text": f.message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": str(f.location.file_path),
                            },
                            "region": {"startLine": f.location.line or 1},
                        }
                    }
                ],
            }
        )

    sarif = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "robot-optimizer",
                        "rules": list(seen_rules.values()),
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(sarif, indent=2, default=str)


# ---------------------------------------------------------------------------
# analyse subcommand
# ---------------------------------------------------------------------------


def _run_analyze(args: argparse.Namespace) -> int:
    path = Path(args.path)
    from .analyzers import (
        BaseAnalyzer,  # local import avoids circular import at module level
    )

    analyzer_names: list[str | BaseAnalyzer] | None = (
        [a.strip() for a in args.analyzers.split(",") if a.strip()]
        if args.analyzers
        else None
    )

    # Task 17: parse --min-severity
    severity_filter: Severity | None = None
    if args.min_severity:
        try:
            severity_filter = Severity.from_string(args.min_severity)
        except ValueError as exc:
            print(f"error: invalid --min-severity value: {exc}", file=sys.stderr)
            return _EXIT_ERROR

    # Task 18: load --config file
    settings = None
    if getattr(args, "config", None):
        try:
            from .config.toml_loader import load_settings_from_toml

            settings = load_settings_from_toml(Path(args.config).parent)
        except Exception as exc:
            print(f"error: failed to load config '{args.config}': {exc}", file=sys.stderr)
            return _EXIT_ERROR

    partial_failure = False

    try:
        if path.is_dir():
            # Task 15+19: use error_handling="warn" to get partial results
            results = analyze_directory(
                path,
                analyzers=analyzer_names,
                settings=settings,
                severity_filter=severity_filter,
                error_handling="warn",
            )
            # Check if we had partial failures
            partial_failure = bool(getattr(results, "errors", []))
            all_findings: list[Finding] = [f for fs in results.values() for f in fs]
        elif path.is_file():
            all_findings = analyze_file(
                path,
                analyzers=analyzer_names,
                settings=settings,
                severity_filter=severity_filter,
            )
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
    output: str
    if args.format == "json":
        output = _format_json(all_findings)
    elif args.format == "sarif":
        output = _format_sarif(all_findings, path)
    else:
        output = _format_text(all_findings, path)

    if args.output_file:
        try:
            Path(args.output_file).write_text(output, encoding="utf-8")
        except OSError as exc:
            print(
                f"error: could not write output file {args.output_file}: {exc}",
                file=sys.stderr,
            )
            return _EXIT_ERROR
        print(f"Results written to {args.output_file}")
    else:
        print(output, end="")

    # Summary line on stderr so it doesn't pollute --format json stdout
    _print_summary(all_findings)

    # Task 19: partial failure takes precedence over findings exit code
    if partial_failure:
        return _EXIT_PARTIAL

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
# upgrade subcommand
# ---------------------------------------------------------------------------


def _run_upgrade(args: argparse.Namespace) -> int:  # noqa: ARG001
    from .premium import PREMIUM_PACKAGE_NAME, UPGRADE_URL, is_premium_installed

    version = _get_version()

    print(f"Robot Framework Optimizer  v{version}")
    print("=" * 50)
    print()
    print("Feature Comparison:")
    print()
    print(f"{'Feature':<38} {'Free':<10} {'Pro'}")
    print("-" * 55)
    features = [
        ("Dead code detection", True, True),
        ("Sleep pattern analysis", True, True),
        ("Flakiness detection", True, True),
        ("Naming convention checks", True, True),
        ("Hardcoded value detection", True, True),
        ("Custom analyzer plugins", True, True),
        ("SARIF output format", True, True),
        ("Auto-fix suggestions", False, True),
        ("HTML / PDF reports", False, True),
        ("Baseline diffing", False, True),
        ("CI/CD dashboard integration", False, True),
        ("Priority support", False, True),
    ]
    for name, free, pro in features:
        free_mark = "✓" if free else "—"
        pro_mark = "✓" if pro else "—"
        print(f"  {name:<36} {free_mark:<10} {pro_mark}")
    print()

    if is_premium_installed():
        print(f"✓ {PREMIUM_PACKAGE_NAME} is installed.")
    else:
        print("Upgrade to Pro:")
        print(f"  pip install {PREMIUM_PACKAGE_NAME}")
        print(f"  More info: {UPGRADE_URL}")

    return _EXIT_OK


# ---------------------------------------------------------------------------
# list-analyzers subcommand (Task 16)
# ---------------------------------------------------------------------------


def _run_list_analyzers(args: argparse.Namespace) -> int:
    from .analyzers import get_analyzer_registry

    registry = get_analyzer_registry()
    names = registry.list()

    if args.format == "json":
        records = []
        for name in names:
            info = registry.get_info(name)
            records.append(info)
        print(json.dumps(records, indent=2))
    else:
        print(f"Available analyzers ({len(names)}):\n")
        for name in names:
            try:
                info = registry.get_info(name)
                tags = info.get("tags", "")
                version = info.get("version", "?")
                desc = info.get("description", "")
                print(f"  {name}  [v{version}]")
                print(f"    {desc}")
                if tags:
                    print(f"    Tags: {tags}")
                print()
            except Exception as exc:
                print(f"  {name}  (error loading info: {exc})")

    return _EXIT_OK


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="robot-optimizer",
        description="Robot Framework test-suite analyser",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {_get_version()}"
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # -- analyze subcommand --------------------------------------------------
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
        choices=["text", "json", "sarif"],
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
    # Task 17: --min-severity flag
    analyze_cmd.add_argument(
        "--min-severity",
        metavar="LEVEL",
        default=None,
        help=(
            "Only report findings at or above this severity "
            "(INFO, WARNING, ERROR). Default: all severities."
        ),
    )
    # Task 18: --config flag
    analyze_cmd.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help=(
            "Path to a TOML configuration file (robot.toml or pyproject.toml). "
            "Overrides settings defaults."
        ),
    )

    # -- list-analyzers subcommand (Task 16) ---------------------------------
    list_cmd = sub.add_parser(
        "list-analyzers",
        help="List available analyzers with their description and tags",
    )
    list_cmd.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    # -- upgrade subcommand --------------------------------------------------
    sub.add_parser(
        "upgrade",
        help="Show feature comparison and upgrade information",
    )

    return parser


def _get_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("robot-framework-optimizer-core")
    except PackageNotFoundError:
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
        case "list-analyzers":
            code = _run_list_analyzers(args)
        case "upgrade":
            code = _run_upgrade(args)
        case _:
            parser.print_help()
            code = _EXIT_ERROR

    sys.exit(code)
