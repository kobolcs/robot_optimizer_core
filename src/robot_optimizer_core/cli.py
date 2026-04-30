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
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import NoReturn, TypedDict

from .api import analyze_directory, analyze_file
from .domain.value_objects import Finding, Severity
from .exceptions import AnalysisError
from .logging import configure_logging

__all__ = ["main"]

# Exit codes
_EXIT_OK = 0
_EXIT_FINDINGS = 1
_EXIT_ERROR = 2
_EXIT_PARTIAL = 3  # Partial failure (some files could not be analysed).

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
    """Produce a SARIF 2.1.0 JSON string from a list of findings.

    ``path`` is the analysed file or directory.  It is used to rewrite absolute
    artifact URIs to relative ones so SARIF output is portable across machines.
    """
    # Build unique rules list and deterministic result ordering from Finding helpers.
    seen_rules: dict[str, dict[str, object]] = {}
    results: list[dict[str, object]] = []

    # Use the directory itself as root; for a single-file analysis use the parent
    # directory so that relative artifact URIs remain meaningful (e.g. "suite.robot"
    # instead of ".").
    root = path.resolve() if path.is_dir() else path.parent.resolve()

    for finding in sorted(
        findings,
        key=lambda x: (
            str(x.location.file_path),
            x.location.line,
            x.pattern.name,
            x.message,
        ),
    ):
        result = finding.to_sarif()
        # Rewrite artifact URIs to paths relative to the analysed root so that
        # SARIF output is portable across machines.
        try:
            physical = result["locations"][0]["physicalLocation"]
            artifact = physical["artifactLocation"]
            file_uri = artifact.get("uri", "")
            candidate = Path(str(file_uri))
            artifact["uri"] = str(candidate.resolve().relative_to(root)).replace("\\", "/")
        except (KeyError, IndexError, ValueError, OSError, TypeError):
            # Keep the generated SARIF location untouched when path conversion
            # fails (e.g. the finding is outside the analysed root).
            pass

        rule_id = str(result.get("ruleId", ""))
        results.append(result)
        if rule_id not in seen_rules:
            rule: dict[str, object] = {
                "id": rule_id,
                "name": finding.pattern.name,
                "shortDescription": {"text": finding.pattern.name},
            }
            if finding.pattern.documentation_url:
                rule["helpUri"] = finding.pattern.documentation_url
            seen_rules[rule_id] = rule

    sarif = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "robot-optimizer",
                        "rules": [seen_rules[key] for key in sorted(seen_rules)],
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(sarif, indent=2, default=str)


