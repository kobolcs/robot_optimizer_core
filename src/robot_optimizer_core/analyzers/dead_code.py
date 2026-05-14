# src/robot_optimizer_core/analyzers/dead_code.py
"""Dead code analyzer for Robot Framework test suites.

This analyzer detects unused keywords and duplicate definitions
that can be safely removed to improve maintainability.
"""

from __future__ import annotations

import dataclasses
import re
import sys
from collections import defaultdict
from collections.abc import Generator, Sequence

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

# Control-flow keywords that open a nested scope.
_CONTROL_FLOW_OPENERS = frozenset(
    {"IF", "ELSE IF", "ELSE", "FOR", "WHILE", "TRY", "EXCEPT", "FINALLY"}
)

_BDD_PREFIXES = frozenset({"given", "when", "then", "and", "but"})


@dataclasses.dataclass
class _UnreachableState:
    """State machine state for unreachable-code detection inside a single pass."""

    in_keywords_section: bool = False
    in_keyword: bool = False
    found_return: bool = False
    current_keyword: str | None = None
    control_depth: int = 0

    def enter_section(self, stripped: str) -> None:
        section = stripped.lower()
        self.in_keywords_section = "keyword" in section
        self.in_keyword = False
        self.found_return = False
        self.control_depth = 0
        self.current_keyword = None

    def enter_keyword(self, name: str) -> None:
        self.in_keyword = True
        self.found_return = False
        self.control_depth = 0
        self.current_keyword = name

    def exit_keyword(self) -> None:
        self.in_keyword = False
        self.found_return = False
        self.control_depth = 0
        self.current_keyword = None


