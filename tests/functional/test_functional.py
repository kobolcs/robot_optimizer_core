# tests/functional/test_functional.py
"""Functional (black-box) tests for the robot-optimizer CLI.

These tests treat the tool as an end-user would: invoking the installed
``robot-optimizer`` entry-point against the real ``examples/bad_robot_suite/``
directory and asserting output contracts, exit codes, and known findings.

They intentionally avoid importing from ``robot_optimizer_core`` so that any
accidental in-process coupling is caught at this boundary.

Stable finding counts come from the committed example suite; update the
EXPECTED_* constants if the suite or an analyzer changes intentionally.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_SUITE = REPO_ROOT / "examples" / "bad_robot_suite"

# ---------------------------------------------------------------------------
# Known-good counts for examples/bad_robot_suite (all analyzers, all severity)
# Update here when the suite or an analyzer output changes intentionally.
# ---------------------------------------------------------------------------

EXPECTED_TOTAL = 49
EXPECTED_BY_TYPE: dict[str, int] = {
    "SLEEP_IN_TEST": 3,
    "HARDCODED_VALUE": 1,
    "SINGLETON_TAG": 6,
    "MISSING_DOCUMENTATION": 23,
    "UNUSED_KEYWORD": 16,
}
EXPECTED_BY_SEVERITY: dict[str, int] = {
    "WARNING": 20,
    "INFO": 29,
}
EXPECTED_BY_FILE: dict[str, int] = {
    "checkout.robot": 6,
    "login.robot": 7,
    "common.resource": 15,
    "legacy_keywords.resource": 21,
}

# Fingerprints are SHA-256(pattern_type \0 posix_path \0 line \0 msg[:120])[:16].
# They are stable across Python / RF versions as long as the example files and
# analyzer messages don't change.
KNOWN_FINGERPRINTS = {
    # Sleep 5s in checkout.robot:19
    "checkout_sleep_5s": "b3a16b9595d062dd",
    # Hardcoded URL in checkout.robot:25
    "checkout_hardcoded_url": "c8ae980756bb5b89",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_cli_exe() -> str:
    """Locate the robot-optimizer entry-point, preferring the active venv."""
    # Prefer the venv that owns this Python interpreter (covers editable installs
    # and tox envs).  Fall back to PATH only when not in a venv.
    venv_bin = Path(sys.executable).parent
    venv_exe = venv_bin / "robot-optimizer"
    if venv_exe.exists():
        return str(venv_exe)
    found = shutil.which("robot-optimizer")
    if found:
        return found
    raise FileNotFoundError("robot-optimizer not found — install the package first")


_CLI_EXE = _find_cli_exe()


def _cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run the installed ``robot-optimizer`` entry-point."""
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    return subprocess.run(
        [_CLI_EXE, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env=env,
    )


def _analyze_json(*extra: str) -> dict[str, Any]:
    """Run analyze against the example suite and return the parsed JSON envelope."""
    result = _cli(
        "analyze",
        str(EXAMPLE_SUITE),
        "--format", "json",
        "--no-fail",
        *extra,
    )
    assert result.returncode == 0, f"CLI exited {result.returncode}\n{result.stderr}"
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# Entry-point availability
# ---------------------------------------------------------------------------


@pytest.mark.functional
class TestEntryPoint:
    def test_version_exits_zero(self) -> None:
        result = _cli("--version")
        assert result.returncode == 0

    def test_version_reports_package_name(self) -> None:
        result = _cli("--version")
        assert "robot-optimizer" in result.stdout.lower()

    def test_version_reports_semver(self) -> None:
        import re
        result = _cli("--version")
        assert re.search(r"\d+\.\d+", result.stdout), f"No semver in: {result.stdout!r}"

    def test_help_exits_zero(self) -> None:
        assert _cli("--help").returncode == 0

    def test_analyze_help_exits_zero(self) -> None:
        assert _cli("analyze", "--help").returncode == 0

    def test_list_analyzers_exits_zero(self) -> None:
        assert _cli("list-analyzers").returncode == 0


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


@pytest.mark.functional
class TestExitCodes:
    def test_findings_produce_exit_one(self) -> None:
        result = _cli("analyze", str(EXAMPLE_SUITE))
        assert result.returncode == 1

    def test_no_fail_produces_exit_zero_despite_findings(self) -> None:
        result = _cli("analyze", str(EXAMPLE_SUITE), "--no-fail")
        assert result.returncode == 0

    def test_missing_path_exits_two(self) -> None:
        result = _cli("analyze", str(EXAMPLE_SUITE / "does_not_exist.robot"))
        assert result.returncode == 2

    def test_empty_directory_exits_zero(self, tmp_path: Path) -> None:
        result = _cli("analyze", str(tmp_path), "--no-fail")
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# JSON output schema
# ---------------------------------------------------------------------------


@pytest.mark.functional
class TestJsonSchema:
    def test_output_is_valid_json(self) -> None:
        result = _cli("analyze", str(EXAMPLE_SUITE), "--format", "json", "--no-fail")
        json.loads(result.stdout)  # must not raise

    def test_schema_version_is_one(self) -> None:
        data = _analyze_json()
        assert data["schema_version"] == "1"

    def test_findings_key_is_list(self) -> None:
        data = _analyze_json()
        assert isinstance(data["findings"], list)

    def test_finding_has_required_keys(self) -> None:
        data = _analyze_json()
        required = {"severity", "message", "pattern_type", "file", "line", "fingerprint"}
        for finding in data["findings"]:
            missing = required - finding.keys()
            assert not missing, f"Finding missing keys: {missing}"

    def test_severity_is_plain_string(self) -> None:
        data = _analyze_json()
        for f in data["findings"]:
            assert isinstance(f["severity"], str)
            assert "." not in f["severity"], f"Enum repr leaked: {f['severity']}"

    def test_fingerprint_is_16_hex_chars(self) -> None:
        data = _analyze_json()
        for f in data["findings"]:
            fp = f["fingerprint"]
            assert len(fp) == 16, f"Bad fingerprint length: {fp!r}"
            assert all(c in "0123456789abcdef" for c in fp), f"Not hex: {fp!r}"


# ---------------------------------------------------------------------------
# Known finding counts against the real example suite
# ---------------------------------------------------------------------------


@pytest.mark.functional
class TestKnownFindings:
    def test_total_finding_count(self) -> None:
        data = _analyze_json()
        assert len(data["findings"]) == EXPECTED_TOTAL

    def test_finding_counts_by_type(self) -> None:
        from collections import Counter
        data = _analyze_json()
        by_type = Counter(f["pattern_type"] for f in data["findings"])
        for pattern_type, expected in EXPECTED_BY_TYPE.items():
            assert by_type[pattern_type] == expected, (
                f"{pattern_type}: expected {expected}, got {by_type[pattern_type]}"
            )

    def test_finding_counts_by_severity(self) -> None:
        from collections import Counter
        data = _analyze_json()
        by_sev = Counter(f["severity"] for f in data["findings"])
        for severity, expected in EXPECTED_BY_SEVERITY.items():
            assert by_sev[severity] == expected, (
                f"{severity}: expected {expected}, got {by_sev[severity]}"
            )

    def test_finding_counts_by_file(self) -> None:
        from collections import Counter
        data = _analyze_json()
        by_file = Counter(f["file"] for f in data["findings"])
        for filename, expected in EXPECTED_BY_FILE.items():
            assert by_file[filename] == expected, (
                f"{filename}: expected {expected}, got {by_file[filename]}"
            )

    def test_sleep_detected_in_checkout(self) -> None:
        data = _analyze_json()
        sleeps = [f for f in data["findings"] if f["pattern_type"] == "SLEEP_IN_TEST"]
        checkout_sleeps = [f for f in sleeps if f["file"] == "checkout.robot"]
        assert len(checkout_sleeps) == 1
        assert checkout_sleeps[0]["line"] == 19

    def test_hardcoded_url_in_checkout(self) -> None:
        data = _analyze_json()
        hcv = [
            f for f in data["findings"]
            if f["pattern_type"] == "HARDCODED_VALUE" and f["file"] == "checkout.robot"
        ]
        assert len(hcv) == 1
        assert hcv[0]["line"] == 25
        assert "staging-retail.example.internal" in hcv[0]["message"]

    def test_dead_keywords_in_resource_files(self) -> None:
        data = _analyze_json()
        unused = [f for f in data["findings"] if f["pattern_type"] == "UNUSED_KEYWORD"]
        resource_files = {f["file"] for f in unused}
        assert "common.resource" in resource_files
        assert "legacy_keywords.resource" in resource_files

    def test_known_fingerprints_present(self) -> None:
        data = _analyze_json()
        found_fps = {f["fingerprint"] for f in data["findings"]}
        for label, fp in KNOWN_FINGERPRINTS.items():
            assert fp in found_fps, f"Known fingerprint for '{label}' not found: {fp}"


# ---------------------------------------------------------------------------
# Severity filtering
# ---------------------------------------------------------------------------


@pytest.mark.functional
class TestSeverityFilter:
    def test_min_severity_warning_excludes_info(self) -> None:
        data = _analyze_json("--min-severity", "WARNING")
        severities = {f["severity"] for f in data["findings"]}
        assert "INFO" not in severities

    def test_min_severity_warning_count(self) -> None:
        data = _analyze_json("--min-severity", "WARNING")
        assert len(data["findings"]) == EXPECTED_BY_SEVERITY["WARNING"]

    def test_min_severity_error_returns_empty(self) -> None:
        # The example suite has no ERROR-level findings
        data = _analyze_json("--min-severity", "ERROR")
        assert len(data["findings"]) == 0


# ---------------------------------------------------------------------------
# Analyzer selection
# ---------------------------------------------------------------------------


@pytest.mark.functional
class TestAnalyzerSelection:
    def test_single_analyzer_sleep_only(self) -> None:
        data = _analyze_json("--analyzers", "sleep_detector")
        types = {f["pattern_type"] for f in data["findings"]}
        assert types == {"SLEEP_IN_TEST"}

    def test_single_analyzer_dead_code_only(self) -> None:
        data = _analyze_json("--analyzers", "dead_code")
        types = {f["pattern_type"] for f in data["findings"]}
        assert types == {"UNUSED_KEYWORD"}

    def test_two_analyzers_combined(self) -> None:
        data = _analyze_json("--analyzers", "sleep_detector,dead_code")
        types = {f["pattern_type"] for f in data["findings"]}
        assert "SLEEP_IN_TEST" in types
        assert "UNUSED_KEYWORD" in types
        assert "MISSING_DOCUMENTATION" not in types


# ---------------------------------------------------------------------------
# list-analyzers
# ---------------------------------------------------------------------------


@pytest.mark.functional
class TestListAnalyzers:
    def test_lists_all_core_analyzers(self) -> None:
        result = _cli("list-analyzers", "--format", "json")
        assert result.returncode == 0
        records = json.loads(result.stdout)
        names = {r["name"] for r in records}
        expected = {
            "dead_code",
            "sleep_detector",
            "hardcoded_value",
            "naming_convention",
            "setup_teardown",
            "tag_consistency",
            "test_documentation",
        }
        assert expected.issubset(names)

    def test_text_output_contains_analyzer_names(self) -> None:
        result = _cli("list-analyzers")
        assert "sleep_detector" in result.stdout
        assert "dead_code" in result.stdout


# ---------------------------------------------------------------------------
# Installed-wheel smoke test (slow — creates a real venv)
# ---------------------------------------------------------------------------


@pytest.mark.functional
@pytest.mark.slow
class TestInstalledWheel:
    """Build the wheel, install it into an isolated venv, and run the CLI.

    This is the only test that proves the entry-point shim, packaging
    metadata, and entry_points discovery all work as a user would experience.
    """

    def test_wheel_installs_and_cli_runs(self, tmp_path: Path) -> None:
        # Build wheel — prefer uv (faster, always available in this repo),
        # fall back to the stdlib 'build' module.
        dist_dir = tmp_path / "dist"
        uv_exe = shutil.which("uv")
        if uv_exe:
            cmd = [uv_exe, "build", "--wheel", "--out-dir", str(dist_dir)]
        else:
            cmd = [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)]
        build = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
        assert build.returncode == 0, f"build failed:\n{build.stderr}"

        wheels = list(dist_dir.glob("*.whl"))
        assert wheels, "No wheel produced"
        wheel = wheels[0]

        # Create an isolated venv
        venv_dir = tmp_path / "venv"
        venv.create(str(venv_dir), with_pip=True, clear=True)
        venv_python = venv_dir / "bin" / "python"

        # Install the wheel
        install = subprocess.run(
            [str(venv_python), "-m", "pip", "install", str(wheel), "--quiet"],
            capture_output=True,
            text=True,
        )
        assert install.returncode == 0, f"pip install failed:\n{install.stderr}"

        # Invoke via the installed entry-point
        cli_exe = venv_dir / "bin" / "robot-optimizer"
        result = subprocess.run(
            [str(cli_exe), "analyze", str(EXAMPLE_SUITE), "--format", "json", "--no-fail"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert result.returncode == 0, f"CLI failed:\n{result.stderr}"
        data = json.loads(result.stdout)
        assert data["schema_version"] == "1"
        assert len(data["findings"]) == EXPECTED_TOTAL