def _format_html(findings: list[Finding], path: Path) -> str:
    class _CategoryInfo(TypedDict):
        count: int
        impact: str
        action: str

    def _display_path(file_path: Path) -> str:
        try:
            return str(file_path.resolve().relative_to(path.resolve()))
        except ValueError:
            return str(file_path)

    def _category_metadata(pattern_name: str) -> tuple[str, str, str]:
        normalized = pattern_name.lower()
        mappings = [
            (
                ("sleep",),
                "Stability / flakiness risk",
                "Fixed sleeps increase execution variance and flaky outcomes.",
                "Replace fixed sleeps with condition-based explicit waits.",
            ),
            (
                ("unused keyword",),
                "Maintainability / legacy debt",
                "Unused legacy keywords create noise and increase maintenance cost.",
                "Remove or confirm legacy keywords and archive obsolete helpers.",
            ),
            (
                ("documentation",),
                "Knowledge transfer / onboarding risk",
                "Missing documentation slows onboarding and raises review effort.",
                "Add concise business-focused documentation to critical tests and keywords.",
            ),
            (
                ("hardcoded",),
                "Environment/configuration risk",
                "Hardcoded values reduce portability between environments.",
                "Move environment-specific data into variables or configuration.",
            ),
            (
                ("tag",),
                "Governance / test selection risk",
                "Tag inconsistency weakens filtering, reporting, and release gates.",
                "Normalize tag taxonomy and enforce conventions in review checks.",
            ),
            (
                ("naming",),
                "Readability / consistency risk",
                "Naming inconsistency reduces readability and increases review friction.",
                "Adopt naming standards and align keywords/tests incrementally.",
            ),
            (
                ("setup", "teardown"),
                "Structure / duplication risk",
                "Setup/teardown issues can duplicate logic and hide dependencies.",
                "Refactor shared setup/teardown behavior into reusable keywords.",
            ),
        ]
        for keywords, category, impact, action in mappings:
            if any(keyword in normalized for keyword in keywords):
                return (category, impact, action)
        return (
            "General quality risk",
            "General quality issues can accumulate into delivery and maintenance cost.",
            "Review and remediate recurring findings as part of sprint quality work.",
        )

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    sev_counts = {"ERROR": 0, "WARNING": 0, "INFO": 0}
    affected_files: set[str] = set()
    category_summary: dict[str, _CategoryInfo] = {}
    category_groups: dict[str, list[Finding]] = {}

    for finding in findings:
        sev_counts[finding.severity.name.upper()] += 1
        display_path = _display_path(finding.location.file_path)
        affected_files.add(display_path)
        category, impact, action = _category_metadata(finding.pattern.name)
        category_groups.setdefault(category, []).append(finding)
        if category not in category_summary:
            category_summary[category] = {
                "count": 0,
                "impact": impact,
                "action": action,
            }
        category_summary[category]["count"] = int(category_summary[category]["count"]) + 1

    if sev_counts["ERROR"] > 0 or sev_counts["WARNING"] >= 10:
        health_status = "High Risk"
    elif sev_counts["WARNING"] > 0:
        health_status = "Moderate Risk"
    elif len(findings) == 0:
        health_status = "Healthy"
    elif len(findings) <= 5 and sev_counts["WARNING"] == 0 and sev_counts["ERROR"] == 0:
        health_status = "Low Risk"
    else:
        health_status = "Moderate Risk"

    severity_phrase = (
        "no significant"
        if not findings
        else "high" if health_status == "High Risk" else "moderate"
    )
    top_categories = sorted(
        category_summary.items(), key=lambda item: int(item[1]["count"]), reverse=True
    )
    sorted_category_names = [category_name for category_name, _ in top_categories]
    top_category_names = ", ".join(category for category, _ in top_categories[:3])
    summary_paragraph = (
        "The analyzed suite shows no significant maintainability or stability risk based on the selected checks. "
        "Continue periodic review to keep this baseline healthy."
        if not findings
        else "The analyzed suite shows "
        f"{severity_phrase} maintainability and stability risk. The most common issues are "
        f"{top_category_names}, which can increase maintenance cost, execution instability, and delivery risk if left unaddressed."
    )

    rows = []
    for finding in sorted(findings, key=lambda x: (str(x.location.file_path), x.location.line)):
        rows.append(
            "<tr>"
            f"<td>{escape(finding.severity.name.upper())}</td>"
            f"<td>{escape(_display_path(finding.location.file_path))}</td>"
            f"<td>{escape(str(finding.location.line))}</td>"
            f"<td>{escape(finding.pattern.name)}</td>"
            f"<td>{escape(finding.message)}</td>"
            f"<td>{escape(finding.pattern.recommendation)}</td>"
            "</tr>"
        )

    no_findings = "<p class='no-findings'>No findings were detected for the selected analyzers.</p>" if not findings else ""
    auto_fixable_count = sum(1 for finding in findings if finding.pattern.auto_fixable)
    table = ""
    if findings:
        table = (
            "<table><thead><tr><th>Severity</th><th>File</th><th>Line</th><th>Pattern</th>"
            "<th>Message</th><th>Recommendation</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )

    recommended_actions = [
        ("Replace fixed sleeps with explicit waits", "sleep"),
        ("Remove or confirm unused legacy keywords", "unused keyword"),
        ("Move hardcoded URLs/config into variables", "hardcoded"),
        ("Add documentation to business-critical tests/keywords", "documentation"),
        ("Normalize tags and naming conventions", "tag|naming"),
    ]
    action_items = []
    for label, matcher in recommended_actions:
        if matcher == "tag|naming":
            is_relevant = any(
                any(part in f.pattern.name.lower() for part in ("tag", "naming"))
                for f in findings
            )
        else:
            is_relevant = any(matcher in f.pattern.name.lower() for f in findings)
        if is_relevant:
            action_items.append(f"<li>{escape(label)}</li>")

    category_cards = "".join(
        "<div class='category-card'>"
        f"<h3>{escape(category)}</h3>"
        f"<p><strong>{meta['count']}</strong> finding(s)</p>"
        f"<p><strong>Why it matters:</strong> {escape(str(meta['impact']))}</p>"
        f"<p><strong>Suggested action:</strong> {escape(str(meta['action']))}</p>"
        "</div>"
        for category, meta in top_categories
    )

    grouped_sections: list[str] = []
    for category_name in sorted_category_names:
        items = category_groups.get(category_name, [])
        sorted_items: list[Finding] = sorted(
            items,
            key=lambda item: (str(item.location.file_path), item.location.line or 0),
        )
        item_cards = "".join(
            "<article class='finding-card'>"
            f"<span class='sev sev-{escape(item.severity.name.lower())}'>{escape(item.severity.name.upper())}</span> "
            f"<span>{escape(_display_path(item.location.file_path))}:{escape(str(item.location.line))}</span>"
            f"<p>{escape(item.message)}</p>"
            f"<p><strong>Recommendation:</strong> {escape(item.pattern.recommendation)}</p>"
            "</article>"
            for item in sorted_items
        )
        grouped_sections.append(f"<section><h3>{escape(category_name)}</h3>{item_cards}</section>")
    grouped_findings = "".join(grouped_sections)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Robot Framework Suite Health Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; color: #1f2937; background: #f8fafc; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 2rem; }}
    h1, h2 {{ margin-bottom: 0.4rem; }}
    .cover, .panel {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.25rem; margin-bottom: 1rem; }}
    .meta {{ color: #4b5563; }}
    .badge {{ display: inline-block; background: #e2e8f0; color: #0f172a; padding: 0.2rem 0.6rem; border-radius: 999px; font-weight: 600; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.75rem; margin: 1rem 0; }}
    .card, .category-card, .finding-card {{ border: 1px solid #d1d5db; border-radius: 8px; padding: 0.75rem 1rem; background: #fff; }}
    .sev {{ display: inline-block; padding: 0.1rem 0.4rem; border-radius: 6px; font-size: 0.75rem; font-weight: 700; }}
    .sev-error {{ background: #fee2e2; color: #991b1b; }}
    .sev-warning {{ background: #fef3c7; color: #92400e; }}
    .sev-info {{ background: #dbeafe; color: #1e3a8a; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    th, td {{ border: 1px solid #e5e7eb; padding: 0.5rem; text-align: left; vertical-align: top; }}
    th {{ background: #f3f4f6; }}
    .no-findings {{ padding: 0.75rem; background: #ecfeff; border: 1px solid #bae6fd; border-radius: 8px; }}
  </style>
</head>
<body>
<main>
  <section class="cover">
    <h1>Robot Framework Optimizer</h1>
    <h2>Robot Framework Suite Health Report</h2>
    <p>Static analysis summary for Robot Framework test-suite maintainability and stability.</p>
    <div class="meta">Analyzed path: {escape(str(path))}<br>Generated: {escape(timestamp)}</div>
  </section>
  <section class="panel">
    <h2>Executive summary</h2>
    <p>Total findings: {len(findings)} · Warnings/Errors: {sev_counts['WARNING'] + sev_counts['ERROR']} · Main risk categories: {escape(top_category_names or 'None')}</p>
    <p>{escape(summary_paragraph)}</p>
  </section>
  <section class="panel">
    <h2>Health status</h2>
    <p><span class="badge">{escape(health_status)}</span></p>
  </section>
  <section class="panel">
    <h2>Key metrics</h2>
    <div class="cards">
    <div class="card"><strong>ERROR</strong><div>{sev_counts['ERROR']}</div></div>
    <div class="card"><strong>WARNING</strong><div>{sev_counts['WARNING']}</div></div>
    <div class="card"><strong>INFO</strong><div>{sev_counts['INFO']}</div></div>
    <div class="card"><strong>Total findings</strong><div>{len(findings)}</div></div>
    <div class="card"><strong>Affected files</strong><div>{len(affected_files)}</div></div>
    <div class="card"><strong>Auto-fixable findings</strong><div>{auto_fixable_count}</div></div>
  </div>
  </section>
  <section class="panel"><h2>Risk categories</h2>{category_cards or '<p>No risk categories detected.</p>'}</section>
  <section class="panel"><h2>Recommended actions</h2><ol>{''.join(action_items) or '<li>Maintain current standards and monitor new findings.</li>'}</ol></section>
  <section class="panel"><h2>Findings by category</h2>{no_findings}{grouped_findings}</section>
  <section class="panel"><h2>Appendix — Detailed Findings</h2>
  {no_findings}
  {table}
</section>
</main>
</body>
</html>
"""


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

    # Parse --min-severity.
    severity_filter: Severity | None = None
    if args.min_severity:
        try:
            severity_filter = Severity.from_string(args.min_severity)
        except ValueError as exc:
            print(f"error: invalid --min-severity value: {exc}", file=sys.stderr)
            return _EXIT_ERROR

    # Load --config file.
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
            # Use error_handling="warn" so directory analysis can return partial results.
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
    elif args.format == "html":
        output = _format_html(all_findings, path)
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

    # Partial failures take precedence over findings exit code.
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
        ("Basic HTML report", True, True),
        ("Auto-fix workflows", False, "coming soon"),
        ("Advanced branded HTML reports", False, "coming soon"),
        ("PDF export", False, "coming soon"),
        ("Baseline diffing", False, "coming soon"),
        ("Historical trend reports", False, "coming soon"),
        ("Dashboards", False, "coming soon"),
        ("Priority support", False, "coming soon"),
    ]
    for name, free, pro in features:
        free_mark = "✓" if free else "—"
        pro_mark = pro if isinstance(pro, str) else ("✓" if pro else "—")
        print(f"  {name:<36} {free_mark:<10} {pro_mark}")
    print()

    if is_premium_installed():
        print(f"✓ {PREMIUM_PACKAGE_NAME} is installed.")
    else:
        print("Interested in Pro features?")
        print(f"  Join the waitlist: {UPGRADE_URL}")
        print("  (Pro launch planned Q3 2026)")

    return _EXIT_OK


# ---------------------------------------------------------------------------
# list-analyzers subcommand
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
    parser.add_argument("--verbose", action="store_true", help="Enable INFO logs to stderr")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logs to stderr")

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
        choices=["text", "json", "sarif", "html"],
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
        metavar="LEVEL",
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
