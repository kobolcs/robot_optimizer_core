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
        assert analyzer._failure_threshold == 0.1
        assert analyzer._min_runs == 5

    def test_missing_threshold_reads_from_container_settings(self) -> None:
        from robot_optimizer_core.config import Settings
        from robot_optimizer_core.di import get_container, reset_container

        reset_container()
        container = get_container()
        container.register_instance(
            "settings",
            Settings(flakiness_threshold=0.15, flakiness_min_runs=7),
            override=True,
        )
        try:
            analyzer = FlakinessAnalyzer(config={"min_runs": 5})
            assert analyzer._failure_threshold == 0.15
        finally:
            reset_container()

    def test_explicit_values_used(self) -> None:
        cfg = {"failure_threshold": 0.25, "min_runs": 10}
        analyzer = FlakinessAnalyzer(config=cfg)
        assert analyzer._failure_threshold == 0.25
        assert analyzer._min_runs == 10
