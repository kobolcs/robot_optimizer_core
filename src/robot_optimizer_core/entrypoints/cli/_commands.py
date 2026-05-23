# src/robot_optimizer_core/entrypoints/cli/_commands.py
"""Subcommand handlers and analysis-orchestration helpers."""

from __future__ import annotations

import json
import signal
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from ...domain.value_objects import Finding, Severity
from ...exceptions import AnalysisError
from ..public_api import analyze_directory, analyze_file
from ._baseline import filter_baseline, load_baseline, save_baseline
from ._formatters import _format_json, _format_junit, _format_sarif, _format_text
from ._html import _format_html

if TYPE_CHECKING:
    import argparse

    from ...application.analyzers import BaseAnalyzer
    from ...infrastructure.config.settings import Settings

# Exit codes — keep in sync with cli module docstring.
_EXIT_OK = 0
_EXIT_FINDINGS = 1
_EXIT_ERROR = 2
_EXIT_PARTIAL = 3

_PLACEHOLDER_COMING_SOON = "coming soon"


def _parse_analyzers(args: argparse.Namespace) -> list[str | BaseAnalyzer] | None:
    if hasattr(args, "analyzers") and args.analyzers:
        return [a.strip() for a in args.analyzers.split(",") if a.strip()]
    return None


def _parse_severity(args: argparse.Namespace) -> Severity | None:
    if not args.min_severity:
        return None
    try:
        return Severity.from_string(args.min_severity)
    except ValueError as exc:
        print(f"error: invalid --min-severity value: {exc}", file=sys.stderr)
        return None


def _load_config(args: argparse.Namespace) -> Settings | None:
    if not getattr(args, "config", None):
        return None
    try:
        from ...infrastructure.config.toml_loader import load_settings_from_toml_file

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
    partial_failure = False
    try:
        if path.is_dir():
            results = analyze_directory(
                path,
                analyzers=analyzer_names,
                settings=settings,
                min_severity=severity_filter,
                error_handling="warn",
                use_cache=use_cache,
            )
            partial_failure = bool(results.errors)
            all_findings: list[Finding] = [
                f for fs in results.findings.values() for f in fs
            ]
        elif path.is_file():
            all_findings = list(analyze_file(
                path,
                analyzers=analyzer_names,
                settings=settings,
                min_severity=severity_filter,
            ))
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
    path = Path(args.path)
    if args.format == "json":
        output = _format_json(all_findings)
    elif args.format == "sarif":
        output = _format_sarif(all_findings, path)
    elif args.format == "html":
        output = _format_html(all_findings, path)
    elif args.format == "junit":
        output = _format_junit(all_findings, path)
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


_WATCH_MAX_FILES_WARN = 500


def _flatten_state(state: dict[Path, list[Finding]]) -> list[Finding]:
    """Flatten per-file state dict into a single ordered list."""
    return [f for findings in state.values() for f in findings]


def _compute_finding_diff(
    prev_findings: list[Finding], curr_findings: list[Finding]
) -> tuple[list[Finding], list[Finding]]:
    """Compute new and resolved findings between two analysis runs.

    Uses ``Finding.fingerprint`` as the stable identity key — the same hash
    used by baseline diffing — so the two mechanisms stay consistent.

    Returns a tuple of (new_findings, resolved_findings).
    """
    prev_fps = {f.fingerprint for f in prev_findings}
    curr_fps = {f.fingerprint for f in curr_findings}

    new_findings = [f for f in curr_findings if f.fingerprint not in prev_fps]
    resolved_findings = [f for f in prev_findings if f.fingerprint not in curr_fps]

    return new_findings, resolved_findings


def _print_watch_diff(new_findings: list[Finding], resolved_findings: list[Finding]) -> None:
    """Print a summary of new and resolved findings."""
    if not new_findings and not resolved_findings:
        print("[✓] No changes", file=sys.stderr)
        return

    if new_findings:
        print(f"\n[+] New findings ({len(new_findings)}):", file=sys.stderr)
        for f in new_findings:
            severity_mark = "!" if f.severity == Severity.ERROR else "·"
            print(f"  {severity_mark} {f.location.file_path}:{f.location.line} - {f.pattern.name}", file=sys.stderr)

    if resolved_findings:
        print(f"\n[✓] Resolved findings ({len(resolved_findings)}):", file=sys.stderr)
        for f in resolved_findings:
            print(f"  ✓ {f.location.file_path}:{f.location.line} - {f.pattern.name}", file=sys.stderr)


_WATCHED_EXTENSIONS = frozenset({".robot", ".resource"})
_WATCH_DEBOUNCE_SECONDS: float = 0.5  # editors may write in multiple steps (save + format)

try:
    from watchdog.events import FileSystemEventHandler as _FileSystemEventHandler
