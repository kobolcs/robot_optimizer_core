# tests/unit/analyzers/test_sleep_detector_naming.py
"""Tests for SleepDetectorAnalyzer naming and settings decoupling."""

from __future__ import annotations

import pytest

from robot_optimizer_core.analyzers.sleep_detector import (
    SleepDetector,
    SleepDetectorAnalyzer,
)


@pytest.mark.unit
class TestSleepDetectorNaming:
    def test_alias_is_same_class(self) -> None:
        assert SleepDetector is SleepDetectorAnalyzer

    def test_canonical_class_name(self) -> None:
        assert SleepDetectorAnalyzer.__name__ == "SleepDetectorAnalyzer"

    def test_registry_name_unchanged(self) -> None:
        assert SleepDetectorAnalyzer().name == "sleep_detector"


@pytest.mark.unit
class TestSleepDetectorSettingsCoupling:
    def test_explicit_thresholds_used_directly(self) -> None:
        explicit = {"severity_thresholds": {"info": 0.5, "warning": 2.0, "error": float("inf")}}
        analyzer = SleepDetectorAnalyzer(config=explicit)
        assert analyzer._severity_thresholds["info"] == 0.5
        assert analyzer._severity_thresholds["warning"] == 2.0

    def test_no_config_reads_thresholds_from_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import robot_optimizer_core.analyzers.sleep_detector as sleep_mod
        from robot_optimizer_core.config import Settings

        custom_settings = Settings(max_acceptable_sleep_seconds=3.0)
        monkeypatch.setattr(sleep_mod, "get_settings", lambda: custom_settings)
        analyzer = SleepDetectorAnalyzer()
        assert analyzer._severity_thresholds["info"] == 3.0
        assert analyzer._severity_thresholds["warning"] == 15.0  # 3.0 * 5

    def test_explicit_thresholds_respected(self) -> None:
        explicit = {"severity_thresholds": {"info": 99.0, "warning": 199.0, "error": float("inf")}}
        analyzer = SleepDetectorAnalyzer(config=explicit)
        assert analyzer._severity_thresholds["info"] == 99.0