def _match_prefixes(call: str, keyword_names: set[str], calls: set[str]) -> None:
    """Add every keyword that is a word-boundary prefix of *call* into *calls*.

    Replaces the O(keywords) inner loop with O(words-in-call) set lookups.
    """
    parts = call.split()
    for n in range(len(parts), 0, -1):
        candidate = " ".join(parts[:n])
        if candidate in keyword_names:
            calls.add(candidate)


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
        keywords, keyword_calls, keyword_display_names = (
            self._extract_keywords_and_calls(test_file)
        )

        if self._check_unused:
            findings.extend(
                self._find_unused_keywords(
                    keywords, keyword_calls, keyword_display_names, test_file
                )
            )

        if self._check_duplicates:
            findings.extend(self._find_duplicate_keywords(keywords, test_file))

        if self._check_unreachable:
            findings.extend(self._find_unreachable_code(test_file))

        return findings

    def _collect_suite_definitions(
        self, files: Sequence[TestFile]
    ) -> tuple[dict[str, list[tuple[TestFile, int]]], list[str], dict[str, str], list[tuple[TestFile, dict[str, list[int]]]]]:
        """Collect keyword definitions and calls from all files in the suite."""
        all_definitions: dict[str, list[tuple[TestFile, int]]] = defaultdict(list)
        raw_candidates: list[str] = []
        per_file_display: dict[str, str] = {}
        file_keywords: list[tuple[TestFile, dict[str, list[int]]]] = []

        for test_file in files:
            keywords, _, display_names = self._extract_keywords_and_calls(test_file)
            file_keywords.append((test_file, keywords))
            for kw_name, line_numbers in keywords.items():
                for line_num in line_numbers:
                    all_definitions[kw_name].append((test_file, line_num))
                per_file_display.setdefault(
                    kw_name, display_names.get(kw_name, kw_name)
                )
            raw_candidates.extend(self._extract_candidate_calls(test_file))

        return all_definitions, raw_candidates, per_file_display, file_keywords

    def _check_unused_keywords(
        self,
        all_definitions: dict[str, list[tuple[TestFile, int]]],
        all_calls: set[str],
        per_file_display: dict[str, str],
    ) -> list[Finding]:
        """Check for unused keywords across the suite."""
        findings: list[Finding] = []
        if not self._check_unused:
            return findings

        for kw_name, locations in all_definitions.items():
            if kw_name in all_calls:
                continue
            display_name = per_file_display.get(kw_name, kw_name)
            if kw_name in _LIFECYCLE_KEYWORDS or any(
                p.match(display_name) for p in self._ignore_patterns
            ):
                continue
            pattern = Pattern(
                type=PatternType.UNUSED_KEYWORD,
                name="Unused Keyword",
                description=f"Keyword '{display_name}' is never called in the suite",
                recommendation="Remove this keyword or use it in your tests",
                documentation_url=None,
                auto_fixable=True,
            )
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

        # Collect definitions and calls
        all_definitions, raw_candidates, per_file_display, file_keywords = (
            self._collect_suite_definitions(files)
        )
        all_calls = self._resolve_calls(raw_candidates, set(all_definitions))

        # Emit findings
        findings: list[Finding] = []
        findings.extend(
            self._check_unused_keywords(all_definitions, all_calls, per_file_display)
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
    ) -> tuple[dict[str, list[int]], set[str], dict[str, str]]:
        """Extract keyword definitions and resolved keyword calls via the RF AST."""
        keywords: dict[str, list[int]] = defaultdict(list)
        keyword_display_names: dict[str, str] = {}

        try:
            from robot.parsing import get_model
            from robot.parsing.model import KeywordSection

            model = get_model(test_file.content)
        except Exception as e:
            self._logger.debug(
                "AST parse failed, falling back to text extraction",
                extra={"file": str(test_file.path), "error": str(e)},
            )
            return self._extract_keywords_and_calls_text(test_file)

        # --- Keyword definitions (KeywordSection only) ---
        for section in model.sections:
            if not isinstance(section, KeywordSection):
                continue
            for keyword_node in section.body:
                name: str | None = getattr(keyword_node, "name", None)
                if not name or not isinstance(name, str):
                    continue
                if name[0].isdigit():
                    continue
                normalized = name.lower()
                line_number: int = getattr(keyword_node, "lineno", 0) or 0
                keywords[normalized].append(line_number)
                keyword_display_names.setdefault(normalized, name)

        # --- Keyword calls (all sections, recursively) ---
        candidate_calls = self._collect_ast_calls(model)
        keyword_names = set(keywords)
        calls = self._resolve_calls(candidate_calls, keyword_names)

        return dict(keywords), calls, keyword_display_names

    def _collect_ast_calls(self, model: object) -> list[str]:
        """Recursively collect all keyword call names from a robot model."""
        calls: list[str] = []
        for section in model.sections:  # type: ignore[attr-defined]
            section_body = getattr(section, "body", None)
            if section_body:
                self._walk_body(section_body, calls)
        return calls

    def _walk_body(self, items: object, calls: list[str]) -> None:
        """Walk an iterable body, collecting keyword call names into *calls*."""
        if not hasattr(items, "__iter__"):
            return
        from collections.abc import Iterable
        for item in items if isinstance(items, Iterable) else []:
            self._collect_item_calls(item, calls)

    def _collect_item_calls(self, item: object, calls: list[str]) -> None:
        """Collect call names from a single AST node and recurse into its bodies."""
        item_type = getattr(item, "type", None)
        if item_type == "KEYWORD":
            name = self._resolve_keyword_call_name(item)
            if name:
                calls.append(name)
        elif item_type in ("SETUP", "TEARDOWN"):
            for token in getattr(item, "data_tokens", []):
                if token.type == "NAME":
                    calls.append(str(token.value))
                    break
        for body in self._iter_nested_bodies(item):
            self._walk_body(body, calls)

    def _resolve_keyword_call_name(self, item: object) -> str | None:
        """Return the effective call name for a KEYWORD node, handling Run Keyword dispatch."""
        name = getattr(item, "keyword", None)
        if not name:
            return None
        name_str = str(name)
        args = list(getattr(item, "args", ()))
        name_lower = name_str.lower()
        if name_lower == "run keyword" and args:
            return f"Run Keyword {args[0]}"
        if name_lower == "run keywords" and args:
            return f"Run Keywords {' '.join(str(a) for a in args)}"
        return name_str

    def _iter_nested_bodies(self, item: object) -> Generator[object, None, None]:
        """Yield each body list reachable from *item* via body, orelse, or Try.next chain."""
        body = getattr(item, "body", None)
        if body:
            yield body
        orelse = getattr(item, "orelse", None)
        if orelse is not None:
            orelse_body = getattr(orelse, "body", None)
            if orelse_body:
                yield orelse_body
        # RF 7.1+ Try/EXCEPT/ELSE/FINALLY branches are linked via .next (not .handlers/.finally_item)
        next_branch = getattr(item, "next", None)
        while next_branch is not None:
            branch_body = getattr(next_branch, "body", None)
            if branch_body:
                yield branch_body
            finalbody = getattr(next_branch, "finalbody", None)
            if finalbody:
                yield finalbody
            next_branch = getattr(next_branch, "next", None)

    def _extract_keywords_and_calls_text(
        self, test_file: TestFile
    ) -> tuple[dict[str, list[int]], set[str], dict[str, str]]:
        """Text-based fallback for _extract_keywords_and_calls."""
        keywords: dict[str, list[int]] = defaultdict(list)
        keyword_display_names: dict[str, str] = {}
        candidate_calls: list[str] = []

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
                if stripped[0].isdigit():
                    continue
                normalized = stripped.lower()
                keywords[normalized].append(line_num)
                keyword_display_names.setdefault(normalized, stripped)
                continue

            if in_test_or_keyword and line.startswith((" ", "\t")):
                candidate_calls.append(stripped)

        keyword_names = set(keywords)
        calls = self._resolve_calls(candidate_calls, keyword_names)
        return dict(keywords), calls, keyword_display_names

    def _extract_candidate_calls(self, test_file: TestFile) -> list[str]:
        """Return all keyword call names from test/keyword sections via the RF AST."""
        try:
            from robot.parsing import get_model

            model = get_model(test_file.content)
            return self._collect_ast_calls(model)
        except Exception as e:
            self._logger.debug(
                "AST parse failed, falling back to text extraction",
                extra={"file": str(test_file.path), "error": str(e)},
            )
            # Fallback: indented lines from text
            candidates: list[str] = []
            lines = test_file.content.splitlines()
            in_test_or_keyword = False
            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.startswith("***"):
                    in_test_or_keyword = (
                        "test case" in stripped.lower() or "keyword" in stripped.lower()
                    )
                    continue
                if in_test_or_keyword and line.startswith((" ", "\t")):
                    candidates.append(stripped)
            return candidates

    def _resolve_calls(
        self, candidates: list[str], keyword_names: set[str]
    ) -> set[str]:
        """Match raw candidate strings against a keyword set, returning matched names."""
        calls: set[str] = set()
        for call in candidates:
            lowered = call.lower()
            _match_prefixes(lowered, keyword_names, calls)

            parts = lowered.split()
            if parts and parts[0] in _BDD_PREFIXES:
                _match_prefixes(" ".join(parts[1:]), keyword_names, calls)

            if lowered.startswith("run keyword "):
                _match_prefixes(lowered.removeprefix("run keyword ").strip(), keyword_names, calls)

            if lowered.startswith("run keywords "):
                for part in re.split(
                    r"\s+AND\s+", lowered.removeprefix("run keywords "), flags=re.IGNORECASE
                ):
                    _match_prefixes(part.strip(), keyword_names, calls)

        return calls

    def _find_unused_keywords(
        self,
        keywords: dict[str, list[int]],
        calls: set[str],
        keyword_display_names: dict[str, str],
        test_file: TestFile,
    ) -> list[Finding]:
        """Find keywords that are never called."""
        findings = []

        for keyword_name, line_numbers in keywords.items():
            if keyword_name not in calls:
                display_name = keyword_display_names.get(keyword_name, keyword_name)

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

    def _create_unreachable_finding(
        self,
        test_file: TestFile,
        line_num: int,
        keyword_name: str,
    ) -> Finding:
        """Create a finding for unreachable code."""
        pattern = Pattern(
            type=PatternType.UNREACHABLE_CODE,
            name="Unreachable Code",
            description="Code after RETURN statement will never execute",
            recommendation="Remove the unreachable code or move it before RETURN",
            documentation_url=None,
            auto_fixable=True,
        )
        return Finding.create(
            pattern=pattern,
            severity=Severity.WARNING,
            location=Location(file_path=test_file.path, line=line_num),
            message=f"Unreachable code after RETURN in keyword '{keyword_name}'",
            keyword_name=keyword_name,
        )

    def _handle_section_line(self, stripped: str, state: _UnreachableState) -> None:
        """Handle a section header line."""
        state.enter_section(stripped)

    def _handle_definition_line(self, stripped: str, state: _UnreachableState) -> None:
        """Handle a definition line (keyword start or end)."""
        if state.in_keywords_section:
            state.enter_keyword(stripped)
        else:
            state.exit_keyword()

    def _handle_statement_line(
        self,
        stripped: str,
        state: _UnreachableState,
        test_file: TestFile,
        line_num: int,
        findings: list[Finding],
    ) -> None:
        """Handle a statement line inside a keyword."""
        upper = stripped.upper()

        if upper in _CONTROL_FLOW_OPENERS:
            state.control_depth += 1
            state.found_return = False
            return

        if upper == "END":
            if state.control_depth > 0:
                state.control_depth -= 1
            state.found_return = False
            return

        if upper.startswith("RETURN"):
            if state.control_depth == 0:
                state.found_return = True
            return

        if state.found_return:
            assert state.current_keyword is not None
            findings.append(
                self._create_unreachable_finding(
                    test_file, line_num, state.current_keyword
                )
            )
            state.found_return = False

    def _find_unreachable_code(self, test_file: TestFile) -> list[Finding]:
        """Find code after RETURN statements inside Keyword definitions.

        A RETURN inside an IF/ELSE branch does not make the lines *after* the
        END unreachable.  ``_UnreachableState.control_depth`` tracks nesting so
        ``found_return`` is only set for top-level RETURNs in the keyword body.
        """
        findings = []
        lines = test_file.content.splitlines()
        state = _UnreachableState()

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()

            if not stripped or stripped.startswith("#"):
                continue

            if stripped.startswith("***"):
                self._handle_section_line(stripped, state)
                continue

            # Non-indented line: boundary between keywords (or a new keyword start)
            if not line.startswith((" ", "\t")):
                self._handle_definition_line(stripped, state)
                continue

            if not state.in_keyword:
                continue

            self._handle_statement_line(stripped, state, test_file, line_num, findings)

        return findings
