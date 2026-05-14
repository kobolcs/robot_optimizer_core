# src/robot_optimizer_core/analyzers/tag_consistency.py
"""Tag consistency analyzer for Robot Framework test suites.

Detects:
- Test cases that have no tags at all
- Tags that appear only once across the suite (likely typos)
- Tags that conflict with reserved Robot Framework system tags
"""

from __future__ import annotations

import re
import sys
from collections import Counter

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

from ..domain.entities import TestFile
from ..domain.value_objects import Finding, Location, Pattern, PatternType, Severity
from .base import BaseAnalyzer, ConfigValue

__all__ = ["TagConsistencyAnalyzer"]

# Robot Framework built-in/reserved tags that tests should not redefine
# See https://robotframework.org/robotframework/latest/RobotFrameworkUserGuide.html#reserved-tags
_RESERVED_TAGS: frozenset[str] = frozenset(
    {
        "robot:skip",
        "robot:skip-on-failure",
        "robot:continue-on-failure",
        "robot:recursive-continue-on-failure",
        "robot:no-dry-run",
        "robot:flatten",
        "robot:exclude",
        "robot:stop-on-failure",
    }
)

# Tag name that conflicts: same as a reserved tag but capitalised differently
_RESERVED_NORMALIZED: frozenset[str] = frozenset(t.lower() for t in _RESERVED_TAGS)


