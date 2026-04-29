# src/robot_optimizer_core/analyzers/naming_convention.py
"""Naming convention analyzer for Robot Framework test suites.

This analyzer detects names (test cases, keywords, variables) that violate
community-recommended Robot Framework conventions.

Conventions enforced:
- Test case names: Title Case words, no CamelCase run-togethers
- Keyword names: Title Case words, no CamelCase run-togethers
- Variable names: ``${UPPER_SNAKE_CASE}`` for suite/global, or
  ``${lower_snake_case}`` for local — CamelCase variable names are flagged
"""

from __future__ import annotations

import re
import sys

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

from ..domain.entities import TestFile
from ..domain.value_objects import Finding, Location, Pattern, PatternType, Severity
from .base import BaseAnalyzer, ConfigValue

__all__ = ["NamingConventionAnalyzer"]

# Matches a run of uppercase letters ≥2 followed by a lowercase letter
# (CamelCase interior boundary) or an uppercase letter immediately followed
# by another uppercase + lowercase sequence (e.g. "MyHTTPRequest")
_CAMEL_RE = re.compile(r"[a-z][A-Z]|[A-Z]{2,}[a-z]")
# Variable inner name (strip sigil and braces): ${MyVar} → "MyVar"
_VAR_INNER_RE = re.compile(r"\$\{([^}]+)\}")
# CamelCase in variable name (no underscores, mixed case)
_VAR_CAMEL_RE = re.compile(r"[a-z][A-Z]|[A-Z][a-z]")


def _is_camel_case_name(name: str) -> bool:
    """Return True if *name* looks like a CamelCase identifier.

    A CamelCase name has NO spaces and contains a lowercase-to-uppercase
    transition (e.g. ``LoginPage``, ``myKeyword``).
    """
    if " " in name:
        return False
    return bool(_CAMEL_RE.search(name))


def _variable_is_camel(inner: str) -> bool:
    """Return True when the variable inner name uses CamelCase."""
    # Ignore index expressions like "LIST[0]"
    bare = inner.split("[")[0].strip()
    if "_" in bare:
        return False
    return bool(_VAR_CAMEL_RE.search(bare))


class NamingConventionAnalyzer(BaseAnalyzer):
    """Detects naming convention violations in Robot Framework files.

    Flags:
    - CamelCase test case / keyword names (should use Title Case with spaces)
    - CamelCase variable names (should use ALL_CAPS or lower_snake_case)

    Configuration:
        check_test_names: Check test case naming (default: True).
        check_keyword_names: Check keyword naming (default: True).
        check_variable_names: Check variable naming (default: True).
        ignore_patterns: List of regex patterns to ignore (matched against
            the full name).
    """

    def __init__(self, config: dict[str, ConfigValue] | None = None) -> None:
        super().__init__(config)
        self._check_tests: bool = bool(
            self.get_config_value("check_test_names", True)
        )
        self._check_keywords: bool = bool(
            self.get_config_value("check_keyword_names", True)
        )
        self._check_variables: bool = bool(
            self.get_config_value("check_variable_names", True)
        )
        ignore_raw: list[ConfigValue] = self.get_config_value("ignore_patterns", [])
        self._ignore: list[re.Pattern[str]] = [
            re.compile(str(p), re.IGNORECASE) for p in ignore_raw
        ]

    @property
    @override
    def name(self) -> str:
        return "naming_convention"

    @property
    @override
    def description(self) -> str:
        return "Detects naming convention violations in test/keyword/variable names"

    @property
    @override
    def tags(self) -> list[str]:
        return ["style", "naming", "readability"]

    @override
    def analyze(self, test_file: TestFile) -> list[Finding]:
        findings: list[Finding] = []
        lines = test_file.content.splitlines()

        in_test_cases = False
        in_keywords = False

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if stripped.startswith("***"):
                lower = stripped.lower()
                in_test_cases = "test case" in lower
                in_keywords = "keyword" in lower and "test case" not in lower
                continue

            # Non-indented line inside a section = definition name
            if not line.startswith((" ", "\t")):
                if in_test_cases and self._check_tests:
                    finding = self._check_name(
                        stripped,
                        line_num,
                        test_file,
                        entity_type="test case",
                    )
                    if finding:
                        findings.append(finding)

                elif in_keywords and self._check_keywords:
                    finding = self._check_name(
                        stripped,
                        line_num,
                        test_file,
                        entity_type="keyword",
                    )
                    if finding:
                        findings.append(finding)
                continue

            # Indented line — look for variable assignments (${Var}=  or  ${Var}    value)
            if self._check_variables:
                for match in _VAR_INNER_RE.finditer(stripped):
                    inner = match.group(1)
                    if _variable_is_camel(inner):
                        if not self._is_ignored(inner):
                            findings.append(
                                self._make_variable_finding(
                                    inner, line_num, test_file
                                )
                            )

        return findings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_name(
        self,
        name: str,
        line_num: int,
        test_file: TestFile,
        entity_type: str,
    ) -> Finding | None:
        if self._is_ignored(name):
            return None
        if not _is_camel_case_name(name):
            return None

        pattern = Pattern(
            type=PatternType.MISSING_DOCUMENTATION,  # closest structural type
            name="CamelCase Name",
            description=(
                f"{entity_type.title()} '{name}' uses CamelCase instead of "
                "Title Case with spaces"
            ),
            recommendation=(
                f"Rename to use words separated by spaces, "
                f"e.g. '{_camel_to_title(name)}'"
            ),
            documentation_url=None,
            auto_fixable=False,
        )
        return Finding.create(
            pattern=pattern,
            severity=Severity.WARNING,
            location=Location(file_path=test_file.path, line=line_num),
            message=(
                f"{entity_type.title()} '{name}' uses CamelCase — "
                "Robot Framework convention is Title Case with spaces"
            ),
            entity_type=entity_type,
            entity_name=name,
        )

    def _make_variable_finding(
        self, inner: str, line_num: int, test_file: TestFile
    ) -> Finding:
        pattern = Pattern(
            type=PatternType.HARDCODED_VALUE,
            name="CamelCase Variable",
            description=f"Variable '${{{inner}}}' uses CamelCase",
            recommendation=(
                "Use ${ALL_CAPS} for suite/global variables "
                "or ${lower_snake_case} for local variables"
            ),
            documentation_url=None,
            auto_fixable=False,
        )
        return Finding.create(
            pattern=pattern,
            severity=Severity.INFO,
            location=Location(file_path=test_file.path, line=line_num),
            message=(
                f"Variable '${{{inner}}}' uses CamelCase — "
                "prefer ${ALL_CAPS} or ${lower_snake_case}"
            ),
            variable_name=inner,
        )

    def _is_ignored(self, name: str) -> bool:
        return any(p.search(name) for p in self._ignore)


def _camel_to_title(name: str) -> str:
    """Best-effort CamelCase → Title Case conversion for suggestions."""
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    return spaced.title()
