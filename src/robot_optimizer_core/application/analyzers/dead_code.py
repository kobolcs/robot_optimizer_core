# src/robot_optimizer_core/application/analyzers/dead_code.py
"""Dead code analyzer for Robot Framework test suites.

This analyzer detects unused keywords and duplicate definitions
that can be safely removed to improve maintainability.
"""

from __future__ import annotations

import dataclasses
import re
import sys
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if sys.version_info >= (3, 12):
    from typing import Protocol, override
else:
    from typing import Protocol

    from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

    from ...domain.entities import TestFile

from collections.abc import Iterable as _Iterable

from ...domain.value_objects import Finding, Location, Pattern, PatternType, Severity
from .base import BaseAnalyzer, ConfigValue


def _unused_keyword_pattern(display_name: str, *, suite_level: bool = False) -> Pattern:
    scope = "the suite" if suite_level else "this file"
    return Pattern(
        pattern_type=PatternType.UNUSED_KEYWORD,
        name="Unused Keyword",
        description=f"Keyword '{display_name}' is never called in {scope}",
        recommendation="Remove this keyword or use it in your tests",
        documentation_url=None,
        auto_fixable=True,
    )

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


def _resolve_calls(candidates: list[str], keyword_names: set[str]) -> set[str]:
    """Match raw candidate strings against a keyword set, returning matched names."""
    calls: set[str] = set()
    for call in candidates:
        lowered = call.lower()
        _match_prefixes(lowered, keyword_names, calls)

        parts = lowered.split()
        if parts and parts[0] in _BDD_PREFIXES:
            _match_prefixes(" ".join(parts[1:]), keyword_names, calls)

        if lowered.startswith("run keyword "):
            _match_prefixes(
                lowered.removeprefix("run keyword ").strip(), keyword_names, calls
            )

        if lowered.startswith("run keywords "):
            for part in re.split(
                r"\s+AND\s+",
                lowered.removeprefix("run keywords "),
                flags=re.IGNORECASE,
            ):
                _match_prefixes(part.strip(), keyword_names, calls)

    return calls


class _DeadCodeStrategy(Protocol):
    """Protocol for keyword/call extraction strategies."""

    def extract(
        self, test_file: TestFile
    ) -> tuple[dict[str, list[int]], set[str], dict[str, str], list[str]]:
        """Extract keyword definitions and calls from *test_file*.

        Returns:
            4-tuple of (keywords, calls, display_names, raw_candidates).
        """
        ...  # pragma: no cover


class _ASTDeadCodeStrategy:
    """Extract keyword definitions and calls via the Robot Framework AST parser.

    Raises any exception raised by ``robot.parsing.get_model`` so the caller
    can decide whether to fall back to a different strategy.
    """

    def extract(
        self, test_file: TestFile
    ) -> tuple[dict[str, list[int]], set[str], dict[str, str], list[str]]:
        from robot.parsing import get_model
        from robot.parsing.model import KeywordSection

        model = get_model(test_file.content)

        keywords: dict[str, list[int]] = defaultdict(list)
        keyword_display_names: dict[str, str] = {}

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

        candidate_calls = self._collect_ast_calls(model)
        keyword_names = set(keywords)
        calls = _resolve_calls(candidate_calls, keyword_names)

        return dict(keywords), calls, keyword_display_names, candidate_calls

    def _collect_ast_calls(self, model: Any) -> list[str]:
        """Recursively collect all keyword call names from a robot model."""
        calls: list[str] = []
        for section in model.sections:
            section_body = getattr(section, "body", None)
            if section_body:
                self._walk_body(section_body, calls)
        return calls

    def _walk_body(self, items: object, calls: list[str]) -> None:
        """Walk an iterable body, collecting keyword call names into *calls*."""
        if not isinstance(items, _Iterable):
            return
        for item in items:
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


