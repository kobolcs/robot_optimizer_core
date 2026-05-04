# tests/unit/analyzers/test_new_analyzers.py
"""Unit tests for the five new built-in analyzers (Tasks 1-5)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from robot_optimizer_core.analyzers import (
    HardcodedValueAnalyzer,
    NamingConventionAnalyzer,
    SetupTeardownAnalyzer,
    TagConsistencyAnalyzer,
)
from robot_optimizer_core.analyzers.test_documentation import (
    TestDocumentationAnalyzer as DocAnalyzer,
)
from robot_optimizer_core.domain.entities import TestFile
from robot_optimizer_core.domain.value_objects import Severity


def _make_file(content: str, name: str = "test.robot") -> TestFile:
    return TestFile(
        path=Path(name),
        content=content,
        size_bytes=len(content),
        last_modified_utc=datetime.now(),
    )


# ---------------------------------------------------------------------------
# NamingConventionAnalyzer
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNamingConventionAnalyzer:
    @pytest.fixture
    def analyzer(self) -> NamingConventionAnalyzer:
        return NamingConventionAnalyzer()

    def test_analyzer_properties(self, analyzer: NamingConventionAnalyzer) -> None:
        assert analyzer.name == "naming_convention"
        assert "naming" in analyzer.tags

    def test_camel_case_test_name_flagged(
        self, analyzer: NamingConventionAnalyzer
    ) -> None:
        content = "*** Test Cases ***\nLoginUserAndVerify\n    Log    hi\n"
        findings = analyzer.analyze(_make_file(content))
        assert len(findings) == 1
        assert "CamelCase" in findings[0].message

    def test_title_case_test_name_ok(self, analyzer: NamingConventionAnalyzer) -> None:
        content = "*** Test Cases ***\nLogin User And Verify\n    Log    hi\n"
        findings = analyzer.analyze(_make_file(content))
        assert findings == []

    def test_camel_case_keyword_flagged(
        self, analyzer: NamingConventionAnalyzer
    ) -> None:
        content = "*** Keywords ***\nOpenBrowserAndLogin\n    Log    hi\n"
        findings = analyzer.analyze(_make_file(content))
        assert len(findings) == 1

    def test_camel_case_variable_flagged(
        self, analyzer: NamingConventionAnalyzer
    ) -> None:
        content = (
            "*** Test Cases ***\nMy Test\n    ${myVar}=    Set Variable    value\n"
        )
        findings = analyzer.analyze(_make_file(content))
        assert any("myVar" in f.message for f in findings)

    def test_upper_snake_case_variable_ok(
        self, analyzer: NamingConventionAnalyzer
    ) -> None:
        content = (
            "*** Test Cases ***\nMy Test\n    ${MY_VAR}=    Set Variable    value\n"
        )
        findings = analyzer.analyze(_make_file(content))
        assert not any("MY_VAR" in f.message for f in findings)

    def test_ignore_patterns(self) -> None:
        analyzer = NamingConventionAnalyzer({"ignore_patterns": ["LoginUser"]})
        content = "*** Test Cases ***\nLoginUserTest\n    Log    hi\n"
        findings = analyzer.analyze(_make_file(content))
        assert findings == []

    def test_empty_file(self, analyzer: NamingConventionAnalyzer) -> None:
        findings = analyzer.analyze(_make_file(""))
        assert findings == []


# ---------------------------------------------------------------------------
# HardcodedValueAnalyzer
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHardcodedValueAnalyzer:
    @pytest.fixture
    def analyzer(self) -> HardcodedValueAnalyzer:
        return HardcodedValueAnalyzer()

    def test_analyzer_properties(self, analyzer: HardcodedValueAnalyzer) -> None:
        assert analyzer.name == "hardcoded_value"
        assert "security" in analyzer.tags

    def test_http_url_flagged(self, analyzer: HardcodedValueAnalyzer) -> None:
        content = "*** Test Cases ***\nMy Test\n    Go To    http://example.com\n"
        findings = analyzer.analyze(_make_file(content))
        assert any("http://example.com" in f.message for f in findings)

    def test_https_url_flagged(self, analyzer: HardcodedValueAnalyzer) -> None:
        content = "*** Test Cases ***\nMy Test\n    Open Browser    https://staging.app.com/login\n"
        findings = analyzer.analyze(_make_file(content))
        assert len(findings) == 1

    def test_localhost_flagged(self, analyzer: HardcodedValueAnalyzer) -> None:
        content = "*** Test Cases ***\nMy Test\n    Connect    localhost\n"
        findings = analyzer.analyze(_make_file(content))
        assert findings  # should flag localhost

    def test_ip_address_flagged(self, analyzer: HardcodedValueAnalyzer) -> None:
        content = "*** Test Cases ***\nMy Test\n    Connect    192.168.1.100\n"
        findings = analyzer.analyze(_make_file(content))
        assert any("192.168.1.100" in f.message for f in findings)

    def test_credential_flagged_as_error(
        self, analyzer: HardcodedValueAnalyzer
    ) -> None:
        content = "*** Test Cases ***\nMy Test\n    Login    password=s3cr3t123\n"
        findings = analyzer.analyze(_make_file(content))
        cred_findings = [f for f in findings if f.severity == Severity.ERROR]
        assert cred_findings

    def test_variable_url_not_flagged(self, analyzer: HardcodedValueAnalyzer) -> None:
        content = "*** Test Cases ***\nMy Test\n    Go To    ${BASE_URL}\n"
        findings = analyzer.analyze(_make_file(content))
        url_findings = [f for f in findings if "url" in f.message.lower()]
        assert url_findings == []

    def test_ignore_patterns(self) -> None:
        analyzer = HardcodedValueAnalyzer({"ignore_patterns": ["example.com"]})
        content = "*** Test Cases ***\nMy Test\n    Go To    http://example.com\n"
        findings = analyzer.analyze(_make_file(content))
        assert findings == []

    def test_check_ports_disabled_by_default(
        self, analyzer: HardcodedValueAnalyzer
    ) -> None:
        """
        Verifies that numeric port-like literals are ignored by default by the HardcodedValueAnalyzer.
        
        Uses a test step containing "8080" and asserts that no findings mention "port".
        """
        content = "*** Test Cases ***\nMy Test\n    Connect    8080\n"
        findings = analyzer.analyze(_make_file(content))
        port_findings = [f for f in findings if "port" in f.message.lower()]
        assert port_findings == []

    def test_check_ports_enabled(self) -> None:
        analyzer = HardcodedValueAnalyzer({"check_ports": True})
        content = "*** Test Cases ***\nMy Test\n    Connect    8080\n"
        findings = analyzer.analyze(_make_file(content))
        assert findings


# ---------------------------------------------------------------------------
# DocAnalyzer
# ---------------------------------------------------------------------------


@pytest.mark.unit
class DocAnalyzerTests:
    @pytest.fixture
    def analyzer(self) -> DocAnalyzer:
        return DocAnalyzer()

    def test_analyzer_properties(self, analyzer: DocAnalyzer) -> None:
        assert analyzer.name == "test_documentation"
        assert "documentation" in analyzer.tags

    def test_undocumented_test_flagged(self, analyzer: DocAnalyzer) -> None:
        content = "*** Test Cases ***\nMy Test\n    Log    hi\n"
        findings = analyzer.analyze(_make_file(content))
        assert any("My Test" in f.message for f in findings)

    def test_documented_test_ok(self, analyzer: DocAnalyzer) -> None:
        content = (
            "*** Test Cases ***\nMy Test\n"
            "    [Documentation]    This is a meaningful description\n"
            "    Log    hi\n"
        )
        findings = analyzer.analyze(_make_file(content))
        assert findings == []

    def test_short_doc_flagged(self, analyzer: DocAnalyzer) -> None:
        content = (
            "*** Test Cases ***\nMy Test\n    [Documentation]    Hi\n    Log    hi\n"
        )
        findings = analyzer.analyze(_make_file(content))
        assert findings  # "Hi" is too short

    def test_undocumented_keyword_flagged(self, analyzer: DocAnalyzer) -> None:
        content = "*** Keywords ***\nMy Keyword\n    Log    hi\n"
        findings = analyzer.analyze(_make_file(content))
        assert findings

    def test_documented_keyword_ok(self, analyzer: DocAnalyzer) -> None:
        content = (
            "*** Keywords ***\nMy Keyword\n"
            "    [Documentation]    Does something important\n"
            "    Log    hi\n"
        )
        findings = analyzer.analyze(_make_file(content))
        assert findings == []

    def test_disable_keyword_check(self) -> None:
        analyzer = DocAnalyzer({"check_keywords": False})
        content = "*** Keywords ***\nMy Keyword\n    Log    hi\n"
        findings = analyzer.analyze(_make_file(content))
        assert findings == []


# ---------------------------------------------------------------------------
# TagConsistencyAnalyzer
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTagConsistencyAnalyzer:
    @pytest.fixture
    def analyzer(self) -> TagConsistencyAnalyzer:
        return TagConsistencyAnalyzer()

    def test_analyzer_properties(self, analyzer: TagConsistencyAnalyzer) -> None:
        assert analyzer.name == "tag_consistency"
        assert "tags" in analyzer.tags

    def test_missing_tags_flagged(self, analyzer: TagConsistencyAnalyzer) -> None:
        content = "*** Test Cases ***\nMy Test\n    Log    hi\n"
        findings = analyzer.analyze(_make_file(content))
        assert any("no [Tags]" in f.message for f in findings)

    def test_test_with_tags_ok(self, analyzer: TagConsistencyAnalyzer) -> None:
        content = (
            "*** Test Cases ***\nMy Test\n"
            "    [Tags]    smoke  regression\n"
            "    Log    hi\n\n"
            "Other Test\n"
            "    [Tags]    smoke  regression\n"
            "    Log    hi\n"
        )
        findings = analyzer.analyze(_make_file(content))
        missing = [f for f in findings if "no [Tags]" in f.message]
        assert missing == []

    def test_singleton_tag_flagged(self, analyzer: TagConsistencyAnalyzer) -> None:
        content = (
            "*** Test Cases ***\nTest A\n    [Tags]    smoke  uniq_typo\n    Log    a\n\n"
            "Test B\n    [Tags]    smoke\n    Log    b\n"
        )
        findings = analyzer.analyze(_make_file(content))
        singleton = [f for f in findings if "once" in f.message.lower()]
        assert singleton

    def test_reserved_tag_conflict(self, analyzer: TagConsistencyAnalyzer) -> None:
        # Wrong capitalisation of a reserved tag
        content = (
            "*** Test Cases ***\nMy Test\n    [Tags]    Robot:Skip\n    Log    hi\n"
        )
        findings = analyzer.analyze(_make_file(content))
        reserved = [f for f in findings if "reserved" in f.message.lower()]
        assert reserved

    def test_correct_reserved_tag_not_flagged(
        self, analyzer: TagConsistencyAnalyzer
    ) -> None:
        content = (
            "*** Test Cases ***\nMy Test\n    [Tags]    robot:skip\n    Log    hi\n"
        )
        findings = analyzer.analyze(_make_file(content))
        reserved = [f for f in findings if "reserved" in f.message.lower()]
        assert reserved == []


# ---------------------------------------------------------------------------
# SetupTeardownAnalyzer
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSetupTeardownAnalyzer:
    @pytest.fixture
    def analyzer(self) -> SetupTeardownAnalyzer:
        return SetupTeardownAnalyzer()

    def test_analyzer_properties(self, analyzer: SetupTeardownAnalyzer) -> None:
        assert analyzer.name == "setup_teardown"
        assert "structure" in analyzer.tags

    def test_repeated_setup_step_flagged(self, analyzer: SetupTeardownAnalyzer) -> None:
        content = (
            "*** Test Cases ***\nTest A\n"
            "    Open Browser    ${URL}\n"
            "    Log    a\n\n"
            "Test B\n"
            "    Open Browser    ${URL}\n"
            "    Log    b\n"
        )
        findings = analyzer.analyze(_make_file(content))
        assert findings

    def test_using_setup_hook_ok(self, analyzer: SetupTeardownAnalyzer) -> None:
        content = (
            "*** Test Cases ***\nTest A\n"
            "    [Setup]    Open Browser    ${URL}\n"
            "    Log    a\n\n"
            "Test B\n"
            "    [Setup]    Open Browser    ${URL}\n"
            "    Log    b\n"
        )
        findings = analyzer.analyze(_make_file(content))
        assert findings == []

    def test_repeated_teardown_step_flagged(
        self, analyzer: SetupTeardownAnalyzer
    ) -> None:
        content = (
            "*** Test Cases ***\nTest A\n"
            "    Log    a\n"
            "    Close Browser\n\n"
            "Test B\n"
            "    Log    b\n"
            "    Close Browser\n"
        )
        findings = analyzer.analyze(_make_file(content))
        assert findings

    def test_single_occurrence_not_flagged(
        self, analyzer: SetupTeardownAnalyzer
    ) -> None:
        content = (
            "*** Test Cases ***\nTest A\n    Open Browser    ${URL}\n    Log    a\n"
        )
        findings = analyzer.analyze(_make_file(content))
        assert findings == []

    def test_empty_file(self, analyzer: SetupTeardownAnalyzer) -> None:
        findings = analyzer.analyze(_make_file(""))
        assert findings == []
