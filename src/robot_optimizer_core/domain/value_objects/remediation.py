# src/robot_optimizer_core/domain/value_objects/remediation.py
"""Structured remediation guidance attached to a Finding."""

from __future__ import annotations

import dataclasses
from typing import Literal

__all__ = ["RemediationHint"]


@dataclasses.dataclass(frozen=True, slots=True)
class RemediationHint:
    """Typed remediation guidance for a finding.

    Replaces the untyped ``Finding.context`` bag for guidance data.  Attach via
    ``Finding(remediation=RemediationHint(...), ...)``.

    Attributes:
        summary: One-line description of what to do.
        effort: Rough effort estimate for the fix.
        steps: Ordered, human-readable fix steps.
        docs_url: Link to authoritative documentation.
        auto_fixable: Whether the optimizer can apply the fix automatically.
        related_rule_ids: Other ``PatternType`` names that are commonly co-located.
    """

    summary: str
    effort: Literal["trivial", "low", "medium", "high"] = "low"
    steps: tuple[str, ...] = ()
    docs_url: str | None = None
    auto_fixable: bool = False
    related_rule_ids: tuple[str, ...] = ()
