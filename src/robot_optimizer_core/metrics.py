# src/robot_optimizer_core/metrics_safe.py
"""Memory-safe metrics collection with automatic cleanup."""
from __future__ import annotations

import time
import threading
from collections import defaultdict, deque
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Protocol, runtime_checkable

from .logging import get_logger

logger = get_logger(__name__)


@dataclass
class TimingStats:
    """Statistics for timing metrics with bounded memory."""
    count: int = 0
    sum: float = 0.0
    min: float = float('inf')
    max: float = 0.0
    samples: deque[tuple[float, datetime]] = field(default_factory=lambda: deque(maxlen=100))
    
    @property
    def mean(self) -> float:
        """Calculate mean timing."""
        return self.sum / self.count if self.count > 0 else 0.0
    
    def add(self, value: float) -> None:
        """Add a timing value with automatic cleanup."""
        self.count += 1
        self.sum += value
        self.min = min(self.min, value)
        self.max = max(self.max, value)
        self.samples.append((value, datetime.now(timezone.utc)))
    
    def cleanup_old_samples(self, max_age: timedelta) -> None:
        """Remove samples older than max_age."""
        cutoff = datetime.now(timezone.utc) - max_age
        while self.samples and self.samples[0][1] < cutoff:
            self.samples.popleft()


