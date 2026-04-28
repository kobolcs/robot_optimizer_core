# tests/unit/test_metrics.py
"""Unit tests for the metrics collector."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from robot_optimizer_core.metrics import MetricsCollector, TimingStats, get_metrics


@pytest.fixture
def collector() -> Iterator[MetricsCollector]:
    m = MetricsCollector(enabled=True)
    yield m
    m.stop()


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
    def test_increment(self, collector: MetricsCollector) -> None:
        collector.increment("test.counter")
        collector.increment("test.counter")
        data = collector.get_metrics()
        assert data["counters"]["test.counter"] == 2

    def test_increment_with_value(self, collector: MetricsCollector) -> None:
        collector.increment("test.counter", 5)
        data = collector.get_metrics()
        assert data["counters"]["test.counter"] == 5

    def test_gauge(self, collector: MetricsCollector) -> None:
        collector.gauge("test.gauge", 42.0)
        data = collector.get_metrics()
        assert data["gauges"]["test.gauge"] == 42.0

    def test_gauge_overwrite(self, collector: MetricsCollector) -> None:
        collector.gauge("g", 1.0)
        collector.gauge("g", 2.0)
        assert collector.get_metrics()["gauges"]["g"] == 2.0

    def test_timing(self, collector: MetricsCollector) -> None:
        collector.timing("test.timing", 0.5)
        data = collector.get_metrics()
        assert "test.timing" in data["timings"]
        assert data["timings"]["test.timing"]["count"] == 1

    def test_timer_context_manager(self, collector: MetricsCollector) -> None:
        with collector.timer("op.duration"):
            pass
        data = collector.get_metrics()
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
        try:
            m2 = get_metrics()
            assert m1 is m2
        finally:
            m1.stop()

    def test_tags_create_separate_keys(self, collector: MetricsCollector) -> None:
        collector.increment("hits", tags={"env": "prod"})
        collector.increment("hits", tags={"env": "dev"})
        data = collector.get_metrics()
        keys = list(data["counters"].keys())
        assert len([k for k in keys if "hits" in k]) == 2

    def test_reset(self, collector: MetricsCollector) -> None:
        collector.increment("x")
        collector.reset()
        data = collector.get_metrics()
        assert data["counters"] == {}
        assert data["gauges"] == {}

    def test_close_stops_collector(self, collector: MetricsCollector) -> None:
        collector.close()

    def test_gdpr_filter_blocks_personal_data_metric(
        self, collector: MetricsCollector
    ) -> None:
        collector.increment("user.login_count")
        data = collector.get_metrics()
        assert "user.login_count" not in data["counters"]

    def test_validate_tags_raises_for_blocked_key(
        self, collector: MetricsCollector
    ) -> None:
        with pytest.raises(ValueError, match="personal data"):
            collector.increment("hits", tags={"user": "alice"})

    def test_validate_tags_raises_for_email_key(
        self, collector: MetricsCollector
    ) -> None:
        with pytest.raises(ValueError, match="personal data"):
            collector.gauge("score", 1.0, tags={"email": "x@y.com"})

    def test_evict_on_counter_overflow(self) -> None:
        m = MetricsCollector(enabled=True, max_counters=2)
        try:
            m.increment("a")
            m.increment("b")
            m.increment("c")  # triggers eviction
            data = m.get_metrics()
            assert len(data["counters"]) <= 2
        finally:
            m.stop()

    def test_evict_on_gauge_overflow(self) -> None:
        m = MetricsCollector(enabled=True, max_gauges=2)
        try:
            m.gauge("a", 1.0)
            m.gauge("b", 2.0)
            m.gauge("c", 3.0)  # triggers eviction
            data = m.get_metrics()
            assert len(data["gauges"]) <= 2
        finally:
            m.stop()

    def test_evict_on_timing_overflow(self) -> None:
        m = MetricsCollector(enabled=True, max_timings=2)
        try:
            m.timing("a", 0.1)
            m.timing("b", 0.2)
            m.timing("c", 0.3)  # triggers eviction
            data = m.get_metrics()
            assert len(data["timings"]) <= 2
        finally:
            m.stop()

    def test_configure_metrics_replaces_global(self) -> None:
        from robot_optimizer_core.metrics import configure_metrics, get_metrics

        m1 = configure_metrics(enabled=True)
        try:
            m2 = get_metrics()
            assert m1 is m2
        finally:
            m1.stop()
