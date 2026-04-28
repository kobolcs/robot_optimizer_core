# tests/unit/test_metrics.py
"""Unit tests for the metrics collector."""
from __future__ import annotations

import pytest

from robot_optimizer_core.metrics import MetricsCollector, TimingStats, get_metrics


@pytest.mark.unit
class TestTimingStats:
    def test_initial_state(self) -> None:
        stats = TimingStats()
        assert stats.count == 0
        assert stats.mean == 0.0
        assert stats.last is None

    def test_add_values(self) -> None:
        stats = TimingStats()
        stats.add(1.0)
        stats.add(3.0)
        assert stats.count == 2
        assert stats.total == 4.0
        assert stats.min == 1.0
        assert stats.max == 3.0
        assert stats.mean == 2.0
        assert stats.last == 3.0

    def test_cleanup_old_samples(self) -> None:
        from datetime import timedelta
        stats = TimingStats()
        stats.add(1.0)
        stats.cleanup_old_samples(timedelta(seconds=0))
        assert len(stats.samples) == 0


@pytest.mark.unit
class TestMetricsCollector:
    def test_increment(self) -> None:
        m = MetricsCollector(enabled=True)
        m.increment("test.counter")
        m.increment("test.counter")
        data = m.get_metrics()
        assert data["counters"]["test.counter"] == 2

    def test_increment_with_value(self) -> None:
        m = MetricsCollector(enabled=True)
        m.increment("test.counter", 5)
        data = m.get_metrics()
        assert data["counters"]["test.counter"] == 5

    def test_gauge(self) -> None:
        m = MetricsCollector(enabled=True)
        m.gauge("test.gauge", 42.0)
        data = m.get_metrics()
        assert data["gauges"]["test.gauge"] == 42.0

    def test_gauge_overwrite(self) -> None:
        m = MetricsCollector(enabled=True)
        m.gauge("g", 1.0)
        m.gauge("g", 2.0)
        assert m.get_metrics()["gauges"]["g"] == 2.0

    def test_timing(self) -> None:
        m = MetricsCollector(enabled=True)
        m.timing("test.timing", 0.5)
        data = m.get_metrics()
        assert "test.timing" in data["timings"]
        assert data["timings"]["test.timing"]["count"] == 1

    def test_timer_context_manager(self) -> None:
        m = MetricsCollector(enabled=True)
        with m.timer("op.duration"):
            pass
        data = m.get_metrics()
        assert "op.duration" in data["timings"]

    def test_disabled_collector_ignores_all(self) -> None:
        m = MetricsCollector(enabled=False)
        m.increment("x")
        m.gauge("y", 1.0)
        m.timing("z", 0.1)
        data = m.get_metrics()
        assert data["counters"] == {}
        assert data["gauges"] == {}

    def test_get_metrics_singleton(self) -> None:
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2

    def test_tags_create_separate_keys(self) -> None:
        m = MetricsCollector(enabled=True)
        m.increment("hits", tags={"env": "prod"})
        m.increment("hits", tags={"env": "dev"})
        data = m.get_metrics()
        keys = list(data["counters"].keys())
        assert len([k for k in keys if "hits" in k]) == 2

    def test_reset(self) -> None:
        m = MetricsCollector(enabled=True)
        m.increment("x")
        m.reset()
        data = m.get_metrics()
        assert data["counters"] == {}
        assert data["gauges"] == {}
