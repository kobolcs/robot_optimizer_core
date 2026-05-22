# tests/unit/test_logging.py
"""Unit tests for structured logging."""

from __future__ import annotations

import json
import logging

import pytest

from robot_optimizer_core.logging import (
    LoggerAdapter,
    StructuredFormatter,
    configure_logging,
    get_logger,
)


@pytest.mark.unit
class TestStructuredFormatter:
    def _make_record(
        self, msg: str = "hello", level: int = logging.INFO
    ) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test",
            level=level,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        return record

    def test_output_is_valid_json(self) -> None:
        fmt = StructuredFormatter()
        record = self._make_record("test message")
        output = fmt.format(record)
        data = json.loads(output)
        assert data["message"] == "test message"
        assert data["level"] == "INFO"

    def test_required_fields_present(self) -> None:
        fmt = StructuredFormatter()
        data = json.loads(fmt.format(self._make_record()))
        for field in (
            "timestamp",
            "level",
            "logger",
            "message",
            "module",
            "function",
            "line",
        ):
            assert field in data

    def test_extra_fields_included(self) -> None:
        fmt = StructuredFormatter()
        record = self._make_record()
        record.analyzer = "dead_code"
        data = json.loads(fmt.format(record))
        assert data.get("extra", {}).get("analyzer") == "dead_code"

    def test_message_key_not_in_extra(self) -> None:
        fmt = StructuredFormatter()
        record = self._make_record()
        record.message = "should be filtered"  # type: ignore[attr-defined]
        data = json.loads(fmt.format(record))
        assert "message" not in data.get("extra", {})

    def test_exception_info_included(self) -> None:
        fmt = StructuredFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = self._make_record()
            record.exc_info = sys.exc_info()
            data = json.loads(fmt.format(record))
            assert "exception" in data


@pytest.mark.unit
class TestGetLogger:
    def test_returns_logger_adapter(self) -> None:
        logger = get_logger("test.module")
        assert isinstance(logger, LoggerAdapter)

    def test_context_stored(self) -> None:
        logger = get_logger("test.ctx", {"component": "analyzer"})
        assert logger.extra.get("component") == "analyzer"

    def test_same_name_different_context(self) -> None:
        a = get_logger("test.module2", {"x": 1})
        b = get_logger("test.module2", {"x": 2})
        assert a.extra["x"] == 1
        assert b.extra["x"] == 2


@pytest.mark.unit
class TestConfigureLogging:
    def test_configure_json_does_not_raise(self) -> None:
        configure_logging(level="WARNING", format_json=True)

    def test_configure_text_format(self) -> None:
        configure_logging(level="DEBUG", format_json=False)

    def test_configure_with_log_file(self, tmp_path: pytest.TempPathFactory) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
            log_path = Path(f.name)
        try:
            configure_logging(level="WARNING", log_file=log_path, format_json=True)
        finally:
            configure_logging(level="WARNING", format_json=False)
            log_path.unlink(missing_ok=True)

    def test_configure_with_log_file_text_format(self, tmp_path) -> None:

        log_path = tmp_path / "test.log"
        configure_logging(level="WARNING", log_file=log_path, format_json=False)
        configure_logging(level="WARNING", format_json=False)

    def test_configure_disables_metrics_handler(self) -> None:
        configure_logging(level="WARNING", enable_metrics=False)

    def test_configure_with_extra_handlers(self) -> None:
        extra = logging.StreamHandler()
        configure_logging(level="WARNING", extra_handlers=[extra])

    def test_configure_with_integer_level(self) -> None:
        configure_logging(level=logging.ERROR)


