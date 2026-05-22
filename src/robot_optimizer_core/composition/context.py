# src/robot_optimizer_core/composition/context.py
"""Application context to eliminate global state and improve testability."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..application.analyzers.registry import AnalyzerRegistry
from ..infrastructure.config.settings import Settings
from .container import (
    ThreadSafeContainer,
    _register_defaults,
    _set_global_container,
    reset_container,
)
from ..infrastructure.discovery import FileDiscoveryService
from ..exceptions import ConfigurationError
from ..infrastructure.logging.adapter import LoggerAdapter, configure_logging
from ..infrastructure.metrics.collector import MetricsCollector
from ..infrastructure.plugins.manager import ValidatedPluginManager


class ScopedContainer(Protocol):
    """Minimal interface for a request-scoped DI container.

    Returned by :meth:`ApplicationContext.request_scope`.  Callers only need
    :meth:`register_instance` and :meth:`resolve`; the concrete implementation
    (``ThreadSafeContainer``) remains a private detail of the ``di`` module.
    """

    def register_instance(
        self, service_type: str, instance: Any, override: bool = False
    ) -> None: ...  # pragma: no cover

    def resolve(self, service_type: str) -> Any: ...  # pragma: no cover


@runtime_checkable
class Service(Protocol):
    """Protocol for services that can be managed by context."""

    def initialize(self, context: ApplicationContext) -> None:
        """Initialize the service with context."""
        ...  # pragma: no cover

    def shutdown(self) -> None:
        """Shutdown the service cleanly."""
        ...  # pragma: no cover


@dataclass
class ApplicationConfig:
    """Configuration for the application context."""

    settings: Settings = field(default_factory=Settings)
    enable_plugins: bool = True
    enable_metrics: bool = True
    enable_logging: bool = True
    log_level: str = "INFO"
    log_format_json: bool | None = None  # None = auto-detect from TTY
    max_memory_mb: int = 500
    thread_pool_size: int = 4

    def validate(self) -> None:
        """Validate configuration."""
        if self.max_memory_mb < 100:
            raise ConfigurationError("max_memory_mb must be at least 100")

        if self.thread_pool_size < 1:
            raise ConfigurationError("thread_pool_size must be at least 1")

        # Validate settings
        self.settings.validate_settings()


class ApplicationContext:
    """Application context that manages all services without global state.

    This replaces all global singletons with a proper context that can be
    created, configured, and destroyed for each use (especially tests).
    """

    def __init__(self, config: ApplicationConfig | None = None):
        """Initialize application context.

        Args:
            config: Application configuration
        """
        self.config = config or ApplicationConfig()
        self.config.validate()

        # Core services (not global!)
        self._container: ThreadSafeContainer | None = None
        self._metrics: MetricsCollector | None = None
        self._plugin_manager: ValidatedPluginManager | None = None
        self._analyzer_registry: AnalyzerRegistry | None = None
        self._loggers: dict[str, LoggerAdapter] = {}

        # Thread-local storage for request context
        self._local = threading.local()

        # Lifecycle tracking
        self._initialized = False
        self._shutdown = False

        # Lock for thread safety
        self._lock = threading.RLock()

    def initialize(self) -> None:
        """Initialize the application context.

        .. warning::
            This method resets the global DI container (via ``reset_container``) and
            replaces it with a new one configured for this context.  Only one
            ``ApplicationContext`` instance may be active at a time; creating and
            initialising a second instance will silently discard the first context's
            container registrations.
        """
        with self._lock:
            if self._initialized:
                return

            if self._shutdown:
                raise RuntimeError("Cannot initialize after shutdown")

            if self.config.enable_logging:
                configure_logging(
                    level=self.config.log_level,
                    format_json=self.config.log_format_json,
                    enable_metrics=False,
                )

            # Reset and configure the global DI container so that api.py's
            # get_container() calls see the settings and services this context
            # was constructed with — both paths converge on the same container.
            reset_container()
            self._container = ThreadSafeContainer()
            _register_defaults(self._container)
            _set_global_container(self._container)

            self._container.register_instance(
                "settings", self.config.settings, override=True
            )
            settings = self.config.settings
            self._container.register_singleton(
                "file_discovery",
                lambda: FileDiscoveryService(settings),
                override=True,
            )
            self._container.register_instance("context", self)

            if self.config.enable_metrics:
                self._metrics = MetricsCollector(enabled=True)
                self._container.register_instance(
                    "metrics", self._metrics, override=True
                )

            # The global registry is already populated by _register_defaults
            # (via get_analyzer_registry / entry-point discovery).
            self._analyzer_registry = self._container.resolve("analyzer_registry")

            if self.config.enable_plugins:
                self._plugin_manager = ValidatedPluginManager()
                self._container.register_instance(
                    "plugin_manager", self._plugin_manager
                )

            self._initialized = True

    def shutdown(self) -> None:
        """Shutdown the application context and clean up resources."""
        with self._lock:
            if self._shutdown:
                return

            if self._plugin_manager:
                for plugin_name in list(self._plugin_manager.plugins.keys()):
                    self._plugin_manager.unload_plugin(plugin_name)

            if self._metrics:
                self._metrics.reset()

            self._loggers.clear()
            self._analyzer_registry = None

            reset_container()

            self._shutdown = True
            self._initialized = False

    @property
    def container(self) -> ScopedContainer:
        """Return the DI container managed by this context."""
        if not self._initialized:
            raise RuntimeError(
                "ApplicationContext not initialized — call .initialize() first "
                "or use it as a context manager: `with ApplicationContext() as ctx:`"
            )
        return self._container  # type: ignore[return-value]

    @property
    def metrics(self) -> MetricsCollector:
        """Get the metrics collector."""
        if not self._initialized:
            raise RuntimeError(
                "ApplicationContext not initialized — call .initialize() first "
                "or use it as a context manager: `with ApplicationContext() as ctx:`"
            )

        if not self._metrics:
            raise RuntimeError("Metrics not enabled")

        return self._metrics

    @property
    def settings(self) -> Settings:
        """Get application settings."""
        return self.config.settings

    @property
    def analyzer_registry(self) -> AnalyzerRegistry:
        """Get the analyzer registry."""
        if not self._initialized:
            raise RuntimeError(
                "ApplicationContext not initialized — call .initialize() first "
                "or use it as a context manager: `with ApplicationContext() as ctx:`"
            )

        if not self._analyzer_registry:
            raise RuntimeError("Analyzer registry not available")

        return self._analyzer_registry

    def get_logger(
        self, name: str, context: dict[str, Any] | None = None
    ) -> LoggerAdapter:
        """Get a logger instance.

        Args:
            name: Logger name
            context: Logger context

        Returns:
            Logger adapter
        """
        if name not in self._loggers:
            # Create logger without global state
            import logging

            logger = logging.getLogger(name)

            # Create adapter with context
            from ..infrastructure.logging.adapter import LoggerAdapter

            adapter = LoggerAdapter(logger, context or {})

            self._loggers[name] = adapter

        return self._loggers[name]

    def get_diagnostic_report(self) -> dict[str, Any]:
        """Return a snapshot of key runtime state for debugging and support.

        Returns:
            Dictionary containing initialization state, registered services,
            analyzer list, active plugins, and metrics summary.
        """
        report: dict[str, Any] = {
            "initialized": self._initialized,
            "shutdown": self._shutdown,
            "services": [],
            "analyzers": [],
            "plugins": [],
            "metrics": None,
        }

        if self._initialized and self._container is not None:
            try:
                from .container import get_container as _get_container
                report["services"] = _get_container()._list_all_services()
            except Exception:
                pass

        if self._analyzer_registry is not None:
            try:
                report["analyzers"] = self._analyzer_registry.list()
            except Exception:
                pass

        if self._plugin_manager is not None:
            try:
                report["plugins"] = list(self._plugin_manager.plugins.keys())
            except Exception:
                pass

        if self._metrics is not None:
            try:
                m = self._metrics.get_metrics()
                report["metrics"] = {
                    "total_metrics": m["system"]["total_metrics"],
                    "uptime_seconds": m["system"]["uptime_seconds"],
                }
            except Exception:
                pass

        return report

    @contextmanager
    def request_scope(self, **context: Any) -> Iterator[ScopedContainer]:
        """Create a request-scoped context.

        Args:
            **context: Request context values

        Yields:
            Request scope
        """
        # Store in thread-local
        if not hasattr(self._local, "context"):
            self._local.context = {}

        old_context = self._local.context.copy()
        self._local.context.update(context)

        # Create scoped container
        if not self._initialized or self._container is None:
            raise RuntimeError(
                "ApplicationContext not initialized — call .initialize() first"
            )
        with self._container.create_scope() as scoped_container:
            # Register request-scoped services
            scoped_container.register_instance("request_context", self._local.context)

            try:
                yield scoped_container
            finally:
                # Restore context
                self._local.context = old_context

    def __enter__(self) -> ApplicationContext:
        """Context manager entry."""
        self.initialize()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Context manager exit."""
        self.shutdown()


# Factory functions (no globals!)
def create_application(config: ApplicationConfig | None = None) -> ApplicationContext:
    """Create a new application context.

    Args:
        config: Application configuration

    Returns:
        New application context
    """
    return ApplicationContext(config)


def create_test_application() -> ApplicationContext:
    """Create an application context for testing.

    Returns:
        Test application context with minimal configuration
    """
    config = ApplicationConfig(
        enable_plugins=False,  # Disable plugins for tests
        enable_metrics=False,  # Disable metrics for tests
        enable_logging=False,  # Disable logging for tests
        settings=Settings(
            max_file_size_mb=1.0,  # Small files for tests
            file_patterns=["*.robot"],
            exclude_patterns=["**/.*"],
        ),
    )

    return ApplicationContext(config)
