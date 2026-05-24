# tests/unit/analyzers/test_sleep_detector_paths.py
"""Coverage tests for SleepDetector paths not exercised by existing tests.

Targets: builtin.sleep qualified call, custom keyword detection, variable
sleep via check_custom, and the evaluate/pattern internal detectors.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from robot_optimizer_core.application.analyzers.sleep_detector import SleepDetector
from robot_optimizer_core.domain.entities import TestFile


def _make(content: str, path: str = "test.robot") -> TestFile:
    return TestFile(
        path=Path(path),
        content=content,
        size_bytes=len(content),
        last_modified_utc=datetime.now(UTC),
    )


@pytest.mark.unit
class TestBuiltinQualifiedSleep:
    """BuiltIn.Sleep (fully qualified) triggers the builtin_qualified path."""

    def test_builtin_sleep_qualified_detected(self) -> None:
        content = "*** Test Cases ***\nT\n    BuiltIn.Sleep    2s\n"
        findings = SleepDetector().analyze(_make(content))
        assert findings
        assert findings[0].context.get("sleep_type") == "builtin_qualified"

    def test_builtin_sleep_qualified_has_correct_duration(self) -> None:
        content = "*** Test Cases ***\nT\n    BuiltIn.Sleep    5s\n"
        findings = SleepDetector().analyze(_make(content))
        assert findings
        assert findings[0].context.get("duration") == "5"


@pytest.mark.unit
class TestCustomKeywordSleep:
    """Wait / Pause / Delay keywords detected when check_custom=True."""

    def test_wait_keyword_detected(self) -> None:
        content = "*** Test Cases ***\nT\n    Wait    3s\n"
        findings = SleepDetector(config={"check_custom": True}).analyze(_make(content))
        assert findings
        assert findings[0].context.get("sleep_type") == "custom"

    def test_pause_keyword_detected(self) -> None:
        content = "*** Test Cases ***\nT\n    Pause    1s\n"
        findings = SleepDetector(config={"check_custom": True}).analyze(_make(content))
        assert findings

    def test_delay_keyword_detected(self) -> None:
        content = "*** Test Cases ***\nT\n    Delay    2s\n"
        findings = SleepDetector(config={"check_custom": True}).analyze(_make(content))
        assert findings

    def test_custom_keywords_not_detected_when_disabled(self) -> None:
        content = "*** Test Cases ***\nT\n    Wait    3s\n"
        findings = SleepDetector(config={"check_custom_sleep": False}).analyze(_make(content))
        assert findings == []


@pytest.mark.unit
class TestVariableSleepViaCheckCustom:
    """Sleep ${VAR} variable path via _detect_sleep_from_call.

    The Robot AST parser strips robot variable arguments, so we must call
    _detect_sleep_from_call directly with a mock that supplies the argument.
    """

    def _mock_call(self, keyword_name: str, arguments: list[str]) -> MagicMock:
        call = MagicMock()
        call.keyword_name = keyword_name
        call.arguments = arguments
        return call

    def test_variable_arg_returns_variable_type(self) -> None:
        detector = SleepDetector()
        call = self._mock_call("Sleep", ["${TIMEOUT}"])
        result = detector._detect_sleep_from_call(call)
        assert result is not None
        assert result.sleep_type == "variable"
        assert result.variable == "TIMEOUT"
        assert result.duration is None

    def test_variable_arg_with_check_custom_false_falls_through(self) -> None:
        detector = SleepDetector(config={"check_custom_sleep": False})
        call = self._mock_call("Sleep", ["${TIMEOUT}"])
        # check_custom=False means the variable branch is skipped;
        # ${TIMEOUT} doesn't match the duration regex so result is None.
        result = detector._detect_sleep_from_call(call)
        assert result is None