class BoundedInMemoryBackend:
    """Memory-bounded metrics backend with automatic cleanup."""
    
    def __init__(
        self,
        max_counters: int = 10000,
        max_gauges: int = 5000,
        max_timing_samples: int = 1000,
        max_timing_stats: int = 1000,
        cleanup_interval: int = 300  # 5 minutes
    ):
        """Initialize with memory bounds."""
        self.max_counters = max_counters
        self.max_gauges = max_gauges
        self.max_timing_samples = max_timing_samples
        self.max_timing_stats = max_timing_stats
        
        # Use bounded collections
        self.counters: dict[str, int] = {}
        self.gauges: dict[str, float] = {}
        self.timing_stats: dict[str, TimingStats] = {}
        
        # Thread safety
        self._lock = threading.RLock()
        self._start_time = time.time()
        
        # Cleanup tracking
        self._access_counts: dict[str, int] = defaultdict(int)
        self._last_cleanup = time.time()
        self.cleanup_interval = cleanup_interval
        
        # Start cleanup thread
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="metrics-cleanup"
        )
        self._cleanup_thread.start()
    
    def increment(self, metric: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
        """Increment a counter with bounds checking."""
        key = self._make_key(metric, tags)
        
        with self._lock:
            # Check bounds
            if key not in self.counters and len(self.counters) >= self.max_counters:
                self._evict_least_used_counter()
            
            self.counters[key] = self.counters.get(key, 0) + value
            self._access_counts[key] += 1
    
    def gauge(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Set a gauge with bounds checking."""
        key = self._make_key(metric, tags)
        
        with self._lock:
            # Check bounds
            if key not in self.gauges and len(self.gauges) >= self.max_gauges:
                self._evict_least_used_gauge()
            
            self.gauges[key] = value
            self._access_counts[key] += 1
    
    def timing(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record timing with bounded storage."""
        key = self._make_key(metric, tags)
        
        with self._lock:
            # Check bounds
            if key not in self.timing_stats and len(self.timing_stats) >= self.max_timing_stats:
                self._evict_least_used_timing()
            
            if key not in self.timing_stats:
                self.timing_stats[key] = TimingStats()
            
            stats = self.timing_stats[key]
            stats.add(value)
            self._access_counts[key] += 1
    
    def get_metrics(self) -> dict[str, Any]:
        """Get all metrics with cleanup."""
        with self._lock:
            # Cleanup if needed
            if time.time() - self._last_cleanup > self.cleanup_interval:
                self._cleanup()
            
            return {
                "counters": dict(self.counters),
                "gauges": dict(self.gauges),
                "timings": {
                    metric: {
                        "count": stats.count,
                        "sum": stats.sum,
                        "mean": stats.mean,
                        "min": stats.min if stats.min != float('inf') else 0,
                        "max": stats.max,
                        "recent_samples": len(stats.samples)
                    }
                    for metric, stats in self.timing_stats.items()
                },
                "memory_usage": {
                    "counters": len(self.counters),
                    "gauges": len(self.gauges),
                    "timing_stats": len(self.timing_stats),
                    "total_access_counts": len(self._access_counts)
                },
                "uptime_seconds": time.time() - self._start_time
            }
    
    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self.counters.clear()
            self.gauges.clear()
            self.timing_stats.clear()
            self._access_counts.clear()
            self._start_time = time.time()
            self._last_cleanup = time.time()
    
    def _cleanup_loop(self) -> None:
        """Background cleanup thread."""
        while True:
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
        for stats in self.timing_stats.values():
            stats.cleanup_old_samples(max_age)
        
        # Remove metrics with zero access in last period
        zero_access = [k for k, v in self._access_counts.items() if v == 0]
        for key in zero_access:
            self.counters.pop(key, None)
            self.gauges.pop(key, None)
            self.timing_stats.pop(key, None)
            del self._access_counts[key]
        
        # Reset access counts for next period
        for key in self._access_counts:
            self._access_counts[key] = 0
        
        self._last_cleanup = time.time()
        
        logger.debug(
            "Metrics cleanup completed",
            extra={
                "removed": len(zero_access),
                "remaining": {
                    "counters": len(self.counters),
                    "gauges": len(self.gauges),
                    "timings": len(self.timing_stats)
                }
            }
        )
    
    def _evict_least_used_counter(self) -> None:
        """Evict least recently used counter."""
        if not self.counters:
            return
        
        # Find least accessed
        least_used = min(
            (k for k in self.counters if k in self._access_counts),
            key=lambda k: self._access_counts[k],
            default=None
        )
        
        if least_used:
            del self.counters[least_used]
            self._access_counts.pop(least_used, None)
    
    def _evict_least_used_gauge(self) -> None:
        """Evict least recently used gauge."""
        if not self.gauges:
            return
        
        least_used = min(
            (k for k in self.gauges if k in self._access_counts),
            key=lambda k: self._access_counts[k],
            default=None
        )
        
        if least_used:
            del self.gauges[least_used]
            self._access_counts.pop(least_used, None)
    
    def _evict_least_used_timing(self) -> None:
        """Evict least recently used timing stats."""
        if not self.timing_stats:
            return
        
        least_used = min(
            (k for k in self.timing_stats if k in self._access_counts),
            key=lambda k: self._access_counts[k],
            default=None
        )
        
        if least_used:
            del self.timing_stats[least_used]
            self._access_counts.pop(least_used, None)
    
    def _make_key(self, metric: str, tags: dict[str, str] | None = None) -> str:
        """Create a metric key with tags."""
        if not tags:
            return metric
        
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{metric}{{{tag_str}}}"


class MemorySafeMetricsCollector:
    """Memory-safe metrics collector."""
    
    def __init__(
        self,
        backend: BoundedInMemoryBackend | None = None,
        enabled: bool = True,
        max_metrics: int = 10000
    ):
        """Initialize with memory bounds."""
        self.backend = backend or BoundedInMemoryBackend()
        self.enabled = enabled
        self.max_metrics = max_metrics
        
        # GDPR compliance
        self._gdpr_filter = self._create_gdpr_filter()
    
    def increment(self, metric: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
        """Increment counter with memory safety."""
        if not self.enabled or not self._gdpr_filter(metric):
            return
        
        self._validate_tags(tags)
        self.backend.increment(metric, value, tags)
    
    def gauge(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Set gauge with memory safety."""
        if not self.enabled or not self._gdpr_filter(metric):
            return
        
        self._validate_tags(tags)
        self.backend.gauge(metric, value, tags)
    
    def timing(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record timing with memory safety."""
        if not self.enabled or not self._gdpr_filter(metric):
            return
        
        self._validate_tags(tags)
        self.backend.timing(metric, value, tags)
    
    @contextmanager
    def timer(self, metric: str, tags: dict[str, str] | None = None) -> Generator[None, None, None]:
        """Time operations with memory safety."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.timing(metric, duration, tags)
    
    def get_metrics(self) -> dict[str, Any]:
        """Get metrics with memory info."""
        if not self.enabled:
            return {}
        
        metrics = self.backend.get_metrics()
        
        # Add memory warnings
        memory_usage = metrics.get("memory_usage", {})
        total_metrics = sum(memory_usage.values())
        
        if total_metrics > self.max_metrics * 0.8:
            logger.warning(
                "Metrics memory usage high",
                extra={
                    "total": total_metrics,
                    "limit": self.max_metrics,
                    "usage_percent": (total_metrics / self.max_metrics) * 100
                }
            )
        
        return metrics
    
    def reset(self) -> None:
        """Reset all metrics."""
        self.backend.reset()
    
    def _create_gdpr_filter(self) -> Callable[[str], bool]:
        """Create GDPR compliance filter."""
        blocked_patterns = [
            "user.", "email.", "name.", "path.full",
            "file.absolute", "personal.", "private.",
            "ip.", "host.", "machine.", "username."
        ]
        
        def filter_func(metric: str) -> bool:
            metric_lower = metric.lower()
            return not any(pattern in metric_lower for pattern in blocked_patterns)
        
        return filter_func
    
    def _validate_tags(self, tags: dict[str, str] | None) -> None:
        """Validate tags for GDPR compliance."""
        if not tags:
            return
        
        blocked_keys = {"user", "email", "name", "ip", "host", "username", "path"}
        
        for key in tags:
            if key.lower() in blocked_keys:
                raise ValueError(
                    f"Tag '{key}' may contain personal data and is not allowed"
                )


# Example: Memory-safe domain events
class BoundedEventStore:
    """Bounded event store for aggregates."""
    
    def __init__(self, max_events_per_aggregate: int = 100):
        """Initialize with bounds."""
        self.max_events = max_events_per_aggregate
        self._events: dict[str, deque] = defaultdict(lambda: deque(maxlen=self.max_events))
        self._lock = threading.Lock()
    
    def add_event(self, aggregate_id: str, event: Any) -> None:
        """Add event with automatic cleanup."""
        with self._lock:
            self._events[aggregate_id].append(event)
    
    def pull_events(self, aggregate_id: str) -> list[Any]:
        """Pull and clear events for aggregate."""
        with self._lock:
            events = list(self._events[aggregate_id])
            self._events[aggregate_id].clear()
            return events
    
    def get_event_count(self, aggregate_id: str) -> int:
        """Get pending event count."""
        with self._lock:
            return len(self._events.get(aggregate_id, []))