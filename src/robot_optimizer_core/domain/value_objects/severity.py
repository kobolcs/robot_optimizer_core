# src/robot_optimizer_core/domain/value_objects/severity.py
"""Severity levels for optimization findings.

This module defines the severity levels used to classify findings
based on their impact and urgency.

Example:
    Using severity levels::

        from robot_optimizer_core import Severity, Finding

        # Create finding with severity
        finding = Finding.create(
            pattern=pattern,
            severity=Severity.ERROR,
            location=location,
            message="Critical issue found"
        )

        # Compare severities
        if finding.severity > Severity.WARNING:
            print("High priority issue!")
"""
from __future__ import annotations

import sys
from enum import IntEnum

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class Severity(IntEnum):
    """Severity levels for optimization findings.

    Severity levels indicate the importance and urgency of addressing
    a finding. They are ordered from most severe (ERROR) to least
    severe (INFO).

    The enum uses integer values for easy comparison:
    - Lower values = higher severity
    - Higher values = lower severity

    Attributes:
        ERROR: Critical issues that should be fixed immediately.
        WARNING: Important issues that should be addressed.
        INFO: Minor improvements or informational findings.

    Example:
        >>> assert Severity.ERROR < Severity.WARNING < Severity.INFO
        >>>
        >>> # Get display properties
        >>> print(f"{Severity.ERROR.emoji} {Severity.ERROR.name}")
        ❌ ERROR
    """

    ERROR = 1    # Critical - breaks best practices or causes issues
    WARNING = 2  # Important - suboptimal but works
    INFO = 3     # Minor - improvement opportunity

    @override
    def __str__(self) -> str:
        """Return the severity name.

        Returns:
            Severity name as string.
        """
        return self.name

    @property
    def emoji(self) -> str:
        """Get emoji representation for the severity.

        Used for console output and visual indicators.

        Returns:
            Emoji character for this severity.

        Example:
            >>> print(f"{Severity.ERROR.emoji} Critical issue")
            ❌ Critical issue
        """
        # Using pattern matching (Python 3.10+)
        match self:
            case Severity.ERROR:
                return "❌"
            case Severity.WARNING:
                return "⚠️"
            case Severity.INFO:
                return "ℹ️"

    @property
    def color(self) -> str:
        """Get color name for console output.

        Used with Rich library for colored terminal output.

        Returns:
            Color name for this severity.
        """
        match self:
            case Severity.ERROR:
                return "red"
            case Severity.WARNING:
                return "yellow"
            case Severity.INFO:
                return "blue"

    @property
    def ansi_code(self) -> str:
        """Get ANSI color code for direct terminal coloring.

        Returns:
            ANSI escape code for this severity's color.
        """
        match self:
            case Severity.ERROR:
                return "\033[91m"    # Bright red
            case Severity.WARNING:
                return "\033[93m"    # Bright yellow
            case Severity.INFO:
                return "\033[94m"    # Bright blue

    @property
    def priority(self) -> int:
        """Get numeric priority (inverse of value).

        Higher priority = more severe = lower enum value.
        This provides an intuitive priority number where
        higher numbers mean higher priority.

        Returns:
            Priority value (1-3, higher is more important).
        """
        return 4 - self.value

    @property
    def description(self) -> str:
        """Get human-readable description of the severity.

        Returns:
            Description of what this severity level means.
        """
        match self:
            case Severity.ERROR:
                return (
                    "Critical issues that break best practices, "
                    "cause test failures, or significantly impact quality"
                )
            case Severity.WARNING:
                return (
                    "Important issues that should be addressed to improve "
                    "test reliability and maintainability"
                )
            case Severity.INFO:
                return (
                    "Minor improvements and suggestions that can enhance "
                    "test suite quality"
                )

    @property
    def exit_code(self) -> int:
        """Get suggested exit code for CLI tools.

        Useful when implementing CLI tools that need to
        return different exit codes based on findings.

        Returns:
            Suggested exit code.
        """
        match self:
            case Severity.ERROR:
                return 2    # Errors found
            case Severity.WARNING:
                return 1    # Warnings found
            case Severity.INFO:
                return 0    # Only info, success

    @classmethod
    def from_string(cls, value: str) -> Severity:
        """Create severity from string representation.

        Case-insensitive conversion from string to severity.

        Args:
            value: String representation ("error", "warning", "info").

        Returns:
            Corresponding Severity enum value.

        Raises:
            ValueError: If string doesn't match any severity.

        Example:
            >>> severity = Severity.from_string("warning")
            >>> assert severity == Severity.WARNING
        """
        try:
            return cls[value.upper()]
        except KeyError as err:
            valid = [s.name.lower() for s in cls]
            raise ValueError(
                f"Invalid severity '{value}'. "
                f"Valid values are: {', '.join(valid)}"
            ) from err

    def is_at_least(self, level: Severity) -> bool:
        """Check if this severity is at least as severe as another.

        Args:
            level: Severity level to compare against.

        Returns:
            True if this severity is equal or more severe.

        Example:
            >>> error = Severity.ERROR
            >>> assert error.is_at_least(Severity.WARNING)
            >>> assert not error.is_at_least(Severity.INFO)
        """
        return self <= level

    def should_fail_build(self) -> bool:
        """Check if this severity should fail a build/check.

        Typically only ERROR severity should fail builds,
        but this can be configured.

        Returns:
            True if build should fail with this severity.
        """
        return self == Severity.ERROR

    def format_count(self, count: int) -> str:
        """Format a count with appropriate plural and emoji.

        Args:
            count: Number of findings with this severity.

        Returns:
            Formatted string with count and emoji.

        Example:
            >>> print(Severity.ERROR.format_count(3))
            ❌ 3 errors
        """
        name = self.name.lower()
        plural = name if count == 1 else f"{name}s"
        return f"{self.emoji} {count} {plural}"
