# src/robot_optimizer_core/analyzers/setup_teardown.py
"""Setup/teardown analyzer for Robot Framework test suites.

Flags test cases that duplicate inline setup/teardown steps that should be
extracted into [Setup] / [Teardown] hooks or suite-level hooks.
"""

from __future__ import annotations

import sys
from collections import Counter
from collections.abc import Callable

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

from ..domain.entities import TestFile
from ..domain.value_objects import Finding, Location, Pattern, PatternType, Severity
from .base import BaseAnalyzer, ConfigValue

__all__ = ["SetupTeardownAnalyzer"]

# Common setup/teardown keyword patterns (case-insensitive substrings)
_SETUP_HINTS: frozenset[str] = frozenset(
    {
        "open browser",
        "launch browser",
        "start browser",
        "navigate to",
        "go to",
        "open application",
        "start application",
        "launch application",
        "setup",
        "set up",
        "initialize",
        "initialise",
        "login",
        "log in",
        "sign in",
        "authenticate",
        "create session",
        "open connection",
        "connect to",
    }
)

_TEARDOWN_HINTS: frozenset[str] = frozenset(
    {
        "close browser",
        "close all browsers",
        "close application",
        "close connection",
        "disconnect",
        "logout",
        "log out",
        "sign out",
        "delete session",
        "teardown",
        "tear down",
        "cleanup",
        "clean up",
        "delete all cookies",
        "close all connections",
    }
)


def _matches_hint(call: str, hints: frozenset[str]) -> bool:
    lower = call.lower()
    return any(hint in lower for hint in hints)