class _RegexDeadCodeStrategy:
    """Extract keyword definitions and calls via line-by-line text scanning.

    Used as fallback when the Robot Framework AST parser cannot process a file.
    """

    def extract(
        self, test_file: TestFile
    ) -> tuple[dict[str, list[int]], set[str], dict[str, str], list[str]]:
        keywords: dict[str, list[int]] = defaultdict(list)
        keyword_display_names: dict[str, str] = {}
        candidate_calls: list[str] = []

        lines = test_file.content.splitlines()
        self._process_text_lines(lines, keywords, keyword_display_names, candidate_calls)

        keyword_names = set(keywords)
        calls = _resolve_calls(candidate_calls, keyword_names)
        return dict(keywords), calls, keyword_display_names, candidate_calls

    def _process_text_lines(
        self,
        lines: list[str],
        keywords: dict[str, list[int]],
        keyword_display_names: dict[str, str],
        candidate_calls: list[str],
    ) -> None:
        """Process lines from a text-based Robot Framework file."""
        in_keywords_section = False
        in_test_or_keyword = False

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("***"):
                in_keywords_section, in_test_or_keyword = (
                    self._update_section_state(stripped)
                )
                continue
            self._process_content_line(
                line,
                stripped,
                line_num,
                in_keywords_section,
                in_test_or_keyword,
                keywords,
                keyword_display_names,
                candidate_calls,
            )

    def _update_section_state(self, section_line: str) -> tuple[bool, bool]:
        """Update state based on section header."""
        section = section_line.lower()
        in_keywords = "keyword" in section
        in_test_or_kw = "test case" in section or "keyword" in section
        return in_keywords, in_test_or_kw

    def _process_content_line(
        self,
        line: str,
        stripped: str,
        line_num: int,
        in_keywords_section: bool,
        in_test_or_keyword: bool,
        keywords: dict[str, list[int]],
        keyword_display_names: dict[str, str],
        candidate_calls: list[str],
    ) -> None:
        """Process a non-empty, non-comment line."""
        if in_keywords_section and not line.startswith((" ", "\t")):
            if not stripped[0].isdigit():
                normalized = stripped.lower()
                keywords[normalized].append(line_num)
                keyword_display_names.setdefault(normalized, stripped)
        elif in_test_or_keyword and line.startswith((" ", "\t")):
            candidate_calls.append(stripped)


