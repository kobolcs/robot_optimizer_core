# src/robot_optimizer_core/__version__.py
"""Version information for Robot Framework Optimizer Core.

This module provides version information following PEP 440.

Attributes:
    __version__ (str): The version string.
    __version_info__ (VersionInfo): Structured version information.
"""
from __future__ import annotations

from typing import NamedTuple


class VersionInfo(NamedTuple):
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
        if self.release != "final":
            version += f"{self.release}{self.serial}"
        return version


__version_info__ = VersionInfo(
    major=1,
    minor=0,
    patch=0,
    release="final",
    serial=0
)

__version__ = str(__version_info__)