# src/robot_optimizer_core/application/analyzers/test_documentation.py
"""Test documentation analyzer for Robot Framework test suites.

Reports test cases and keywords that lack a [Documentation] entry,
enforcing self-documenting test standards.
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

from ...domain.entities import TestFile
from ...domain.value_objects import Finding, Location, Pattern, PatternType
from ...infrastructure.parsers.robot_ast_parser import RobotASTParser
from .base import BaseAnalyzer, ConfigValue

__all__ = ["TestDocumentationAnalyzer"]


class TestDocumentationAnalyzer(BaseAnalyzer):
    """Detects test cases and keywords that lack [Documentation].

    Configuration:
        check_test_cases: Check test case docs (default: True).
        check_keywords: Check keyword docs (default: True).
        min_doc_length: Minimum documentation length in characters (default: 10).
        severity_tests: Severity for undocumented test cases (default: WARNING).
        severity_keywords: Severity for undocumented keywords (default: INFO).
    """

    def __init__(self, config: dict[str, ConfigValue] | None = None) -> None:
        super().__init__(config)
        self._check_tests = bool(self.get_config_value("check_test_cases", True))
        self._check_keywords = bool(self.get_config_value("check_keywords", True))
        self._min_len = int(str(self.get_config_value("min_doc_length", 10)))

        sev_tests_raw = str(self.get_config_value("severity_tests", "WARNING")).upper()
        sev_kw_raw = str(self.get_config_value("severity_keywords", "INFO")).upper()
        from ...domain.value_objects import Severity as Sev

        self._sev_tests = Sev[sev_tests_raw]
        self._sev_keywords = Sev[sev_kw_raw]

    @property
    @override
    def name(self) -> str:
        return "test_documentation"

    @property
    @override
    def description(self) -> str:
        return "Reports test cases and keywords that lack [Documentation]"

    @property
    @override
    def tags(self) -> list[str]:
        return ["documentation", "style", "readability"]

    def _create_finding(
        self,
        test_file: TestFile,
        name: str,
        line: int,
        entity: str,
        *,
        has_doc: bool,
        doc_text: str,
    ) -> Finding | None:
        """Create a finding if entity lacks required documentation."""
        if has_doc and len(doc_text.strip()) >= self._min_len:
            return None
        severity = (
            self._sev_tests if entity == "test case" else self._sev_keywords
        )
        reason = (
            "missing [Documentation]"
            if not has_doc
            else f"[Documentation] is too short (< {self._min_len} chars)"
        )
        pattern = Pattern(
            pattern_type=PatternType.MISSING_DOCUMENTATION,
            name="Missing Documentation",
            description=f"{entity.title()} '{name}' has {reason}",
            recommendation=(
                f"Add [Documentation]    <description of what '{name}' does>"
            ),
            documentation_url=None,
            auto_fixable=False,
        )
        return Finding.create(
            pattern=pattern,
            severity=severity,
            location=Location(file_path=test_file.path, line=line),
            message=(f"{entity.title()} '{name}' has {reason}"),
            entity_type=entity,
            entity_name=name,
        )

    @override
    def analyze(self, test_file: TestFile) -> list[Finding]:
        findings: list[Finding] = []
        suite = RobotASTParser().parse_suite(test_file)

        if self._check_tests:
            for tc in suite.test_cases:
                doc_text = tc.documentation or ""
                has_doc = bool(doc_text.strip())
                finding = self._create_finding(
                    test_file,
                    tc.name,
                    tc.location.line,
                    "test case",
                    has_doc=has_doc,
                    doc_text=doc_text,
                )
                if finding:
                    findings.append(finding)

        if self._check_keywords:
            for kw in suite.keywords:
                doc_text = kw.documentation or ""
                has_doc = bool(doc_text.strip())
                finding = self._create_finding(
                    test_file,
                    kw.name,
                    kw.location.line,
                    "keyword",
                    has_doc=has_doc,
                    doc_text=doc_text,
                )
                if finding:
                    findings.append(finding)

        return findings
