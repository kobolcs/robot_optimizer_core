# tests/unit/analyzers/test_sleep_detector_naming.py
"""Tests for SleepDetectorAnalyzer naming and settings decoupling."""

from __future__ import annotations

from unittest.mock import patch

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
    def test_explicit_thresholds_skip_get_settings(self) -> None:
        explicit = {"severity_thresholds": {"info": 0.5, "warning": 2.0, "error": float("inf")}}
        with patch("robot_optimizer_core.analyzers.sleep_detector.get_settings") as mock:
            SleepDetectorAnalyzer(config=explicit)
            mock.assert_not_called()

    def test_no_config_calls_get_settings(self) -> None:
        with patch("robot_optimizer_core.analyzers.sleep_detector.get_settings") as mock:
            from robot_optimizer_core.config import Settings
            mock.return_value = Settings()
            SleepDetectorAnalyzer()
            mock.assert_called_once()

    def test_explicit_thresholds_respected(self) -> None:
        explicit = {"severity_thresholds": {"info": 99.0, "warning": 199.0, "error": float("inf")}}
        analyzer = SleepDetectorAnalyzer(config=explicit)
        assert analyzer._severity_thresholds["info"] == 99.0
