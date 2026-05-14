# tests/unit/analyzers/test_flakiness_settings.py
"""Tests that FlakinessAnalyzer resolves settings through the container."""

from __future__ import annotations

import pytest

from robot_optimizer_core.analyzers.flakiness import FlakinessAnalyzer


@pytest.mark.unit
class TestFlakinessSettingsCoupling:
    def test_both_keys_present_uses_config_values(self) -> None:
        cfg = {"failure_threshold": 0.1, "min_runs": 5}
        analyzer = FlakinessAnalyzer(config=cfg)
        assert analyzer._failure_threshold == pytest.approx(0.1)
        assert analyzer._min_runs == 5

    def test_missing_threshold_reads_from_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import robot_optimizer_core.analyzers.flakiness as flakiness_mod
        from robot_optimizer_core.config import Settings

        custom_settings = Settings(flakiness_threshold=0.15, flakiness_min_runs=7)
        monkeypatch.setattr(flakiness_mod, "get_settings", lambda: custom_settings)
        analyzer = FlakinessAnalyzer(config={"min_runs": 5})
        assert analyzer._failure_threshold == pytest.approx(0.15)

    def test_explicit_values_used(self) -> None:
        cfg = {"failure_threshold": 0.25, "min_runs": 10}
        analyzer = FlakinessAnalyzer(config=cfg)
        assert analyzer._failure_threshold == pytest.approx(0.25)
        assert analyzer._min_runs == 10
