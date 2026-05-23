# src/robot_optimizer_core/infrastructure/metrics/collector.py
"""Memory-safe metrics collection with GDPR compliance.

Provides ``MetricsCollector``, a thread-safe, bounded metrics store with
automatic LRU eviction and background cleanup. Metric keys that match
known personal-data prefixes (``user.``, ``email.``, etc.) are silently
dropped to comply with GDPR constraints.

Example:
    Recording analysis metrics::

        from robot_optimizer_core.infrastructure.metrics.collector import get_metrics

        metrics = get_metrics()
        metrics.increment("analysis.completed")
        with metrics.timer("analysis.duration"):
            do_analysis()
        report = metrics.get_metrics()
"""

from __future__ import annotations

import logging as _stdlib_logging
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

from ...exceptions import ValidationError as _ValidationError

__all__ = [
    "MetricsCollector",
    "TimingStats",
    "configure_metrics",
    "get_metrics",
    "reset_metrics",
]

logger = _stdlib_logging.getLogger(__name__)


@dataclass
class TimingStats:
    """Running statistics for a single timing metric, with bounded sample storage.

    Attributes:
        count: Total number of observations recorded.
        total: Sum of all observed values (seconds).
        min: Minimum observed value.
        max: Maximum observed value.
        samples: Bounded deque of ``(value, timestamp)`` pairs (max 100 entries).
    """

    count: int = 0
    total: float = 0.0
    min: float = float("inf")
    max: float = 0.0
    samples: deque[tuple[float, datetime]] = field(
        default_factory=lambda: deque(maxlen=100)
    )

    @property
    def mean(self) -> float:
        """Mean of all recorded values, or ``0.0`` when no samples exist.

        Returns:
            Arithmetic mean in seconds.
        """
        return self.total / self.count if self.count > 0 else 0.0

    @property
    def last(self) -> float | None:
        """Most recently recorded value, or ``None`` when no samples exist.

        Returns:
            Last timing value in seconds, or ``None``.
        """
        return self.samples[-1][0] if self.samples else None

    def add(self, value: float) -> None:
        """Record a new timing observation.

        Args:
            value: Duration in seconds to record.
        """
        self.count += 1
        self.total += value
        self.min = min(self.min, value)
        self.max = max(self.max, value)
        self.samples.append((value, datetime.now(UTC)))

    def cleanup_old_samples(self, max_age: timedelta) -> None:
        """Discard samples older than *max_age*.

        Args:
            max_age: Samples with a timestamp older than ``now - max_age`` are
                removed from the left of the deque.
        """
        cutoff = datetime.now(UTC) - max_age
        while self.samples and self.samples[0][1] <= cutoff:
            self.samples.popleft()