except ImportError:  # pragma: no cover — watchdog is optional
    class _FileSystemEventHandler:  # type: ignore[no-redef]
        pass


class _FileChangeHandler(_FileSystemEventHandler):
    """Watchdog event handler for watch mode.

    Encapsulates per-file state and analysis callbacks so it can be constructed
    and tested independently of the observer loop.
    """

    def __init__(
        self,
        state: dict[Path, list[Finding]],
        analyzer_names: list[str | BaseAnalyzer] | None,
        settings: Settings | None,
        severity_filter: Severity | None,
    ) -> None:
        super().__init__()
        self._state = state
        self._analyzer_names = analyzer_names
        self._settings = settings
        self._severity_filter = severity_filter

    @staticmethod
    def _decode_path(raw: str | bytes) -> Path:
        if isinstance(raw, bytes):
            return Path(raw.decode("utf-8"))
        return Path(raw)

    def on_modified(self, event: object) -> None:
        if getattr(event, "is_directory", False):
            return
        file_path = self._decode_path(event.src_path)  # type: ignore[union-attr]
        if file_path.suffix not in _WATCHED_EXTENSIONS:
            return

        time.sleep(_WATCH_DEBOUNCE_SECONDS)

        print(f"\n[*] File changed: {file_path}", file=sys.stderr)
        prev_flat = _flatten_state(self._state)
        findings, _ = _analyze_path(file_path, self._analyzer_names, self._settings, self._severity_filter, use_cache=False)
        if findings is None:
            return
        self._state[file_path] = findings
        curr_flat = _flatten_state(self._state)
        new_f, resolved_f = _compute_finding_diff(prev_flat, curr_flat)
        _print_watch_diff(new_f, resolved_f)

    def on_deleted(self, event: object) -> None:
        if getattr(event, "is_directory", False):
            return
        file_path = self._decode_path(event.src_path)  # type: ignore[union-attr]
        if file_path not in self._state:
            return

        print(f"\n[*] File deleted: {file_path}", file=sys.stderr)
        prev_flat = _flatten_state(self._state)
        self._state.pop(file_path)
        curr_flat = _flatten_state(self._state)
        new_f, resolved_f = _compute_finding_diff(prev_flat, curr_flat)
        _print_watch_diff(new_f, resolved_f)

    def on_moved(self, event: object) -> None:
        src = self._decode_path(event.src_path)  # type: ignore[union-attr]
        dest = self._decode_path(event.dest_path)  # type: ignore[union-attr]
        if src.suffix not in _WATCHED_EXTENSIONS and dest.suffix not in _WATCHED_EXTENSIONS:
            return

        print(f"\n[*] File moved: {src} → {dest}", file=sys.stderr)
        prev_flat = _flatten_state(self._state)
        self._state.pop(src, None)
        if dest.suffix in _WATCHED_EXTENSIONS:
            findings, _ = _analyze_path(dest, self._analyzer_names, self._settings, self._severity_filter, use_cache=False)
            self._state[dest] = findings if findings is not None else []
        curr_flat = _flatten_state(self._state)
        new_f, resolved_f = _compute_finding_diff(prev_flat, curr_flat)
        _print_watch_diff(new_f, resolved_f)


