# src/robot_optimizer_core/premium/__init__.py
"""Premium feature boundary for Robot Framework Optimizer Core.

This module establishes the clean freemium boundary between the free Core
package and the optional ``robot-framework-optimizer-pro`` package.

Free-edition behaviour
----------------------
- :data:`is_premium_installed` returns ``False``.
- :func:`requires_premium` decorator raises :class:`PremiumFeatureError`
  when a decorated callable is invoked.
- :func:`fire_telemetry_event` is a no-op unless *both* telemetry is
  explicitly opted-in via :attr:`~robot_optimizer_core.config.Settings.enable_telemetry`
  **and** a handler has been registered by the Pro package.  No network
  traffic is ever produced by the free edition.

Pro-edition extension
---------------------
The Pro package calls :func:`register_telemetry_handler` at import time to
attach its own analytics backend.  The Core package never imports from Pro
directly, keeping the dependency strictly one-directional.

Example::

    from robot_optimizer_core.premium import (
        PremiumFeatureError,
        is_premium_installed,
        requires_premium,
    )

    if not is_premium_installed():
        print("Running in free mode")

    @requires_premium("html_reports")
    def generate_html_report(findings):
        ...  # only reachable with Pro installed
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any, TypeVar

from ..exceptions import RobotOptimizerError

__all__ = [
    "PREMIUM_PACKAGE_NAME",
    "UPGRADE_URL",
    "PremiumFeatureError",
    "fire_telemetry_event",
    "is_premium_installed",
    "register_telemetry_handler",
    "requires_premium",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PREMIUM_PACKAGE_NAME = "robot-framework-optimizer-pro"
UPGRADE_URL = "https://github.com/kobolcs/robot_optimizer_core"

# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

F = TypeVar("F", bound=Callable[..., Any])


class PremiumFeatureError(RobotOptimizerError):
    """Raised when a premium-only feature is invoked without Pro installed.

    Attributes:
        feature_name: The name of the premium feature that was requested.
        upgrade_url: URL where the Pro package can be obtained.
    """

    __slots__ = ("feature_name", "upgrade_url")

    def __init__(self, feature_name: str) -> None:
        """Initialise the error with an actionable upgrade message.

        Args:
            feature_name: Identifier of the premium feature.
        """
        self.feature_name = feature_name
        self.upgrade_url = UPGRADE_URL
        message = (
            f"'{feature_name}' is a premium feature. "
            f"Install '{PREMIUM_PACKAGE_NAME}' to enable it.\n"
            f"  pip install {PREMIUM_PACKAGE_NAME}\n"
            f"  More info: {UPGRADE_URL}"
        )
        super().__init__(
            message,
            details={"feature": feature_name, "upgrade_url": UPGRADE_URL},
        )


# ---------------------------------------------------------------------------
# Premium detection
# ---------------------------------------------------------------------------


def is_premium_installed() -> bool:
    """Return ``True`` if the Pro package is importable in the current environment.

    Uses :func:`importlib.metadata.distribution` for a reliable,
    installation-time check that does not require importing the package.

    Returns:
        ``True`` when ``robot-framework-optimizer-pro`` is installed,
        ``False`` otherwise.
    """
    try:
        from importlib.metadata import PackageNotFoundError, distribution

        distribution(PREMIUM_PACKAGE_NAME)
        return True
    except Exception:  # PackageNotFoundError or anything unexpected
        return False


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def requires_premium(feature_name: str) -> Callable[[F], F]:
    """Decorator that guards a function behind a Pro installation check.

    When the decorated callable is invoked without Pro installed,
    :class:`PremiumFeatureError` is raised **before** the function body
    executes.

    Args:
        feature_name: Human-readable name of the premium feature, used in
            the error message and telemetry event.

    Returns:
        Decorator that wraps the target callable.

    Example::

        @requires_premium("html_reports")
        def generate_html_report(findings: list[Finding]) -> bytes:
            ...  # Pro-only implementation
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not is_premium_installed():
                fire_telemetry_event(
                    "premium_stub_triggered", feature=feature_name
                )
                raise PremiumFeatureError(feature_name)
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


# ---------------------------------------------------------------------------
# Telemetry hook (GDPR-compliant, no-op in free edition)
# ---------------------------------------------------------------------------

# The handler is ``None`` in the free edition.  The Pro package registers its
# own callable at import time via :func:`register_telemetry_handler`.
_telemetry_handler: Callable[[str, dict[str, object]], None] | None = None


def register_telemetry_handler(
    handler: Callable[[str, dict[str, object]], None],
) -> None:
    """Register a telemetry event handler (called by the Pro package only).

    The handler receives two positional arguments:

    - ``event_name`` (:class:`str`): identifier such as
      ``"premium_stub_triggered"`` or ``"analysis_complete"``.
    - ``properties`` (:class:`dict`): arbitrary key/value metadata.
      The free edition never includes PII; the Pro package must follow
      the same constraint.

    Args:
        handler: Callable that processes telemetry events.
    """
    global _telemetry_handler
    _telemetry_handler = handler


def fire_telemetry_event(event: str, **properties: object) -> None:
    """Fire a telemetry event when telemetry is opted-in.

    This function is a **guaranteed no-op** unless:

    1. The user explicitly sets
       :attr:`~robot_optimizer_core.config.Settings.enable_telemetry` to
       ``True`` (or ``ROBOT_OPTIMIZER_TELEMETRY=1`` env-var), **and**
    2. A handler has been registered via :func:`register_telemetry_handler`.

    No network calls are ever made by the free edition regardless of
    this setting.  The function silently swallows all exceptions so that
    telemetry failures never affect analysis results.

    Args:
        event: Event identifier string.
        **properties: Arbitrary key/value event metadata (no PII).
    """
    try:
        # Lazy import to avoid circular dependency at module import time.
        from ..config import get_settings

        if not get_settings().enable_telemetry:
            return
    except Exception:
        return

    if _telemetry_handler is None:
        return

    try:
        _telemetry_handler(event, dict(properties))
    except Exception:
        pass  # Telemetry must never propagate exceptions
