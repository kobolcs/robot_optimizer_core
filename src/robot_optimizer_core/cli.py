# src/robot_optimizer_core/cli.py
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

import argparse
import json
import sys
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn, TypedDict

from .api import analyze_directory, analyze_file
from .cache import AnalysisCache
from .config.settings import Settings
from .domain.value_objects import Finding, Severity
from .exceptions import AnalysisError
from .logging import configure_logging

if TYPE_CHECKING:
    from .analyzers import BaseAnalyzer

__all__ = ["main"]

# Exit codes — keep in sync with the module docstring above.
_EXIT_OK = 0       # No findings (or --no-fail passed)
_EXIT_FINDINGS = 1  # One or more findings at/above min-severity
_EXIT_ERROR = 2    # Fatal error (missing file, bad config, I/O failure)
_EXIT_PARTIAL = 3  # Completed with some unanalysable files (error_handling="warn")

# Severity names (for JSON and HTML reports)
_SEV_ERROR = "ERROR"
_SEV_WARNING = "WARNING"
_SEV_INFO = "INFO"

# Health status labels
_HEALTH_HIGH_RISK = "High Risk"
_HEALTH_MODERATE_RISK = "Moderate Risk"
_HEALTH_LOW_RISK = "Low Risk"
_HEALTH_HEALTHY = "Healthy"
_PLACEHOLDER_COMING_SOON = "coming soon"

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


def _get_template_path() -> Path:
    """Get path to the HTML report template."""
    return Path(__file__).parent / "resources" / "report.html.j2"


def _render_html_template(context: dict[str, Any]) -> str:
    """Render HTML report using Jinja2 template.

    Args:
        context: Template variables

    Returns:
        Rendered HTML string
    """
    try:
        from jinja2 import Environment, FileSystemLoader
        from markupsafe import Markup
    except ImportError:
        # Fallback if jinja2 not available; use legacy rendering
        return _format_html_legacy(context)

    template_path = _get_template_path()
    if not template_path.exists():
        return _format_html_legacy(context)

    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=True,
    )
    # Mark HTML strings as safe so they don't get double-escaped
    # SAFETY: All values for these keys are either pre-escaped via html.escape()
    # in their respective _html_render_* functions, or are hardcoded constants
    # (_HTML_STYLES, _compute_no_findings_html). No user input is included.
    safe_context = context.copy()
    for key in (
        "action_items",
        "grouped_findings",
        "findings_table",
        "styles",
        "no_findings_html",
    ):
        if key in safe_context:
            value = safe_context[key]
            if isinstance(value, list):
                safe_context[key] = [
                    Markup(v) if isinstance(v, str) else v for v in value  # noqa: S704
                ]
            elif isinstance(value, str):
                safe_context[key] = Markup(value)  # noqa: S704
    template = env.get_template(template_path.name)
    return template.render(**safe_context)


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
            artifact["uri"] = str(candidate.resolve().relative_to(root)).replace(
                "\\", "/"
            )
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


class _CategoryInfo(TypedDict):
    count: int
    impact: str
    action: str


def _html_display_path(file_path: Path, root: Path) -> str:
    """Return file_path relative to root, or its string form if that fails."""
    try:
        return str(file_path.resolve().relative_to(root))
    except ValueError:
        return str(file_path)


