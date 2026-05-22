# src/robot_optimizer_core/application/analyzers/naming_convention.py
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

from ...domain.entities import TestFile
from ...domain.value_objects import Finding, Location, Pattern, PatternType, Severity
from ...infrastructure.parsers.robot_ast_parser import RobotASTParser
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
    """Return ``True`` when *name* looks like a CamelCase identifier.

    A CamelCase name has no spaces and contains a lowercase-to-uppercase
    boundary (e.g. ``LoginPage``, ``myKeyword``).  Names with spaces are
    Title-Case words and are never flagged.

    Args:
        name: Raw test-case or keyword name from the Robot file.

    Returns:
        ``True`` if the name uses CamelCase.
    """
    if " " in name:
        return False
    return bool(_CAMEL_RE.search(name))


def _variable_is_camel(inner: str) -> bool:
    """Return ``True`` when a variable's inner name uses CamelCase.

    Index expressions (e.g. ``LIST[0]``) are stripped before checking.
    Names containing underscores are considered snake_case and not flagged.

    Args:
        inner: The inner variable name without sigil and braces
            (e.g. ``"MyVar"`` for ``${MyVar}``).

    Returns:
        ``True`` if the variable name is CamelCase.
    """
    bare = inner.split("[", maxsplit=1)[0].strip()
    if "_" in bare:
        return False
    return bool(_VAR_CAMEL_RE.search(bare))


class NamingConventionAnalyzer(BaseAnalyzer):
    """Detects naming convention violations in Robot Framework files.

    Flags CamelCase identifiers in test case names, keyword names, and
    variable names where Robot Framework community conventions recommend
    Title Case with spaces (for tests/keywords) or ``${ALL_CAPS}`` /
    ``${lower_snake_case}`` (for variables).

    Configuration keys (passed via the ``config`` dict):
        check_test_names (bool): Check test case name casing. Default: ``True``.
        check_keyword_names (bool): Check keyword name casing. Default: ``True``.
        check_variable_names (bool): Check variable name casing. Default: ``True``.
        ignore_patterns (list[str]): Regex patterns matched against names;
            matching names are not reported. Default: ``[]``.
    """

    _TEST_CASE_SECTION = "test case"

    def __init__(self, config: dict[str, ConfigValue] | None = None) -> None:
        """Initialize the analyzer with optional configuration overrides.

        Args:
            config: Per-analyzer configuration dict. Recognised keys are
                ``check_test_names``, ``check_keyword_names``,
                ``check_variable_names``, and ``ignore_patterns``.
        """
        super().__init__(config)
        self._check_tests: bool = bool(self.get_config_value("check_test_names", True))
        self._check_keywords: bool = bool(
            self.get_config_value("check_keyword_names", True)
        )
        self._check_variables: bool = bool(
            self.get_config_value("check_variable_names", True)
        )
        ignore_raw = self.get_list_config("ignore_patterns", [])
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

    def _check_definition_name(
        self,
        line: str,
        line_num: int,
        test_file: TestFile,
        *,
        in_test_cases: bool,
        in_keywords: bool,
    ) -> Finding | None:
        """Check a definition line (test case or keyword name) for violations."""
        if in_test_cases and self._check_tests:
            return self._check_name(line, line_num, test_file, entity_type="test case")
        if in_keywords and self._check_keywords:
            return self._check_name(line, line_num, test_file, entity_type="keyword")
        return None

    def _check_variables_in_line(
        self, line: str, line_num: int, test_file: TestFile
    ) -> list[Finding]:
        """Extract and check variables in an indented line."""
        findings: list[Finding] = []
        if not self._check_variables:
            return findings
        for match in _VAR_INNER_RE.finditer(line):
            inner = match.group(1)
            if _variable_is_camel(inner) and not self._is_ignored(inner):
                findings.append(
                    self._make_variable_finding(inner, line_num, test_file)
                )
        return findings

    @override
    def analyze(self, test_file: TestFile) -> list[Finding]:
        findings: list[Finding] = []
        suite = RobotASTParser().parse_suite(test_file)

        if self._check_tests:
            for tc in suite.test_cases:
                finding = self._check_name(
                    tc.name, tc.location.line, test_file, entity_type="test case"
                )
                if finding:
                    findings.append(finding)

        if self._check_keywords:
            for kw in suite.keywords:
                finding = self._check_name(
                    kw.name, kw.location.line, test_file, entity_type="keyword"
                )
                if finding:
                    findings.append(finding)

        # Variable names: scan indented lines to catch assignment targets (${x}=)
        # and inline usages, as the AST model does not surface assignment variables.
        if self._check_variables:
            for line_num, line in enumerate(test_file.content.splitlines(), 1):
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or stripped.startswith("***"):
                    continue
                if not line.startswith((" ", "\t")):
                    continue
                findings.extend(self._check_variables_in_line(stripped, line_num, test_file))

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
            pattern_type=PatternType.CAMEL_CASE_NAME,
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
            pattern_type=PatternType.HARDCODED_VALUE,
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
    """Convert a CamelCase name to a Title Case suggestion for findings.

    This is best-effort; it handles common patterns like ``LoginPage`` →
    ``Login Page`` and ``MyHTTPRequest`` → ``My Http Request`` but may not
    produce perfect output for all edge cases.

    Args:
        name: CamelCase string to convert.

    Returns:
        Title-cased string with spaces inserted at CamelCase boundaries.
    """
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    return spaced.title()