class TagConsistencyAnalyzer(BaseAnalyzer):
    """Detects tag-related issues in Robot Framework test suites.

    Configuration:
        check_missing_tags: Report tests with no tags (default: True).
        check_singleton_tags: Report tags used only once (default: True).
        check_reserved_tags: Report conflicting system tags (default: True).
        singleton_threshold: Minimum uses to not be a singleton (default: 2).
    """

    def __init__(self, config: dict[str, ConfigValue] | None = None) -> None:
        super().__init__(config)
        self._check_missing = bool(self.get_config_value("check_missing_tags", True))
        self._check_singletons = bool(
            self.get_config_value("check_singleton_tags", True)
        )
        self._check_reserved = bool(self.get_config_value("check_reserved_tags", True))
        self._singleton_threshold = int(
            str(self.get_config_value("singleton_threshold", 2))
        )

    @property
    @override
    def name(self) -> str:
        return "tag_consistency"

    @property
    @override
    def description(self) -> str:
        return (
            "Detects missing tags, singleton tags (likely typos), "
            "and reserved tag conflicts"
        )

    @property
    @override
    def tags(self) -> list[str]:
        return ["tags", "structure", "style"]

    def _collect_tag_info(
        self, lines: list[str]
    ) -> list[tuple[str, int, list[str]]]:
        """Collect test case info: (name, first_line, tags) for every test."""
        tag_info: list[tuple[str, int, list[str]]] = []
        in_test_cases = False
        current_name: str | None = None
        current_line = 1
        current_tags: list[str] = []

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.startswith("***"):
                if current_name is not None:
                    tag_info.append((current_name, current_line, current_tags))
                    current_name = None
                    current_tags = []
                in_test_cases = "test case" in stripped.lower()
                continue

            if in_test_cases and not line.startswith((" ", "\t")):
                if current_name is not None:
                    tag_info.append((current_name, current_line, current_tags))
                if stripped.startswith("#"):
                    current_name = None
                    current_tags = []
                    continue
                current_name = stripped
                current_line = line_num
                current_tags = []
                continue

            if current_name:
                current_tags = self._extract_tags_from_line(stripped, current_tags)

        if current_name is not None:
            tag_info.append((current_name, current_line, current_tags))

        return tag_info

    def _extract_tags_from_line(
        self, stripped: str, current_tags: list[str]
    ) -> list[str]:
        """Extract tags from a [Tags] line."""
        if stripped.lower().startswith("[tags]"):
            rest = stripped[len("[tags]") :].strip()
            if rest:
                tag_parts = re.split(r"  +|\t+", rest)
                return [t.strip() for t in tag_parts if t.strip()]
        return current_tags

    def _check_test_tags(
        self,
        test_name: str,
        test_line: int,
        tags: list[str],
        tag_counts: Counter[str],
        test_file: TestFile,
    ) -> list[Finding]:
        """Return all findings for a single test's tags.

        Args:
            test_name: Name of the test case.
            test_line: Line number where the test case starts.
            tags: Tags declared on the test.
            tag_counts: Suite-wide counter of tag occurrences.
            test_file: The file being analysed.

        Returns:
            List of findings (may be empty).
        """
        if self._check_missing and not tags:
            return [self._missing_tag_finding(test_name, test_line, test_file)]

        findings: list[Finding] = []
        for tag in tags:
            if self._check_reserved and (
                tag.lower() in _RESERVED_NORMALIZED and tag not in _RESERVED_TAGS
            ):
                findings.append(
                    self._reserved_tag_finding(tag, test_name, test_line, test_file)
                )

            if self._check_singletons and tag_counts[tag] < self._singleton_threshold:
                findings.append(
                    self._singleton_tag_finding(tag, test_name, test_line, test_file)
                )

        return findings

    def analyze(self, test_file: TestFile) -> list[Finding]:
        lines = test_file.content.splitlines()
        test_tag_info = self._collect_tag_info(lines)

        # Build suite-wide tag counter for singleton detection
        all_tags: list[str] = [t for _, _, tags in test_tag_info for t in tags]
        tag_counts = Counter(all_tags)

        findings: list[Finding] = []
        for test_name, test_line, tags in test_tag_info:
            findings.extend(
                self._check_test_tags(test_name, test_line, tags, tag_counts, test_file)
            )

        return findings

    # ------------------------------------------------------------------
    # Finding factories
    # ------------------------------------------------------------------

    def _missing_tag_finding(
        self, test_name: str, line_num: int, test_file: TestFile
    ) -> Finding:
        pattern = Pattern(
            type=PatternType.NO_TAGS,
            name="Missing Tags",
            description=f"Test case '{test_name}' has no [Tags]",
            recommendation=(
                "Add [Tags]    <category>  <feature> to improve traceability "
                "and enable selective test execution"
            ),
            documentation_url=None,
            auto_fixable=False,
        )
        return Finding.create(
            pattern=pattern,
            severity=Severity.INFO,
            location=Location(file_path=test_file.path, line=line_num),
            message=f"Test case '{test_name}' has no [Tags]",
            test_name=test_name,
        )

    def _singleton_tag_finding(
        self, tag: str, test_name: str, line_num: int, test_file: TestFile
    ) -> Finding:
        pattern = Pattern(
            type=PatternType.SINGLETON_TAG,
            name="Singleton Tag",
            description=(f"Tag '{tag}' is only used in '{test_name}' — possible typo"),
            recommendation=(
                f"Verify the tag '{tag}' is intentional; "
                "if it is a category tag, apply it to all related tests"
            ),
            documentation_url=None,
            auto_fixable=False,
        )
        return Finding.create(
            pattern=pattern,
            severity=Severity.INFO,
            location=Location(file_path=test_file.path, line=line_num),
            message=(f"Tag '{tag}' appears only once in this file — check for typo"),
            tag=tag,
            test_name=test_name,
        )

    def _reserved_tag_finding(
        self, tag: str, test_name: str, line_num: int, test_file: TestFile
    ) -> Finding:
        pattern = Pattern(
            type=PatternType.RESERVED_TAG,
            name="Reserved Tag Conflict",
            description=(
                f"Tag '{tag}' looks like a Robot Framework reserved tag "
                "but uses incorrect capitalisation"
            ),
            recommendation=(
                f"Use the exact reserved form, e.g. '{tag.lower()}', "
                "or rename to avoid confusion"
            ),
            documentation_url=None,
            auto_fixable=False,
        )
        return Finding.create(
            pattern=pattern,
            severity=Severity.WARNING,
            location=Location(file_path=test_file.path, line=line_num),
            message=(
                f"Tag '{tag}' conflicts with a Robot Framework reserved tag "
                "(capitalisation mismatch)"
            ),
            tag=tag,
            test_name=test_name,
        )
