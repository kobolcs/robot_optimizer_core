# src/robot_optimizer_core/deprecation.py
"""Deprecation utilities for maintaining API stability.

This module provides decorators and functions for marking deprecated
functionality and providing migration paths for users.

Example:
    Deprecating a function::

        from robot_optimizer_core import deprecated

        @deprecated(
            since="1.2.0",
            removed_in="2.0.0",
            replacement="analyze_file"
        )
        def old_analyze_function(path):
            # Old implementation
            return analyze_file(path)
"""
from __future__ import annotations

import functools
import inspect
import warnings
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")


class RobotOptimizerDeprecationWarning(UserWarning):
    """Warning category for Robot Framework Optimizer deprecations."""


def deprecated(
    since: str,
    removed_in: str | None = None,
    replacement: str | None = None,
    details: str | None = None
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to mark functions, methods, or classes as deprecated.

    This decorator will issue a deprecation warning when the decorated
    callable is used. It preserves the original function's metadata.

    Args:
        since: Version when the deprecation was introduced.
        removed_in: Version when the feature will be removed (optional).
        replacement: Name of replacement function/class (optional).
        details: Additional details about the deprecation (optional).

    Returns:
        Decorator function.

    Example:
        >>> @deprecated(
        ...     since="1.2.0",
        ...     removed_in="2.0.0",
        ...     replacement="new_function"
        ... )
        ... def old_function():
        ...     pass
    """
    def decorator(obj: Callable[P, R]) -> Callable[P, R]:
        """Actual decorator that wraps the object."""
        # Build deprecation message
        name = obj.__name__
        msg_parts = [f"'{name}' is deprecated since version {since}"]

        if removed_in:
            msg_parts.append(f"and will be removed in version {removed_in}")

        if replacement:
            msg_parts.append(f"Use '{replacement}' instead")

        if details:
            msg_parts.append(details)

        message = ". ".join(msg_parts) + "."

        if inspect.isclass(obj):
            # Handle class deprecation
            return _deprecate_class(obj, message)
        # Handle function/method deprecation
        @functools.wraps(obj)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            warnings.warn(
                message,
                category=RobotOptimizerDeprecationWarning,
                stacklevel=2
            )
            return obj(*args, **kwargs)

        # Add deprecation metadata
        wrapper.__deprecated__ = True
        wrapper.__deprecated_since__ = since
        wrapper.__deprecated_removed_in__ = removed_in
        wrapper.__deprecated_replacement__ = replacement

        return wrapper

    return decorator


def _deprecate_class(cls: type[T], message: str) -> type[T]:
    """Deprecate a class by wrapping its __init__ method.

    Args:
        cls: Class to deprecate.
        message: Deprecation message.

    Returns:
        Modified class.
    """
    original_init = cls.__init__

    @functools.wraps(original_init)
    def new_init(self: T, *args: Any, **kwargs: Any) -> None:
        warnings.warn(
            message,
            category=RobotOptimizerDeprecationWarning,
            stacklevel=2
        )
        original_init(self, *args, **kwargs)

    cls.__init__ = new_init
    cls.__deprecated__ = True

    return cls


def deprecation_warning(
    message: str,
    category: type[Warning] = RobotOptimizerDeprecationWarning,
    stacklevel: int = 2
) -> None:
    """Issue a deprecation warning.

    This is a convenience function for issuing deprecation warnings
    with consistent formatting.

    Args:
        message: Warning message.
        category: Warning category (default: RobotOptimizerDeprecationWarning).
        stacklevel: Stack level for warning (default: 2).

    Example:
        >>> deprecation_warning(
        ...     "Using 'old_param' is deprecated, use 'new_param' instead"
        ... )
    """
    warnings.warn(message, category=category, stacklevel=stacklevel)


def deprecated_parameter(
    param_name: str,
    since: str,
    removed_in: str | None = None,
    replacement: str | None = None
) -> None:
    """Warn about a deprecated parameter.

    This function should be called within a function/method to warn
    about deprecated parameters.

    Args:
        param_name: Name of the deprecated parameter.
        since: Version when deprecated.
        removed_in: Version when it will be removed.
        replacement: Replacement parameter name.

    Example:
        >>> def my_function(old_param=None, new_param=None):
        ...     if old_param is not None:
        ...         deprecated_parameter(
        ...             "old_param",
        ...             since="1.2.0",
        ...             replacement="new_param"
        ...         )
        ...         new_param = old_param
    """
    msg_parts = [f"Parameter '{param_name}' is deprecated since version {since}"]

    if removed_in:
        msg_parts.append(f"and will be removed in version {removed_in}")

    if replacement:
        msg_parts.append(f"Use '{replacement}' instead")

    message = ". ".join(msg_parts) + "."
    deprecation_warning(message, stacklevel=3)


def check_deprecated(obj: Any) -> bool:
    """Check if an object is marked as deprecated.

    Args:
        obj: Object to check.

    Returns:
        True if object is deprecated.

    Example:
        >>> if check_deprecated(some_function):
        ...     print("This function is deprecated")
    """
    return getattr(obj, "__deprecated__", False)


def get_deprecation_info(obj: Any) -> dict[str, Any] | None:
    """Get deprecation information for an object.

    Args:
        obj: Object to check.

    Returns:
        Dictionary with deprecation info or None if not deprecated.

    Example:
        >>> info = get_deprecation_info(old_function)
        >>> if info:
        ...     print(f"Deprecated since: {info['since']}")
    """
    if not check_deprecated(obj):
        return None

    return {
        "since": getattr(obj, "__deprecated_since__", None),
        "removed_in": getattr(obj, "__deprecated_removed_in__", None),
        "replacement": getattr(obj, "__deprecated_replacement__", None),
    }


class DeprecatedMixin:
    """Mixin class for deprecated functionality.

    Classes can inherit from this mixin to mark themselves as deprecated
    and provide consistent deprecation behavior.

    Example:
        >>> class OldAnalyzer(DeprecatedMixin, BaseAnalyzer):
        ...     _deprecated_since = "1.2.0"
        ...     _deprecated_replacement = "NewAnalyzer"
    """

    _deprecated_since: str = "1.0.0"
    _deprecated_removed_in: str | None = None
    _deprecated_replacement: str | None = None
    _deprecated_details: str | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize and issue deprecation warning."""
        super().__init__(*args, **kwargs)

        cls_name = self.__class__.__name__
        msg_parts = [f"'{cls_name}' is deprecated since version {self._deprecated_since}"]

        if self._deprecated_removed_in:
            msg_parts.append(f"and will be removed in version {self._deprecated_removed_in}")

        if self._deprecated_replacement:
            msg_parts.append(f"Use '{self._deprecated_replacement}' instead")

        if self._deprecated_details:
            msg_parts.append(self._deprecated_details)

        message = ". ".join(msg_parts) + "."
        deprecation_warning(message, stacklevel=3)


def renamed_parameter(**mappings: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to handle renamed parameters with deprecation warnings.

    This decorator allows old parameter names to still work while
    issuing deprecation warnings.

    Args:
        **mappings: Mapping of old names to new names.

    Returns:
        Decorator function.

    Example:
        >>> @renamed_parameter(old_name="new_name", another_old="another_new")
        ... def my_function(new_name=None, another_new=None):
        ...     pass
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # Check for old parameter names
            for old_name, new_name in mappings.items():
                if old_name in kwargs:
                    deprecated_parameter(
                        old_name,
                        since="1.0.0",  # Should be configured
                        replacement=new_name
                    )

                    # Move value to new name if not already set
                    if new_name not in kwargs:
                        kwargs[new_name] = kwargs.pop(old_name)
                    else:
                        # Both old and new provided, remove old
                        kwargs.pop(old_name)

            return func(*args, **kwargs)

        return wrapper

    return decorator