class MetricsCollector:
    """Thread-safe metrics collector with bounded memory and GDPR compliance.

    Metric stores are bounded by ``max_counters``, ``max_gauges``, and
    ``max_timings``; the least-recently-used entry is evicted when a store is
    full. A background daemon thread decays access counts and removes idle
    metrics every ``cleanup_interval`` seconds.

    Metric keys that match known personal-data prefixes (e.g. ``"user."``,
    ``"email."``) are silently dropped so no PII is ever stored.

    Attributes:
        enabled: When ``False``, all recording methods are no-ops.
        max_counters: Maximum number of counter keys before LRU eviction.
        max_gauges: Maximum number of gauge keys before LRU eviction.
        max_timings: Maximum number of timing keys before LRU eviction.
        cleanup_interval: Background cleanup period in seconds.
    """

    def __init__(
        self,
        enabled: bool = True,
        max_counters: int = 10000,
        max_gauges: int = 5000,
        max_timings: int = 1000,
        cleanup_interval: int = 300,
    ) -> None:
        """Create a metrics collector with configurable bounds and cleanup cadence.

        Args:
            enabled: When ``False``, all recording methods become no-ops and no
                background thread is started.
            max_counters: Maximum distinct counter keys to keep in memory.
            max_gauges: Maximum distinct gauge keys to keep in memory.
            max_timings: Maximum distinct timing keys to keep in memory.
            cleanup_interval: Seconds between background cleanup runs.
        """
        self.enabled = enabled
        self.max_counters = max_counters
        self.max_gauges = max_gauges
        self.max_timings = max_timings

        # Metrics storage
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float] = {}
        self._timings: dict[str, TimingStats] = {}

        # Thread safety
        self._lock = threading.RLock()
        self._start_time = time.time()

        # Access tracking for LRU eviction
        self._access_counts: dict[str, int] = defaultdict(int)
        self._last_cleanup = time.time()
        self.cleanup_interval = cleanup_interval

        # GDPR compliance
        self._gdpr_filter = self._create_gdpr_filter()

        # Start cleanup thread if enabled
        self._stop_event = threading.Event()
        if enabled:
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_loop, daemon=True, name="metrics-cleanup"
            )
            self._cleanup_thread.start()

    def increment(
        self, metric: str, value: int = 1, tags: dict[str, str] | None = None
    ) -> None:
        """Increment a counter metric."""
        if not self.enabled or not self._gdpr_filter(metric):
            return

        self._validate_tags(tags)
        key = self._make_key(metric, tags)

        with self._lock:
            # Check bounds
            if key not in self._counters and len(self._counters) >= self.max_counters:
                self._evict_least_used(self._counters)

            self._counters[key] = self._counters.get(key, 0) + value
            self._access_counts[key] += 1

    def gauge(
        self, metric: str, value: float, tags: dict[str, str] | None = None
    ) -> None:
        """Set a gauge metric."""
        if not self.enabled or not self._gdpr_filter(metric):
            return

        self._validate_tags(tags)
        key = self._make_key(metric, tags)

        with self._lock:
            # Check bounds
            if key not in self._gauges and len(self._gauges) >= self.max_gauges:
                self._evict_least_used(self._gauges)

            self._gauges[key] = value
            self._access_counts[key] += 1

    def timing(
        self, metric: str, value: float, tags: dict[str, str] | None = None
    ) -> None:
        """Record a timing metric."""
        if not self.enabled or not self._gdpr_filter(metric):
            return

        self._validate_tags(tags)
        key = self._make_key(metric, tags)

        with self._lock:
            # Check bounds
            if key not in self._timings and len(self._timings) >= self.max_timings:
                self._evict_least_used(self._timings)

            if key not in self._timings:
                self._timings[key] = TimingStats()

            self._timings[key].add(value)
            self._access_counts[key] += 1

    @contextmanager
    def timer(
        self, metric: str, tags: dict[str, str] | None = None
    ) -> Generator[None, None, None]:
        """Context manager for timing operations."""
        start_time = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start_time
            self.timing(metric, duration, tags)

    def get_metrics(self) -> dict[str, Any]:
        """Get all metrics as a dictionary."""
        with self._lock:
            # Trigger cleanup if needed
            if time.time() - self._last_cleanup > self.cleanup_interval:
                self._cleanup()

            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "timings": {
                    metric: {
                        "count": stats.count,
                        "total": stats.total,
                        "mean": stats.mean,
                        "min": stats.min if stats.min != float("inf") else 0,
                        "max": stats.max,
                        "last": stats.last,
                        "samples": len(stats.samples),
                    }
                    for metric, stats in self._timings.items()
                },
                "system": {
                    "uptime_seconds": time.time() - self._start_time,
                    "total_metrics": len(self._counters)
                    + len(self._gauges)
                    + len(self._timings),
                    "memory_usage": {
                        "counters": len(self._counters),
                        "gauges": len(self._gauges),
                        "timings": len(self._timings),
                    },
                },
            }

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._timings.clear()
            self._access_counts.clear()
            self._start_time = time.time()
            self._last_cleanup = time.time()

    def stop(self) -> None:
        """Signal the background cleanup thread to stop and wait for it to exit."""
        stop_event = getattr(self, "_stop_event", None)
        if stop_event is None or stop_event.is_set():
            return
        stop_event.set()
        cleanup_thread = getattr(self, "_cleanup_thread", None)
        if cleanup_thread is not None and cleanup_thread.is_alive():
            cleanup_thread.join(timeout=2)

    def close(self) -> None:
        """Release collector resources."""
        self.stop()

    def __del__(self) -> None:
        with suppress(Exception):
            self.stop()

    def _cleanup_loop(self) -> None:
        """Background cleanup thread."""
        while not self._stop_event.wait(timeout=self.cleanup_interval):
            try:
                with self._lock:
                    self._cleanup()
            except Exception:
                logger.exception("Metrics cleanup error")

    def _cleanup(self) -> None:
        """Perform cleanup of old data."""
        # Clean old timing samples
        max_age = timedelta(hours=1)
        for stats in self._timings.values():
            stats.cleanup_old_samples(max_age)

        # Remove metrics with zero recent access
        zero_access = [k for k, v in self._access_counts.items() if v == 0]
        for key in zero_access:
            self._counters.pop(key, None)
            self._gauges.pop(key, None)
            self._timings.pop(key, None)
            del self._access_counts[key]

        # Decay access counts for next period
        for key in self._access_counts:
            self._access_counts[key] = self._access_counts[key] // 2

        self._last_cleanup = time.time()

        if zero_access:
            logger.debug(
                "Metrics cleanup completed",
                extra={
                    "removed": len(zero_access),
                    "remaining": len(self._counters)
                    + len(self._gauges)
                    + len(self._timings),
                },
            )

    def _evict_least_used(self, store: dict[str, Any]) -> None:
        """Evict the least accessed entry from a metric store."""
        if not store:
            return
        least_used = min(store, key=lambda k: self._access_counts.get(k, 0))
        del store[least_used]
        self._access_counts.pop(least_used, None)

    def _make_key(self, metric: str, tags: dict[str, str] | None = None) -> str:
        """Create a metric key with tags."""
        if not tags:
            return metric

        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{metric}{{{tag_str}}}"

    def _create_gdpr_filter(self) -> Callable[[str], bool]:
        """Create GDPR compliance filter."""
        blocked_patterns = [
            "user.",
            "email.",
            "name.",
            "password.",
            "token.",
            "path.full",
            "file.absolute",
            "personal.",
            "private.",
            "ip.",
            "host.",
            "machine.",
            "username.",
            "address.",
            "phone.",
            "ssn.",
            "credit",
            "account.",
        ]

        def filter_func(metric: str) -> bool:
            metric_lower = metric.lower()
            return not any(pattern in metric_lower for pattern in blocked_patterns)

        return filter_func

    def _validate_tags(self, tags: dict[str, str] | None) -> None:
        """Validate tags for GDPR compliance."""
        if not tags:
            return

        blocked_keys = {
            "user",
            "email",
            "name",
            "password",
            "token",
            "ip",
            "host",
            "username",
            "path",
            "address",
            "phone",
            "ssn",
            "account",
        }

        for key in tags:
            if key.lower() in blocked_keys:
                raise _ValidationError(
                    f"Tag '{key}' may contain personal data and is not allowed. "
                    "Use anonymized identifiers instead.",
                    field_name=key,
                    validation_rule="gdpr_tag_blocklist",
                )


# Global metrics instance
_global_metrics: MetricsCollector | None = None
_metrics_lock = threading.Lock()


def get_metrics() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global _global_metrics

    if _global_metrics is None:
        with _metrics_lock:
            if _global_metrics is None:
                _global_metrics = MetricsCollector()

    return _global_metrics


def configure_metrics(**kwargs: Any) -> MetricsCollector:
    """Configure the global metrics collector."""
    global _global_metrics

    with _metrics_lock:
        if _global_metrics is not None:
            _global_metrics.stop()
        _global_metrics = MetricsCollector(**kwargs)

    return _global_metrics


def reset_metrics() -> None:
    """Stop and discard the global metrics collector.

    Primarily useful for tests and reset_container() so metric data
    does not bleed between test runs.
    """
    global _global_metrics
    with _metrics_lock:
        if _global_metrics is not None:
            _global_metrics.stop()
            _global_metrics = None
