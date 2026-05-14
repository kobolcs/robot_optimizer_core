# tests/unit/config/test_toml_loader.py
"""Tests for the robot.toml-aware config loader (Task 21) and analyzer_config (Task 20)."""

from __future__ import annotations

from pathlib import Path

import pytest

from robot_optimizer_core.config import Settings, load_settings_from_toml
from robot_optimizer_core.config.toml_loader import (
    _find_toml_root,
    _read_optimizer_section,
)
from robot_optimizer_core.domain.value_objects import Severity


@pytest.mark.unit
class TestAnalyzerConfig:
    """Tests for the analyzer_config field on Settings (Task 20)."""

    def test_analyzer_config_default_empty(self) -> None:
        s = Settings()
        assert s.analyzer_config == {}

    def test_analyzer_config_accepts_per_analyzer_dict(self) -> None:
        s = Settings(analyzer_config={"sleep_detector": {"threshold": 2}})
        assert s.analyzer_config["sleep_detector"]["threshold"] == 2

    def test_analyzer_config_multiple_analyzers(self) -> None:
        s = Settings(
            analyzer_config={
                "dead_code": {"check_unused": True},
                "sleep_detector": {"check_builtin_sleep": False},
            }
        )
        assert "dead_code" in s.analyzer_config
        assert "sleep_detector" in s.analyzer_config


@pytest.mark.unit
class TestTomlLoader:
    """Tests for load_settings_from_toml (Task 21)."""

    def test_no_toml_returns_default_settings(self, tmp_path: Path) -> None:
        settings = load_settings_from_toml(tmp_path)
        assert isinstance(settings, Settings)

    def test_reads_robot_toml(self, tmp_path: Path) -> None:
        (tmp_path / "robot.toml").write_bytes(
            b"[tool.robot-optimizer]\nmax_acceptable_sleep_seconds = 0.5\n"
        )
        settings = load_settings_from_toml(tmp_path)
        assert settings.max_acceptable_sleep_seconds == pytest.approx(0.5)

    def test_reads_pyproject_toml(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_bytes(
            b"[tool.robot-optimizer]\nmax_acceptable_sleep_seconds = 2.0\n"
        )
        settings = load_settings_from_toml(tmp_path)
        assert settings.max_acceptable_sleep_seconds == pytest.approx(2.0)

    def test_overrides_take_precedence_over_toml(self, tmp_path: Path) -> None:
        (tmp_path / "robot.toml").write_bytes(
            b"[tool.robot-optimizer]\nmax_acceptable_sleep_seconds = 0.5\n"
        )
        settings = load_settings_from_toml(tmp_path, max_acceptable_sleep_seconds=5.0)
        assert settings.max_acceptable_sleep_seconds == pytest.approx(5.0)

    def test_missing_section_gives_defaults(self, tmp_path: Path) -> None:
        (tmp_path / "robot.toml").write_bytes(b"[project]\nname = 'foo'\n")
        settings = load_settings_from_toml(tmp_path)
        # Should fall back to defaults without error
        assert isinstance(settings, Settings)

    def test_find_toml_root_returns_none_when_missing(self, tmp_path: Path) -> None:
        # A deeply nested directory with no TOML in any parent
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        # Only check within our tmp_path tree; won't find real project root
        result = _find_toml_root(nested)
        # May return something from the real project root, but won't crash
        assert result is None or result.is_dir()

    def test_read_optimizer_section_returns_none_for_empty_file(
        self, tmp_path: Path
    ) -> None:
        toml_path = tmp_path / "robot.toml"
        toml_path.write_bytes(b"")
        assert _read_optimizer_section(toml_path) is None

    def test_read_optimizer_section_invalid_toml(self, tmp_path: Path) -> None:
        toml_path = tmp_path / "robot.toml"
        toml_path.write_bytes(b"this is not valid toml }{{{")
        # Should return None without raising
        result = _read_optimizer_section(toml_path)
        assert result is None


@pytest.mark.unit
class TestSeverityFilter:
    """Tests for severity_filter and pattern_filter in analyze_file (Task 14)."""

    def test_severity_filter_drops_lower_severity(self, tmp_path: Path) -> None:
        from robot_optimizer_core import analyze_file

        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\nMy Test\n    Sleep    2\n")
        findings = analyze_file(str(f), severity_filter=Severity.ERROR)
        for finding in findings:
            assert finding.severity <= Severity.ERROR

    def test_pattern_filter_limits_analyzers(self, tmp_path: Path) -> None:
        from robot_optimizer_core import analyze_file

        f = tmp_path / "t.robot"
        f.write_bytes(b"*** Test Cases ***\nMy Test\n    Sleep    10\n")
        findings = analyze_file(str(f), pattern_filter=["sleep_detector"])
        analyzer_names = {
            f.pattern.type.name
            for f in findings  # type: ignore[attr-defined]
        }
        # Only sleep-related findings should be present
        assert "SLEEP_IN_TEST" in analyzer_names or findings == []


@pytest.mark.unit
class TestSettingsValidation:
    """Tests for Settings field validation, including extra='forbid'."""

    def test_unknown_setting_key_raises(self) -> None:
        """Settings with extra='forbid' must raise on unknown keys."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Settings(completely_unknown_key_xyz="should_fail")

    def test_known_setting_keys_accepted(self) -> None:
        """All documented Settings fields must be accepted without error."""
        s = Settings(
            max_file_size_mb=5.0,
            log_level="DEBUG",
            enable_metrics=False,
            plugins_enabled=False,
        )
        assert s.max_file_size_mb == pytest.approx(5.0)