@pytest.mark.unit
class TestLoggerAdapterContext:
    def test_add_context(self) -> None:
        from robot_optimizer_core.logging import get_logger

        adapter = get_logger("test.adapter.add")
        adapter.add_context(component="parser")
        assert adapter.extra.get("component") == "parser"

    def test_remove_context(self) -> None:
        from robot_optimizer_core.logging import get_logger

        adapter = get_logger("test.adapter.remove")
        adapter.add_context(component="parser", stage="init")
        adapter.remove_context("stage")
        assert "stage" not in adapter.extra
        assert adapter.extra.get("component") == "parser"

    def test_with_context_returns_new_adapter(self) -> None:
        from robot_optimizer_core.logging import LoggerAdapter, get_logger

        adapter = get_logger("test.adapter.with")
        new_adapter = adapter.with_context(phase="analysis")
        assert isinstance(new_adapter, LoggerAdapter)
        assert new_adapter.extra.get("phase") == "analysis"
        # original unchanged
        assert "phase" not in adapter.extra


@pytest.mark.unit
class TestMetricsHandler:
    def test_emit_increments_total(self) -> None:
        from robot_optimizer_core.logging import MetricsHandler
        from robot_optimizer_core.infrastructure.metrics.collector import MetricsCollector

        m = MetricsCollector(enabled=True)
        handler = MetricsHandler()
        # MetricsHandler uses the global; patch it
        import robot_optimizer_core.infrastructure.metrics.collector as _metrics_mod

        old = _metrics_mod._global_metrics
        _metrics_mod._global_metrics = m
        try:
            record = logging.LogRecord(
                name="test", level=logging.WARNING, pathname="",
                lineno=0, msg="warn", args=(), exc_info=None,
            )
            handler.emit(record)
            data = m.get_metrics()
            assert data["counters"].get("logs.total", 0) >= 1
        finally:
            _metrics_mod._global_metrics = old
            m.stop()

    def test_emit_error_increments_module_counter(self) -> None:
        from robot_optimizer_core.logging import MetricsHandler
        from robot_optimizer_core.infrastructure.metrics.collector import MetricsCollector

        m = MetricsCollector(enabled=True)
        handler = MetricsHandler()
        import robot_optimizer_core.infrastructure.metrics.collector as _metrics_mod

        old = _metrics_mod._global_metrics
        _metrics_mod._global_metrics = m
        try:
            record = logging.LogRecord(
                name="robot_optimizer_core.mymodule",
                level=logging.ERROR, pathname="",
                lineno=0, msg="err", args=(), exc_info=None,
            )
            handler.emit(record)
            data = m.get_metrics()
            assert any("errors" in k for k in data["counters"])
        finally:
            _metrics_mod._global_metrics = old
            m.stop()


@pytest.mark.unit
class TestLogContextVariable:
    def test_context_var_included_in_output(self) -> None:
        import json
        import logging

        from robot_optimizer_core.logging import StructuredFormatter, logging_context

        fmt = StructuredFormatter()
        token = logging_context.set({"request_id": "abc123"})
        try:
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="",
                lineno=0, msg="with ctx", args=(), exc_info=None,
            )
            data = json.loads(fmt.format(record))
            assert data.get("context", {}).get("request_id") == "abc123"
        finally:
            logging_context.reset(token)


@pytest.mark.unit
class TestLogConvenienceFunctions:
    def test_log_analysis_start_no_logger(self, tmp_path) -> None:

        from robot_optimizer_core.logging import log_analysis_start

        f = tmp_path / "t.robot"
        f.write_bytes(b"")
        log_analysis_start(f, "dead_code")

    def test_log_analysis_start_with_nonexistent_file(self, tmp_path) -> None:

        from robot_optimizer_core.logging import log_analysis_start

        log_analysis_start(tmp_path / "nope.robot", "dead_code")

    def test_log_analysis_complete_no_logger(self, tmp_path) -> None:

        from robot_optimizer_core.logging import log_analysis_complete

        log_analysis_complete(tmp_path / "t.robot", "dead_code", 5, 0.1)

    def test_log_error_no_logger(self) -> None:
        from robot_optimizer_core.logging import log_error

        log_error(ValueError("test error"), {"file": "test.robot"})
