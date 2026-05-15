# tests/unit/domain/value_objects/test_severity.py
"""Unit tests for Severity enum.

Comprehensive tests for all Severity methods and properties to ensure
complete coverage and mutation testing resilience.
"""

from __future__ import annotations

import pytest

from robot_optimizer_core.domain.value_objects import Severity


@pytest.mark.unit
class TestSeverity:
    """Test the Severity enum."""

    def test_severity_values(self) -> None:
        """Test severity enum values."""
        assert Severity.ERROR.value == 1
        assert Severity.WARNING.value == 2
        assert Severity.INFO.value == 3

    def test_severity_ordering(self) -> None:
        """Test that severities are properly ordered."""
        # ERROR is most severe (lowest value)
        assert Severity.ERROR < Severity.WARNING
        assert Severity.WARNING < Severity.INFO
        assert Severity.ERROR < Severity.INFO

        # Reverse comparisons
        assert Severity.INFO > Severity.WARNING
        assert Severity.WARNING > Severity.ERROR
        assert Severity.INFO > Severity.ERROR

        # Equality
        assert Severity.ERROR is Severity.ERROR
        assert not (Severity.ERROR == Severity.WARNING)

    def test_severity_string_representation(self) -> None:
        """Test string representation."""
        assert str(Severity.ERROR) == "ERROR"
        assert str(Severity.WARNING) == "WARNING"
        assert str(Severity.INFO) == "INFO"

    def test_severity_emoji(self) -> None:
        """Test emoji representations."""
        assert Severity.ERROR.emoji == "❌"
        assert Severity.WARNING.emoji == "⚠️"
        assert Severity.INFO.emoji == "ℹ️"

    def test_severity_color(self) -> None:
        """Test color representations for console output."""
        assert Severity.ERROR.color == "red"
        assert Severity.WARNING.color == "yellow"
        assert Severity.INFO.color == "blue"

    def test_severity_ansi_codes(self) -> None:
        """Test ANSI color codes."""
        assert Severity.ERROR.ansi_code == "\033[91m"  # Bright red
        assert Severity.WARNING.ansi_code == "\033[93m"  # Bright yellow
        assert Severity.INFO.ansi_code == "\033[94m"  # Bright blue

    def test_severity_priority(self) -> None:
        """Test priority values (inverse of enum value)."""
        assert Severity.ERROR.priority == 3  # Highest priority
        assert Severity.WARNING.priority == 2
        assert Severity.INFO.priority == 1  # Lowest priority

    def test_severity_description(self) -> None:
        """Test human-readable descriptions."""
        error_desc = Severity.ERROR.description
        assert "critical" in error_desc.lower()
        assert "best practices" in error_desc.lower()

        warning_desc = Severity.WARNING.description
        assert "important" in warning_desc.lower()
        assert "reliability" in warning_desc.lower()

        info_desc = Severity.INFO.description
        assert "minor" in info_desc.lower()
        assert "enhancement" in info_desc.lower() or "quality" in info_desc.lower()

    def test_severity_exit_codes(self) -> None:
        """Test suggested exit codes for CLI tools."""
        assert Severity.ERROR.exit_code == 2
        assert Severity.WARNING.exit_code == 1
        assert Severity.INFO.exit_code == 0

    def test_from_string(self) -> None:
        """Test creating severity from string."""
        # Case insensitive
        assert Severity.from_string("error") == Severity.ERROR
        assert Severity.from_string("ERROR") == Severity.ERROR
        assert Severity.from_string("Error") == Severity.ERROR

        assert Severity.from_string("warning") == Severity.WARNING
        assert Severity.from_string("WARNING") == Severity.WARNING

        assert Severity.from_string("info") == Severity.INFO
        assert Severity.from_string("INFO") == Severity.INFO

        # Invalid values
        with pytest.raises(ValueError) as exc_info:
            Severity.from_string("invalid")
        assert "Invalid severity" in str(exc_info.value)
        assert "error, warning, info" in str(exc_info.value)

        with pytest.raises(ValueError):
            Severity.from_string("")

        with pytest.raises(ValueError):
            Severity.from_string("CRITICAL")

    def test_is_at_least(self) -> None:
        """Test severity level comparison method."""
        # ERROR is at least ERROR, WARNING, and INFO
        assert Severity.ERROR.is_at_least(Severity.ERROR)
        assert Severity.ERROR.is_at_least(Severity.WARNING)
        assert Severity.ERROR.is_at_least(Severity.INFO)

        # WARNING is at least WARNING and INFO, but not ERROR
        assert not Severity.WARNING.is_at_least(Severity.ERROR)
        assert Severity.WARNING.is_at_least(Severity.WARNING)
        assert Severity.WARNING.is_at_least(Severity.INFO)

        # INFO is only at least INFO
        assert not Severity.INFO.is_at_least(Severity.ERROR)
        assert not Severity.INFO.is_at_least(Severity.WARNING)
        assert Severity.INFO.is_at_least(Severity.INFO)

    def test_should_fail_build(self) -> None:
        """Test build failure determination."""
        assert Severity.ERROR.should_fail_build() is True
        assert Severity.WARNING.should_fail_build() is False
        assert Severity.INFO.should_fail_build() is False

    def test_format_count(self) -> None:
        """Test formatting counts with proper pluralization."""
        # Singular
        assert Severity.ERROR.format_count(1) == "❌ 1 error"
        assert Severity.WARNING.format_count(1) == "⚠️ 1 warning"
        assert Severity.INFO.format_count(1) == "ℹ️ 1 info"

        # Plural
        assert Severity.ERROR.format_count(0) == "❌ 0 errors"
        assert Severity.ERROR.format_count(2) == "❌ 2 errors"
        assert Severity.ERROR.format_count(10) == "❌ 10 errors"

        assert Severity.WARNING.format_count(3) == "⚠️ 3 warnings"
        assert Severity.INFO.format_count(5) == "ℹ️ 5 infos"

    def test_severity_iteration(self) -> None:
        """Test that we can iterate over severity values."""
        severities = list(Severity)
        assert len(severities) == 3
        assert Severity.ERROR in severities
        assert Severity.WARNING in severities
        assert Severity.INFO in severities

    def test_severity_membership(self) -> None:
        """Test membership testing."""
        assert Severity.ERROR in Severity
        assert Severity.WARNING in Severity
        assert Severity.INFO in Severity

        # These shouldn't be members
        assert Severity(1) is Severity.ERROR
        assert all(member.value != "ERROR" for member in Severity)
