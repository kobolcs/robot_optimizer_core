# src/robot_optimizer_core/__version__.py
"""Version information for Robot Framework Optimizer Core.

This module provides version information following PEP 440.

Attributes:
    __version__ (str): The version string.
    __version_info__ (VersionInfo): Structured version information.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VersionInfo:
    """Structured version information.

    Attributes:
        major: Major version number.
        minor: Minor version number.
        patch: Patch version number.
        release: Release type (e.g., 'final', 'alpha', 'beta', 'rc').
        serial: Serial number for non-final releases.
    """
    major: int
    minor: int
    patch: int
    release: str = "final"
    serial: int = 0

    def __str__(self) -> str:
        """Return version string.

        Returns:
            Version string in PEP 440 format.
        """
        version = f"{self.major}.{self.minor}.{self.patch}"
        match self.release:
            case "final":
                return version
            case _:
                return f"{version}{self.release}{self.serial}"

    def __lt__(self, other: VersionInfo) -> bool:
        """Compare versions for ordering."""
        if not isinstance(other, VersionInfo):
            return NotImplemented

        # Compare major.minor.patch first
        if (self.major, self.minor, self.patch) != (other.major, other.minor, other.patch):
            return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

        # Then compare release types
        release_order = {"alpha": 1, "beta": 2, "rc": 3, "final": 4}
        self_order = release_order.get(self.release, 0)
        other_order = release_order.get(other.release, 0)

        if self_order != other_order:
            return self_order < other_order

        # Finally compare serial numbers
        return self.serial < other.serial

    def is_compatible_with(self, required: VersionInfo) -> bool:
        """Check if this version is compatible with a required version.

        Args:
            required: Required minimum version.

        Returns:
            True if this version is >= required version.
        """
        return not (self < required)

    @property
    def is_prerelease(self) -> bool:
        """Check if this is a prerelease version."""
        return self.release != "final"

    @property
    def version_tuple(self) -> tuple[int, int, int]:
        """Get version as a tuple for easy comparison."""
        return (self.major, self.minor, self.patch)


__version_info__ = VersionInfo(
    major=1,
    minor=0,
    patch=0,
    release="final",
    serial=0
)

__version__ = str(__version_info__)
