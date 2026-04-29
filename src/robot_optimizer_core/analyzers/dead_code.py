# src/robot_optimizer_core/analyzers/dead_code.py
"""Dead code analyzer for Robot Framework test suites.

This analyzer detects unused keywords and duplicate definitions
that can be safely removed to improve maintainability.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from collections.abc import Sequence

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

from ..domain.entities import TestFile
from ..domain.value_objects import Finding, Location, Pattern, PatternType, Severity
from .base import BaseAnalyzer, ConfigValue

__all__ = ["DeadCodeAnalyzer"]

_LIFECYCLE_KEYWORDS = frozenset(
    {
        "suite setup",
        "suite teardown",
        "test setup",
        "test teardown",
    }
)

# Control-flow keywords that open a nested scope (Task 8)
_CONTROL_FLOW_OPENERS = frozenset(
    {"IF", "ELSE IF", "ELSE", "FOR", "WHILE", "TRY", "EXCEPT", "FINALLY"}
)


class DeadCodeAnalyzer(BaseAnalyzer):
    """Analyzer for detecting dead code in Robot Framework files.

    Detects:
    - Unused keywords
    - Duplicate keyword definitions
    - Unreachable code after RETURN statements
    """

    def __init__(self, config: dict[str, ConfigValue] | None = None) -> None:
        """Initialize the analyzer."""
        super().__init__(config)
        self._check_unused = self.get_config_value("check_unused", True)
        self._check_duplicates = self.get_config_value("check_duplicates", True)
        self._check_unreachable = self.get_config_value("check_unreachable", True)
        ignore_patterns: list[ConfigValue] = self.get_config_value(
            "ignore_patterns", []
        )
        self._ignore_patterns = [
            re.compile(str(pattern), re.IGNORECASE) for pattern in ignore_patterns
        ]
        self._keyword_display_names: dict[str, str] = {}
        self.validate_config()

    @property
    @override
    def name(self) -> str:
        return "dead_code"

    @property
    @override
    def description(self) -> str:
        return "Finds unused keywords and duplicate definitions"

    @property
    @override
    def tags(self) -> list[str]:
        return ["keywords", "maintenance", "cleanup"]

    @property
    @override
    def supports_auto_fix(self) -> bool:
        return True

    @override
    def validate_config(self) -> None:
        """Validate analyzer configuration."""
        from ..exceptions import ConfigurationError

        for key in ("check_unused", "check_duplicates", "check_unreachable"):
            value = self.get_config_value(key, True)
            if not isinstance(value, bool):
                raise ConfigurationError(
                    f"Config key '{key}' must be a boolean",
                    config_key=f"{self.name}.{key}",
                    provided_value=value,
                )
        patterns: list[ConfigValue] = self.get_config_value("ignore_patterns", [])
        if not isinstance(patterns, list):
            raise ConfigurationError(
                "Config key 'ignore_patterns' must be a list",
                config_key=f"{self.name}.ignore_patterns",
                provided_value=type(patterns).__name__,
            )

    @override
    def analyze(self, test_file: TestFile) -> list[Finding]:
        """Analyze test file for dead code."""
        findings = []

        # Parse the file structure in a single pass (optimization)
        keywords, keyword_calls = self._extract_keywords_and_calls(test_file)

        if self._check_unused:
            findings.extend(
                self._find_unused_keywords(keywords, keyword_calls, test_file)
            )

        if self._check_duplicates:
            findings.extend(self._find_duplicate_keywords(keywords, test_file))

        if self._check_unreachable:
            findings.extend(self._find_unreachable_code(test_file))

        return findings

    def analyze_suite(self, files: Sequence[TestFile]) -> list[Finding]:
        """Analyze a suite of files for dead code with cross-file awareness.

        A keyword defined in one file is only reported as unused when it has
        no callers in *any* file in the suite.  Duplicate detection and
        unreachable-code detection remain per-file.

        Args:
            files: All test/resource files that form the suite.

        Returns:
            List of findings across all files.
        """
        if not files:
            return []

        # --- First pass: collect definitions and raw candidate calls -----------
        all_definitions: dict[str, list[tuple[TestFile, int]]] = defaultdict(list)
        raw_candidates: list[str] = []
        per_file_display: dict[str, str] = {}
        # Cache parsed keywords per file to avoid re-parsing in duplicate/unreachable pass
        file_keywords: list[tuple[TestFile, dict[str, list[int]]]] = []

        for test_file in files:
            keywords, _ = self._extract_keywords_and_calls(test_file)
            file_keywords.append((test_file, keywords))
            for kw_name, line_numbers in keywords.items():
                for line_num in line_numbers:
                    all_definitions[kw_name].append((test_file, line_num))
                per_file_display.setdefault(kw_name, self._keyword_display_names.get(kw_name, kw_name))
            raw_candidates.extend(self._extract_candidate_calls(test_file))

        # Resolve raw candidates against the full suite-wide keyword set
        all_calls = self._resolve_calls(raw_candidates, set(all_definitions))

        # --- Second pass: emit findings ---------------------------------------
        findings: list[Finding] = []

        if self._check_unused:
            for kw_name, locations in all_definitions.items():
                if kw_name in all_calls:
                    continue
                display_name = per_file_display.get(kw_name, kw_name)
                if kw_name in _LIFECYCLE_KEYWORDS:
                    continue
                if any(p.match(display_name) for p in self._ignore_patterns):
                    continue
                pattern = Pattern(
                    type=PatternType.UNUSED_KEYWORD,
                    name="Unused Keyword",
                    description=f"Keyword '{display_name}' is never called in the suite",
                    recommendation="Remove this keyword or use it in your tests",
                    documentation_url=None,
                    auto_fixable=True,
                )
                # Report only the first definition site to avoid noise
                test_file, line_num = locations[0]
                findings.append(
                    Finding.create(
                        pattern=pattern,
                        severity=Severity.WARNING,
                        location=Location(file_path=test_file.path, line=line_num),
                        message=f"Keyword '{display_name}' is defined but never used in the suite",
                        keyword_name=display_name,
                    )
                )

        if self._check_duplicates:
            for test_file, keywords in file_keywords:
                findings.extend(self._find_duplicate_keywords(keywords, test_file))

        if self._check_unreachable:
            for test_file in files:
                findings.extend(self._find_unreachable_code(test_file))

        return findings

    def _extract_keywords_and_calls(
        self, test_file: TestFile
    ) -> tuple[dict[str, list[int]], set[str]]:
        """Extract keyword definitions and resolved keyword calls.

        Task 7: Also captures doubly-indented lines inside FOR loops so that
        keywords called inside ``FOR … END`` blocks are no longer missed.
        """
        keywords: dict[str, list[int]] = defaultdict(list)
        self._keyword_display_names = {}
        candidate_calls: list[str] = []
        calls: set[str] = set()

        lines = test_file.content.splitlines()
        in_keywords_section = False
        in_test_or_keyword = False

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            if not stripped or stripped.startswith("#"):
                continue

            if stripped.startswith("***"):
                section = stripped.lower()
                in_keywords_section = "keyword" in section
                in_test_or_keyword = "test case" in section or "keyword" in section
                continue

            if in_keywords_section and not line.startswith((" ", "\t")):
                # Ignore malformed definitions such as names beginning with a digit.
                if stripped[0].isdigit():
                    continue
                normalized = stripped.lower()
                keywords[normalized].append(line_num)
                self._keyword_display_names.setdefault(normalized, stripped)
                continue

            # Task 7: capture any indented line (including doubly-indented FOR bodies)
            if in_test_or_keyword and line.startswith((" ", "\t")):
                candidate_calls.append(stripped)

        keyword_names = set(keywords)

        for call in candidate_calls:
            lowered = call.lower()
            parts = call.split()
            lowered_parts = [part.lower() for part in parts]

            # Direct full-line/prefix matches against known local keyword definitions.
            for keyword in keyword_names:
                if lowered == keyword or lowered.startswith(keyword + " "):
                    calls.add(keyword)

            # BDD prefixes: Given/When/Then/And/But <keyword>
            if lowered_parts and lowered_parts[0] in {
                "given",
                "when",
                "then",
                "and",
                "but",
            }:
                bdd_call = " ".join(lowered_parts[1:])
                for keyword in keyword_names:
                    if bdd_call == keyword or bdd_call.startswith(keyword + " "):
                        calls.add(keyword)

            # Dynamic Robot calls: Run Keyword <keyword>, Run Keywords <kw> AND <kw>
            if lowered.startswith("run keyword "):
                dynamic_call = lowered.removeprefix("run keyword ").strip()
                for keyword in keyword_names:
                    if dynamic_call == keyword or dynamic_call.startswith(
                        keyword + " "
                    ):
                        calls.add(keyword)

            if lowered.startswith("run keywords "):
                dynamic_parts = [
                    part.strip().lower()
                    for part in re.split(
                        r"\s+AND\s+", call[len("Run Keywords ") :], flags=re.IGNORECASE
                    )
                ]
                for dynamic_call in dynamic_parts:
                    for keyword in keyword_names:
                        if dynamic_call == keyword or dynamic_call.startswith(
                            keyword + " "
                        ):
                            calls.add(keyword)

        return dict(keywords), calls

    def _extract_candidate_calls(self, test_file: TestFile) -> list[str]:
        """Return all indented (call-site) stripped lines from test/keyword sections."""
        candidates: list[str] = []
        lines = test_file.content.splitlines()
        in_test_or_keyword = False
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("***"):
                in_test_or_keyword = "test case" in stripped.lower() or "keyword" in stripped.lower()
                continue
            if in_test_or_keyword and line.startswith((" ", "\t")):
                candidates.append(stripped)
        return candidates

    def _resolve_calls(self, candidates: list[str], keyword_names: set[str]) -> set[str]:
        """Match raw candidate strings against a keyword set, returning matched names."""
        calls: set[str] = set()
        for call in candidates:
            lowered = call.lower()
            lowered_parts = lowered.split()

            for keyword in keyword_names:
                if lowered == keyword or lowered.startswith(keyword + " "):
                    calls.add(keyword)

            if lowered_parts and lowered_parts[0] in {"given", "when", "then", "and", "but"}:
                bdd_call = " ".join(lowered_parts[1:])
                for keyword in keyword_names:
                    if bdd_call == keyword or bdd_call.startswith(keyword + " "):
                        calls.add(keyword)

            if lowered.startswith("run keyword "):
                dynamic_call = lowered.removeprefix("run keyword ").strip()
                for keyword in keyword_names:
                    if dynamic_call == keyword or dynamic_call.startswith(keyword + " "):
                        calls.add(keyword)

            if lowered.startswith("run keywords "):
                for part in re.split(r"\s+AND\s+", call[len("Run Keywords "):], flags=re.IGNORECASE):
                    dynamic_call = part.strip().lower()
                    for keyword in keyword_names:
                        if dynamic_call == keyword or dynamic_call.startswith(keyword + " "):
                            calls.add(keyword)
        return calls

    def _find_unused_keywords(
        self, keywords: dict[str, list[int]], calls: set[str], test_file: TestFile
    ) -> list[Finding]:
        """Find keywords that are never called."""
        findings = []

        for keyword_name, line_numbers in keywords.items():
            if keyword_name not in calls:
                display_name = self._keyword_display_names.get(
                    keyword_name, keyword_name
                )

                # Skip special keywords and configured ignore patterns
                if keyword_name in _LIFECYCLE_KEYWORDS:
                    continue
                if any(
                    pattern.match(display_name) for pattern in self._ignore_patterns
                ):
                    continue

                pattern = Pattern(
                    type=PatternType.UNUSED_KEYWORD,
                    name="Unused Keyword",
                    description=f"Keyword '{display_name}' is never called",
                    recommendation="Remove this keyword or use it in your tests",
                    documentation_url=None,
                    auto_fixable=True,
                )

                finding = Finding.create(
                    pattern=pattern,
                    severity=Severity.WARNING,
                    location=Location(file_path=test_file.path, line=line_numbers[0]),
                    message=f"Keyword '{display_name}' is defined but never used",
                    keyword_name=display_name,
                )
                findings.append(finding)

        return findings

    def _find_duplicate_keywords(
        self, keywords: dict[str, list[int]], test_file: TestFile
    ) -> list[Finding]:
        """Find keywords defined multiple times."""
        findings = []

        for keyword_name, line_numbers in keywords.items():
            if len(line_numbers) > 1:
                pattern = Pattern.duplicate_keyword(keyword_name)

                # Create findings for all duplicates after the first
                for line_num in line_numbers[1:]:
                    finding = Finding.create(
                        pattern=pattern,
                        severity=Severity.ERROR,
                        location=Location(file_path=test_file.path, line=line_num),
                        message=f"Keyword '{keyword_name}' is already defined at line {line_numbers[0]}",
                        first_definition_line=line_numbers[0],
                        duplicate_count=len(line_numbers),
                    )
                    findings.append(finding)

        return findings

    def _find_unreachable_code(self, test_file: TestFile) -> list[Finding]:
        """Find code after RETURN statements inside Keyword definitions.

        Task 8: A RETURN inside an IF/ELSE branch does not make the lines
        *after* the END unreachable.  We track IF/ELSE/END nesting depth so
        that ``found_return`` is only propagated when we exit a keyword body
        without any intervening control-flow block.
        """
        findings = []
        lines = test_file.content.splitlines()

        in_keywords_section = False
        in_keyword = False
        found_return = False
        current_keyword = None
        # Track IF/ELSE/TRY/EXCEPT/WHILE/FOR nesting (any control-flow block
        # that can legitimately contain a RETURN without making the remaining
        # keyword body unreachable).
        control_depth = 0

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            if not stripped or stripped.startswith("#"):
                continue

            # Track section changes
            if stripped.startswith("***"):
                section = stripped.lower()
                in_keywords_section = "keyword" in section
                in_keyword = False
                found_return = False
                control_depth = 0
                continue

            # Non-indented line: start of a new keyword (only inside Keywords section)
            if not line.startswith((" ", "\t")):
                in_keyword = False
                found_return = False
                control_depth = 0
                if in_keywords_section:
                    current_keyword = stripped
                    in_keyword = True
                continue

            if not in_keyword:
                continue

            upper = stripped.upper()

            # Track control-flow block depth
            if upper in _CONTROL_FLOW_OPENERS:
                # Entering a nested block — any RETURN inside it is scoped
                control_depth += 1
                # A RETURN found *before* this block is still valid context, but
                # the block entry resets it so we don't false-positive lines after END.
                if found_return:
                    found_return = False
                continue

            if upper == "END":
                if control_depth > 0:
                    control_depth -= 1
                # Exiting a control-flow block does not itself mean unreachable
                found_return = False
                continue

            # Check for RETURN inside a keyword body
            if upper.startswith("RETURN"):
                if control_depth == 0:
                    # Top-level RETURN in the keyword body
                    found_return = True
                # A RETURN inside a nested block does NOT set found_return
                continue

            # Check for code after a top-level RETURN
            if found_return and stripped and not stripped.startswith("#"):
                pattern = Pattern(
                    type=PatternType.UNREACHABLE_CODE,
                    name="Unreachable Code",
                    description="Code after RETURN statement will never execute",
                    recommendation="Remove the unreachable code or move it before RETURN",
                    documentation_url=None,
                    auto_fixable=True,
                )

                finding = Finding.create(
                    pattern=pattern,
                    severity=Severity.WARNING,
                    location=Location(file_path=test_file.path, line=line_num),
                    message=f"Unreachable code after RETURN in keyword '{current_keyword}'",
                    keyword_name=current_keyword,
                )
                findings.append(finding)

                # Only report first line of unreachable code per keyword
                found_return = False

        return findings
