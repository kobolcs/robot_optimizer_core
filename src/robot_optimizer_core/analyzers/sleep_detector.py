# src/robot_optimizer_core/analyzers/sleep_detector.py
"""Sleep pattern detector for Robot Framework tests.

This analyzer detects usage of Sleep keywords that make tests slow
and fragile. It identifies various sleep patterns and suggests
better alternatives.

Example:
    Using the sleep detector::

        from robot_optimizer_core.analyzers import SleepDetector
        from robot_optimizer_core import TestFile

        analyzer = SleepDetector()
        test_file = TestFile.from_path("tests/login.robot")
        findings = analyzer.analyze(test_file)

        for finding in findings:
            duration = finding.context.get('duration_seconds')
            print(f"Sleep {duration}s at line {finding.line_number}")
"""

from __future__ import annotations

import dataclasses
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import ClassVar, cast

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

from ..config.settings import get_settings
from ..domain.entities import TestFile
from ..domain.value_objects import (
    Finding,
    Location,
    Pattern,
    PatternType,
    Severity,
    SleepPattern,
)
from ..domain.value_objects.robot_ast import KeywordCall
from ..exceptions import ConfigurationError
from ..parsers.robot_ast_parser import RobotASTParser
from .base import BaseAnalyzer, ConfigValue

__all__ = ["SleepDetector", "SleepDetectorAnalyzer"]

# ---------------------------------------------------------------------------
# Unit normalisation helper
# ---------------------------------------------------------------------------

_UNIT_MAP: dict[str, str] = {
    # seconds
    "s": "s",
    "sec": "s",
    "second": "seconds",
    "seconds": "seconds",
    # minutes
    "m": "m",
    "min": "m",
    "minute": "minutes",
    "minutes": "minutes",
    # milliseconds
    "ms": "ms",
    "millisecond": "ms",
    "milliseconds": "ms",
    # hours — convert for threshold comparison
    "h": "h",
    "hour": "h",
    "hours": "h",
    # days
    "d": "d",
    "day": "d",
    "days": "d",
}

# Multipliers to seconds for extended units used in threshold comparison
_UNIT_TO_SECONDS: dict[str, float] = {
    "ms": 0.001,
    "s": 1.0,
    "seconds": 1.0,
    "m": 60.0,
    "minutes": 60.0,
    "h": 3600.0,
    "d": 86400.0,
}


def _normalise_unit(raw: str | None) -> str:
    """Normalise a raw unit token from a regex match to a canonical form.

    Falls back to ``"s"`` when *raw* is None or unrecognised.
    """
    if not raw:
        return "s"
    lower = raw.lower().strip()
    return _UNIT_MAP.get(lower, "s")


@dataclasses.dataclass(slots=True)
class _AnalyzeCtx:
    """Per-analyze() call state; avoids instance mutation and is thread-safe."""

    lines: list[str]
    library: str | None
    block_names: dict[int, str | None]


