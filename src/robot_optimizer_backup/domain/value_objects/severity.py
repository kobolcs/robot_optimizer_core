# src/robot_optimizer/domain/value_objects/severity.py
"""Defines severity levels for optimization findings."""
from enum import Enum, auto


class Severity(Enum):
    """Severity levels for optimization findings."""

    ERROR = auto()    # Must fix - breaks best practices or causes issues
    WARNING = auto()  # Should fix - suboptimal but works
    INFO = auto()     # Could fix - minor improvement opportunity

    def __lt__(self, other: 'Severity') -> bool:
        """Compare severity levels. ERROR > WARNING > INFO."""
        # Lower value = higher severity
        return self.value < other.value

    @property
    def emoji(self) -> str:
        """Get emoji representation for the severity."""
        return {
            Severity.ERROR: "❌",
            Severity.WARNING: "⚠️",
            Severity.INFO: "ℹ️"
        }[self]

    @property
    def color(self) -> str:
        """Get color name for rich console output."""
        return {
            Severity.ERROR: "red",
            Severity.WARNING: "yellow",
            Severity.INFO: "blue"
        }[self]
