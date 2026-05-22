# src/robot_optimizer_core/entrypoints/cli/_html.py
"""HTML report generation for the robot-optimizer CLI."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from ...domain.value_objects import Finding

# Severity label constants used in HTML stats
_SEV_ERROR = "ERROR"
_SEV_WARNING = "WARNING"
_SEV_INFO = "INFO"

# Health status labels
_HEALTH_HIGH_RISK = "High Risk"
_HEALTH_MODERATE_RISK = "Moderate Risk"
_HEALTH_LOW_RISK = "Low Risk"
_HEALTH_HEALTHY = "Healthy"


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
    _HEALTH_HIGH_RISK: ("#ef4444", "#ef44441a", "#ef444455", "#ef444433"),
    _HEALTH_MODERATE_RISK: ("#f59e0b", "#f59e0b1a", "#f59e0b55", "#f59e0b33"),
    _HEALTH_HEALTHY: ("#0d9488", "#0d94881a", "#0d948855", "#0d948833"),
    _HEALTH_LOW_RISK: ("#0d9488", "#0d94881a", "#0d948855", "#0d948833"),
}
_HEALTH_COLOR_DEFAULT = ("#6b7280", "#6b72801a", "#6b728055", "#6b728033")


def _get_template_path() -> Path:
    """Get path to the HTML report template."""
    # __file__ is entrypoints/cli/_html.py; resources/ lives two levels up in cli/../../resources/
    return Path(__file__).parent.parent.parent / "resources" / "report.html.j2"


def _render_html_template(context: dict[str, Any]) -> str:
    """Render HTML report using Jinja2 template."""
    from jinja2 import Environment, FileSystemLoader
    from markupsafe import Markup

    template_path = _get_template_path()
    if not template_path.exists():
        raise FileNotFoundError(f"HTML report template not found: {template_path}")

    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=True,
    )
    # SAFETY: All values for these keys are either pre-escaped via html.escape()
    # in their respective _html_render_* functions, or are hardcoded constants.
    # No user input is included.
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
                    Markup(v) if isinstance(v, str) else v for v in value
                ]
            elif isinstance(value, str):
                safe_context[key] = Markup(value)
    template = env.get_template(template_path.name)
    return template.render(**safe_context)


def _format_html(findings: list[Finding], path: Path) -> str:
    """Format findings as an HTML health report."""
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


