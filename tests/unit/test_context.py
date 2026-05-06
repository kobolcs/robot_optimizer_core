# tests/unit/test_context.py
"""Tests for ApplicationContext and related factories."""

from __future__ import annotations

import pytest

from robot_optimizer_core.context import (
    ApplicationConfig,
    ApplicationContext,
    create_application,
    create_test_application,
)


class TestApplicationConfig:
    def test_default_config_is_valid(self) -> None:
        config = ApplicationConfig()
        config.validate()

    def test_low_memory_mb_raises(self) -> None:
        config = ApplicationConfig(max_memory_mb=50)
        with pytest.raises(ValueError, match="max_memory_mb"):
            config.validate()

    def test_zero_thread_pool_raises(self) -> None:
        config = ApplicationConfig(thread_pool_size=0)
        with pytest.raises(ValueError, match="thread_pool_size"):
            config.validate()


class TestApplicationContextLifecycle:
    def test_initialize_sets_initialized_flag(self) -> None:
        ctx = create_test_application()
        ctx.initialize()
        assert ctx._initialized
        ctx.shutdown()

    def test_initialize_is_idempotent(self) -> None:
        ctx = create_test_application()
        ctx.initialize()
        ctx.initialize()
        assert ctx._initialized
        ctx.shutdown()

    def test_shutdown_sets_shutdown_flag(self) -> None:
        ctx = create_test_application()
        ctx.initialize()
        ctx.shutdown()
        assert ctx._shutdown
        assert not ctx._initialized

    def test_shutdown_is_idempotent(self) -> None:
        ctx = create_test_application()
        ctx.initialize()
        ctx.shutdown()
        ctx.shutdown()
        assert ctx._shutdown

    def test_cannot_reinitialize_after_shutdown(self) -> None:
        ctx = create_test_application()
        ctx.initialize()
        ctx.shutdown()
        with pytest.raises(RuntimeError, match="after shutdown"):
            ctx.initialize()

    def test_context_manager_initializes_and_shuts_down(self) -> None:
        with create_test_application() as ctx:
            assert ctx._initialized
        assert ctx._shutdown


class TestApplicationContextProperties:
    def test_container_lazy_initializes(self) -> None:
        ctx = create_test_application()
        assert not ctx._initialized
        container = ctx.container
        assert ctx._initialized
        assert container is not None
        ctx.shutdown()

    def test_settings_returns_config_settings(self) -> None:
        ctx = create_test_application()
        assert ctx.settings is ctx.config.settings

    def test_analyzer_registry_returns_registry(self) -> None:
        ctx = create_test_application()
        ctx.initialize()
        registry = ctx.analyzer_registry
        assert registry is not None
        ctx.shutdown()

    def test_analyzer_registry_raises_after_shutdown(self) -> None:
        ctx = create_test_application()
        ctx.initialize()
        ctx.shutdown()
        with pytest.raises(RuntimeError):
            _ = ctx.analyzer_registry

    def test_metrics_raises_when_disabled(self) -> None:
        ctx = create_test_application()
        ctx.initialize()
        with pytest.raises(RuntimeError, match="not enabled"):
            _ = ctx.metrics
        ctx.shutdown()

    def test_metrics_available_when_enabled(self) -> None:
        config = ApplicationConfig(
            enable_plugins=False,
            enable_metrics=True,
            enable_logging=False,
        )
        with ApplicationContext(config) as ctx:
            assert ctx.metrics is not None


class TestApplicationContextLogger:
    def test_get_logger_returns_adapter(self) -> None:
        ctx = create_test_application()
        logger = ctx.get_logger("test.module")
        assert logger is not None

    def test_get_logger_caches_instance(self) -> None:
        ctx = create_test_application()
        l1 = ctx.get_logger("cached.name")
        l2 = ctx.get_logger("cached.name")
        assert l1 is l2

    def test_get_logger_with_context(self) -> None:
        ctx = create_test_application()
        logger = ctx.get_logger("test.module", context={"request_id": "abc"})
        assert logger is not None


class TestApplicationContextRequestScope:
    def test_request_scope_yields_container(self) -> None:
        with create_test_application() as ctx:
            with ctx.request_scope(user_id="test123") as scoped:
                assert scoped is not None

    def test_request_scope_restores_context_after_exit(self) -> None:
        with create_test_application() as ctx:
            with ctx.request_scope(key="value"):
                pass
            # After exiting scope, context should be restored
            assert not hasattr(ctx._local, "context") or ctx._local.context == {}


class TestFactoryFunctions:
    def test_create_application_returns_context(self) -> None:
        ctx = create_application()
        assert isinstance(ctx, ApplicationContext)
        ctx.shutdown()

    def test_create_test_application_disables_plugins_metrics_logging(self) -> None:
        ctx = create_test_application()
        assert not ctx.config.enable_plugins
        assert not ctx.config.enable_metrics
        assert not ctx.config.enable_logging

    def test_create_test_application_small_max_file_size(self) -> None:
        ctx = create_test_application()
        assert ctx.config.settings.max_file_size_mb == 1.0


class TestBuiltinAnalyzerRegistration:
    """Verify ApplicationContext registers all built-in analyzers."""

    EXPECTED_BUILTINS = {
        "dead_code",
        "sleep_detector",
        "flakiness",
        "hardcoded_value",
        "naming_convention",
        "setup_teardown",
        "tag_consistency",
        "test_documentation",
    }

    def test_all_builtin_analyzers_registered(self) -> None:
        ctx = create_test_application()
        ctx.initialize()
        registered = set(ctx.analyzer_registry.list())
        missing = self.EXPECTED_BUILTINS - registered
        assert not missing, f"ApplicationContext missing analyzers: {missing}"
        ctx.shutdown()

    def test_no_builtin_analyzer_is_missing_after_reinit(self) -> None:
        ctx = create_test_application()
        ctx.initialize()
        ctx.shutdown()
        ctx2 = create_test_application()
        ctx2.initialize()
        registered = set(ctx2.analyzer_registry.list())
        missing = self.EXPECTED_BUILTINS - registered
        assert not missing, f"Missing after re-init: {missing}"
        ctx2.shutdown()


class TestShutdownCleanup:
    def test_shutdown_clears_analyzer_registry(self) -> None:
        ctx = create_test_application()
        ctx.initialize()
        assert ctx._analyzer_registry is not None
        ctx.shutdown()
        assert ctx._analyzer_registry is None

    def test_shutdown_with_metrics_resets_them(self) -> None:
        config = ApplicationConfig(
            enable_plugins=False,
            enable_metrics=True,
            enable_logging=False,
        )
        ctx = ApplicationContext(config)
        ctx.initialize()
        ctx.metrics.increment("test.counter")
        ctx.shutdown()
        assert ctx._shutdown