class SetupTeardownAnalyzer(BaseAnalyzer):
    """Detects repeated inline setup/teardown steps.

    When the same setup-like or teardown-like keyword is called as the first
    (or last) step in ≥ *duplication_threshold* test cases without using
    [Setup] / [Teardown], a finding is reported for each affected test.

    Configuration:
        duplication_threshold: Minimum tests sharing a step to flag it
            (default: 2).
        check_setup: Check for repeated first-step patterns (default: True).
        check_teardown: Check for repeated last-step patterns (default: True).
    """

    def __init__(self, config: dict[str, ConfigValue] | None = None) -> None:
        super().__init__(config)
        raw_threshold = self.get_config_value("duplication_threshold", 2)
        if isinstance(raw_threshold, bool):
            msg = "duplication_threshold must be an integer, not a boolean"
            raise TypeError(msg)
        if isinstance(raw_threshold, int):
            self._threshold = raw_threshold
        elif isinstance(raw_threshold, float):
            if not raw_threshold.is_integer():
                msg = f"duplication_threshold must be a whole number, got: {raw_threshold}"
                raise ValueError(msg)
            self._threshold = int(raw_threshold)
        elif isinstance(raw_threshold, str):
            try:
                self._threshold = int(raw_threshold.strip())
            except ValueError as e:
                msg = f"duplication_threshold must be an integer, got: {raw_threshold}"
                raise ValueError(msg) from e
        else:
            msg = f"duplication_threshold must be an integer, got {type(raw_threshold).__name__}"
            raise TypeError(msg)
        if self._threshold < 1:
            msg = "duplication_threshold must be >= 1"
            raise ValueError(msg)
        self._check_setup = bool(self.get_config_value("check_setup", True))
        self._check_teardown = bool(self.get_config_value("check_teardown", True))

    @property
    @override
    def name(self) -> str:
        return "setup_teardown"

    @property
    @override
    def description(self) -> str:
        return (
            "Detects repeated inline setup/teardown steps that should use "
            "[Setup]/[Teardown] hooks"
        )

    @property
    @override
    def tags(self) -> list[str]:
        return ["structure", "duplication", "best-practices"]

    def _check_for_duplicates(
        self,
        test_steps: list[tuple[str, int, list[str], bool]],
        test_file: TestFile,
        kind: str,
        hints: set[str],
        step_getter: Callable[[list[str]], str],
    ) -> list[Finding]:
        """Check for duplicated setup/teardown steps.

        Args:
            test_steps: Parsed test case steps.
            test_file: The test file being analyzed.
            kind: Either "setup" or "teardown".
            hints: Set of hint keywords for this kind.
            step_getter: Function to extract step (lambda for first/last element).

        Returns:
            List of findings.
        """
        findings: list[Finding] = []

        # Count occurrences of hints
        step_counts: Counter[str] = Counter()
        for _, _, steps, _ in test_steps:
            if steps:
                step = step_getter(steps)
                if _matches_hint(step, hints):
                    step_counts[step.lower()] += 1

        # Check each test for duplicated steps
        for test_name, line_num, steps, hook_info in test_steps:
            if not steps or hook_info:
                continue
            step = step_getter(steps)
            if (
                _matches_hint(step, hints)
                and step_counts[step.lower()] >= self._threshold
            ):
                findings.append(
                    self._make_finding(
                        test_name,
                        line_num,
                        test_file,
                        step=step,
                        kind=kind,
                        count=step_counts[step.lower()],
                    )
                )

        return findings

    @override
    def analyze(self, test_file: TestFile) -> list[Finding]:
        findings: list[Finding] = []
        test_steps = self._parse_test_steps(test_file)

        if not test_steps:
            return findings

        if self._check_setup:
            findings.extend(
                self._check_for_duplicates(
                    test_steps,
                    test_file,
                    kind="setup",
                    hints=_SETUP_HINTS,
                    step_getter=lambda steps: steps[0],
                )
            )

        if self._check_teardown:
            findings.extend(
                self._check_for_duplicates(
                    test_steps,
                    test_file,
                    kind="teardown",
                    hints=_TEARDOWN_HINTS,
                    step_getter=lambda steps: steps[-1],
                )
            )

        return findings

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_test_steps(
        self, test_file: TestFile
    ) -> list[tuple[str, int, list[str], bool]]:
        """Parse test cases returning (name, line, steps, has_setup_or_teardown)."""
        result: list[tuple[str, int, list[str], bool]] = []
        lines = test_file.content.splitlines()
        in_test_cases = False
        current_name: str | None = None
        current_line = 1
        current_steps: list[str] = []
        has_hook = False

        def flush() -> None:
            if current_name:
                result.append(
                    (current_name, current_line, list(current_steps), has_hook)
                )

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("***"):
                flush()
                current_name = None
                current_steps = []
                has_hook = False
                in_test_cases = "test case" in stripped.lower()
                continue

            if in_test_cases and not line.startswith((" ", "\t")):
                flush()
                current_name = stripped if not stripped.startswith("#") else None
                current_line = line_num
                current_steps = []
                has_hook = False
                continue

            if current_name and line.startswith((" ", "\t")):
                lower = stripped.lower()
                if lower.startswith("[setup]") or lower.startswith("[teardown]"):
                    has_hook = True
                    continue
                if lower.startswith("[") and lower.endswith("]"):
                    continue  # other settings like [Tags], [Documentation]
                if stripped.startswith("#"):
                    continue
                # Strip variable assignment prefix:  ${var}=    Keyword  → Keyword
                keyword_call = stripped
                if stripped.startswith("${") and "=" in stripped:
                    parts = stripped.split("=", 1)
                    keyword_call = parts[1].strip() if len(parts) > 1 else stripped
                current_steps.append(keyword_call)

        flush()
        return result

    # ------------------------------------------------------------------
    # Finding factory
    # ------------------------------------------------------------------

    def _make_finding(
        self,
        test_name: str,
        line_num: int,
        test_file: TestFile,
        step: str,
        kind: str,
        count: int,
    ) -> Finding:
        hook = "[Setup]" if kind == "setup" else "[Teardown]"
        pattern = Pattern(
            type=PatternType.MISSING_SETUP_TEARDOWN,
            name=f"Inline {kind.title()} Step",
            description=(
                f"Test case '{test_name}' contains inline {kind} step "
                f"'{step}' (shared by {count} tests)"
            ),
            recommendation=(
                f"Move '{step}' to {hook} or a Suite {kind.title()} to avoid duplication"
            ),
            documentation_url=None,
            auto_fixable=False,
        )
        return Finding.create(
            pattern=pattern,
            severity=Severity.WARNING,
            location=Location(file_path=test_file.path, line=line_num),
            message=(
                f"Inline {kind} step '{step}' is repeated in {count} tests "
                f"— use {hook} instead"
            ),
            test_name=test_name,
            step=step,
            kind=kind,
            shared_count=count,
        )