def _run_watch_mode(
    path: Path,
    analyzer_names: list[str | BaseAnalyzer] | None,
    settings: Settings | None,
    severity_filter: Severity | None,
    args: argparse.Namespace,
) -> int:
    """Run in watch mode: monitor files and re-analyze on changes.

    State is kept as a ``dict[Path, list[Finding]]`` so that a change to one
    file never corrupts findings from other files.  Every event snapshots the
    full prev state, applies the per-file update, then diffs against the new
    full state — keeping scope consistent across all event types.
    """
    try:
        from watchdog.observers import Observer
    except ImportError:
        print(
            "error: watch mode requires watchdog library. Install with: pip install robot-framework-optimizer-core[watch]",
            file=sys.stderr,
        )
        return _EXIT_ERROR

    # ------------------------------------------------------------------ init
    print(f"[*] Watching {path} for changes (Ctrl+C to exit)...", file=sys.stderr)

    # Build per-file state from the initial scan so we never start with a
    # scope mismatch between a directory's files.
    state: dict[Path, list[Finding]] = {}
    if path.is_dir():
        from ..public_api import analyze_directory as _analyze_dir

        try:
            dir_result = _analyze_dir(
                path,
                analyzers=analyzer_names,
                settings=settings,
                min_severity=severity_filter,
                error_handling="warn",
                use_cache=True,
            )
            state = dict(dir_result.findings)
        except Exception as exc:
            print(f"error: initial analysis failed: {exc}", file=sys.stderr)
            return _EXIT_ERROR
    elif path.is_file():
        file_findings, _ = _analyze_path(path, analyzer_names, settings, severity_filter, use_cache=True)
        if file_findings is None:
            return _EXIT_ERROR
        state = {path: file_findings}
    else:
        print(f"error: path does not exist: {path}", file=sys.stderr)
        return _EXIT_ERROR

    if len(state) > _WATCH_MAX_FILES_WARN:
        print(
            f"[!] Watching {len(state)} files — consider narrowing the path for faster diffs",
            file=sys.stderr,
        )

    should_exit = False

    def handle_signal(signum: int, frame: object) -> None:
        nonlocal should_exit
        should_exit = True

    signal.signal(signal.SIGINT, handle_signal)

    handler = _FileChangeHandler(state, analyzer_names, settings, severity_filter)
    observer = Observer()
    observer.schedule(handler, str(path), recursive=True)
    observer.start()

    try:
        while not should_exit:
            time.sleep(0.5)
    finally:
        observer.stop()
        observer.join()
        print("\n[*] Watch mode exited", file=sys.stderr)

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
        from ...composition.context import get_analysis_service
        get_analysis_service().clear_cache()

    # Handle watch mode
    if getattr(args, "watch", False):
        return _run_watch_mode(path, analyzer_names, settings, severity_filter, args)

    use_cache = not getattr(args, "no_cache", False)
    all_findings, partial_failure = _analyze_path(
        path, analyzer_names, settings, severity_filter, use_cache=use_cache
    )
    if all_findings is None:
        return _EXIT_ERROR

    # --baseline / --update-baseline handling
    baseline_path = getattr(args, "baseline", None)
    update_baseline = getattr(args, "update_baseline", False)
    if baseline_path is not None:
        baseline_file = Path(baseline_path)
        return _run_with_baseline(
            all_findings, baseline_file, update_baseline, partial_failure, args
        )

    if _write_output(all_findings, args) == _EXIT_ERROR:
        return _EXIT_ERROR

    _print_summary(all_findings)

    if partial_failure:
        return _EXIT_PARTIAL
    if all_findings and not args.no_fail:
        return _EXIT_FINDINGS
    return _EXIT_OK


def _run_with_baseline(
    all_findings: list[Finding],
    baseline_file: Path,
    update_baseline: bool,
    partial_failure: bool,
    args: argparse.Namespace,
) -> int:
    """Apply baseline logic: write, update, or filter findings."""
    # First run or forced update: write baseline and exit clean.
    if not baseline_file.exists() or update_baseline:
        try:
            save_baseline(all_findings, baseline_file)
        except OSError as exc:
            print(f"error: could not write baseline '{baseline_file}': {exc}", file=sys.stderr)
            return _EXIT_ERROR
        action = "Updated" if baseline_file.exists() and update_baseline else "Created"
        print(
            f"Baseline {action.lower()}: {baseline_file} ({len(all_findings)} finding(s))",
            file=sys.stderr,
        )
        return _EXIT_OK

    # Subsequent runs: load baseline and suppress matching findings.
    try:
        baseline_keys = load_baseline(baseline_file)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return _EXIT_ERROR

    new_findings, suppressed = filter_baseline(all_findings, baseline_keys)

    # Only report new findings.
    if _write_output(new_findings, args) == _EXIT_ERROR:
        return _EXIT_ERROR

    _print_baseline_summary(new_findings, suppressed)

    if partial_failure:
        return _EXIT_PARTIAL
    if new_findings and not args.no_fail:
        return _EXIT_FINDINGS
    return _EXIT_OK


def _print_baseline_summary(
    new_findings: list[Finding], suppressed: list[Finding]
) -> None:
    total = len(new_findings) + len(suppressed)
    print(
        f"Baseline: {len(new_findings)} new, {len(suppressed)} suppressed "
        f"(of {total} total finding(s))",
        file=sys.stderr,
    )


def _print_summary(findings: list[Finding]) -> None:
    if not findings:
        return
    from collections import Counter
    counts = Counter(f.severity.name for f in findings)
    parts = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    print(f"Summary: {len(findings)} finding(s)  [{parts}]", file=sys.stderr)


def _run_upgrade(_args: argparse.Namespace) -> int:
    from ...premium import PREMIUM_PACKAGE_NAME, UPGRADE_URL, is_premium_installed
    from ._parser import _get_version

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


def _run_diagnose(args: argparse.Namespace) -> int:
    """Print diagnostic information as JSON and exit 0."""
    import json

    from ...composition.context import ApplicationConfig, ApplicationContext

    ctx = ApplicationContext(ApplicationConfig(
        enable_plugins=False,
        enable_metrics=False,
        enable_logging=False,
    ))
    ctx.initialize()
    try:
        report = ctx.get_diagnostic_report()
    finally:
        ctx.shutdown()

    print(json.dumps(report, indent=2, default=str))
    return _EXIT_OK


def _run_list_analyzers(args: argparse.Namespace) -> int:
    from ...application.analyzers import get_analyzer_registry

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
