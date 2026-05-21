# src/robot_optimizer_core/cli/__init__.py
"""Command-line interface for robot-optimizer.

Provides the ``robot-optimizer`` entry-point with the following subcommands:

- ``analyze``        — analyse a ``.robot`` / ``.resource`` file or directory
- ``list-analyzers`` — list available analyzers with descriptions and tags
- ``upgrade``        — show free-vs-Pro feature comparison and upgrade info

Example:
    Basic usage::

        robot-optimizer analyze path/to/suite/
        robot-optimizer analyze tests/login.robot --format json
        robot-optimizer analyze tests/ --analyzers dead_code,sleep_detector
        robot-optimizer analyze tests/ --no-fail
        robot-optimizer analyze tests/ --min-severity WARNING
        robot-optimizer analyze tests/ --config robot.toml
        robot-optimizer analyze tests/ --watch
        robot-optimizer list-analyzers
        robot-optimizer list-analyzers --format json

Exit codes:
    0 (OK):       No findings, or ``--no-fail`` was passed.
    1 (FINDINGS): One or more findings at or above the minimum severity.
    2 (ERROR):    Fatal error — file not found, I/O failure, bad config, etc.
    3 (PARTIAL):  Analysis completed but some files could not be analysed
                  (``error_handling="warn"`` mode; partial results are still
                  written to the output).
"""

from __future__ import annotations

import sys
from typing import NoReturn

from ..logging import configure_logging
from ._commands import _EXIT_ERROR, _run_analyze, _run_list_analyzers, _run_upgrade
from ._parser import _build_parser

__all__ = ["main"]


def _ensure_utf8_streams() -> None:
    """Reconfigure stdout/stderr to UTF-8 so non-ASCII output works on Windows.

    The CLI emits Unicode characters such as em-dashes and arrows. On Windows
    the default console encoding is cp1252, which raises ``UnicodeEncodeError``
    when these are written. Python 3.7+ exposes ``reconfigure`` on TextIOWrapper
    streams; use it defensively (the streams may have been replaced by a test
    runner with an object that does not support reconfigure).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                # Stream is already detached or doesn't support encoding changes;
                # fall back silently rather than crash before argument parsing.
                pass


def main(argv: list[str] | None = None) -> NoReturn:
    """Entry point registered as ``robot-optimizer`` in pyproject.toml."""
    _ensure_utf8_streams()
    parser = _build_parser()
    args = parser.parse_args(argv)

    log_level = "WARNING"
    if getattr(args, "debug", False):
        log_level = "DEBUG"
    elif getattr(args, "verbose", False):
        log_level = "INFO"
    configure_logging(level=log_level, format_json=False)

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
