# src/robot_optimizer_core/analyzers/test_documentation.py
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

from ..domain.entities import TestFile
from ..domain.value_objects import Finding, Location, Pattern, PatternType, Severity
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

        sev_tests_raw = str(
            self.get_config_value("severity_tests", "WARNING")
        ).upper()
        sev_kw_raw = str(
            self.get_config_value("severity_keywords", "INFO")
        ).upper()
        from ..domain.value_objects import Severity as Sev

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

    @override
    def analyze(self, test_file: TestFile) -> list[Finding]:
        findings: list[Finding] = []
        lines = test_file.content.splitlines()

        in_test_cases = False
        in_keywords = False

        current_name: str | None = None
        current_line: int = 1
        current_entity: str = "test case"
        has_doc = False
        doc_text = ""

        def flush() -> None:
            nonlocal has_doc, doc_text
            if current_name is None:
                return
            entity = current_entity
            check = (entity == "test case" and self._check_tests) or (
                entity == "keyword" and self._check_keywords
            )
            if not check:
                return
            if not has_doc or len(doc_text.strip()) < self._min_len:
                severity = (
                    self._sev_tests if entity == "test case" else self._sev_keywords
                )
                reason = (
                    "missing [Documentation]"
                    if not has_doc
                    else f"[Documentation] is too short (< {self._min_len} chars)"
                )
                pattern = Pattern(
                    type=PatternType.MISSING_DOCUMENTATION,
                    name="Missing Documentation",
                    description=f"{entity.title()} '{current_name}' has {reason}",
                    recommendation=(
                        f"Add [Documentation]    <description of what '{current_name}' does>"
                    ),
                    documentation_url=None,
                    auto_fixable=False,
                )
                findings.append(
                    Finding.create(
                        pattern=pattern,
                        severity=severity,
                        location=Location(
                            file_path=test_file.path, line=current_line
                        ),
                        message=(
                            f"{entity.title()} '{current_name}' has {reason}"
                        ),
                        entity_type=entity,
                        entity_name=current_name,
                    )
                )
            has_doc = False
            doc_text = ""

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            if not stripped:
                continue

            if stripped.startswith("***"):
                flush()
                current_name = None
                lower = stripped.lower()
                in_test_cases = "test case" in lower
                in_keywords = "keyword" in lower and "test case" not in lower
                continue

            # Non-indented line in a tracked section = new definition
            if not line.startswith((" ", "\t")):
                if in_test_cases or in_keywords:
                    flush()
                    if stripped.startswith("#"):
                        continue
                    current_name = stripped
                    current_line = line_num
                    current_entity = "test case" if in_test_cases else "keyword"
                    has_doc = False
                    doc_text = ""
                continue

            # Indented line — check for [Documentation]
            if current_name and stripped.lower().startswith("[documentation]"):
                has_doc = True
                # Extract doc text after the tag
                parts = stripped.split(None, 1)
                doc_text = parts[1] if len(parts) > 1 else ""

        flush()
        return findings