class DeadCodeAnalyzer(BaseAnalyzer):
    """Analyzer for detecting dead code in Robot Framework files.

    Detects three categories of dead code:

    - **Unused keywords** — keywords defined but never called within the
      analysed scope (per-file or suite-level).
    - **Duplicate keyword definitions** — the same keyword name defined more
      than once in the same file.
    - **Unreachable code** — statements after a top-level ``RETURN`` inside a
      keyword body that will never execute.

    Configuration keys (passed via the ``config`` dict):
        check_unused (bool): Enable unused-keyword detection. Default: ``True``.
        check_duplicates (bool): Enable duplicate-keyword detection. Default: ``True``.
        check_unreachable (bool): Enable unreachable-code detection. Default: ``True``.
        ignore_patterns (list[str]): Regex patterns; matching keyword names are
            excluded from unused-keyword reports. Default: ``[]``.
    """

    def __init__(self, config: dict[str, ConfigValue] | None = None) -> None:
        """Initialize the analyzer with optional configuration overrides.

        Args:
            config: Per-analyzer configuration dict. Recognised keys are
                ``check_unused``, ``check_duplicates``, ``check_unreachable``,
                and ``ignore_patterns``.
        """
        super().__init__(config)
        self._check_unused = self.get_config_value("check_unused", True)
        self._check_duplicates = self.get_config_value("check_duplicates", True)
        self._check_unreachable = self.get_config_value("check_unreachable", True)
        ignore_patterns = self.get_list_config("ignore_patterns", [])
        self._ignore_patterns = [
            re.compile(str(pattern), re.IGNORECASE) for pattern in ignore_patterns
        ]
        self._ast_strategy: _DeadCodeStrategy = _ASTDeadCodeStrategy()
        self._regex_strategy: _DeadCodeStrategy = _RegexDeadCodeStrategy()
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
        from ...exceptions import ConfigurationError

        for key in ("check_unused", "check_duplicates", "check_unreachable"):
            value = self.get_config_value(key, True)
            if not isinstance(value, bool):
                raise ConfigurationError(
                    f"Config key '{key}' must be a boolean",
                    config_key=f"{self.name}.{key}",
                    provided_value=value,
                )
        patterns = self.get_list_config("ignore_patterns", [])
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
        keywords, keyword_calls, keyword_display_names, _ = (
            self._extract_keywords_and_calls(test_file)
        )

        if self._check_unused:
            findings.extend(
                self._find_unused_keywords(
                    keywords, keyword_calls, keyword_display_names, test_file
                )
            )

        if self._check_duplicates:
            findings.extend(self._find_duplicate_keywords(keywords, test_file, keyword_display_names))

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

        all_definitions, file_keywords, all_calls, per_file_display = (
            self._collect_suite_definitions(files)
        )

        findings: list[Finding] = []
        if self._check_unused:
            findings.extend(
                self._find_suite_unused_keywords(all_definitions, all_calls, per_file_display)
            )
        if self._check_duplicates:
            findings.extend(self._find_all_duplicate_keywords(file_keywords, per_file_display))
        if self._check_unreachable:
            findings.extend(self._find_all_unreachable_code(files))

        return findings

    def _collect_suite_definitions(
        self, files: Sequence[TestFile]
    ) -> tuple[
        dict[str, list[tuple[TestFile, int]]],
        list[tuple[TestFile, dict[str, list[int]]]],
        set[str],
        dict[str, str],
    ]:
        """Collect all keyword definitions and calls across suite files."""
        all_definitions: dict[str, list[tuple[TestFile, int]]] = defaultdict(list)
        raw_candidates: list[str] = []
        per_file_display: dict[str, str] = {}
        file_keywords: list[tuple[TestFile, dict[str, list[int]]]] = []

        for test_file in files:
            keywords, _, display_names, candidates = self._extract_keywords_and_calls(
                test_file
            )
            file_keywords.append((test_file, keywords))
            for kw_name, line_numbers in keywords.items():
                for line_num in line_numbers:
                    all_definitions[kw_name].append((test_file, line_num))
                per_file_display.setdefault(
                    kw_name, display_names.get(kw_name, kw_name)
                )
            raw_candidates.extend(candidates)

        all_calls = _resolve_calls(raw_candidates, set(all_definitions))
        return all_definitions, file_keywords, all_calls, per_file_display

    def _find_suite_unused_keywords(
        self,
        all_definitions: dict[str, list[tuple[TestFile, int]]],
        all_calls: set[str],
        per_file_display: dict[str, str],
    ) -> list[Finding]:
        """Find unused keywords across the suite."""
        if not all_definitions:
            return []
        findings: list[Finding] = []
        for kw_name, locations in all_definitions.items():
            if kw_name in all_calls:
                continue
            display_name = per_file_display.get(kw_name, kw_name)
            if kw_name in _LIFECYCLE_KEYWORDS:
                continue
            if any(p.match(display_name) for p in self._ignore_patterns):
                continue
            test_file, line_num = locations[0]
            findings.append(
                Finding.create(
                    pattern=_unused_keyword_pattern(display_name, suite_level=True),
                    severity=Severity.WARNING,
                    location=Location(file_path=test_file.path, line=line_num),
                    message=f"Keyword '{display_name}' is defined but never used in the suite",
                    keyword_name=display_name,
                )
            )
        return findings

    def _find_all_duplicate_keywords(
        self,
        file_keywords: list[tuple[TestFile, dict[str, list[int]]]],
        per_file_display: dict[str, str] | None = None,
    ) -> list[Finding]:
        """Find duplicate keywords across all files."""
        findings: list[Finding] = []
        for test_file, keywords in file_keywords:
            findings.extend(self._find_duplicate_keywords(keywords, test_file, per_file_display))
        return findings

    def _find_all_unreachable_code(self, files: Sequence[TestFile]) -> list[Finding]:
        """Find unreachable code across all files."""
        findings: list[Finding] = []
        for test_file in files:
            findings.extend(self._find_unreachable_code(test_file))
        return findings

    def _extract_keywords_and_calls(
        self, test_file: TestFile
    ) -> tuple[dict[str, list[int]], set[str], dict[str, str], list[str]]:
        """Extract keyword definitions and calls.

        Tries the AST strategy first; falls back to the regex strategy if the
        Robot Framework parser raises an exception.
        """
        try:
            return self._ast_strategy.extract(test_file)
        except Exception as e:
            self._logger.debug(
                "AST parse failed, falling back to regex strategy",
                extra={"file": str(test_file.path), "error": str(e)},
            )
            return self._regex_strategy.extract(test_file)

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

                finding = Finding.create(
                    pattern=_unused_keyword_pattern(display_name),
                    severity=Severity.WARNING,
                    location=Location(file_path=test_file.path, line=line_numbers[0]),
                    message=f"Keyword '{display_name}' is defined but never used",
                    keyword_name=display_name,
                )
                findings.append(finding)

        return findings

    def _find_duplicate_keywords(
        self,
        keywords: dict[str, list[int]],
        test_file: TestFile,
        display_names: dict[str, str] | None = None,
    ) -> list[Finding]:
        """Find keywords defined multiple times."""
        findings = []

        for keyword_name, line_numbers in keywords.items():
            if len(line_numbers) > 1:
                # Use the original-case display name so user-facing messages
                # match the actual keyword casing rather than the normalised key.
                display = (display_names or {}).get(keyword_name, keyword_name)
                pattern = Pattern.duplicate_keyword(display)

                # Create findings for all duplicates after the first
                for line_num in line_numbers[1:]:
                    finding = Finding.create(
                        pattern=pattern,
                        severity=Severity.ERROR,
                        location=Location(file_path=test_file.path, line=line_num),
                        message=f"Keyword '{display}' is already defined at line {line_numbers[0]}",
                        first_definition_line=line_numbers[0],
                        duplicate_count=len(line_numbers),
                    )
                    findings.append(finding)

        return findings

    def _make_unreachable_finding(
        self, test_file: TestFile, line_num: int, keyword_name: str
    ) -> Finding:
        pattern = Pattern(
            pattern_type=PatternType.UNREACHABLE_CODE,
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

    def _process_unreachable_line(
        self,
        line: str,
        stripped: str,
        state: _UnreachableState,
        test_file: TestFile,
        line_num: int,
        findings: list[Finding],
    ) -> None:
        if not stripped or stripped.startswith("#"):
            return
        if stripped.startswith("***"):
            state.enter_section(stripped)
            return
        if not line.startswith((" ", "\t")):
            if state.in_keywords_section:
                state.enter_keyword(stripped)
            else:
                state.exit_keyword()
            return
        if not state.in_keyword:
            return
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
            if state.current_keyword is None:
                raise AnalysisError(
                    "Unreachable invariant: found_return=True but no current_keyword",
                    file_path=test_file.path,
                    analyzer=self.name,
                )
            findings.append(
                self._make_unreachable_finding(test_file, line_num, state.current_keyword)
            )
            state.found_return = False

    def _find_unreachable_code(self, test_file: TestFile) -> list[Finding]:
        """Find code after RETURN statements inside Keyword definitions.

        A RETURN inside an IF/ELSE branch does not make the lines *after* the
        END unreachable.  ``_UnreachableState.control_depth`` tracks nesting so
        ``found_return`` is only set for top-level RETURNs in the keyword body.
        """
        findings: list[Finding] = []
        state = _UnreachableState()
        for line_num, line in enumerate(test_file.content.splitlines(), 1):
            self._process_unreachable_line(
                line, line.strip(), state, test_file, line_num, findings
            )
        return findings
