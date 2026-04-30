# src/robot_optimizer_core/deprecation.py
"""Backward-compatibility shim — this module is now internal.

.. deprecated::
    Import from ``robot_optimizer_core._deprecation`` directly if needed.
    This public module will be removed in a future release.
"""
from __future__ import annotations

from ._deprecation import (  # noqa: F401  — re-exported for backward compat
    DeprecatedMixin,
    RobotOptimizerDeprecationWarning,
    check_deprecated,
    deprecated,
    deprecated_parameter,
    deprecation_warning,
    get_deprecation_info,
    renamed_parameter,
)

__all__ = [
    "DeprecatedMixin",
    "RobotOptimizerDeprecationWarning",
    "check_deprecated",
    "deprecated",
    "deprecated_parameter",
    "deprecation_warning",
    "get_deprecation_info",
    "renamed_parameter",
]