class SleepDetectorAnalyzer(BaseAnalyzer):
    """Detects sleep usage in Robot Framework tests.

    This analyzer finds Sleep keyword usage and categorizes findings
    by severity based on duration. It suggests appropriate wait
    conditions as replacements.

    Configuration:
        severity_thresholds: Dict mapping duration to severity.
        suggest_alternatives: Whether to suggest replacements.
        check_builtin_sleep: Check BuiltIn.Sleep usage.
        check_custom_sleep: Check custom sleep implementations.
    """

    def __init__(self, config: dict[str, ConfigValue] | None = None) -> None:
        """Initialize the analyzer.

        Args:
            config: Analyzer configuration.
        """
        super().__init__(config)

        if "severity_thresholds" not in self.config:
            max_acceptable = get_settings().max_acceptable_sleep_seconds
            self._severity_thresholds: dict[str, float] = {
                "info": max_acceptable,
                "warning": max_acceptable * 5,
                "error": float("inf"),
            }
        else:
            self._severity_thresholds = cast(dict[str, float], self.config["severity_thresholds"])

        # Configuration
        self._suggest_alternatives = self.get_config_value("suggest_alternatives", True)
        self._check_builtin = self.get_config_value("check_builtin_sleep", True)
        self._check_custom = self.get_config_value("check_custom_sleep", True)

        # Compile patterns
        self._sleep_patterns = self._compile_sleep_patterns()
        self.validate_config()

    @property
    @override
    def name(self) -> str:
        """Get analyzer name.

        Returns:
            Analyzer name.
        """
        return "sleep_detector"

    @property
    @override
    def description(self) -> str:
        """Get analyzer description.

        Returns:
            Analyzer description.
        """
        return "Finds Sleep keyword usage that makes tests slow and fragile"

    @property
    @override
    def tags(self) -> list[str]:
        """Get analyzer tags.

        Returns:
            List of tags.
        """
        return ["performance", "stability", "wait-conditions"]

    @property
    @override
    def supports_auto_fix(self) -> bool:
        """Check if analyzer supports auto-fixing.

        Returns:
            True (sleep can be replaced with waits).
        """
        return True

    # Regex to parse a numeric duration from a single keyword argument value.
    _DURATION_ARG_RE: re.Pattern[str] = re.compile(
        r"^(\d+(?:\.\d+)?)\s*(s|seconds?|m|minutes?|ms|milliseconds?|h|hours?|d|days?|min)?$",
        re.IGNORECASE,
    )
    _VAR_ARG_RE: re.Pattern[str] = re.compile(r"^\$\{([^}]+)\}$")
    _TIME_SLEEP_ARG_RE: re.Pattern[str] = re.compile(
        r"time\.sleep\s*\(\s*(\d+(?:\.\d+)?)\s*\)"
    )

    def _detect_sleep_from_call(
        self, call: KeywordCall
    ) -> dict[str, str | Decimal | None] | None:
        """Detect a sleep pattern from an AST keyword call."""
        name_lower = call.keyword_name.lower()

        # Evaluate / Run Keyword containing time.sleep(N)
        if self._check_builtin and name_lower in ("evaluate", "run keyword"):
            arg = call.arguments[0] if call.arguments else ""
            m = self._TIME_SLEEP_ARG_RE.search(arg)
            if m:
                try:
                    return {
                        "type": "evaluate_sleep",
                        "duration": Decimal(m.group(1)),
                        "unit": "s",
                        "duration_str": m.group(1),
                    }
                except (ValueError, InvalidOperation):
                    pass
            return None

        is_builtin = self._check_builtin and name_lower in ("sleep", "builtin.sleep")
        is_custom = self._check_custom and name_lower in ("wait", "pause", "delay")
        if not (is_builtin or is_custom):
            return None
        if not call.arguments:
            return None

        arg = call.arguments[0]

        # Variable sleep (check_custom guards this branch, matching original behaviour)
        if self._check_custom and name_lower == "sleep":
            var_m = self._VAR_ARG_RE.match(arg)
            if var_m:
                return {
                    "type": "variable",
                    "variable": var_m.group(1),
                    "duration": None,
                    "unit": None,
                }

        # Numeric duration
        dur_m = self._DURATION_ARG_RE.match(arg)
        if dur_m:
            duration_str = dur_m.group(1)
            unit = _normalise_unit(dur_m.group(2))
            try:
                duration = Decimal(duration_str)
                if name_lower == "builtin.sleep":
                    sleep_type = "builtin_qualified"
                elif is_custom:
                    sleep_type = "custom"
                else:
                    sleep_type = "builtin"
                return {
                    "type": sleep_type,
                    "duration": duration,
                    "unit": unit,
                    "duration_str": duration_str,
                }
            except (ValueError, InvalidOperation):
                self._logger.warning(
                    f"Invalid sleep duration: {duration_str}",
                    extra={"call": call.keyword_name},
                )

        return None

    @override
    def analyze(self, test_file: TestFile) -> list[Finding]:
        """Find all sleep patterns in the test file.

        Args:
            test_file: The test file to analyze.

        Returns:
            List of findings.
        """
        findings = []
        lines = test_file.content.splitlines()
        library = self._detect_library(lines) if self._suggest_alternatives else None
        block_names, _ = self._build_file_index(lines)
        ctx = _AnalyzeCtx(lines=lines, library=library, block_names=block_names)

        suite = RobotASTParser().parse_suite(test_file)
        for call in suite.all_keyword_calls:
            if sleep_info := self._detect_sleep_from_call(call):
                line_num = call.location.line
                original_text = (
                    lines[line_num - 1].strip() if 0 < line_num <= len(lines) else ""
                )
                if finding := self._create_finding(
                    sleep_info, test_file, line_num, original_text, ctx
                ):
                    findings.append(finding)

        return findings

    def _compile_sleep_patterns(self) -> list[tuple[re.Pattern[str], str]]:
        """Compile regex patterns for sleep detection.

        Supports ``Sleep  2 minutes``, ``Sleep  500ms``, ``Sleep  1.5s``
        and all Robot Framework time-string formats with a space between number
        and unit.

        Returns:
            List of (pattern, type) tuples.
        """
        patterns = []

        if self._check_builtin:
            # Standard Sleep keyword — number and unit with optional space
            patterns.append(
                (
                    re.compile(
                        r"^\s*Sleep\s+(\d+(?:\.\d+)?)\s*"
                        r"(s|seconds?|m|minutes?|ms|milliseconds?|h|hours?|d|days?|min)?",
                        re.IGNORECASE,
                    ),
                    "builtin",
                )
            )

            # BuiltIn.Sleep format
            patterns.append(
                (
                    re.compile(
                        r"^\s*BuiltIn\.Sleep\s+(\d+(?:\.\d+)?)\s*"
                        r"(s|seconds?|m|minutes?|ms|milliseconds?|h|hours?|d|days?|min)?",
                        re.IGNORECASE,
                    ),
                    "builtin_qualified",
                )
            )

        if self._check_custom:
            # Custom sleep patterns (common variations)
            patterns.append(
                (
                    re.compile(
                        r"^\s*(?:Wait|Pause|Delay)\s+(\d+(?:\.\d+)?)\s*"
                        r"(s|seconds?|m|minutes?|ms|milliseconds?|h|hours?|min)?",
                        re.IGNORECASE,
                    ),
                    "custom",
                )
            )

            # Sleep with variable
            patterns.append(
                (re.compile(r"^\s*Sleep\s+\$\{([^}]+)\}", re.IGNORECASE), "variable")
            )

        return patterns

    # Regex for detecting time.sleep() inside Evaluate calls
    _EVALUATE_SLEEP_RE: re.Pattern[str] = re.compile(
        r"^\s*(?:Evaluate|Run Keyword)\s+.*time\.sleep\s*\(\s*(\d+(?:\.\d+)?)\s*\)",
        re.IGNORECASE,
    )

    def _detect_evaluate_sleep(self, line: str) -> dict[str, str | Decimal | None] | None:
        """Detect ``Evaluate  time.sleep(N)`` on *line*.

        Returns:
            Sleep information dict, or ``None`` if not matched.
        """
        m = self._EVALUATE_SLEEP_RE.match(line)
        if not m:
            return None
        duration_str = m.group(1)
        try:
            duration = Decimal(duration_str)
            return {
                "type": "evaluate_sleep",
                "duration": duration,
                "unit": "s",
                "duration_str": duration_str,
            }
        except (ValueError, InvalidOperation):
            return None

    def _detect_pattern_sleep(
        self, match: re.Match[str], sleep_type: str
    ) -> dict[str, str | Decimal | None] | None:
        """Build a sleep-info dict from a compiled-pattern match result.

        Args:
            match: Regex match object from one of ``_sleep_patterns``.
            sleep_type: Pattern category label (e.g. ``"builtin"``, ``"variable"``).

        Returns:
            Sleep information dict, or ``None`` when the duration is unparseable.
        """
        if sleep_type == "variable":
            return {
                "type": sleep_type,
                "variable": match.group(1),
                "duration": None,
                "unit": None,
            }

        # Numeric sleep
        duration_str = match.group(1)
        raw_unit = (
            match.group(2)
            if match.lastindex is not None and match.lastindex >= 2
            else None
        )
        unit = _normalise_unit(raw_unit)
        try:
            duration = Decimal(duration_str)
            return {
                "type": sleep_type,
                "duration": duration,
                "unit": unit,
                "duration_str": duration_str,
            }
        except (ValueError, InvalidOperation):
            self._logger.warning(
                f"Invalid sleep duration: {duration_str}",
                extra={"line": match.string},
            )
            return None

    def _detect_sleep(self, line: str) -> dict[str, str | Decimal | None] | None:
        """Detect sleep pattern in a line.

        Normalises duration using Robot Framework's own ``timestring_to_secs``
        utility when available, falling back to built-in unit multipliers.
        Also detects ``Evaluate  time.sleep(N)`` calls.

        Args:
            line: Line to check.

        Returns:
            Sleep information dict or None.
        """
        if self._check_builtin:
            if result := self._detect_evaluate_sleep(line):
                return result

        for pattern, sleep_type in self._sleep_patterns:
            if match := pattern.match(line):
                return self._detect_pattern_sleep(match, sleep_type)

        return None

    def _create_finding(
        self,
        sleep_info: dict[str, str | Decimal | None],
        test_file: TestFile,
        line_num: int,
        original_text: str,
        ctx: _AnalyzeCtx | None = None,
    ) -> Finding | None:
        """Create a finding from sleep information.

        Args:
            sleep_info: Sleep detection information.
            test_file: The test file.
            line_num: Line number.
            original_text: Original line text.

        Returns:
            Finding object or None.
        """
        # Handle variable sleep
        if sleep_info["duration"] is None:
            pattern = Pattern(
                pattern_type=PatternType.SLEEP_IN_TEST,
                name="Variable Sleep",
                description=f"Sleep with variable duration: ${{{sleep_info['variable']}}}",
                recommendation="Replace with explicit wait condition",
                documentation_url=None,
                auto_fixable=False,  # Can't auto-fix without knowing duration
            )

            return Finding.create(
                pattern=pattern,
                severity=Severity.WARNING,
                location=Location(file_path=test_file.path, line=line_num),
                message="Sleep with variable duration makes tests unpredictable",
                sleep_type=sleep_info["type"],
                variable_name=sleep_info["variable"],
                original_text=original_text,
            )

        # Create sleep pattern value object
        try:
            sleep_pattern = SleepPattern(
                duration=cast("Decimal", sleep_info["duration"]),
                unit=cast("str", sleep_info["unit"]),
                line_number=line_num,
                original_text=original_text,
            )
        except ValueError as e:
            self._logger.error(f"Invalid sleep pattern: {e}")
            return None

        # Determine severity based on duration
        severity = self._determine_severity(sleep_pattern.duration_in_seconds)

        # Create pattern with duration
        pattern = Pattern.sleep_in_test(
            f"{sleep_info['duration']} {sleep_info['unit']}"
        )

        # Build message with suggestion
        message = f"Sleep {sleep_info['duration']} {sleep_info['unit']} makes tests slow and fragile"

        if self._suggest_alternatives:
            if suggestion := self._suggest_alternative(
                sleep_pattern, test_file, line_num, ctx
            ):
                message += f". {suggestion}"

        return Finding.create(
            pattern=pattern,
            severity=severity,
            location=Location(file_path=test_file.path, line=line_num),
            message=message,
            duration=str(sleep_info["duration"]),
            unit=sleep_info["unit"],
            duration_seconds=sleep_pattern.duration_in_seconds,
            sleep_type=sleep_info["type"],
            original_text=original_text,
            auto_fixable=True,
        )

    def _determine_severity(self, duration_seconds: float) -> Severity:
        """Determine severity based on sleep duration.

        Args:
            duration_seconds: Duration in seconds.

        Returns:
            Severity level.
        """
        return self.determine_severity_by_threshold(
            duration_seconds, self._severity_thresholds
        )

    # Wait keyword constants
    _WAIT_ELEMENT_VISIBLE = "Wait Until Element Is Visible"
    _WAIT_PAGE_CONTAINS = "Wait Until Page Contains"
    _WAIT_KEYWORD_SUCCEEDS = "Wait Until Keyword Succeeds"
    _WAIT_FOR_ELEMENTS_STATE = "Wait For Elements State"
    _WAIT_FOR_NAVIGATION = "Wait For Navigation"
    _WAIT_FOR_RESPONSE = "Wait For Response"

    # Library-specific wait keywords keyed by context category
    _LIBRARY_WAITS: ClassVar[dict[str, dict[str, str]]] = {
        "seleniumlibrary": {
            "ui": _WAIT_ELEMENT_VISIBLE,
            "page": _WAIT_PAGE_CONTAINS,
            "verify": _WAIT_KEYWORD_SUCCEEDS,
            "network": _WAIT_KEYWORD_SUCCEEDS,
            "generic": _WAIT_ELEMENT_VISIBLE,
        },
        "browser": {
            "ui": _WAIT_FOR_ELEMENTS_STATE,
            "page": _WAIT_FOR_NAVIGATION,
            "verify": _WAIT_KEYWORD_SUCCEEDS,
            "network": _WAIT_FOR_RESPONSE,
            "generic": _WAIT_FOR_ELEMENTS_STATE,
        },
        "appiumlibrary": {
            "ui": _WAIT_ELEMENT_VISIBLE,
            "page": _WAIT_PAGE_CONTAINS,
            "verify": _WAIT_KEYWORD_SUCCEEDS,
            "network": _WAIT_KEYWORD_SUCCEEDS,
            "generic": _WAIT_ELEMENT_VISIBLE,
        },
    }
    _GENERIC_WAITS: ClassVar[dict[str, str]] = {
        "ui": _WAIT_ELEMENT_VISIBLE,
        "page": _WAIT_PAGE_CONTAINS,
        "verify": _WAIT_KEYWORD_SUCCEEDS,
        "network": _WAIT_KEYWORD_SUCCEEDS,
        "generic": _WAIT_KEYWORD_SUCCEEDS,
    }

    def _detect_library(self, lines: list[str]) -> str | None:
        """Return the canonical library name from *** Settings *** Library imports."""
        in_settings = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("***"):
                in_settings = "setting" in stripped.lower()
                continue
            if not in_settings:
                continue
            lower = stripped.lower()
            if lower.startswith("library"):
                for lib in self._LIBRARY_WAITS:
                    if lib in lower:
                        return lib
        return None

    # Precompiled regexes for fast context classification (used in the index pass).
    _VERIFY_RE: re.Pattern[str] = re.compile(
        r"should|verify|check|assert|expect|contain|equal|match"
    )
    _PAGE_RE: re.Pattern[str] = re.compile(
        r"page|navigate|url|title|reload|refresh|location|tab|window"
    )
    _UI_RE: re.Pattern[str] = re.compile(
        r"click|element|button|input|checkbox|radio|select|focus|hover|drag|drop|type|fill|press"
    )
    _NETWORK_RE: re.Pattern[str] = re.compile(
        r"request|response|api|http|fetch|xhr|ajax|websocket"
    )

    def _build_file_index(
        self, lines: list[str]
    ) -> tuple[dict[int, str | None], dict[int, str]]:
        """Build block-name index in O(n); category dict is empty (lazy per-finding).

        Returns:
            (block_names, {}) — categories are computed on-demand in _suggest_alternative.
        """
        block_names: dict[int, str | None] = {}
        current_block: str | None = None
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("***"):
                current_block = None
            elif stripped and not line.startswith((" ", "\t")):
                current_block = stripped
            block_names[idx + 1] = current_block
        return block_names, {}

    def _enclosing_block_name(
        self,
        lines: list[str],
        line_num: int,
        block_names: dict[int, str | None] | None = None,
    ) -> str | None:
        """Return the test case or keyword name that contains line_num (1-based)."""
        if block_names:
            return block_names.get(line_num)
        # Fallback linear scan for callers without a pre-built index (e.g. tests)
        for idx in range(line_num - 2, -1, -1):
            line = lines[idx]
            if line.startswith((" ", "\t")) or not line.strip():
                continue
            stripped = line.strip()
            if stripped.startswith("***"):
                return None
            return stripped
        return None

    def _classify_context(self, context_lines: list[str]) -> str:
        """Classify context as verify / page / ui / network / generic.

        Verify is checked first: Robot Framework's 'Should' keywords are
        assertion helpers even when the line also contains 'element'.
        """
        combined = " ".join(ln.lower() for ln in context_lines if ln)
        if self._VERIFY_RE.search(combined):
            return "verify"
        if self._PAGE_RE.search(combined):
            return "page"
        if self._UI_RE.search(combined):
            return "ui"
        if self._NETWORK_RE.search(combined):
            return "network"
        return "generic"

    def _suggest_alternative(
        self,
        sleep_pattern: SleepPattern,
        test_file: TestFile,
        line_num: int,
        ctx: _AnalyzeCtx | None = None,
    ) -> str | None:
        """Suggest a context- and library-aware alternative to sleep."""
        if ctx is not None:
            lines = ctx.lines
            library = ctx.library
            block_names: dict[int, str | None] | None = ctx.block_names
        else:
            lines = test_file.content.splitlines()
            library = self._detect_library(lines)
            block_names = None

        lo, hi = max(0, line_num - 4), min(len(lines), line_num + 3)
        context_lines = [lines[i].strip() for i in range(lo, hi) if lines[i].strip()]
        category = self._classify_context(context_lines)

        waits = (
            self._LIBRARY_WAITS.get(library, self._GENERIC_WAITS)
            if library
            else self._GENERIC_WAITS
        )
        wait_keyword = waits.get(category, waits["generic"])

        block = self._enclosing_block_name(lines, line_num, block_names)
        block_hint = f" in '{block}'" if block else ""

        duration = sleep_pattern.duration_in_seconds
        if duration < 1:
            return (
                f"Sub-second sleep{block_hint} — verify it is necessary; "
                f"if so, replace with '{wait_keyword}'"
            )
        if duration < 5:
            return f"Replace with '{wait_keyword}'{block_hint}"
        return (
            f"Long sleep ({duration:.0f}s){block_hint} indicates missing synchronization — "
            f"use '{wait_keyword}' or redesign the wait strategy"
        )

    @override
    def validate_config(self) -> None:
        """Validate analyzer configuration.

        Raises:
            ConfigurationError: If configuration is invalid.
        """
        # Validate severity thresholds
        thresholds = self._severity_thresholds

        if not isinstance(thresholds, dict):
            raise ConfigurationError(
                "Severity thresholds must be a dictionary",
                config_key="severity_thresholds",
                provided_value=type(thresholds).__name__,
            )

        required_keys = {"info", "warning", "error"}
        if missing := required_keys - set(thresholds.keys()):
            raise ConfigurationError(
                f"Missing severity thresholds: {missing}",
                config_key="severity_thresholds",
                provided_value=list(thresholds.keys()),
            )

        # Validate threshold values are numbers
        for key, value in thresholds.items():
            if not isinstance(value, (int, float)):
                raise ConfigurationError(
                    f"Threshold '{key}' must be numeric",
                    config_key=f"severity_thresholds.{key}",
                    provided_value=value,
                )


# Backward-compatible alias
SleepDetector = SleepDetectorAnalyzer
