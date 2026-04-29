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
from typing import cast

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

from ..config import get_settings
from ..domain.entities import TestFile
from ..domain.value_objects import (
    Finding,
    Location,
    Pattern,
    PatternType,
    Severity,
    SleepPattern,
)
from ..exceptions import ConfigurationError
from .base import BaseAnalyzer, ConfigValue

__all__ = ["SleepDetector"]

# ---------------------------------------------------------------------------
# Unit normalisation helper (Task 9)
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


class SleepDetector(BaseAnalyzer):
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

        # Get severity thresholds from settings
        settings = get_settings()
        max_acceptable = settings.max_acceptable_sleep_seconds

        # Default thresholds
        self._severity_thresholds = self.get_config_value(
            "severity_thresholds",
            {
                "info": max_acceptable,  # <= 1s by default
                "warning": max_acceptable * 5,  # <= 5s
                "error": float("inf"),  # > 5s
            },
        )

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

        for line_num, line in enumerate(lines, 1):
            if sleep_info := self._detect_sleep(line):
                if finding := self._create_finding(
                    sleep_info, test_file, line_num, line.strip(), ctx
                ):
                    findings.append(finding)

        return findings

    def _compile_sleep_patterns(self) -> list[tuple[re.Pattern[str], str]]:
        """Compile regex patterns for sleep detection.

        Task 9: Supports ``Sleep  2 minutes``, ``Sleep  500ms``, ``Sleep  1.5s``
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

    # Task 10: regex for detecting time.sleep() inside Evaluate calls
    _EVALUATE_SLEEP_RE: re.Pattern[str] = re.compile(
        r"^\s*(?:Evaluate|Run Keyword)\s+.*time\.sleep\s*\(\s*(\d+(?:\.\d+)?)\s*\)",
        re.IGNORECASE,
    )

    def _detect_sleep(self, line: str) -> dict[str, str | Decimal | None] | None:
        """Detect sleep pattern in a line.

        Task 9: Normalises duration using Robot Framework's own
        ``timestring_to_secs`` utility when available, falling back to the
        built-in unit multipliers.
        Task 10: Also detects ``Evaluate  time.sleep(N)`` calls.

        Args:
            line: Line to check.

        Returns:
            Sleep information dict or None.
        """
        # Task 10: check for time.sleep() inside Evaluate first
        if self._check_builtin:
            if m := self._EVALUATE_SLEEP_RE.match(line):
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
                    pass

        for pattern, sleep_type in self._sleep_patterns:
            if match := pattern.match(line):
                match sleep_type:
                    case "variable":
                        # Variable sleep - can't determine duration
                        return {
                            "type": sleep_type,
                            "variable": match.group(1),
                            "duration": None,
                            "unit": None,
                        }
                    case _:
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
                                extra={"line": line},
                            )
                            return None

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
                type=PatternType.SLEEP_IN_TEST,
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

    # Library-specific wait keywords keyed by context category
    _LIBRARY_WAITS: dict[str, dict[str, str]] = {
        "seleniumlibrary": {
            "ui": "Wait Until Element Is Visible",
            "page": "Wait Until Page Contains",
            "verify": "Wait Until Keyword Succeeds",
            "network": "Wait Until Keyword Succeeds",
            "generic": "Wait Until Element Is Visible",
        },
        "browser": {
            "ui": "Wait For Elements State",
            "page": "Wait For Navigation",
            "verify": "Wait Until Keyword Succeeds",
            "network": "Wait For Response",
            "generic": "Wait For Elements State",
        },
        "appiumlibrary": {
            "ui": "Wait Until Element Is Visible",
            "page": "Wait Until Page Contains",
            "verify": "Wait Until Keyword Succeeds",
            "network": "Wait Until Keyword Succeeds",
            "generic": "Wait Until Element Is Visible",
        },
    }
    _GENERIC_WAITS: dict[str, str] = {
        "ui": "Wait Until Element Is Visible",
        "page": "Wait Until Page Contains",
        "verify": "Wait Until Keyword Succeeds",
        "network": "Wait Until Keyword Succeeds",
        "generic": "Wait Until Keyword Succeeds",
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
    _VERIFY_RE: re.Pattern[str] = re.compile(r"should|verify|check|assert|expect|contain|equal|match")
    _PAGE_RE: re.Pattern[str] = re.compile(r"page|navigate|url|title|reload|refresh|location|tab|window")
    _UI_RE: re.Pattern[str] = re.compile(r"click|element|button|input|checkbox|radio|select|focus|hover|drag|drop|type|fill|press")
    _NETWORK_RE: re.Pattern[str] = re.compile(r"request|response|api|http|fetch|xhr|ajax|websocket")

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

        waits = self._LIBRARY_WAITS.get(library, self._GENERIC_WAITS) if library else self._GENERIC_WAITS
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
