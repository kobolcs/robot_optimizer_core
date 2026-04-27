# src/robot_optimizer_core/metrics.py
"""Modern memory-safe metrics collection with GDPR compliance."""
from __future__ import annotations

import logging as _stdlib_logging
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = _stdlib_logging.getLogger(__name__)


@dataclass
class TimingStats:
    """Statistics for timing metrics with bounded memory."""
    count: int = 0
    total: float = 0.0
    min: float = float("inf")
    max: float = 0.0
    samples: deque[tuple[float, datetime]] = field(default_factory=lambda: deque(maxlen=100))

    @property
    def mean(self) -> float:
        """Calculate mean timing."""
        return self.total / self.count if self.count > 0 else 0.0

    @property
    def last(self) -> float | None:
        """Get the last recorded value."""
        return self.samples[-1][0] if self.samples else None

    def add(self, value: float) -> None:
        """Add a timing value."""
        self.count += 1
        self.total += value
        self.min = min(self.min, value)
        self.max = max(self.max, value)
        self.samples.append((value, datetime.now(UTC)))

    def cleanup_old_samples(self, max_age: timedelta) -> None:
        """Remove samples older than max_age."""
        cutoff = datetime.now(UTC) - max_age
        while self.samples and self.samples[0][1] < cutoff:
            self.samples.popleft()


class MetricsCollector:
    """Modern metrics collector with memory safety and GDPR compliance.

    Features:
    - Bounded memory usage with automatic cleanup
    - GDPR-compliant filtering of personal data
    - Thread-safe operations
    - Efficient storage with automatic eviction
    """

    def __init__(
        self,
        enabled: bool = True,
        max_counters: int = 10000,
        max_gauges: int = 5000,
        max_timings: int = 1000,
        cleanup_interval: int = 300  # 5 minutes
    ):
        """Initialize metrics collector."""
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
        if enabled:
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_loop,
                daemon=True,
                name="metrics-cleanup"
            )
            self._cleanup_thread.start()

    def increment(self, metric: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
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

    def gauge(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
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

    def timing(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
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
    def timer(self, metric: str, tags: dict[str, str] | None = None) -> Generator[None, None, None]:
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
                        "samples": len(stats.samples)
                    }
                    for metric, stats in self._timings.items()
                },
                "system": {
                    "uptime_seconds": time.time() - self._start_time,
                    "total_metrics": len(self._counters) + len(self._gauges) + len(self._timings),
                    "memory_usage": {
                        "counters": len(self._counters),
                        "gauges": len(self._gauges),
                        "timings": len(self._timings)
                    }
                }
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

    def _cleanup_loop(self) -> None:
        """Background cleanup thread."""
        while self.enabled:
            try:
                time.sleep(self.cleanup_interval)
                with self._lock:
                    self._cleanup()
            except Exception as e:
                logger.error(f"Metrics cleanup error: {e}")

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
                    "remaining": len(self._counters) + len(self._gauges) + len(self._timings)
                }
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
            "user.", "email.", "name.", "password.", "token.",
            "path.full", "file.absolute", "personal.", "private.",
            "ip.", "host.", "machine.", "username.", "address.",
            "phone.", "ssn.", "credit", "account."
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
            "user", "email", "name", "password", "token",
            "ip", "host", "username", "path", "address",
            "phone", "ssn", "account"
        }

        for key in tags:
            if key.lower() in blocked_keys:
                raise ValueError(
                    f"Tag '{key}' may contain personal data and is not allowed. "
                    f"Use anonymized identifiers instead."
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
        _global_metrics = MetricsCollector(**kwargs)

    return _global_metrics