# (pattern-name substrings, category, impact, action)
_PATTERN_CATEGORY_MAP: list[tuple[tuple[str, ...], str, str, str]] = [
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
        ("naming", "camelcase", "camel_case"),
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
_PATTERN_CATEGORY_DEFAULT = (
    "General quality risk",
    "General quality issues can accumulate into delivery and maintenance cost.",
    "Review and remediate recurring findings as part of sprint quality work.",
)


def _html_category_metadata(pattern_name: str) -> tuple[str, str, str]:
    """Return (category, impact, action) for an HTML report finding group."""
    normalized = pattern_name.lower()
    for keywords, category, impact, action in _PATTERN_CATEGORY_MAP:
        if any(kw in normalized for kw in keywords):
            return (category, impact, action)
    return _PATTERN_CATEGORY_DEFAULT


def _html_compute_stats(
    findings: list[Finding],
    path: Path,
) -> tuple[
    str,
    dict[str, int],
    set[str],
    dict[str, _CategoryInfo],
    dict[str, list[Finding]],
]:
    """Compute summary statistics used by the HTML report."""
    root = path.resolve() if path.is_dir() else path.parent.resolve()
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    sev_counts: dict[str, int] = {_SEV_ERROR: 0, _SEV_WARNING: 0, _SEV_INFO: 0}
    affected_files: set[str] = set()
    category_summary: dict[str, _CategoryInfo] = {}
    category_groups: dict[str, list[Finding]] = {}

    for finding in findings:
        sev_counts[finding.severity.name.upper()] += 1
        display_path = _html_display_path(finding.location.file_path, root)
        affected_files.add(display_path)
        category, impact, action = _html_category_metadata(finding.pattern.name)
        category_groups.setdefault(category, []).append(finding)
        if category not in category_summary:
            category_summary[category] = {
                "count": 0,
                "impact": impact,
                "action": action,
            }
        category_summary[category]["count"] = (
            int(category_summary[category]["count"]) + 1
        )

    return timestamp, sev_counts, affected_files, category_summary, category_groups


def _html_health_status(sev_counts: dict[str, int], findings: list[Finding]) -> str:
    """Classify the overall suite health into a display label."""
    if sev_counts[_SEV_ERROR] > 0 or sev_counts[_SEV_WARNING] >= 10:
        return _HEALTH_HIGH_RISK
    if sev_counts[_SEV_WARNING] > 0:
        return _HEALTH_MODERATE_RISK
    if not findings:
        return _HEALTH_HEALTHY
    if (
        len(findings) <= 5
        and sev_counts[_SEV_WARNING] == 0
        and sev_counts[_SEV_ERROR] == 0
    ):
        return _HEALTH_LOW_RISK
    return _HEALTH_MODERATE_RISK


def _html_render_category_cards(
    top_categories: list[tuple[str, _CategoryInfo]],
) -> str:
    """Render one card per risk category."""
    return "".join(
        "<div class='category-card'>"
        f"<h3>{escape(category)}</h3>"
        f"<p><strong>{meta['count']}</strong> finding(s)</p>"
        f"<p><strong>Why it matters:</strong> {escape(str(meta['impact']))}</p>"
        f"<p><strong>Suggested action:</strong> {escape(str(meta['action']))}</p>"
        "</div>"
        for category, meta in top_categories
    )


def _html_render_action_items(findings: list[Finding]) -> str:
    """Return an HTML fragment of <li> elements for relevant recommended actions."""
    recommended_actions = [
        ("Replace fixed sleeps with explicit waits", "sleep"),
        ("Remove or confirm unused legacy keywords", "unused keyword"),
        ("Move hardcoded URLs/config into variables", "hardcoded"),
        ("Add documentation to business-critical tests/keywords", "documentation"),
        ("Normalize tags and naming conventions", "tag|naming"),
    ]
    items: list[str] = []
    for label, matcher in recommended_actions:
        if matcher == "tag|naming":
            is_relevant = any(
                any(
                    part in f.pattern.name.lower()
                    for part in ("tag", "naming", "camelcase", "camel_case")
                )
                for f in findings
            )
        else:
            is_relevant = any(matcher in f.pattern.name.lower() for f in findings)
        if is_relevant:
            items.append(f"<li>{escape(label)}</li>")
    return "".join(items)


def _html_render_grouped_findings(
    sorted_category_names: list[str],
    category_groups: dict[str, list[Finding]],
    root: Path,
) -> str:
    """Render per-category finding cards grouped into <section> elements."""
    sections: list[str] = []
    for category_name in sorted_category_names:
        sorted_items = sorted(
            category_groups.get(category_name, []),
            key=lambda item: (str(item.location.file_path), item.location.line or 0),
        )
        item_cards = "".join(
            "<article class='finding-card'>"
            f"<span class='sev sev-{escape(item.severity.name.lower())}'>"
            f"{escape(item.severity.name.upper())}</span> "
            f"<span>{escape(_html_display_path(item.location.file_path, root))}"
            f":{escape(str(item.location.line))}</span>"
            f"<p>{escape(item.message)}</p>"
            f"<p><strong>Recommendation:</strong> {escape(item.pattern.recommendation)}</p>"
            "</article>"
            for item in sorted_items
        )
        sections.append(
            f"<section class='finding-section'><h3>{escape(category_name)}</h3>{item_cards}</section>"
        )
    return "".join(sections)


def _html_render_findings_table(findings: list[Finding], root: Path) -> str:
    """Render the appendix table of all findings sorted by file and line."""
    if not findings:
        return ""
    rows = [
        "<tr>"
        f"<td>{escape(f.severity.name.upper())}</td>"
        f"<td>{escape(_html_display_path(f.location.file_path, root))}</td>"
        f"<td>{escape(str(f.location.line))}</td>"
        f"<td>{escape(f.pattern.name)}</td>"
        f"<td>{escape(f.message)}</td>"
        f"<td>{escape(f.pattern.recommendation)}</td>"
        "</tr>"
        for f in sorted(
            findings, key=lambda x: (str(x.location.file_path), x.location.line)
        )
    ]
    return (
        "<table><thead><tr><th>Severity</th><th>File</th><th>Line</th><th>Pattern</th>"
        "<th>Message</th><th>Recommendation</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _compute_severity_phrase(findings: list[Finding], health_status: str) -> str:
    """Determine severity description based on findings and health status."""
    if not findings:
        return "no significant"
    if health_status == _HEALTH_HIGH_RISK:
        return "high"
    if health_status == _HEALTH_LOW_RISK:
        return "low"
    return "moderate"


def _compute_summary_paragraph(
    findings: list[Finding], severity_phrase: str, top_category_names: str
) -> str:
    """Compute the summary paragraph text for the report."""
    if not findings:
        return (
            "The analyzed suite shows no significant maintainability or stability risk "
            "based on the selected checks. Continue periodic review to keep this baseline healthy."
        )
    return (
        f"The analyzed suite shows {severity_phrase} maintainability and stability risk. "
        f"The most common issues are {top_category_names}, which can increase maintenance "
        "cost, execution instability, and delivery risk if left unaddressed."
    )


def _compute_no_findings_html(findings: list[Finding]) -> str:
    """Compute the HTML to display when no findings are present."""
    if not findings:
        return "<p class='no-findings'>No findings were detected for the selected analyzers.</p>"
    return ""


_HTML_STYLES = """\
    :root {
      --accent:      #0d9488;
      --accent-dark: #0a7a70;
      --accent-glow: #e6f7f5;
      --ink:         #1c1f26;
      --paper:       #f4f5f7;
      --dark-card:   #22262f;
      --muted:       #6b7280;
      --border:      #d1d5db;
      --warm:        #eaecef;
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'DM Sans', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: var(--paper);
      color: var(--ink);
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
    }
    main { max-width: 1100px; margin: 0 auto; padding: 2.5rem 1.5rem; }
    .cover {
      background: var(--dark-card);
      border-radius: 20px;
      padding: 2.5rem 2rem;
      margin-bottom: 1.5rem;
      position: relative;
      overflow: hidden;
    }
    .cover::before {
      content: "";
      position: absolute;
      inset: 0;
      background: radial-gradient(ellipse 60% 80% at 100% 0%, rgba(13,148,136,.35) 0%, transparent 70%);
      pointer-events: none;
    }
    .cover-eyebrow {
      font-family: 'Space Mono', ui-monospace, 'Cascadia Code', 'Fira Mono', monospace;
      font-size: .7rem; letter-spacing: .12em; text-transform: uppercase;
      color: var(--accent); margin-bottom: .5rem;
    }
    .cover h1 { font-size: 1.75rem; font-weight: 700; color: #fff; margin-bottom: .25rem; }
    .cover h2 { font-size: 1rem; font-weight: 400; color: rgba(255,255,255,.65); margin-bottom: 1rem; }
    .cover-meta {
      font-family: 'Space Mono', ui-monospace, 'Cascadia Code', 'Fira Mono', monospace;
      font-size: .72rem; color: rgba(255,255,255,.45); line-height: 1.8;
    }
    .panel {
      background: #fff; border: 1px solid var(--border); border-radius: 16px;
      padding: 1.5rem 1.75rem; margin-bottom: 1.25rem;
    }
    .panel h2 {
      font-size: 1rem; font-weight: 700; text-transform: uppercase; letter-spacing: .06em;
      color: var(--muted); margin-bottom: 1rem; padding-bottom: .5rem;
      border-bottom: 1px solid var(--warm);
    }
    .panel p { color: var(--ink); margin-bottom: .6rem; }
    .panel p:last-child { margin-bottom: 0; }
    .health-badge {
      display: inline-flex; align-items: center; gap: .5rem;
      padding: .45rem 1rem; border-radius: 999px;
      font-family: 'Space Mono', ui-monospace, 'Cascadia Code', 'Fira Mono', monospace;
      font-size: .85rem; font-weight: 700;
      background: var(--health-color-bg);
      color: var(--health-color);
      border: 1.5px solid var(--health-color-border);
    }
    .health-dot {
      width: 8px; height: 8px; border-radius: 50%;
      background: var(--health-color);
      box-shadow: 0 0 0 3px var(--health-color-glow);
    }
    .bento {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: .75rem; margin-top: .5rem;
    }
    .metric-card {
      background: var(--paper); border: 1px solid var(--border);
      border-radius: 12px; padding: 1rem; transition: border-color .15s;
    }
    .metric-card:hover { border-color: var(--accent); }
    .metric-card .metric-label {
      font-family: 'Space Mono', ui-monospace, 'Cascadia Code', 'Fira Mono', monospace;
      font-size: .68rem; letter-spacing: .06em; text-transform: uppercase;
      color: var(--muted); margin-bottom: .35rem;
    }
    .metric-card .metric-value { font-size: 1.75rem; font-weight: 700; color: var(--ink); line-height: 1; }
    .metric-card.accent { border-color: var(--accent); background: var(--accent-glow); }
    .metric-card.accent .metric-value { color: var(--accent-dark); }
    .category-grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: .75rem; margin-top: .5rem;
    }
    .category-card {
      background: var(--paper); border: 1px solid var(--border);
      border-radius: 12px; padding: 1rem 1.25rem;
      transition: box-shadow .15s, border-color .15s;
    }
    .category-card:hover { border-color: var(--accent); box-shadow: 0 4px 16px rgba(13,148,136,.1); }
    .category-card h3 { font-size: .9rem; font-weight: 700; color: var(--ink); margin-bottom: .5rem; }
    .category-card p { font-size: .82rem; color: var(--muted); margin-bottom: .35rem; line-height: 1.5; }
    .category-card strong { color: var(--ink); }
    ol { padding-left: 1.25rem; }
    ol li { padding: .4rem 0; font-size: .9rem; color: var(--ink); border-bottom: 1px solid var(--warm); }
    ol li:last-child { border-bottom: none; }
    section.finding-section { margin-bottom: 1rem; }
    section.finding-section h3 {
      font-size: .85rem; font-weight: 700; color: var(--accent-dark);
      margin-bottom: .5rem; padding: .25rem .6rem; background: var(--accent-glow);
      border-radius: 6px; display: inline-block;
    }
    .finding-card {
      border: 1px solid var(--border); border-radius: 10px;
      padding: .75rem 1rem; margin-bottom: .5rem; background: #fff; transition: border-color .15s;
    }
    .finding-card:hover { border-color: var(--accent); }
    .finding-card p { font-size: .85rem; color: var(--muted); margin-top: .35rem; }
    .finding-card .finding-loc {
      font-family: 'Space Mono', ui-monospace, 'Cascadia Code', 'Fira Mono', monospace;
      font-size: .75rem; color: var(--muted);
    }
    .sev {
      display: inline-block; padding: .15rem .5rem; border-radius: 6px;
      font-family: 'Space Mono', ui-monospace, 'Cascadia Code', 'Fira Mono', monospace;
      font-size: .68rem; font-weight: 700; letter-spacing: .04em;
    }
    .sev-error   { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
    .sev-warning { background: #fef3c7; color: #92400e; border: 1px solid #fcd34d; }
    .sev-info    { background: var(--accent-glow); color: var(--accent-dark); border: 1px solid #99d9d4; }
    .table-wrap { overflow-x: auto; margin-top: .75rem; }
    table { border-collapse: collapse; width: 100%; font-size: .82rem; }
    th, td { border: 1px solid var(--border); padding: .55rem .75rem; text-align: left; vertical-align: top; }
    th {
      background: var(--warm);
      font-family: 'Space Mono', ui-monospace, 'Cascadia Code', 'Fira Mono', monospace;
      font-size: .68rem; text-transform: uppercase; letter-spacing: .06em;
      color: var(--muted); font-weight: 700;
    }
    tr:hover td { background: var(--accent-glow); }
    .no-findings {
      display: flex; align-items: center; gap: .75rem;
      padding: 1rem 1.25rem; background: var(--accent-glow);
      border: 1px solid #99d9d4; border-radius: 10px;
      color: var(--accent-dark); font-weight: 600;
    }
    .no-findings::before { content: "✓"; font-size: 1.1rem; }"""


_HEALTH_COLORS: dict[str, tuple[str, str, str, str]] = {
    # status: (base, bg-alpha, border-alpha, glow-alpha) as hex colours
    _HEALTH_HIGH_RISK: ("#ef4444", "#ef44441a", "#ef444455", "#ef444433"),
    _HEALTH_MODERATE_RISK: ("#f59e0b", "#f59e0b1a", "#f59e0b55", "#f59e0b33"),
    _HEALTH_HEALTHY: ("#0d9488", "#0d94881a", "#0d948855", "#0d948833"),
    _HEALTH_LOW_RISK: ("#0d9488", "#0d94881a", "#0d948855", "#0d948833"),
}
_HEALTH_COLOR_DEFAULT = ("#6b7280", "#6b72801a", "#6b728055", "#6b728033")


def _format_html(findings: list[Finding], path: Path) -> str:
    """Format findings as HTML report using template-based rendering."""
    root = path.resolve() if path.is_dir() else path.parent.resolve()
    timestamp, sev_counts, affected_files, category_summary, category_groups = (
        _html_compute_stats(findings, path)
    )

    health_status = _html_health_status(sev_counts, findings)
    hc, hc_bg, hc_border, hc_glow = _HEALTH_COLORS.get(
        health_status, _HEALTH_COLOR_DEFAULT
    )

    top_categories = sorted(
        category_summary.items(), key=lambda item: int(item[1]["count"]), reverse=True
    )
    sorted_category_names = [name for name, _ in top_categories]
    top_category_names = ", ".join(cat for cat, _ in top_categories[:3])

    severity_phrase = _compute_severity_phrase(findings, health_status)
    summary_paragraph = _compute_summary_paragraph(
        findings, severity_phrase, top_category_names
    )
    no_findings_html = _compute_no_findings_html(findings)
    auto_fixable_count = sum(1 for f in findings if f.pattern.auto_fixable)

    action_items = _html_render_action_items(findings)
    grouped_findings = _html_render_grouped_findings(
        sorted_category_names, category_groups, root
    )
    table = _html_render_findings_table(findings, root)

    # Prepare template context
    context: dict[str, Any] = {
        "health_color": hc,
        "health_color_bg": hc_bg,
        "health_color_border": hc_border,
        "health_color_glow": hc_glow,
        "styles": _HTML_STYLES,
        "analyzed_path": str(path),
        "timestamp": timestamp,
        "health_status": health_status,
        "total_findings": len(findings),
        "error_count": sev_counts[_SEV_ERROR],
        "warning_count": sev_counts[_SEV_WARNING],
        "info_count": sev_counts[_SEV_INFO],
        "warning_error_count": sev_counts[_SEV_WARNING] + sev_counts[_SEV_ERROR],
        "affected_files_count": len(affected_files),
        "auto_fixable_count": auto_fixable_count,
        "top_categories": top_categories,
        "top_categories_str": top_category_names or "None",
        "summary_paragraph": summary_paragraph,
        "action_items": action_items,
        "no_findings_html": no_findings_html,
        "grouped_findings": [grouped_findings],
        "findings_table": table,
        "escape": escape,
    }

    return _render_html_template(context)


def _format_html_legacy(context: dict[str, Any]) -> str:
    """Legacy HTML rendering (fallback if template not available)."""
    # Use context dict to generate HTML the old way
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Robot Framework Suite Health Report</title>
  <style>
    :root {{
      --health-color: {context["health_color"]};
      --health-color-bg: {context["health_color_bg"]};
      --health-color-border: {context["health_color_border"]};
      --health-color-glow: {context["health_color_glow"]};
    }}
{context["styles"]}
  </style>
</head>
<body>
<main>
  <section class="cover">
    <div class="cover-eyebrow">Robot Framework Optimizer</div>
    <h1>Suite Health Report</h1>
    <h2>Static analysis · maintainability &amp; stability</h2>
    <div class="cover-meta">
      Analyzed: {escape(context["analyzed_path"])}<br>
      Generated: {escape(context["timestamp"])}
    </div>
  </section>

  <section class="panel">
    <h2>Health status</h2>
    <span class="health-badge"><span class="health-dot"></span>{escape(context["health_status"])}</span>
  </section>

  <section class="panel">
    <h2>Executive summary</h2>
    <p>Total findings: <strong>{context["total_findings"]}</strong> &nbsp;·&nbsp; Warnings/Errors: <strong>{context["warning_error_count"]}</strong> &nbsp;·&nbsp; Main risk categories: <strong>{escape(context["top_categories_str"])}</strong></p>
    <p>{escape(context["summary_paragraph"])}</p>
  </section>

  <section class="panel">
    <h2>Key metrics</h2>
    <div class="bento">
      <div class="metric-card"><div class="metric-label">Total findings</div><div class="metric-value">{context["total_findings"]}</div></div>
      <div class="metric-card"><div class="metric-label">ERROR</div><div class="metric-value">{context["error_count"]}</div></div>
      <div class="metric-card"><div class="metric-label">WARNING</div><div class="metric-value">{context["warning_count"]}</div></div>
      <div class="metric-card"><div class="metric-label">INFO</div><div class="metric-value">{context["info_count"]}</div></div>
      <div class="metric-card"><div class="metric-label">Affected files</div><div class="metric-value">{context["affected_files_count"]}</div></div>
      <div class="metric-card accent"><div class="metric-label">Auto-fixable findings</div><div class="metric-value">{context["auto_fixable_count"]}</div></div>
    </div>
  </section>

  <section class="panel">
    <h2>Risk categories</h2>
    <div class="category-grid">
      {_html_render_category_cards(context["top_categories"]) or "<p>No risk categories detected.</p>"}
    </div>
  </section>

  <section class="panel">
    <h2>Recommended actions</h2>
    <ol>
      {"".join(context["action_items"]) or "<li>Maintain current standards and monitor new findings.</li>"}
    </ol>
  </section>

  <section class="panel">
    <h2>Findings by category</h2>
    {context["no_findings_html"]}
    {"".join(context["grouped_findings"])}
  </section>

  <section class="panel">
    <h2>Appendix — Detailed Findings</h2>
    {context["no_findings_html"]}
    <div class="table-wrap">{context["findings_table"]}</div>
  </section>
</main>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# analyse subcommand
# ---------------------------------------------------------------------------


def _parse_analyzers(args: argparse.Namespace) -> list[str | BaseAnalyzer] | None:
    """Parse analyzer names from arguments."""
    if hasattr(args, "analyzers") and args.analyzers:
        return [a.strip() for a in args.analyzers.split(",") if a.strip()]
    return None


def _parse_severity(args: argparse.Namespace) -> Severity | None:
    """Parse and validate severity filter. Returns None on error or if not set."""
    if not args.min_severity:
        return None
    try:
        return Severity.from_string(args.min_severity)
    except ValueError as exc:
        print(f"error: invalid --min-severity value: {exc}", file=sys.stderr)
        return None


def _load_config(args: argparse.Namespace) -> Settings | None:
    """Load config file. Returns None on error or if not set."""
    if not getattr(args, "config", None):
        return None
    try:
        from .config.toml_loader import load_settings_from_toml_file

        return load_settings_from_toml_file(args.config)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None
    except Exception as exc:
        print(
            f"error: failed to load config '{args.config}': {exc}", file=sys.stderr
        )
        return None


def _analyze_path(
    path: Path,
    analyzer_names: list[str | BaseAnalyzer] | None,
    settings: Settings | None,
    severity_filter: Severity | None,
    use_cache: bool = True,
) -> tuple[list[Finding] | None, bool]:
    """Analyze a file or directory and return findings and partial failure status."""
    partial_failure = False
    try:
        if path.is_dir():
            results = analyze_directory(
                path,
                analyzers=analyzer_names,
                settings=settings,
                severity_filter=severity_filter,
                error_handling="warn",
                use_cache=use_cache,
            )
            partial_failure = bool(results.errors)
            all_findings: list[Finding] = [f for fs in results.findings.values() for f in fs]
        elif path.is_file():
            all_findings = analyze_file(
                path,
                analyzers=analyzer_names,
                settings=settings,
                severity_filter=severity_filter,
            )
        else:
            print(f"error: path does not exist: {path}", file=sys.stderr)
            return None, False

    except AnalysisError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None, False
    except ExceptionGroup as eg:
        for sub_exc in eg.exceptions:
            print(f"error: {sub_exc}", file=sys.stderr)
        return None, False

    return all_findings, partial_failure


def _write_output(all_findings: list[Finding], args: argparse.Namespace) -> int:
    """Format and write analysis results. Returns exit code."""
    path = Path(args.path)
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

    return _EXIT_OK


def _run_analyze(args: argparse.Namespace) -> int:
    path = Path(args.path)

    analyzer_names = _parse_analyzers(args)

    severity_filter = _parse_severity(args)
    if severity_filter is None and args.min_severity:
        return _EXIT_ERROR

    settings = _load_config(args)
    if settings is None and getattr(args, "config", None):
        return _EXIT_ERROR

    if getattr(args, "clear_cache", False):
        AnalysisCache().clear()

    use_cache = not getattr(args, "no_cache", False)
    all_findings, partial_failure = _analyze_path(
        path, analyzer_names, settings, severity_filter, use_cache=use_cache
    )
    if all_findings is None:
        return _EXIT_ERROR

    if _write_output(all_findings, args) == _EXIT_ERROR:
        return _EXIT_ERROR

    _print_summary(all_findings)

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


def _run_upgrade(_args: argparse.Namespace) -> int:
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
        ("Auto-fix workflows", False, _PLACEHOLDER_COMING_SOON),
        ("Advanced branded HTML reports", False, _PLACEHOLDER_COMING_SOON),
        ("PDF export", False, _PLACEHOLDER_COMING_SOON),
        ("Baseline diffing", False, _PLACEHOLDER_COMING_SOON),
        ("Historical trend reports", False, _PLACEHOLDER_COMING_SOON),
        ("Dashboards", False, _PLACEHOLDER_COMING_SOON),
        ("Priority support", False, _PLACEHOLDER_COMING_SOON),
    ]
    for name, free, pro in features:
        free_mark = "✓" if free else "—"
        if isinstance(pro, str):
            pro_mark = pro
        elif pro:
            pro_mark = "✓"
        else:
            pro_mark = "—"
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
            except (KeyError, TypeError, AttributeError) as exc:
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
    """Return the installed package version string, or ``"unknown"`` if not found."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version("robot-framework-optimizer-core")
    except PackageNotFoundError:
        return "unknown"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


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
