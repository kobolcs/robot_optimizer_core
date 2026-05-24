# src/robot_optimizer_core/entrypoints/cli/_parser.py
"""Argument parser for robot-optimizer CLI."""

from __future__ import annotations

import argparse


def _get_version() -> str:
    """Return the installed package version string, or ``"unknown"`` if not found."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("robot-framework-optimizer-core")
    except PackageNotFoundError:
        return "unknown"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="robot-optimizer",
        description="Robot Framework test-suite analyser",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {_get_version()}"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable INFO logs to stderr"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable DEBUG logs to stderr"
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
        choices=["text", "json", "sarif", "html", "junit"],
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
    # --min-severity flag
    analyze_cmd.add_argument(
        "--min-severity",
        choices=["INFO", "WARNING", "ERROR"],
        default=None,
        help=(
            "Only report findings at or above this severity "
            "(INFO, WARNING, ERROR). Default: all severities."
        ),
    )
    # --config flag
    analyze_cmd.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help=(
            "Path to a TOML configuration file (robot.toml or pyproject.toml). "
            "Overrides settings defaults."
        ),
    )
    analyze_cmd.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Disable the file-hash result cache for this run.",
    )
    analyze_cmd.add_argument(
        "--clear-cache",
        action="store_true",
        default=False,
        help="Clear the result cache before analysing.",
    )
    analyze_cmd.add_argument(
        "--watch",
        action="store_true",
        default=False,
        help="Watch mode: re-analyze on file save and show diff (requires watchdog library)",
    )
    analyze_cmd.add_argument(
        "--baseline",
        metavar="FILE",
        default=None,
        help=(
            "Path to a baseline JSON file.  On first run (or when the file "
            "does not exist) all findings are written to the file and the "
            "command exits 0.  On subsequent runs, findings that match a "
            "baseline entry are suppressed; only new findings are reported."
        ),
    )
    analyze_cmd.add_argument(
        "--update-baseline",
        action="store_true",
        default=False,
        help="Refresh the baseline file with the current run's findings.",
    )

    # -- list-analyzers subcommand ---------------------------------
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

    # -- diagnose subcommand -------------------------------------------------
    sub.add_parser(
        "diagnose",
        help="Print a JSON diagnostic report of the current environment",
    )

    return parser
