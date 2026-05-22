# tests/unit/analyzers/test_pattern_types.py
"""Tests for correct PatternType usage across analyzers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from robot_optimizer_core.application.analyzers.naming_convention import NamingConventionAnalyzer
from robot_optimizer_core.application.analyzers.tag_consistency import TagConsistencyAnalyzer
from robot_optimizer_core.domain.entities import TestFile
from robot_optimizer_core.domain.value_objects.pattern import PatternType


def _make(tmp_path: Path, content: str) -> TestFile:
    f = tmp_path / "t.robot"
    f.write_bytes(content.encode())
    return TestFile(
        path=f,
        content=content,
        size_bytes=len(content),
        last_modified_utc=datetime.now(UTC),
    )


@pytest.mark.unit
class TestNamingPatternType:
    def test_camelcase_test_uses_camel_case_name_type(self, tmp_path: Path) -> None:
        content = "*** Test Cases ***\nLoginPage\n    Log    hi\n"
        findings = NamingConventionAnalyzer().analyze(_make(tmp_path, content))
        types = {f.pattern.type for f in findings}
        assert PatternType.CAMEL_CASE_NAME in types
        assert PatternType.MISSING_DOCUMENTATION not in types

    def test_camelcase_keyword_uses_camel_case_name_type(self, tmp_path: Path) -> None:
        content = "*** Keywords ***\nDoLogin\n    Log    hi\n"
        findings = NamingConventionAnalyzer().analyze(_make(tmp_path, content))
        types = {f.pattern.type for f in findings}
        assert PatternType.CAMEL_CASE_NAME in types


@pytest.mark.unit
class TestTagPatternTypes:
    def test_singleton_tag_uses_singleton_tag_type(self, tmp_path: Path) -> None:
        content = "*** Test Cases ***\nMy Test\n    [Tags]    unique_xyz\n"
        analyzer = TagConsistencyAnalyzer(config={"singleton_threshold": 2})
        findings = analyzer.analyze(_make(tmp_path, content))
        assert any(f.pattern.type == PatternType.SINGLETON_TAG for f in findings)

    def test_reserved_tag_uses_reserved_tag_type(self, tmp_path: Path) -> None:
        content = "*** Test Cases ***\nMy Test\n    [Tags]    Robot:Skip\n"
        analyzer = TagConsistencyAnalyzer()
        findings = analyzer.analyze(_make(tmp_path, content))
        assert any(f.pattern.type == PatternType.RESERVED_TAG for f in findings)

    def test_missing_tag_uses_no_tags_type(self, tmp_path: Path) -> None:
        content = "*** Test Cases ***\nMy Test\n    Log    hi\n"
        findings = TagConsistencyAnalyzer().analyze(_make(tmp_path, content))
        assert any(f.pattern.type == PatternType.NO_TAGS for f in findings)
