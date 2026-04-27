# src/robot_optimizer_core/context.py
"""Application context to eliminate global state and improve testability."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .analyzers.registry import AnalyzerRegistry
from .config.settings import Settings
from .di import ThreadSafeContainer
from .discovery.file_finder import FileDiscoveryService
from .logging import LoggerAdapter, configure_logging
from .metrics import MetricsCollector
from .parsers.robot_ast_parser import RobotASTParser
from .plugin import SecurePluginManager


@runtime_checkable
class Service(Protocol):
    """Protocol for services that can be managed by context."""

    def initialize(self, context: ApplicationContext) -> None:
        """Initialize the service with context."""
        ...

    def shutdown(self) -> None:
        """Shutdown the service cleanly."""
        ...


@dataclass
class ApplicationConfig:
    """Configuration for the application context."""
    settings: Settings = field(default_factory=Settings)
    enable_plugins: bool = True
    enable_metrics: bool = True
    enable_logging: bool = True
    log_level: str = "INFO"
    log_format_json: bool = True
    max_memory_mb: int = 500
    thread_pool_size: int = 4

    def validate(self) -> None:
        """Validate configuration."""
        if self.max_memory_mb < 100:
            raise ValueError("max_memory_mb must be at least 100")

        if self.thread_pool_size < 1:
            raise ValueError("thread_pool_size must be at least 1")

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
        self._plugin_manager: SecurePluginManager | None = None
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
        """Initialize the application context."""
        with self._lock:
            if self._initialized:
                return

            if self._shutdown:
                raise RuntimeError("Cannot initialize after shutdown")

            # Initialize logging
            if self.config.enable_logging:
                configure_logging(
                    level=self.config.log_level,
                    format_json=self.config.log_format_json,
                    enable_metrics=False  # We have our own metrics
                )

            # Initialize container
            self._container = ThreadSafeContainer()
            self._setup_container()

            # Initialize metrics
            if self.config.enable_metrics:
                self._metrics = MetricsCollector(
                    enabled=True
                )
                self._container.register_instance("metrics", self._metrics)

            # Initialize analyzer registry
            self._analyzer_registry = AnalyzerRegistry()
            self._register_builtin_analyzers()

            # Initialize plugin manager
            if self.config.enable_plugins:
                self._plugin_manager = SecurePluginManager(
                    registry=self._analyzer_registry
                )
                self._container.register_instance("plugin_manager", self._plugin_manager)

            self._initialized = True

    def shutdown(self) -> None:
        """Shutdown the application context and clean up resources."""
        with self._lock:
            if self._shutdown:
                return

            # Shutdown services in reverse order
            if self._plugin_manager:
                for plugin_name in list(self._plugin_manager.plugins.keys()):
                    self._plugin_manager.unload_plugin(plugin_name)

            if self._metrics:
                self._metrics.reset()

            if self._container:
                self._container.clear()

            self._loggers.clear()
            self._analyzer_registry = None

            self._shutdown = True
            self._initialized = False

    @property
    def container(self) -> ThreadSafeContainer:
        """Get the DI container."""
        if not self._initialized:
            self.initialize()

        if not self._container:
            raise RuntimeError("Container not available")

        return self._container

    @property
    def metrics(self) -> MetricsCollector:
        """Get the metrics collector."""
        if not self._initialized:
            self.initialize()

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
            self.initialize()

        if not self._analyzer_registry:
            raise RuntimeError("Analyzer registry not available")

        return self._analyzer_registry

    def get_logger(self, name: str, context: dict[str, Any] | None = None) -> LoggerAdapter:
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
            from .logging import LoggerAdapter
            adapter = LoggerAdapter(logger, context or {})

            self._loggers[name] = adapter

        return self._loggers[name]

    def _setup_container(self) -> None:
        """Set up the DI container with services."""
        # Register settings
        self._container.register_instance("settings", self.config.settings)

        # Register core services
        self._container.register_singleton(
            "file_discovery",
            lambda: FileDiscoveryService(self.config.settings)
        )

        self._container.register(
            "parser",
            RobotASTParser
        )

        # Register context itself for services that need it
        self._container.register_instance("context", self)

    def _register_builtin_analyzers(self) -> None:
        """Register built-in analyzers."""
        from .analyzers.dead_code import DeadCodeAnalyzer
        from .analyzers.flakiness import FlakinessAnalyzer
        from .analyzers.sleep_detector import SleepDetector

        self._analyzer_registry.register("dead_code", DeadCodeAnalyzer)
        self._analyzer_registry.register("sleep_detector", SleepDetector)
        self._analyzer_registry.register("flakiness", FlakinessAnalyzer)

    @contextmanager
    def request_scope(self, **context: Any):
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
        with self.container.create_scope() as scoped_container:
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

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
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
            exclude_patterns=["**/.*"]
        )
    )

    return ApplicationContext(config)
