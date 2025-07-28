# src/robot_optimizer_core/metrics.py
"""GDPR-compliant metrics collection for Robot Framework Optimizer Core.

This module provides basic metrics collection that respects user privacy.
No personal data is collected, only anonymous usage statistics.

The metrics system is designed to be extended by the Pro version with
additional backends (e.g., Prometheus, StatsD).

Example:
    Collecting metrics::
    
        from robot_optimizer_core import get_metrics
        
        metrics = get_metrics()
        metrics.increment("analysis.completed")
        metrics.timing("analysis.duration", 1.5)
        metrics.gauge("findings.count", 10)
"""
from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MetricsBackend(Protocol):
    """Protocol for metrics storage backends.
    
    This protocol defines the interface that metrics backends must implement.
    The Pro version can provide additional backends like Prometheus or StatsD.
    """

    def increment(self, metric: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
        """Increment a counter metric.
        
        Args:
            metric: Metric name.
            value: Value to increment by.
            tags: Optional tags for the metric.
        """
        ...

    def gauge(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Set a gauge metric.
        
        Args:
            metric: Metric name.
            value: Gauge value.
            tags: Optional tags for the metric.
        """
        ...

    def timing(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record a timing metric.
        
        Args:
            metric: Metric name.
            value: Time in seconds.
            tags: Optional tags for the metric.
        """
        ...

    def get_metrics(self) -> dict[str, Any]:
        """Get all collected metrics.
        
        Returns:
            Dictionary of metrics.
        """
        ...

    def reset(self) -> None:
        """Reset all metrics."""
        ...


@dataclass
class TimingStats:
    """Statistics for timing metrics."""
    count: int = 0
    sum: float = 0.0
    min: float = float('inf')
    max: float = 0.0

    @property
    def mean(self) -> float:
        """Calculate mean timing."""
        return self.sum / self.count if self.count > 0 else 0.0

    def add(self, value: float) -> None:
        """Add a timing value."""
        self.count += 1
        self.sum += value
        self.min = min(self.min, value)
        self.max = max(self.max, value)


class InMemoryBackend:
    """Simple in-memory metrics backend.
    
    This backend stores metrics in memory and is suitable for
    development and testing. It does not persist metrics.
    
    Attributes:
        counters: Counter metrics.
        gauges: Gauge metrics.
        timings: Timing metrics with statistics.
    """

    __slots__ = ('_start_time', 'counters', 'gauges', 'timings')

    def __init__(self) -> None:
        """Initialize the in-memory backend."""
        self.counters: dict[str, int] = defaultdict(int)
        self.gauges: dict[str, float] = {}
        self.timings: dict[str, list[float]] = defaultdict(list)
        self._start_time = time.time()

    def increment(self, metric: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
        """Increment a counter metric."""
        key = self._make_key(metric, tags)
        self.counters[key] += value

    def gauge(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Set a gauge metric."""
        key = self._make_key(metric, tags)
        self.gauges[key] = value

    def timing(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record a timing metric."""
        key = self._make_key(metric, tags)
        self.timings[key].append(value)

    def get_metrics(self) -> dict[str, Any]:
        """Get all collected metrics with statistics."""
        return {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "timings": {
                metric: {
                    "count": len(values),
                    "sum": sum(values),
                    "mean": sum(values) / len(values) if values else 0,
                    "min": min(values) if values else 0,
                    "max": max(values) if values else 0,
                }
                for metric, values in self.timings.items()
            },
            "uptime_seconds": time.time() - self._start_time,
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self.counters.clear()
        self.gauges.clear()
        self.timings.clear()
        self._start_time = time.time()

    def _make_key(self, metric: str, tags: dict[str, str] | None = None) -> str:
        """Create a metric key with tags.
        
        Args:
            metric: Base metric name.
            tags: Optional tags.
            
        Returns:
            Metric key including tags.
        """
        if not tags:
            return metric

        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{metric}{{{tag_str}}}"


class MetricsCollector:
    """Main metrics collector with GDPR compliance.
    
    This collector ensures that no personal data is collected in metrics.
    It provides a simple API for collecting anonymous usage statistics.
    
    Attributes:
        backend: The metrics storage backend.
        enabled: Whether metrics collection is enabled.
        filters: List of metric name filters.
    """

    __slots__ = ('backend', 'enabled', 'filters')

    def __init__(
        self,
        backend: MetricsBackend | None = None,
        enabled: bool = True,
        filters: list[Callable[[str], bool]] | None = None
    ) -> None:
        """Initialize the metrics collector.
        
        Args:
            backend: Metrics storage backend (default: InMemoryBackend).
            enabled: Whether to collect metrics.
            filters: Optional filters to exclude certain metrics.
        """
        self.backend = backend or InMemoryBackend()
        self.enabled = enabled
        self.filters = filters or []

        # Add default GDPR filter
        self.filters.append(self._gdpr_filter)

    def increment(self, metric: str, value: int = 1, tags: dict[str, str] | None = None) -> None:
        """Increment a counter metric.
        
        Args:
            metric: Metric name (e.g., "analysis.completed").
            value: Value to increment by.
            tags: Optional tags (must not contain personal data).
            
        Example:
            >>> metrics.increment("analyzer.dead_code.findings", value=5)
        """
        if not self.enabled or not self._should_collect(metric):
            return

        self._validate_tags(tags)
        self.backend.increment(metric, value, tags)

    def gauge(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Set a gauge metric.
        
        Args:
            metric: Metric name (e.g., "memory.usage_mb").
            value: Gauge value.
            tags: Optional tags (must not contain personal data).
            
        Example:
            >>> metrics.gauge("active.analyzers", 3)
        """
        if not self.enabled or not self._should_collect(metric):
            return

        self._validate_tags(tags)
        self.backend.gauge(metric, value, tags)

    def timing(self, metric: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record a timing metric.
        
        Args:
            metric: Metric name (e.g., "analysis.duration").
            value: Time in seconds.
            tags: Optional tags (must not contain personal data).
            
        Example:
            >>> metrics.timing("parser.duration", 0.150)
        """
        if not self.enabled or not self._should_collect(metric):
            return

        self._validate_tags(tags)
        self.backend.timing(metric, value, tags)

    @contextmanager
    def timer(self, metric: str, tags: dict[str, str] | None = None) -> Generator[None, None, None]:
        """Context manager for timing operations.
        
        Args:
            metric: Metric name for the timing.
            tags: Optional tags.
            
        Yields:
            None
            
        Example:
            >>> with metrics.timer("analysis.total_duration"):
            ...     analyze_file("test.robot")
        """
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.timing(metric, duration, tags)

    def get_metrics(self) -> dict[str, Any]:
        """Get all collected metrics.
        
        Returns:
            Dictionary of collected metrics.
        """
        if not self.enabled:
            return {}
        return self.backend.get_metrics()

    def reset(self) -> None:
        """Reset all metrics."""
        self.backend.reset()

    def _should_collect(self, metric: str) -> bool:
        """Check if a metric should be collected.
        
        Args:
            metric: Metric name.
            
        Returns:
            True if metric should be collected.
        """
        return all(f(metric) for f in self.filters)

    def _gdpr_filter(self, metric: str) -> bool:
        """GDPR compliance filter.
        
        This filter prevents collection of metrics that might
        contain personal data.
        
        Args:
            metric: Metric name.
            
        Returns:
            True if metric is GDPR compliant.
        """
        # Reject metrics with potential personal data
        blocked_patterns = [
            "user.", "email.", "name.", "path.full",
            "file.absolute", "personal.", "private."
        ]

        metric_lower = metric.lower()
        return not any(pattern in metric_lower for pattern in blocked_patterns)

    def _validate_tags(self, tags: dict[str, str] | None) -> None:
        """Validate that tags don't contain personal data.
        
        Args:
            tags: Tags to validate.
            
        Raises:
            ValueError: If tags contain potential personal data.
        """
        if not tags:
            return

        blocked_keys = {"user", "email", "name", "ip", "host", "username"}

        for key in tags:
            if key.lower() in blocked_keys:
                raise ValueError(
                    f"Tag '{key}' may contain personal data and is not allowed"
                )


# Global metrics instance
_metrics: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    """Get the global metrics collector.
    
    Returns:
        The global metrics collector instance.
        
    Example:
        >>> metrics = get_metrics()
        >>> metrics.increment("analysis.started")
    """
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics


def configure_metrics(
    backend: MetricsBackend | None = None,
    enabled: bool = True,
    filters: list[Callable[[str], bool]] | None = None
) -> None:
    """Configure the global metrics collector.
    
    Args:
        backend: Metrics storage backend.
        enabled: Whether to enable metrics collection.
        filters: Additional metric filters.
        
    Example:
        >>> configure_metrics(enabled=False)  # Disable metrics
    """
    global _metrics
    _metrics = MetricsCollector(backend, enabled, filters)
