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
    def _make_record(self, msg: str = "hello", level: int = logging.INFO) -> logging.LogRecord:
        record = logging.LogRecord(
            name="test", level=level, pathname="", lineno=0,
            msg=msg, args=(), exc_info=None
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
        for field in ("timestamp", "level", "logger", "message", "module", "function", "line"):
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
