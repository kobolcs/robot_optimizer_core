# tests/unit/analyzers/test_sleep_detector.py
"""Unit tests for SleepDetector context-aware fix suggestions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from robot_optimizer_core.analyzers.sleep_detector import SleepDetector
from robot_optimizer_core.domain.entities import TestFile


def _make(content: str, path: str = "test.robot") -> TestFile:
    return TestFile(
        path=Path(path),
        content=content,
        size_bytes=len(content),
        last_modified_utc=datetime.now(),
    )


@pytest.mark.unit
class TestSleepDetectorSuggestions:
    def _find_message(self, content: str) -> str:
        findings = SleepDetector().analyze(_make(content))
        assert findings, "expected at least one finding"
        return findings[0].message

    def test_selenium_ui_context_suggests_wait_until_element(self) -> None:
        content = "*** Settings ***\nLibrary    SeleniumLibrary\n\n*** Test Cases ***\nT\n    Sleep    2\n    Click Element    id:btn\n"
        assert "Wait Until Element Is Visible" in self._find_message(content)

    def test_browser_library_suggests_wait_for_elements_state(self) -> None:
        content = "*** Settings ***\nLibrary    Browser\n\n*** Test Cases ***\nT\n    Sleep    2\n    Click    id=btn\n"
        assert "Wait For Elements State" in self._find_message(content)

    def test_appium_library_suggests_wait_until_element(self) -> None:
        content = "*** Settings ***\nLibrary    AppiumLibrary\n\n*** Test Cases ***\nT\n    Sleep    2\n    Click Element    id:btn\n"
        assert "Wait Until Element Is Visible" in self._find_message(content)

    def test_no_library_falls_back_to_generic(self) -> None:
        content = "*** Test Cases ***\nT\n    Sleep    3\n    Log    hi\n"
        msg = self._find_message(content)
        assert "Wait Until" in msg or "Wait For" in msg

    def test_suggestion_includes_enclosing_block_name(self) -> None:
        content = "*** Test Cases ***\nLogin Test\n    Sleep    3\n    Log    done\n"
        assert "Login Test" in self._find_message(content)

    def test_suggestion_includes_keyword_name(self) -> None:
        content = "*** Keywords ***\nWait For Page Load\n    Sleep    2\n    Log    done\n"
        assert "Wait For Page Load" in self._find_message(content)

    def test_sub_second_sleep_mentions_sub_second(self) -> None:
        content = "*** Test Cases ***\nT\n    Sleep    0.3\n"
        msg = self._find_message(content)
        assert "sub-second" in msg.lower() or "Sub-second" in msg

    def test_long_sleep_mentions_synchronization(self) -> None:
        content = "*** Test Cases ***\nT\n    Sleep    10\n"
        msg = self._find_message(content)
        assert "synchronization" in msg.lower() or "Long sleep" in msg


@pytest.mark.unit
class TestSleepDetectorHelpers:
    def _d(self) -> SleepDetector:
        return SleepDetector()

    def test_detect_library_selenium(self) -> None:
        lines = ["*** Settings ***", "Library    SeleniumLibrary", "*** Test Cases ***"]
        assert self._d()._detect_library(lines) == "seleniumlibrary"

    def test_detect_library_browser(self) -> None:
        lines = ["*** Settings ***", "Library    Browser", ""]
        assert self._d()._detect_library(lines) == "browser"

    def test_detect_library_none(self) -> None:
        assert self._d()._detect_library(["*** Test Cases ***", "T", "    Sleep    1"]) is None

    def test_classify_context_ui(self) -> None:
        assert self._d()._classify_context(["Click Element    id:btn"]) == "ui"

    def test_classify_context_page(self) -> None:
        assert self._d()._classify_context(["Navigate To    https://x"]) == "page"

    def test_classify_context_verify(self) -> None:
        assert self._d()._classify_context(["Element Should Contain    id:x    text"]) == "verify"

    def test_classify_context_generic(self) -> None:
        assert self._d()._classify_context(["Log    message"]) == "generic"

    def test_enclosing_block_name_found(self) -> None:
        lines = ["*** Test Cases ***", "My Test", "    Sleep    1"]
        assert self._d()._enclosing_block_name(lines, 3) == "My Test"
