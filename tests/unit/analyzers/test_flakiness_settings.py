# tests/unit/analyzers/test_flakiness_settings.py
"""Tests that FlakinessAnalyzer only calls get_settings when needed."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from robot_optimizer_core.analyzers.flakiness import FlakinessAnalyzer


@pytest.mark.unit
class TestFlakinessSettingsCoupling:
    def test_both_keys_present_skips_get_settings(self) -> None:
        cfg = {"failure_threshold": 0.1, "min_runs": 5}
        with patch("robot_optimizer_core.analyzers.flakiness.get_settings") as mock:
            FlakinessAnalyzer(config=cfg)
            mock.assert_not_called()

    def test_missing_threshold_calls_get_settings(self) -> None:
        cfg = {"min_runs": 5}
        with patch("robot_optimizer_core.analyzers.flakiness.get_settings") as mock:
            from robot_optimizer_core.config import Settings
            mock.return_value = Settings()
            FlakinessAnalyzer(config=cfg)
            mock.assert_called_once()

    def test_explicit_values_used(self) -> None:
        cfg = {"failure_threshold": 0.25, "min_runs": 10}
        analyzer = FlakinessAnalyzer(config=cfg)
        assert analyzer._failure_threshold == 0.25
        assert analyzer._min_runs == 10
